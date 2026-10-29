"""Step text: turn each file's reading into clean, whole text.

The reading step gives *printed lines*: a sentence is cut wherever the page ran out of width, page numbers and
DocuSign stamps sit among the words, two columns of a form can come out glued into one line, and a table cell
("Per Year") stands alone, torn from its row. None of that is fit for splitting contracts into sections. This step
fixes it, page by page and then across pages:

  1. furniture   drop page numbers ("Page 5 of 7"), DocuSign stamps, lines with words that repeat in the top or
                 bottom margin of 3 or more pages of a file (running headers and footers), and logo noise.
                 Every drop is logged in removed.csv.
  2. tables      pricing tables are not read again: the rows checked by arithmetic in the table step (T1-T6) are
                 put in their place, one row per line ("Catalog Cloud Subscription | Per Year | ... | USD 12,000")
  3. columns     a printed line is split where the gap between two words is far wider than a space, so two
                 columns side by side become two pieces
  4. grids       a printed row with two or more pieces, at least one short, is a row of a form or a smaller table.
                 Its pieces stay together ("Customer: | University of Nebraska Medical Center | Billing Contact:"),
                 and a short piece wrapped onto the next line joins the cell it sits under. Exceptions: a clause
                 number and its text ("17.   Insurance. ..."), and a line that continues a running sentence.
  5. paragraphs  other lines join into paragraphs. A paragraph ends at a wider gap, a change of column, or a
                 numbered start ("12. Proprietary Rights.") that follows a finished sentence. A word split by a
                 hyphen at a line end is rejoined.
  6. page breaks a paragraph that ends a page in mid-sentence continues with the first paragraph of the next page

Outputs: outputs/text/<file>.md (readable), outputs/text/blocks.jsonl (every block with its pages and kind),
         outputs/text/removed.csv (everything dropped, and why), outputs/text/checks.csv (see check()),
         outputs/text/missing_candidates.csv (words another OCR engine read that the clean text lacks)
"""
import csv
import difflib
import json
import re
from collections import Counter, defaultdict

import pypdfium2 as pdfium

from .common import OUT, files, normalize, pdf_path, write_csv
from .reading import _covered, best_reading, is_scanned, is_word, load, page_source, real_word_share
from .tables import geometry_rows

FURNITURE = [(re.compile(r"^page\s*\d+\s*(of\s*\d+)?$", re.I), "page number"),
             (re.compile(r"^-?\s*\d{1,3}\s*-?$"), "page number"),
             (re.compile(r"^docu\s?sign envelope id", re.I), "DocuSign stamp")]
MARGIN = 0.09            # top and bottom 9% of the page: where running headers, footers and page numbers sit
NUMBERED = re.compile(r"^(\(?\d{1,2}(\.\d{1,2})*\.?\)?|\([a-z]{1,4}\)|[A-Z]\.)\s+\S")
NUMBER_ONLY = re.compile(r"^(\d{1,2}(\.\d{1,2})*\.?|\([a-z]{1,4}\)|\(?\d{1,2}\))$")
END = re.compile(r"[.;:?!)\"”]$")


# ---------------------------------------------------------------- pieces of printed lines

def pieces(lines: list[dict]) -> list[dict]:
    """Split each printed line at gaps much wider than a space (two columns side by side)."""
    out = []
    for line in lines:
        words = sorted(line.get("words") or [], key=lambda w: w["box"][0])
        if not words:
            out.append({"text": line["text"], "box": line["box"], "n": len(line["text"].split())})
            continue
        h = sorted(w["box"][3] - w["box"][1] for w in words)[len(words) // 2]
        group = [words[0]]
        for prev, w in zip(words, words[1:]):
            if w["box"][0] - prev["box"][2] > max(2.2 * h, 0.02):
                out.append(_piece(group))
                group = []
            group.append(w)
        out.append(_piece(group))
    return out


def _piece(words):
    return {"text": " ".join(w["text"] for w in words), "n": len(words),
            "box": [min(w["box"][0] for w in words), min(w["box"][1] for w in words),
                    max(w["box"][2] for w in words), max(w["box"][3] for w in words)]}


def is_noise(text: str) -> bool:
    """Logo or stamp read as letters: mostly single characters and symbols ("; N ST = U CT U = ="); a scrap with no
    letter or digit at all ("|", ":", "]"); a signature rule ("_______"). When unsure, text is kept: a lone "1" may be
    a quantity, "A." a section letter, "Qty" a column header (what_failed.md, 25). Dot leaders of a table of contents
    ("Overview ......") are text, not noise."""
    if "...." in text or re.search(r"[A-Za-z]{4,}|\d{3,}|[✔✓☑]", text):
        return False                                     # a real word, a number or a tick mark: keep
    if not re.search(r"[A-Za-z0-9§]", text) or re.fullmatch(r"[_\-–—=. ]{5,}", text):
        return True
    toks = text.split()
    return len(toks) >= 3 and sum(len(t) == 1 or not re.search(r"[A-Za-z0-9]", t) for t in toks) / len(toks) >= 0.6


def _repeat_key(text: str) -> str:
    return re.sub(r"\d+", "#", normalize(text).lower())


def _is_repeated(text: str, repeated: set[str]) -> bool:
    """Exactly, or nearly: one copy of a footer may be misread ("Uptiated 02/2018" for "Updated 02/2018")."""
    key = _repeat_key(text)
    return key in repeated or any(difflib.SequenceMatcher(None, key, r).ratio() >= 0.85 for r in repeated)


def furniture_patterns(file_id: str, n_pages: int) -> set[str]:
    """Texts with at least 3 letters, printed in the top or bottom margin of 3 or more pages of this file.
    (Letters required: clause numbers like "19.6" that happen to start near the top of pages are not headers.)"""
    seen = defaultdict(set)
    for p in range(1, n_pages + 1):
        for pc in pieces(best_reading(file_id, p)):
            if pc["box"][1] < MARGIN or pc["box"][3] > 1 - MARGIN:
                seen[_repeat_key(pc["text"])].add(p)
    return {t for t, ps in seen.items() if len(ps) >= 3 and len(re.findall(r"[a-z]", t)) >= 3}


# ---------------------------------------------------------------- one page

def page_blocks(file_id: str, page: int, repeated: set[str], zones: list[dict], removed: list[dict]) -> list[dict]:
    in_zone = lambda pc: any(z["y0"] - 0.005 <= (pc["box"][1] + pc["box"][3]) / 2 <= z["y1"] + 0.005 for z in zones)
    keep = []
    lines = best_reading(file_id, page)
    if page_source(file_id, page) != "textlayer+patch":
        # Tesseract reading a grey bar or a logo: Apple Vision saw no text there, and Tesseract was either very
        # unsure (under 30%: "5 eis =", "£5", which I confirmed are not on the page) or unsure (under 50%) and
        # the result is neither words nor numbers ("Rn NRE Jo AINSI"). A real sentence end Tesseract was unsure of
        # ("Customer's instructions.", 48%) and a lone "1" (47%) stay (what_failed.md, 26 and 30).
        vision = load("vision", file_id, page)
        unsure = [l for l in lines if l.get("conf") is not None and l["conf"] < 0.5
                  and not any(_covered(l, v) or _covered(v, l) for v in vision)
                  and (l["conf"] < 0.3 or real_word_share(l["text"]) < 0.5 and not re.search(r"\d", l["text"]))]
        for l in unsure:
            removed.append({"file_id": file_id, "page": page, "reason": "unsure OCR, not confirmed", "text": l["text"]})
        lines = [l for l in lines if l not in unsure]
    for pc in pieces(lines):
        t = normalize(pc["text"])
        why = next((name for pat, name in FURNITURE if pat.search(t)), None)
        in_margin = pc["box"][1] < MARGIN or pc["box"][3] > 1 - MARGIN
        if why == "page number" and not in_margin and not t.lower().startswith("page"):
            why = None                                  # a bare number mid-page is content (a quantity)
        if not why and in_margin and _is_repeated(t, repeated):
            why = "repeated header/footer"
        if not why and is_noise(t):
            why = "logo or noise"
        if why:
            removed.append({"file_id": file_id, "page": page, "reason": why, "text": t})
        elif t and not in_zone(pc):
            keep.append({**pc, "text": t})
    keep.sort(key=lambda p: (p["box"][1] + p["box"][3]) / 2)
    rows = []
    for pc in keep:
        yc, h = (pc["box"][1] + pc["box"][3]) / 2, pc["box"][3] - pc["box"][1]
        if rows and abs(yc - rows[-1]["yc"]) < 0.5 * max(h, rows[-1]["h"]):
            rows[-1]["pieces"].append(pc)
        else:
            rows.append({"yc": yc, "h": h, "pieces": [pc]})
    blocks, open_para, grid = [], {}, None
    for r in rows:
        ps = sorted(r["pieces"], key=lambda p: p["box"][0])
        # a clause number set apart from its text ("17.      Insurance. ...") is one line, not two cells
        if len(ps) == 2 and NUMBER_ONLY.match(ps[0]["text"]) and ps[1]["n"] >= 3:
            ps = [_merge(ps)]
        is_grid = len(ps) >= 2 and any(p["n"] < 6 for p in ps)
        # a line that carries on a running sentence is prose, even with odd gaps (an underlined link)
        para = open_para.get(0)
        if is_grid and para and not END.search(para["last"]["text"]) \
                and 0 <= ps[0]["box"][1] - para["last"]["box"][3] < 0.9 * r["h"] \
                and abs(ps[0]["box"][0] - para["last"]["box"][0]) < 0.03:
            ps, is_grid = [_merge(ps)], False
        if is_grid:
            if grid is None or r["yc"] - grid["bottom"] > 0.04:
                grid = {"kind": "grid", "pages": [page], "rows": [], "bottom": 0, "y": r["yc"]}
                blocks.append(grid)
            grid["rows"].append({"yc": r["yc"], "cells": [[p] for p in ps]})
            grid["bottom"] = r["yc"]
            open_para = {}
            continue
        for pc in ps:
            if grid is not None and pc["n"] < 6 and _wrap_into_grid(grid, pc, r["yc"]):
                continue                                  # a wrapped cell, now inside its row
            col = _column_key(pc)
            para = open_para.get(col)
            gap = pc["box"][1] - para["last"]["box"][3] if para else None
            starts_item = NUMBERED.match(pc["text"]) and (para is None or END.search(para["last"]["text"]))
            new = (para is None or gap > 0.9 * (pc["box"][3] - pc["box"][1]) or starts_item
                   or abs(pc["box"][0] - para["last"]["box"][0]) > 0.06 and not _continues(para["last"], pc))
            if new:
                para = {"kind": "paragraph", "pages": [page], "lines": [], "last": None, "y": pc["box"][1]}
                blocks.append(para)
                open_para[col] = para
            para["lines"].append(pc)
            para["last"] = pc
        if grid is not None and r["yc"] - grid["bottom"] > 0.04:
            grid = None
    for z in zones:                                       # the checked pricing tables, in their place
        blocks.append({"kind": "table", "pages": [page], "rows": z["rows"], "y": z["y0"], "y1": z["y1"]})
    blocks.sort(key=lambda b: b["y"])
    blocks = _fill_or_drop_labels(blocks, file_id, page, removed)
    blocks = _drop_empty_sections(blocks, file_id, page, removed)
    return [_finish(b) for b in blocks]


LABEL = re.compile(r"^[A-Z][\w./&#()' -]{0,45}[:?]$")


def is_label(text: str) -> bool:
    """A form label waiting for a value: "Billing Contact:", "P.O. Required?", "Zip/Postal Code:"."""
    return bool(LABEL.match(text)) and len(text.split()) <= 5


def _yc(piece) -> float:
    return (piece["box"][1] + piece["box"][3]) / 2


def _fill_or_drop_labels(blocks, file_id, page, removed):
    """An empty field in a side-by-side form row ("Customer: | ... | Billing Contact:" with nothing after the last
    label). Only labels inside such rows are considered, not in capitals ("ACCEPTED BY:" is a title), and only when
    nothing is printed directly below them ("Metrics and Descriptions:" and "Supplier Name:" have their content
    below). First the value is looked for a little above or below the label's line and to its right (a typed name
    often sits above the "Name:" line); only if there is none is the label dropped, and logged. A blacked-out
    value or an unreadable signature also leaves its label empty (decisions.md, C7)."""
    def candidates(label_piece, right_limit):
        out = []
        for b in blocks:
            if b["kind"] == "paragraph" and len(b["lines"]) == 1 and not is_label(b["lines"][0]["text"]) \
                    and b["lines"][0]["n"] < 6:
                out.append((b, None, None, b["lines"][0]))
            elif b["kind"] == "grid":
                for row in b["rows"]:
                    for cell in row["cells"]:
                        if len(cell) == 1 and not is_label(cell[0]["text"]):
                            out.append((b, row, cell, cell[0]))
        return [c for c in out if abs(_yc(c[3]) - _yc(label_piece)) < 0.02 and c[3] is not label_piece
                and c[3]["box"][0] > label_piece["box"][2] - 0.005 and c[3]["box"][2] < right_limit + 0.005]

    def take(c):
        b, row, cell, piece = c
        if row is None:
            blocks.remove(b)
        else:
            row["cells"].remove(cell)
        return piece

    for b in [b for b in blocks if b["kind"] == "grid"]:
        for row in b["rows"]:
            i = 0
            while i < len(row["cells"]):
                cell = row["cells"][i]
                label = cell[-1]
                nxt = row["cells"][i + 1] if i + 1 < len(row["cells"]) else None
                text = " ".join(p["text"] for p in cell)
                if is_label(text) and not text.isupper() and not _content_below(blocks, label) \
                        and (nxt is None or is_label(" ".join(p["text"] for p in nxt))):
                    found = candidates(label, nxt[0]["box"][0] if nxt else 2.0)
                    if found:
                        row["cells"].insert(i + 1, [take(min(found, key=lambda c: abs(_yc(c[3]) - _yc(label))))])
                        i += 2
                        continue
                    removed.append({"file_id": file_id, "page": page, "reason": "empty form field", "text": text})
                    row["cells"].pop(i)
                    continue
                i += 1
        b["rows"] = [r for r in b["rows"] if r["cells"]]
    return [b for b in blocks if b["kind"] != "grid" or b["rows"]]


def _content_below(blocks, label) -> bool:
    """Is something other than another label printed directly under this label (within about two lines)?"""
    x0, bottom = label["box"][0], label["box"][3]
    for b in blocks:
        pieces_ = b.get("lines") or [p for r in b.get("rows", []) if isinstance(r, dict) for c in r["cells"] for p in c]
        for p in pieces_:
            if p is not label and 0 <= p["box"][1] - bottom < 0.03 and abs(p["box"][0] - x0) < 0.05 \
                    and not is_label(p["text"]):
                return True
    return False


def _drop_empty_sections(blocks, file_id, page, removed):
    """A section title with nothing under it ("Notes" on F02 p3): a short, left-aligned title that is the last thing
    on its page, with at least a tenth of the page blank below. A title whose section goes on overleaf sits at the
    bottom of the page, and longer last lines are often content (a signer's title, a "Source:" link), so only this
    narrow case is dropped (decisions.md, C7)."""
    if not blocks:
        return blocks
    last = blocks[-1]
    if last["kind"] == "paragraph" and len(last["lines"]) == 1:
        piece = last["lines"][0]
        text = piece["text"]                         # a label ("Title:") is a field, not a section title
        # only a short title: one or two words, no digits or colon, left-aligned (a centred title alone on a page,
        # like "Exhibit A", is kept), at least a tenth of the page blank below it ("Notes" on F02 p3 has 14%)
        is_title = (len(text.split()) <= 2 and not re.search(r"[\d:/]", text) and text[:1].isupper()
                    and piece["box"][0] < 0.25)
        if is_title and piece["box"][3] < 1 - MARGIN - 0.1:
            removed.append({"file_id": file_id, "page": page, "reason": "empty section", "text": text})
            return blocks[:-1]
    return blocks


def _merge(ps):
    return _piece([{"text": p["text"], "box": p["box"]} for p in ps]) | {"n": sum(p["n"] for p in ps)}


def _column_key(pc) -> int:
    """Which column a piece is in, coarsely: left or right half of the page for narrow pieces."""
    narrow = pc["box"][2] - pc["box"][0] < 0.45
    return int(pc["box"][0] >= 0.48) if narrow else 0


def _continues(last, pc) -> bool:
    """A line indented differently can still continue a sentence (a hanging indent)."""
    return not END.search(last["text"]) and pc["text"][:1].islower()


def _wrap_into_grid(grid, pc, yc) -> bool:
    near = [r for r in grid["rows"] if abs(r["yc"] - yc) < 0.03]
    for row in sorted(near, key=lambda r: abs(r["yc"] - yc)):
        for cell in row["cells"]:
            x0, x1 = min(p["box"][0] for p in cell), max(p["box"][2] for p in cell)
            overlap = min(x1, pc["box"][2]) - max(x0, pc["box"][0])
            if overlap > 0.4 * (pc["box"][2] - pc["box"][0]):
                cell.append(pc)
                cell.sort(key=lambda p: p["box"][1])
                return True
    return False


def _join_lines(texts: list[str]) -> str:
    out = ""
    for t in texts:
        if out.endswith("-") and t[:1].islower():
            joined = re.findall(r"[A-Za-z]+-$", out)
            head = joined[0][:-1] if joined else ""
            first = re.match(r"[a-z]+", t).group()
            out = out[:-1] + t if head and is_word(head + first) else out + t     # "con-tract" -> "contract"
        else:
            out = f"{out} {t}" if out else t
    return out


def _finish(b) -> dict:
    if b["kind"] == "table":
        return {"kind": "table", "pages": b["pages"], "rows": b["rows"], "text": "\n".join(b["rows"])}
    if b["kind"] == "grid":
        rows = [" | ".join(_join_lines([p["text"] for p in cell]) for cell in r["cells"]) for r in b["rows"]]
        return {"kind": "grid", "pages": b["pages"], "rows": rows, "text": "\n".join(rows)}
    text = _join_lines([p["text"] for p in b["lines"]])
    kind = "heading" if len(b["lines"]) == 1 and len(text.split()) <= 10 and not END.search(text) else "paragraph"
    return {"kind": kind, "pages": b["pages"], "text": text, "n_lines": len(b["lines"])}


# ---------------------------------------------------------------- across pages, and the whole file

def file_blocks(file_id: str, n_pages: int, removed: list[dict]) -> list[dict]:
    repeated = furniture_patterns(file_id, n_pages)
    zones = []
    geometry_rows(file_id, n_pages, zones=zones)
    blocks = []
    for p in range(1, n_pages + 1):
        page = page_blocks(file_id, p, repeated, [z for z in zones if z["page"] == p], removed)
        # a paragraph that stops mid-sentence at the bottom of a page continues at the top of the next one
        first = next((b for b in page if b["kind"] in ("paragraph", "heading")), None)
        prev = blocks[-1] if blocks else None
        if prev and prev["kind"] == "paragraph" and first is not None and page and page[0] is first:
            mid_sentence = not END.search(prev["text"]) and (prev["n_lines"] >= 2 or len(prev["text"]) > 60)
            continues = first["text"][:1].islower() or (prev["text"][-40:].isupper() and first["text"][:20].isupper())
            if mid_sentence and continues:
                prev["text"] = _join_lines([prev["text"], first["text"]])
                prev["pages"] = prev["pages"] + [p]
                prev["n_lines"] += first.get("n_lines", 1)
                prev["joined_across_pages"] = True
                page.remove(first)
        blocks += page
    return blocks


def raw_lines(file_id: str, n_pages: int) -> list[str]:
    out = []
    for p in range(1, n_pages + 1):
        lines = best_reading(file_id, p)
        out += [normalize(l["text"]) for l in sorted(lines, key=lambda l: (round(l["box"][1] * 200), l["box"][0]))]
    return out


# ---------------------------------------------------------------- checks: count each problem before and after

def check(file_id: str, n_pages: int, blocks: list[dict], removed: list[dict]) -> dict:
    """Counts of the four problems, in the raw printed lines (before) and in the clean text (after).
      furniture        lines that are a page number ("Page x of y") or a DocuSign stamp
      broken sentences a unit that ends without closing punctuation and the next starts in lowercase
      lone fragments   a unit of one or two words outside a table or form
      missing text     words a third, independent engine (RapidOCR) read on a scanned page that the clean text
                       lacks (dictionary words of 5+ letters, not counting text removed on purpose). If our reading
                       has a line in the same place, the word was misread; if not, a whole line is missing."""
    raw = raw_lines(file_id, n_pages)
    is_furniture = lambda t: bool(FURNITURE[0][0].search(t) or FURNITURE[2][0].search(t))
    broken = lambda a, b: bool(a) and bool(b) and not END.search(a) and b[:1].islower()
    prose = [b for b in blocks if b["kind"] == "paragraph"]
    res = {
        "file_id": file_id,
        "furniture_before": sum(map(is_furniture, raw)),
        "furniture_after": sum(is_furniture(b["text"]) for b in blocks if b["kind"] in ("paragraph", "heading")),
        "broken_sentences_before": sum(broken(a, b) for a, b in zip(raw, raw[1:])),
        "broken_sentences_after": sum(broken(a["text"], b["text"]) for a, b in zip(prose, prose[1:])),
        "lone_fragments_before": sum(len(t.split()) <= 2 for t in raw),
        "lone_fragments_after": sum(len(b["text"].split()) <= 2 for b in blocks if b["kind"] in ("paragraph", "heading")),
        "joined_across_pages": sum(bool(b.get("joined_across_pages")) for b in blocks),
        "removed": sum(r["file_id"] == file_id for r in removed),
    }
    clean_words = Counter(w for b in blocks for w in re.findall(r"[a-z]{5,}", b["text"].lower()))
    missing, scanned = [], [p for p in range(1, n_pages + 1) if _scanned(file_id, p)]
    for p in scanned:
        dropped = {w for r in removed if r["file_id"] == file_id and r["page"] == p
                   for w in re.findall(r"[a-z]{5,}", r["text"].lower())} | {"envelope"}
        third_lines = load("rapidocr", file_id, p)
        third = Counter(w for l in third_lines for w in re.findall(r"[a-z]{5,}", l["text"].lower())
                        if is_word(w) and w not in dropped)
        ours = best_reading(file_id, p)
        for w, n in (third - clean_words).items():
            # is there a line of ours where the third engine read this word? then we misread it; if not, we lack it
            where = next(l for l in third_lines if w in l["text"].lower())
            kind = "misread word" if any(_covered(where, o) or _covered(o, where) for o in ours) else "missing line"
            missing += [(p, w, kind, where["text"])] * n
    res["scanned_pages"] = len(scanned)
    res["missing_lines"] = len({(p, t) for p, w, k, t in missing if k == "missing line"})
    res["misread_words"] = sum(k == "misread word" for p, w, k, t in missing)
    res["_missing"] = missing
    return res


_INV = None


def _scanned(file_id: str, page: int) -> bool:
    global _INV
    if _INV is None:
        with open(OUT / "reading" / "page_inventory.csv") as fh:
            _INV = {(r["file_id"], int(r["page"])): r for r in csv.DictReader(fh)}
    return is_scanned(_INV[(file_id, page)])


def to_markdown(f: dict, blocks: list[dict]) -> str:
    out = [f"# {f['file_id']}: {f['description']}", f"_{f['file']}_", ""]
    for b in blocks:
        note = ", joined across pages" if b.get("joined_across_pages") else ""
        tag = f"<!-- p{'-'.join(map(str, b['pages']))} {b['kind']}{note} -->"
        if b["kind"] in ("grid", "table"):
            out += [tag, *[f"    {r}" for r in b["rows"]], ""]
        elif b["kind"] == "heading":
            out += [tag, f"**{b['text']}**", ""]
        else:
            out += [tag, b["text"], ""]
    return "\n".join(out)


def main() -> None:
    removed, all_blocks, checks, missing_rows = [], [], [], []
    for f in files():
        n = len(pdfium.PdfDocument(str(pdf_path(f))))
        blocks = file_blocks(f["file_id"], n, removed)
        (OUT / "text").mkdir(parents=True, exist_ok=True)
        (OUT / "text" / f"{f['file_id']}.md").write_text(to_markdown(f, blocks))
        all_blocks += [{"file_id": f["file_id"], **b} for b in blocks]
        c = check(f["file_id"], n, blocks, removed)
        missing_rows += [{"file_id": f["file_id"], "page": p, "word": w, "kind": k, "third_engine_line": t}
                         for p, w, k, t in c.pop("_missing")]
        checks.append(c)
    with open(OUT / "text" / "blocks.jsonl", "w") as fh:
        for b in all_blocks:
            fh.write(json.dumps(b) + "\n")
    write_csv(OUT / "text" / "removed.csv", removed, ["file_id", "page", "reason", "text"])
    write_csv(OUT / "text" / "missing_candidates.csv", missing_rows,
              ["file_id", "page", "word", "kind", "third_engine_line"])
    total = {k: sum(c[k] for c in checks) for k in checks[0] if k != "file_id"}
    write_csv(OUT / "text" / "checks.csv", checks + [{"file_id": "ALL", **total}])
    print("  ", total)
