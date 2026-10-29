"""Step R: read every page.

For each page we keep several readings side by side, all in one format (a list of lines, each with its text,
its box on the page and, where the engine gives them, word boxes and a confidence):

  textlayer   the text stored inside the PDF (exact when it exists; scanned pages have none)
  vision      Apple Vision OCR on a 300 dpi image of the page
  tesseract   Tesseract 5 OCR (tessdata_best English model) on the same image
  rapidocr    RapidOCR on the same image (the engine the earlier pipeline used, but at 300 dpi)
  baseline    the earlier pipeline's output (Docling + RapidOCR at 216 dpi), copied into data/; text only, no boxes

Boxes are [x0, y0, x1, y1] as fractions of the page size, origin top-left, so every engine is comparable.

Outputs:
  work/pages/<file>/pNNN.png                 page images
  work/ocr/<engine>/<file>/pNNN.json         raw readings
  outputs/reading/page_inventory.csv         one row per page: text layer size and quality, image cover
"""
import gzip
import json
import re
import subprocess
import time
from pathlib import Path

import pdfplumber
import pypdfium2 as pdfium

from .common import (DATA, DPI, ON_MAC, OUT, ROOT, TESSDATA, THREADS, WORK, files, page_png, pdf_path, read_json,
                     write_csv, write_json)

ENGINES = ["vision", "tesseract", "rapidocr"]
VISION_BIN = ROOT / "tools" / "vision_ocr"
SCANNED_MAX_WORDS = 40   # a page is "scanned" when an image covers it and its text layer has fewer words than this
SCANNED_MIN_IMAGE_COVER = 0.9
_WORDS = None


def english_words() -> set[str]:
    """English word list (Webster's 2nd, the list macOS ships as /usr/share/dict/words), kept in data/ because
    Linux servers often lack it, and so every computer uses exactly the same list."""
    global _WORDS
    if _WORDS is None:
        with gzip.open(DATA / "english_words.txt.gz", "rt", encoding="utf-8") as fh:
            _WORDS = {w.strip().lower() for w in fh}
    return _WORDS


def is_word(token: str) -> bool:
    """In the word list as is, or after taking off a common ending (-s, -es, -ed, -ing, -ly; "using" -> "use")."""
    words = english_words()
    t = token.lower()
    if t in words:
        return True
    for suffix in ("s", "es", "ed", "ing", "ly"):
        stem = t[: -len(suffix)]
        if t.endswith(suffix) and ((len(stem) >= 3 and stem in words) or (len(stem) >= 2 and stem + "e" in words)):
            return True
    return False


def word_share(tokens: list[str]) -> float:
    """Share of alphabetic tokens (3+ letters) that are English words: a rough check that stored text is readable.
    Names and product words ("Hendrickson", "UNMC") are not in the list, so a clean order form scores about 0.8."""
    toks = [t for t in tokens if re.fullmatch(r"[A-Za-z]{3,}", t)]
    return sum(map(is_word, toks)) / len(toks) if toks else 0.0


# ---------------------------------------------------------------- page images and inventory

def render_pages() -> None:
    for f in files():
        doc = pdfium.PdfDocument(str(pdf_path(f)))
        for i in range(len(doc)):
            out = page_png(f["file_id"], i + 1)
            if not out.exists():
                out.parent.mkdir(parents=True, exist_ok=True)
                doc[i].render(scale=DPI / 72).to_pil().convert("RGB").save(out)


def textlayer_page(page) -> list[dict]:
    """The PDF's own text as lines: words whose vertical centres are close are one line."""
    W, H = float(page.width), float(page.height)
    words = page.extract_words(keep_blank_chars=False, use_text_flow=False)
    words.sort(key=lambda w: ((w["top"] + w["bottom"]) / 2, w["x0"]))
    lines, cur, cur_y = [], [], None
    for w in words:
        y = (w["top"] + w["bottom"]) / 2
        if cur and abs(y - cur_y) > 0.5 * (w["bottom"] - w["top"]):
            lines.append(cur)
            cur = []
        cur.append(w)
        cur_y = y if len(cur) == 1 else cur_y
    if cur:
        lines.append(cur)
    out = []
    for ln in lines:
        ln.sort(key=lambda w: w["x0"])
        wb = [{"text": w["text"], "box": [w["x0"] / W, w["top"] / H, w["x1"] / W, w["bottom"] / H]} for w in ln]
        out.append({"text": " ".join(w["text"] for w in ln), "conf": 1.0, "words": wb,
                    "box": [min(b["box"][0] for b in wb), min(b["box"][1] for b in wb),
                            max(b["box"][2] for b in wb), max(b["box"][3] for b in wb)]})
    return out


def inventory() -> list[dict]:
    rows = []
    for f in files():
        with pdfplumber.open(pdf_path(f)) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                lines = textlayer_page(page)
                write_json(WORK / "ocr" / "textlayer" / f["file_id"] / f"p{i:03d}.json", lines)
                tokens = [w["text"] for ln in lines for w in ln["words"]]
                area = float(page.width) * float(page.height)
                img_cover = sum(max(0.0, (min(im["x1"], page.width) - max(im["x0"], 0)))
                                * max(0.0, (min(im["bottom"], page.height) - max(im["top"], 0)))
                                for im in page.images) / area
                rows.append({"file_id": f["file_id"], "page": i, "textlayer_words": len(tokens),
                             "textlayer_word_share": round(word_share(tokens), 3),
                             "image_cover": round(min(img_cover, 1.0), 3)})
    write_csv(OUT / "reading" / "page_inventory.csv", rows)
    return rows


def is_scanned(row: dict) -> bool:
    """A picture of a page: one image covers it and the PDF holds (almost) no text. The few words some scans
    do hold are DocuSign stamps added on top. A sparse digital page (F09 p13, 36 words, no image) is not scanned."""
    return float(row["image_cover"]) >= SCANNED_MIN_IMAGE_COVER and int(row["textlayer_words"]) < SCANNED_MAX_WORDS


# ---------------------------------------------------------------- OCR engines

def ocr_vision(png: Path) -> list[dict]:
    """Apple Vision on one image. Results are saved next to the image (<name>.vision.json) and reused, so the
    server, which has no Apple Vision, can use what the Mac read (cell re-reads in bench/tables.py)."""
    cache = Path(png).with_suffix(".vision.json")
    if cache.exists():
        return read_json(cache)
    if not ON_MAC:
        print(f"    note: no Apple Vision here and no saved result for {png.name}; skipping it", flush=True)
        return []
    if not VISION_BIN.exists():
        subprocess.run(["swiftc", "-O", str(ROOT / "tools" / "vision_ocr.swift"), "-o", str(VISION_BIN)], check=True)
    out = json.loads(subprocess.run([str(VISION_BIN), str(png)], check=True, capture_output=True).stdout)
    if "cells" in Path(png).parts:
        write_json(cache, out)
    return out


_TESS = None


def ocr_tesseract(png: Path) -> list[dict]:
    global _TESS
    from tesserocr import PSM, RIL, PyTessBaseAPI, iterate_level
    if _TESS is None:
        _TESS = PyTessBaseAPI(path=str(TESSDATA), lang="eng", psm=PSM.AUTO)
    api = _TESS
    api.SetImageFile(str(png))
    W, H = api.GetThresholdedImage().size
    api.Recognize()
    lines, cur = [], None
    for it in iterate_level(api.GetIterator(), RIL.WORD):
        txt = it.GetUTF8Text(RIL.WORD)
        if not txt or not txt.strip():
            continue
        if cur is None or it.IsAtBeginningOf(RIL.TEXTLINE):
            cur = {"words": []}
            lines.append(cur)
        x0, y0, x1, y1 = it.BoundingBox(RIL.WORD)
        cur["words"].append({"text": txt.strip(), "box": [x0 / W, y0 / H, x1 / W, y1 / H],
                             "conf": it.Confidence(RIL.WORD) / 100})
    for ln in lines:
        wb = ln["words"]
        ln.update(text=" ".join(w["text"] for w in wb), conf=sum(w["conf"] for w in wb) / len(wb),
                  box=[min(w["box"][0] for w in wb), min(w["box"][1] for w in wb),
                       max(w["box"][2] for w in wb), max(w["box"][3] for w in wb)])
    return lines


_RAPID = None


def ocr_rapidocr(png: Path) -> list[dict]:
    global _RAPID
    from PIL import Image
    from rapidocr import RapidOCR
    if _RAPID is None:
        # RapidOCR shrinks images whose long side is over 2000 px by default; allow the full 300 dpi page.
        _RAPID = RapidOCR(params={"Global.max_side_len": 3600,
                                  "EngineConfig.onnxruntime.intra_op_num_threads": THREADS})
        import logging
        logging.getLogger("RapidOCR").setLevel(logging.WARNING)
    W, H = Image.open(png).size
    res = _RAPID(str(png))
    lines = []
    if res.boxes is None:
        return lines
    for quad, txt, score in zip(res.boxes, res.txts, res.scores):
        xs, ys = [float(p[0]) for p in quad], [float(p[1]) for p in quad]
        lines.append({"text": txt, "conf": float(score), "words": [],
                      "box": [min(xs) / W, min(ys) / H, max(xs) / W, max(ys) / H]})
    return lines


OCR = {"vision": ocr_vision, "tesseract": ocr_tesseract, "rapidocr": ocr_rapidocr}


def run_ocr(pages: list[tuple[str, int]], label: str, engines=ENGINES) -> None:
    for engine in engines:
        if engine == "vision" and not ON_MAC:
            done = sum((WORK / "ocr" / "vision" / f / f"p{p:03d}.json").exists() for f, p in pages)
            print(f"  vision, {label} pages: Apple Vision runs only on a Mac; using the {done} of {len(pages)} "
                  f"pages it read there", flush=True)
            continue
        t0, n = time.time(), 0
        todo = [(f, p) for f, p in pages if not (WORK / "ocr" / engine / f / f"p{p:03d}.json").exists()]
        if todo:
            print(f"  {engine}, {label} pages: {len(todo)} to read", flush=True)
        for file_id, page in todo:
            write_json(WORK / "ocr" / engine / file_id / f"p{page:03d}.json", OCR[engine](page_png(file_id, page)))
            n += 1
            if n % 10 == 0:
                print(f"    {n} of {len(todo)} done ({time.time() - t0:.0f}s)", flush=True)
        print(f"  {engine}, {label} pages: {n} read in {time.time() - t0:.0f}s", flush=True)


# ---------------------------------------------------------------- reading the results back

def _covered(line: dict, other: dict) -> bool:
    """Does `other` sit on top of `line`? (They share most of line's height and width.)"""
    a, b = line["box"], other["box"]
    h = min(a[3], b[3]) - max(a[1], b[1])
    w = min(a[2], b[2]) - max(a[0], b[0])
    return h > 0.5 * (a[3] - a[1]) and w > 0.3 * (a[2] - a[0])


LOW_CONF = 0.6   # Tesseract's own confidence (0-1) below which a line is probably not text it could read


def combine(primary: list[dict], filler: list[dict]) -> list[dict]:
    """Primary reading, with the filler's lines added where the primary has nothing (or only a line it was
    unsure of). Tesseract misses text on shaded or coloured backgrounds; Apple Vision misses whole paragraphs
    now and then. Each fills the other's gaps (decisions.md, R7)."""
    keep = [l for l in primary
            if l["conf"] >= LOW_CONF or not any(_covered(l, f) for f in filler)]
    for f in filler:
        if not any(_covered(f, l) or _covered(l, f) for l in keep):
            keep.append(f)
    return keep


def load(engine: str, file_id: str, page: int) -> list[dict]:
    """One engine's reading of one page, as a list of lines."""
    if engine == "tess+vision":
        return combine(load("tesseract", file_id, page), load("vision", file_id, page))
    if engine == "baseline":
        out = []
        for line in open(DATA / "baseline_docling_rapidocr" / f"{file_id}.jsonl"):
            b = json.loads(line)
            if b["page"] == page:
                out.append({"text": b["text"], "conf": None, "box": None, "words": []})
        return out
    path = WORK / "ocr" / engine / file_id / f"p{page:03d}.json"
    return read_json(path) if path.exists() else []


# Which reading later steps use. Digital pages: always the PDF's own text. Scanned pages: the reading that
# scored best on the test made for that kind of content (decisions.md, R7 and T5):
#   running text  -> tess+vision (hand-checked lines, outputs/reading/ocr_scores.csv)
#   pricing tables -> vision     (arithmetic checks, outputs/tables/pricing_scores.csv)
SCANNED_READING = "tess+vision"
TABLE_READING = "vision"
_INV = None


def page_source(file_id: str, page: int, scanned_engine: str = SCANNED_READING) -> str:
    global _INV
    if _INV is None:
        import csv
        with open(OUT / "reading" / "page_inventory.csv") as fh:
            _INV = {(r["file_id"], int(r["page"])): r for r in csv.DictReader(fh)}
    return scanned_engine if is_scanned(_INV[(file_id, page)]) else "textlayer"


def best_reading(file_id: str, page: int, scanned_engine: str = SCANNED_READING) -> list[dict]:
    return load(page_source(file_id, page, scanned_engine), file_id, page)


def page_text(lines: list[dict]) -> str:
    """Lines in reading order (top to bottom, then left to right), joined by single spaces."""
    if lines and lines[0].get("box"):
        lines = sorted(lines, key=lambda l: (round(l["box"][1] * 200), l["box"][0]))
    return " ".join(l["text"] for l in lines)


def main() -> None:
    print("rendering pages at", DPI, "dpi")
    render_pages()
    print("page inventory (text layer)")
    inv = inventory()
    # Scanned pages first: they are the ones that need OCR, and the hand-checked answer key comes from them.
    scanned = [(r["file_id"], r["page"]) for r in inv if is_scanned(r)]
    digital = [(r["file_id"], r["page"]) for r in inv if not is_scanned(r)]
    print(f"OCR: {len(scanned)} pages without a usable text layer, {len(digital)} with one")
    run_ocr(scanned, "scanned")
    run_ocr(digital, "digital")
