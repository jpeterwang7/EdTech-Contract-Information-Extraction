"""The two privacy methods that need the lab server. Run with server/run_privacy.sh.

  embed  turns every block into a meaning vector (sentence-transformers, all-mpnet-base-v2), on the CPU
  llm    asks Llama 3.1 8B, served by vLLM, where sections start and whether each section is in the category

Both save raw answers for ALL files in work/privacy/. Scoring and threshold tuning then happen on the Mac in seconds
with `python run.py privacy`, on the tuning files only, so test scores stay unseen and the server is not needed again.
"""
import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from .privacy import DEFINITION, PRIV, load_blocks, rule_sections

EMBED_MODEL = "sentence-transformers/all-mpnet-base-v2"
LLM_MODEL = os.environ.get("LLM_MODEL", "meta-llama/Llama-3.1-8B-Instruct")
BASE = os.environ.get("LLM_BASE_URL", "http://localhost:8000/v1").rstrip("/")
WINDOW, OVERLAP = 30, 5            # blocks shown to Llama at once, and how many repeat in the next window
PREVIEW_WORDS, SECTION_WORDS = 60, 1800


def embed() -> None:
    """A long block is cut into 150-word pieces (the model reads about that much at a time) and averaged."""
    import numpy as np
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(EMBED_MODEL, device="cpu")
    blocks = load_blocks()
    out = {"__definition__": model.encode(DEFINITION, normalize_embeddings=True)}
    for f, bs in blocks.items():
        vecs = []
        for b in bs:
            words = b["words"] or ["."]
            parts = [" ".join(words[i:i + 150]) for i in range(0, len(words), 150)]
            v = model.encode(parts, normalize_embeddings=True).mean(axis=0)
            vecs.append(v / (np.linalg.norm(v) or 1.0))
        out[f] = np.vstack(vecs)
        print(f"  {f}: {len(bs)} blocks", flush=True)
    PRIV.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(PRIV / "embeddings.npz", **out)


def _cache() -> dict:
    path = PRIV / "llm_cache.jsonl"
    if not path.exists():
        return {}
    with open(path) as fh:
        return {d["key"]: d["reply"] for d in map(json.loads, fh)}


def _post(system: str, user: str, max_tokens: int, json_mode: bool = True) -> str:
    body = {"model": LLM_MODEL, "temperature": 0, "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    req = urllib.request.Request(BASE + "/chat/completions", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            return json.load(r)["choices"][0]["message"]["content"] or ""
    except urllib.error.HTTPError as e:
        if e.code == 400 and json_mode:              # this server has no JSON mode; the prompt still asks for JSON
            return _post(system, user, max_tokens, json_mode=False)
        raise


def _ask_all(jobs: list[tuple[str, str]], max_tokens: int, label: str) -> list[dict | None]:
    cache = _cache()
    PRIV.mkdir(parents=True, exist_ok=True)

    def one(job):
        key = hashlib.sha1(f"{LLM_MODEL}\n{job[0]}\n{job[1]}".encode()).hexdigest()
        return key, cache[key] if key in cache else _post(job[0], job[1], max_tokens)

    replies = []
    with ThreadPoolExecutor(16) as pool, open(PRIV / "llm_cache.jsonl", "a") as fh:
        for n, (key, reply) in enumerate(pool.map(one, jobs), 1):
            if key not in cache:
                fh.write(json.dumps({"key": key, "reply": reply}) + "\n")
                fh.flush()
            replies.append(_parse(reply))
            if n % 50 == 0 or n == len(jobs):
                print(f"  {label}: {n} of {len(jobs)}", flush=True)
    return replies


def _parse(reply: str) -> dict | None:
    m = re.search(r"\{.*\}", reply or "", re.S)
    try:
        return json.loads(m.group()) if m else None
    except json.JSONDecodeError:
        return None


SPLIT_SYSTEM = ("You split contracts into sections. A section is a run of blocks about one subject, such as one numbered "
                "clause, one table or one form. Blocks that continue a clause stay in its section. You are shown numbered "
                'blocks. Reply with JSON only: {"starts": [the numbers of the blocks that start a new section]}')
YES_SYSTEM = ('You judge contract text. Category: ' + DEFINITION + ' Reply with JSON only: {"in_category": true} if the text '
              'has terms or statements in this category, otherwise {"in_category": false}.')


def _windows(n: int):
    step = WINDOW - OVERLAP
    return [(a, min(a + WINDOW, n)) for a in range(0, max(n - OVERLAP, 1), step)]


def _section_text(bs: list[dict], sec: list[int]) -> str:
    """A section's text, cut at SECTION_WORDS words so it fits the model's limit."""
    words = [w for k in sec for w in bs[k]["words"]]
    return " ".join(words[:SECTION_WORDS])


def llm() -> None:
    blocks = load_blocks()
    # 1. section starts, window by window
    jobs, where = [], []
    for f, bs in blocks.items():
        for a, b in _windows(len(bs)):
            lines = [f"[{k}] {' '.join(bs[k]['words'][:PREVIEW_WORDS])}" for k in range(a, b)]
            jobs.append((SPLIT_SYSTEM, "\n".join(lines)))
            where.append((f, a, b))
    replies = _ask_all(jobs, 600, "section starts")
    starts = {f: {0} for f in blocks}
    bad = 0
    for (f, a, b), r in zip(where, replies):
        if not r or not isinstance(r.get("starts"), list):
            bad += 1
            continue
        keep_from = a + OVERLAP // 2 if a else a                 # the overlap belongs half to each window
        starts[f] |= {int(x) for x in r["starts"] if isinstance(x, (int, float)) and keep_from <= int(x) < b}
    print(f"  section starts: {bad} of {len(jobs)} replies unusable", flush=True)
    llm_secs = {}
    for f, bs in blocks.items():
        cuts = sorted(s for s in starts[f] if s < len(bs))
        llm_secs[f] = [list(range(a, b)) for a, b in zip(cuts, cuts[1:] + [len(bs)])]
    # 2. yes or no, for Llama's sections and for the rules' sections
    results = {}
    for tag, secs in (("llm_yes", llm_secs), ("rules_yes", {f: rule_sections(bs) for f, bs in blocks.items()})):
        js, idx = [], []
        for f, ss in secs.items():
            for s in ss:
                js.append((YES_SYSTEM, _section_text(blocks[f], s)))
                idx.append(f)
        replies = _ask_all(js, 30, tag)
        unusable = sum(r is None for r in replies)
        print(f"  {tag}: {unusable} of {len(js)} replies unusable (counted as no)", flush=True)
        out = {f: [] for f in blocks}
        for f, r in zip(idx, replies):
            out[f].append(bool(r and r.get("in_category") is True))
        results[tag] = out
    (PRIV / "llm_answers.json").write_text(json.dumps({"llm_sections": llm_secs, **results}))
