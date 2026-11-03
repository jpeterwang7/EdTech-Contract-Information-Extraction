"""Step privacy: find every data-governance-and-privacy passage and return it whole.

Every method does two jobs on the clean text (outputs/text/blocks.jsonl): split a file into sections, then decide
which sections belong to the category. A section is a run of whole blocks, so the signed text is never rewritten.

Methods
  rules    split at numbered clauses, headings, run-in titles, tables and forms; keep sections with privacy terms
  meaning  split where neighbouring blocks change subject; keep sections close in meaning to the category definition
           (needs work/privacy/embeddings.npz, made on the server by bench/privacy_server.py)
  llm      Llama marks where sections start and answers yes or no for each section
  rules+llm  the rules' sections, with Llama answering yes or no

Answer key: data/gold/privacy_passages.csv. Core passages must be found. Borderline passages are for a person to check:
returning them neither helps nor hurts a method. The F09 security brochure is not contract terms, so it is left out of
every score and every review count.

Scores (counted in words), for a set of files:
  found  share of core text returned. The most important: what is missed never reaches extraction.
  clean  share of the returned text that really is core (borderline text is left out of this count)
  whole  share of core passages returned complete, inside one section
  F2     one summary of found and clean that weighs found twice as much; used only to tune thresholds

Tuning uses TUNE files only. TEST scores are printed only with `python run.py privacy-test`, once everything is frozen.
"""
import csv
import json
import re
from collections import defaultdict
from pathlib import Path

from .common import DATA, OUT, WORK, normalize, write_csv
from .ocr_eval import align

TUNE = ["F01", "F02", "F03", "F04", "F05", "F06", "F09", "F11", "F12"]
TEST = ["F07", "F08", "F10", "F13", "F14"]
PRIV = WORK / "privacy"

DEFINITION = ("Data governance and privacy: who owns customer, student or user data; how the vendor may use, analyze or "
              "share it, including aggregated or de-identified data and training AI models; disclosure to third "
              "parties; how long data is kept and how it is exported, returned or deleted; security safeguards and "
              "data breach notification; and duties under privacy laws such as FERPA and GDPR.")


# ---------------------------------------------------------------- text and answer key

def load_blocks() -> dict[str, list[dict]]:
    out = defaultdict(list)
    with open(OUT / "text" / "blocks.jsonl") as fh:
        for line in fh:
            b = json.loads(line)
            b["words"] = normalize(b["text"]).split()
            out[b["file_id"]].append(b)
    return out


def _span(block: dict, start: str, end: str) -> tuple[int, int]:
    """Word range of an excerpt inside a block; the whole block if no phrases are given."""
    text = " ".join(block["words"])
    s = text[:align(normalize(start), text)[1]].count(" ") if start else 0
    if end:
        stop = align(normalize(end), text)[2]
        return s, min(text[:stop].count(" ") + 1, len(block["words"]))
    return s, len(block["words"])


def load_gold(blocks: dict) -> list[dict]:
    """Passages as lists of (block, first word, last word + 1)."""
    gold = []
    with open(DATA / "gold" / "privacy_passages.csv") as fh:
        for g in csv.DictReader(fh):
            bs = blocks[g["file_id"]]
            a, b = int(g["block_start"]), int(g["block_end"])
            if " ".join(bs[a]["text"].split()[:7]) != g["anchor"]:
                raise SystemExit(f"{g['passage_id']}: block {a} of {g['file_id']} no longer starts with {g['anchor']!r}; "
                                 "the clean text changed, so the answer key must be re-anchored")
            spans = []
            for k in range(a, b + 1):
                s, e = 0, len(bs[k]["words"])
                if k == a and g["start_phrase"]:
                    s = _span(bs[k], g["start_phrase"], "")[0]
                if k == b and g["end_phrase"]:
                    e = _span(bs[k], "", g["end_phrase"])[1]
                spans.append((k, s, e))
            gold.append({**g, "spans": spans})
    return gold


# ---------------------------------------------------------------- scoring

BROCHURE = ("F09", 43)      # F09's security brochure starts at this block; it is left out of all scoring


def contract_blocks(blocks: dict, f: str) -> range:
    """The blocks of a file that are scored: everything except the non-binding brochure."""
    return range(BROCHURE[1]) if f == BROCHURE[0] else range(len(blocks[f]))


def score(blocks: dict, gold: list[dict], chosen: dict[str, list[list[int]]], file_ids: list[str]) -> dict:
    """chosen: file -> the sections a method kept, each a list of block numbers."""
    core, neutral, passages = defaultdict(set), defaultdict(set), []
    for g in gold:
        if g["file_id"] not in file_ids or g["binding"] == "no":
            continue
        words = {(k, w) for k, s, e in g["spans"] for w in range(s, e)}
        if g["strength"] == "core":
            core[g["file_id"]] |= words
            passages.append((g["file_id"], words))
        else:
            neutral[g["file_id"]] |= words
    got_core = returned = 0
    for f in file_ids:
        scored = set(contract_blocks(blocks, f))
        sel = {(k, w) for sec in chosen.get(f, []) for k in sec if k in scored for w in range(len(blocks[f][k]["words"]))}
        got_core += len(sel & core[f])
        returned += len(sel - neutral[f])
    total = sum(len(v) for v in core.values())
    whole = sum(any({k for k, _ in words} <= set(sec) for sec in chosen.get(f, [])) for f, words in passages)
    found = got_core / total if total else 0.0
    clean = got_core / returned if returned else 0.0
    f2 = 5 * found * clean / (4 * clean + found) if found + clean else 0.0
    return {"found": round(found, 3), "clean": round(clean, 3), "whole": round(whole / len(passages), 3) if passages else 0,
            "F2": round(f2, 3), "passages": len(passages), "sections_kept": sum(len(chosen.get(f, [])) for f in file_ids),
            "words_returned": returned}


# ---------------------------------------------------------------- method 1: rules

TOP_NUMBER = re.compile(r"^(\d{1,2}\.\s*[A-Z]|[A-Z]\.\s+[A-Z])")
TITLE = re.compile(r"^(?:[A-Z][\w/&'’-]*\s+){0,4}[A-Z][\w/&'’-]*[.:]\s+[A-Z(\"“]")
TERMS = re.compile(r"customer data|user data|usage data|aggregated data|personal information|personal data"
                   r"|personally identifiable|\bpii\b|privacy|ferpa|gdpr|coppa|data breach|data exposure|data security"
                   r"|data classification|data processing|student information(?! system)|education records?|de-identif"
                   r"|anonymi|encrypt", re.I)
# "Customer Content" alone is not enough: an indemnity clause mentions it too. It counts next to a word about owning,
# using, securing, exporting or removing it.
CONTENT = re.compile(r"(?:own|propert|use|secur|export|access|display|delet|remov|maintain|confidential)\w*\W+(?:\w+\W+){0,6}"
                     r"customer content|customer content\W+(?:\w+\W+){0,6}(?:remain|propert|secur|export)", re.I)
SKIP_SECTION = re.compile(r"envelope (?:sent|summary)|signer events", re.I)     # DocuSign's log ("Hashed/Encrypted")


def rule_sections(bs: list[dict]) -> list[list[int]]:
    """A new section at a heading, table or form, a numbered clause ("12. Term", not "12.1"), or a run-in title
    ("Duration: ...", "Confidentiality. ...")."""
    secs: list[list[int]] = []
    for i, b in enumerate(bs):
        starts = (b["kind"] in ("heading", "grid", "table") or not secs or bs[i - 1]["kind"] in ("grid", "table")
                  or TOP_NUMBER.match(b["text"]) or TITLE.match(b["text"]))
        if starts:
            secs.append([i])
        else:
            secs[-1].append(i)
    return secs


def rule_keep(bs: list[dict], sec: list[int]) -> bool:
    text = " ".join(bs[k]["text"] for k in sec)
    return bool((TERMS.search(text) or CONTENT.search(text)) and not SKIP_SECTION.search(text))


def run_rules(blocks: dict) -> dict:
    return {f: [s for s in rule_sections(bs) if rule_keep(bs, s)] for f, bs in blocks.items()}


# ---------------------------------------------------------------- reporting

def report(rows: list[dict], path: Path) -> None:
    write_csv(path, rows)
    for r in rows:
        print("  " + "  ".join(f"{k}={v}" for k, v in r.items()))


def _load_npz() -> dict | None:
    import numpy as np
    path = PRIV / "embeddings.npz"
    return dict(np.load(path)) if path.exists() else None


def meaning_sections(vecs, cut: float) -> list[list[int]]:
    """Start a new section where a block's meaning is far from the block before it."""
    secs = [[0]]
    for i in range(1, len(vecs)):
        if float(vecs[i] @ vecs[i - 1]) < cut:
            secs.append([i])
        else:
            secs[-1].append(i)
    return secs


def run_meaning(blocks: dict, emb: dict, cut: float, keep: float) -> dict:
    """Keep a section when the average of its blocks, weighted by length, is close to the category definition."""
    import numpy as np
    out = {}
    for f, bs in blocks.items():
        vecs = emb[f]
        kept = []
        for sec in meaning_sections(vecs, cut):
            weights = np.array([max(len(bs[k]["words"]), 1) for k in sec], dtype=float)
            v = (vecs[sec] * weights[:, None]).sum(axis=0)
            v = v / (np.linalg.norm(v) or 1.0)
            if float(v @ emb["__definition__"]) >= keep:
                kept.append(sec)
        out[f] = kept
    return out


def tune_meaning(blocks: dict, gold: list[dict], emb: dict) -> tuple[float, float]:
    """Try combinations of the two thresholds on the tuning files only; keep the best F2. (Tuned with the brochure as a
    target, it kept only brochure sections and found no contract clause: what_failed.md, 36.)"""
    best = (-1.0, 0.0, 0.0)
    for cut in [x / 20 for x in range(0, 17)]:
        for keep in [x / 20 for x in range(2, 15)]:
            f2 = score(blocks, gold, run_meaning(blocks, emb, cut, keep), TUNE)["F2"]
            if f2 > best[0]:
                best = (f2, cut, keep)
    return best[1], best[2]


def methods_available(blocks: dict, gold: list[dict]) -> dict:
    out = {"rules": run_rules(blocks)}
    emb = _load_npz()
    if emb:
        cut, keep = tune_meaning(blocks, gold, emb)
        (OUT / "privacy").mkdir(parents=True, exist_ok=True)
        (OUT / "privacy" / "meaning_thresholds.json").write_text(json.dumps({"cut": cut, "keep": keep}))
        print(f"  meaning: thresholds from the tuning files: cut={cut}, keep={keep}")
        out["meaning"] = run_meaning(blocks, emb, cut, keep)
    answers = PRIV / "llm_answers.json"
    if answers.exists():
        a = json.loads(answers.read_text())
        out["llm"] = {f: [s for s, yes in zip(a["llm_sections"][f], a["llm_yes"][f]) if yes] for f in blocks}
        out["rules+llm"] = {f: [s for s, yes in zip(rule_sections(blocks[f]), a["rules_yes"][f]) if yes] for f in blocks}
    return out


# ---------------------------------------------------------------- the three-way sorter

WIDE_NET = re.compile(r"\b(data|records?|confidential\w*|secur\w*|passwords?|privacy|personal\w*|consents?|delet\w*|destr\w*"
                      r"|retain\w*|retention|export\w*|student\w*|anonymi\w*|customer content|credentials?|disclos\w*)\b", re.I)


def section_signals(blocks: dict, emb: dict, answers: dict) -> dict:
    """For each of the rules' sections in the contracts: the three methods' opinions, and the wide word net.
    The rules' sections are the unit because they returned the most passages whole."""
    import numpy as np
    out = {}
    for f, bs in blocks.items():
        scored = set(contract_blocks(blocks, f))
        rows = []
        for sec, yes in zip(rule_sections(bs), answers["rules_yes"][f]):
            if not set(sec) <= scored:
                continue
            weights = np.array([max(len(bs[k]["words"]), 1) for k in sec], dtype=float)
            v = (emb[f][sec] * weights[:, None]).sum(axis=0)
            v = v / (np.linalg.norm(v) or 1.0)
            rows.append({"sec": sec, "rules": rule_keep(bs, sec), "llm": yes, "meaning": float(v @ emb["__definition__"]),
                         "net": bool(WIDE_NET.search(" ".join(bs[k]["text"] for k in sec))),
                         "words": sum(len(bs[k]["words"]) for k in sec)})
        out[f] = rows
    return out


def sort_sections(rows: list[dict], t: float, auto_votes: int, use_net: bool) -> dict:
    """Votes = rules + Llama + meaning (similarity at or above t). Enough votes: automatically in. No vote, and not
    caught by the wide net if it is used: automatically out. Everything else goes to a person."""
    out = {"in": [], "check": [], "out": []}
    for r in rows:
        votes = r["rules"] + r["llm"] + (r["meaning"] >= t)
        if votes >= auto_votes:
            out["in"].append(r)
        elif votes == 0 and not (use_net and r["net"]):
            out["out"].append(r)
        else:
            out["check"].append(r)
    return out


def _weigh(blocks, gold, signals, sorted_, files) -> dict:
    """Core text is found if it lands in "in" or "check" (the person is assumed to answer like the key)."""
    core, bord, total = defaultdict(set), defaultdict(set), 0
    for g in gold:
        if g["file_id"] in files and g["binding"] == "yes":
            for k, s, e in g["spans"]:
                (core if g["strength"] == "core" else bord)[g["file_id"]] |= {(k, w) for w in range(s, e)}
    res = {"core_words": 0, "core_found_auto": 0, "core_found_after_check": 0, "wrong_auto_in": 0, "checked_words": 0,
           "checked_sections": 0, "auto_in_words": 0, "auto_out_words": 0, "borderline_words": 0, "borderline_checked": 0,
           "borderline_auto_in": 0, "total_words": 0}
    for f in files:
        res["core_words"] += len(core[f])
        res["borderline_words"] += len(bord[f])
        for lane, rows in sorted_[f].items():
            for r in rows:
                res["total_words"] += r["words"]
                ws = {(k, w) for k in r["sec"] for w in range(len(blocks[f][k]["words"]))}
                if lane == "in":
                    res["auto_in_words"] += r["words"]
                    res["core_found_auto"] += len(ws & core[f])
                    res["core_found_after_check"] += len(ws & core[f])
                    res["wrong_auto_in"] += len(ws - core[f] - bord[f])
                    res["borderline_auto_in"] += len(ws & bord[f])
                elif lane == "check":
                    res["checked_words"] += r["words"]
                    res["checked_sections"] += 1
                    res["core_found_after_check"] += len(ws & core[f])
                    res["borderline_checked"] += len(ws & bord[f])
                else:
                    res["auto_out_words"] += r["words"]
    return res


CORE_TARGET, BORDERLINE_TARGET = 1.0, 0.95


def sweep(blocks, gold, signals) -> list[tuple[dict, dict]]:
    return [({"t": t, "auto_votes": v, "use_net": n}, _weigh(blocks, gold, signals,
             {f: sort_sections(signals[f], t, v, n) for f in TUNE}, TUNE))
            for t in [x / 20 for x in range(4, 15)] for v in (2, 3) for n in (True, False)]


def tune_sorter(results: list[tuple[dict, dict]]) -> dict:
    """Limits first: all core text found, and nearly all borderline text in front of a person. Among the settings
    that meet them, the lowest total of words a person reads and wrong words let in automatically (decisions.md, P7)."""
    ok = [(w["checked_words"] + w["wrong_auto_in"], i) for i, (_, w) in enumerate(results)
          if w["core_found_after_check"] >= CORE_TARGET * w["core_words"]
          and w["borderline_checked"] >= BORDERLINE_TARGET * w["borderline_words"]]
    return results[min(ok)[1]][0]


def run_sorter(blocks: dict, gold: list[dict], files: list[str], rows: list[dict]) -> None:
    emb, path = _load_npz(), PRIV / "llm_answers.json"
    if not (emb and path.exists()):
        return
    signals = section_signals(blocks, emb, json.loads(path.read_text()))
    choice_path = OUT / "privacy" / "sorter_settings.json"
    if files == TUNE:
        results = sweep(blocks, gold, signals)
        write_csv(OUT / "privacy" / "sorter_all_settings_tune.csv", [_row(s_, w) for s_, w in results])
        settings = tune_sorter(results)
        choice_path.write_text(json.dumps(settings))
    else:
        settings = json.loads(choice_path.read_text())
    sorted_ = {f: sort_sections(signals[f], settings["t"], settings["auto_votes"], settings["use_net"]) for f in files}
    print("  sorter: " + "  ".join(f"{k}={v}" for k, v in _row(settings, _weigh(blocks, gold, signals, sorted_, files)).items()))
    rows_out = [{"file_id": f, "lane": lane, "first_block": r["sec"][0], "last_block": r["sec"][-1], "words": r["words"],
                 "rules": r["rules"], "llm": r["llm"], "meaning": round(r["meaning"], 3), "net": r["net"],
                 "text": " ".join(blocks[f][r["sec"][0]]["words"][:30])}
                for f in files for lane, rs in sorted_[f].items() for r in rs]
    write_csv(OUT / "privacy" / f"sorted_sections_{'tune' if files == TUNE else 'test'}.csv", rows_out)


def _row(settings: dict, w: dict) -> dict:
    pct = lambda a, b: round(100 * a / b, 1) if b else 0.0
    return {**settings, "found_pct_after_check": pct(w["core_found_after_check"], w["core_words"]),
            "found_pct_automatic": pct(w["core_found_auto"], w["core_words"]),
            "check_sections": w["checked_sections"], "check_pct_of_words": pct(w["checked_words"], w["total_words"]),
            "auto_in_clean_pct": pct(w["auto_in_words"] - w["wrong_auto_in"], w["auto_in_words"]),
            "auto_out_pct_of_words": pct(w["auto_out_words"], w["total_words"]),
            "borderline_checked_pct": pct(w["borderline_checked"], w["borderline_words"])}


def main(split: str = "TUNE") -> None:
    blocks = load_blocks()
    gold = load_gold(blocks)
    files = TUNE if split == "TUNE" else TEST
    rows = [{"method": name, "split": split, **score(blocks, gold, chosen, files)}
            for name, chosen in methods_available(blocks, gold).items()]
    report(rows, OUT / "privacy" / f"scores_{split.lower()}.csv")
    run_sorter(blocks, gold, files, rows)


def main_test() -> None:
    main("TEST")
