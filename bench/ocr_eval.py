"""Steps ocr-sample and ocr-eval: how well does each reading method read the contracts?

Two answer keys:

1. Hand-checked lines from scanned pages (data/gold/ocr_lines.csv). The real test, because scanned pages are
   where reading goes wrong. `ocr-sample` picks two lines per scanned page at random and saves a picture of each
   line (data/gold/ocr_crops/). A person types what the picture says into `gold_text`. The lines are picked
   half from Apple Vision's line boxes and half from Tesseract's, so neither engine decides alone which text
   gets tested.

2. Digital pages, where the PDF stores the exact text. We turn those pages into pictures, run OCR on the
   pictures, and compare with the stored text. No hand work, many lines, but easier than real scans (no blur,
   no tilt), so it shows the best an engine can do.

Three scores per engine (all explained in docs/decisions.md, R5):
  character error rate (CER)  edits needed to turn the engine's text into the true text, divided by the length
                              of the true text. 0 = perfect, 0.10 = one character in ten wrong.
  words found                 share of the true line's words that appear anywhere in the engine's page text,
                              ignoring order (so a table read column by column is not punished here)
  numbers exact               share of the true line's numbers (prices, dates, quantities) that the engine
                              read exactly right, in the matching place
"""
import random
import re
from collections import Counter, defaultdict

import numpy as np
from PIL import Image, ImageDraw

from .common import DATA, OUT, WORK, normalize, page_png, read_json, write_csv
from .reading import ENGINES, is_scanned, load, page_text

GOLD = DATA / "gold" / "ocr_lines.csv"
CROPS = DATA / "gold" / "ocr_crops"
SEED = 20261028
SKIP = re.compile(r"docusign envelope id", re.I)   # stamped on every page by DocuSign, not contract text
# Text stored in a PDF that a reader never sees, so it cannot be the answer for what a page shows:
# "(cid:182)" = a character the PDF stores without saying which letter it is; "\s1\" = DocuSign's invisible
# signature-placement tags; "......" = table-of-contents dot leaders (decisions.md, R5).
UNSEEN = re.compile(r"\(cid:\d+\)|\\[a-z]\d+\\|\.{6,}")
NUM = re.compile(r"\d[\d,.:/-]*\d|\d")
GOLD_FIELDS = ["line_id", "file_id", "page", "x0", "y0", "x1", "y1", "picked_from", "kind", "gold_text",
               "human_checked", "notes"]


def inventory() -> list[dict]:
    import csv
    with open(OUT / "reading" / "page_inventory.csv") as fh:
        return list(csv.DictReader(fh))


# ---------------------------------------------------------------- alignment

def _sellers(g: np.ndarray, t: np.ndarray, free_start: bool) -> np.ndarray:
    """Edit-distance table, last row only. With free_start the match may begin anywhere in t."""
    n = len(t)
    idx = np.arange(n + 1, dtype=np.int32)
    prev = np.zeros(n + 1, dtype=np.int32) if free_start else idx.copy()
    for i in range(1, len(g) + 1):
        tmp = np.empty(n + 1, dtype=np.int32)
        tmp[0] = i
        tmp[1:] = np.minimum(prev[:-1] + (t != g[i - 1]), prev[1:] + 1)
        prev = np.minimum.accumulate(tmp - idx) + idx      # insertions along the row
    return prev


def align(gold: str, text: str) -> tuple[int, int, int]:
    """Find the stretch of `text` that best matches `gold`. Returns (edits, start, end).
    This lets us score a single line against a whole page without knowing where on the page the engine put it."""
    if not gold:
        return 0, 0, 0
    if not text:
        return len(gold), 0, 0
    as_arr = lambda s: np.frombuffer(s.encode("utf-32-le"), dtype=np.uint32)
    last = _sellers(as_arr(gold), as_arr(text), free_start=True)
    end = int(np.argmin(last))
    rev = _sellers(as_arr(gold[::-1]), as_arr(text[:end][::-1]), free_start=False)
    k = int(np.argmin(rev))
    return int(last[end]), end - k, end


def score_line(gold: str, page: str) -> dict:
    gold, page = normalize(gold), normalize(page)
    edits, s, e = align(gold, page)
    window = page[s:e]
    gw = Counter(re.findall(r"[a-z0-9]+", gold.lower()))
    pw = Counter(re.findall(r"[a-z0-9]+", page.lower()))
    nums = NUM.findall(gold)
    return {"chars": len(gold), "edits": edits, "cer": edits / max(len(gold), 1),
            "words": sum(gw.values()), "words_found": sum((gw & pw).values()),
            "numbers": len(nums), "numbers_exact": sum(n in window for n in nums), "engine_text": window}


# ---------------------------------------------------------------- answer key 1: sample lines from scanned pages

def _overlap(a, b) -> bool:
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


def sample() -> None:
    import csv
    if GOLD.exists():
        raise SystemExit(f"{GOLD} exists; it may hold hand-typed answers. Move it away to sample again.")
    rng = random.Random(SEED)
    rows = []
    for r in inventory():
        if not is_scanned(r):
            continue
        fid, page = r["file_id"], int(r["page"])
        picked = []
        for engine in ("vision", "tesseract"):
            cands = [l for l in load(engine, fid, page)
                     if len(l["text"].strip()) >= 8 and not SKIP.search(l["text"])
                     and not any(_overlap(l["box"], p) for p in picked)]
            if cands:
                c = rng.choice(cands)
                picked.append(c["box"])
                rows.append({"file_id": fid, "page": page, "picked_from": engine, "box": c["box"]})
    CROPS.mkdir(parents=True, exist_ok=True)
    out = []
    for i, row in enumerate(rows, start=1):
        lid = f"L{i:03d}"
        x0, y0, x1, y1 = row["box"]
        x0, y0, x1, y1 = max(0, x0 - .012), max(0, y0 - .004), min(1, x1 + .012), min(1, y1 + .004)
        img = Image.open(page_png(row["file_id"], row["page"]))
        W, H = img.size
        img.crop((int(x0 * W), int(y0 * H), int(x1 * W), int(y1 * H))).save(CROPS / f"{lid}.png")
        out.append({"line_id": lid, "file_id": row["file_id"], "page": row["page"], "x0": round(x0, 4),
                    "y0": round(y0, 4), "x1": round(x1, 4), "y1": round(y1, 4), "picked_from": row["picked_from"],
                    "kind": "", "gold_text": "", "human_checked": "", "notes": ""})
    write_csv(GOLD, out, GOLD_FIELDS)
    make_sheets(out)
    print(f"  {len(out)} lines sampled from scanned pages -> {GOLD}")


def make_sheets(rows: list[dict], per_sheet: int = 10) -> None:
    """Stack line pictures into sheets with their IDs, to type the answer key from (work/gold_sheets/)."""
    d = WORK / "gold_sheets"
    d.mkdir(parents=True, exist_ok=True)
    for s in range(0, len(rows), per_sheet):
        crops = [(r["line_id"], Image.open(CROPS / f"{r['line_id']}.png")) for r in rows[s:s + per_sheet]]
        width = min(max(c.width for _, c in crops) + 160, 2600)
        height = sum(min(c.height, 400) + 24 for _, c in crops)
        sheet = Image.new("RGB", (width, height), "white")
        draw, y = ImageDraw.Draw(sheet), 0
        for lid, c in crops:
            draw.text((6, y + 6), lid, fill="red")
            c.thumbnail((width - 160, 400))
            sheet.paste(c, (150, y))
            draw.line([(0, y + c.height + 12), (width, y + c.height + 12)], fill="#bbbbbb")
            y += c.height + 24
        sheet.save(d / f"sheet_{s // per_sheet + 1:02d}.png")


# ---------------------------------------------------------------- scoring

def _summarise(details: list[dict], keys: list[str]) -> list[dict]:
    groups = defaultdict(list)
    for d in details:
        groups[tuple(d[k] for k in keys)].append(d)
    out = []
    for g, ds in sorted(groups.items()):
        chars, edits = sum(d["chars"] for d in ds), sum(d["edits"] for d in ds)
        words, nums = sum(d["words"] for d in ds), sum(d["numbers"] for d in ds)
        out.append({**dict(zip(keys, g)), "lines": len(ds), "chars": chars,
                    "cer": round(edits / max(chars, 1), 4),
                    "lines_perfect": round(sum(d["edits"] == 0 for d in ds) / len(ds), 3),
                    "words_found": round(sum(d["words_found"] for d in ds) / max(words, 1), 4),
                    "numbers": nums,
                    "numbers_exact": round(sum(d["numbers_exact"] for d in ds) / nums, 4) if nums else ""})
    return out


def evaluate() -> None:
    import csv
    engines = ["baseline"] + ENGINES + ["tess+vision", "tess+vision+vote"]
    # 1. hand-checked lines on scanned pages
    with open(GOLD) as fh:
        gold = [g for g in csv.DictReader(fh) if g["gold_text"].strip()]
    details = []
    for g in gold:
        for engine in engines:
            s = score_line(g["gold_text"], page_text(load(engine, g["file_id"], int(g["page"]))))
            details.append({"answer_key": "scanned_hand", "engine": engine, "line_id": g["line_id"],
                            "file_id": g["file_id"], "page": g["page"], "kind": g["kind"] or "?",
                            "gold_text": g["gold_text"], **s})
    # 2. digital pages: the PDF's own text is the answer
    rng = random.Random(SEED)
    for r in inventory():
        # pages with 100+ stored words that are mostly real words (a garbled text layer would score far lower;
        # the lowest page here, an order form full of names, scores 0.77; decisions.md, R5)
        if is_scanned(r) or int(r["textlayer_words"]) < 100 or float(r["textlayer_word_share"]) < .70:
            continue
        fid, page = r["file_id"], int(r["page"])
        lines = [l for l in load("textlayer", fid, page)
                 if len(l["text"]) >= 15 and not SKIP.search(l["text"]) and not UNSEEN.search(l["text"])]
        for l in rng.sample(lines, min(8, len(lines))):
            for engine in ENGINES + ["tess+vision", "tess+vision+vote"]:
                ocr = load(engine, fid, page)
                if not ocr:
                    continue
                s = score_line(l["text"], page_text(ocr))
                details.append({"answer_key": "digital_textlayer", "engine": engine, "line_id": "",
                                "file_id": fid, "page": page, "kind": "digital", "gold_text": l["text"], **s})
    write_csv(OUT / "reading" / "ocr_line_scores.csv", details)
    summary = _summarise(details, ["answer_key", "engine"]) + _summarise(
        [d for d in details if d["answer_key"] == "scanned_hand"], ["answer_key", "kind", "engine"])
    write_csv(OUT / "reading" / "ocr_scores.csv", summary,
              ["answer_key", "kind", "engine", "lines", "chars", "cer", "lines_perfect", "words_found",
               "numbers", "numbers_exact"])
    for s in summary:
        print("  " + "  ".join(f"{k}={v}" for k, v in s.items() if k not in ("chars",)))
