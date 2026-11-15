"""Step tables: read the pricing tables two ways and check them with arithmetic.

Every Instructure order form prices its products in tables with the same kind of columns
(Description, Start Date, End Date, Metric, Qty, Price, Amount), followed by Sub-Total, Year Total and
Grand Total rows. That gives a free accuracy test that needs no hand labels:
  row check       Qty x Price = Amount on every product row
  subtotal check  the product rows above a Sub-Total / Year Total add up to it
  grand check     all product rows of an order form add up to its Grand Total
A wrong digit, a lost row or a value put in the wrong column breaks at least one of these.

Two methods:
  docling    the table structure the earlier pipeline got from Docling's table model (TableFormer)
  geometry   ours: find the header row by its column names, then put every word under the header it sits
             below, using the word positions from the chosen reading (PDF text, or Apple Vision on scans)

Outputs: outputs/tables/pricing_rows_<method>.csv, outputs/tables/pricing_checks_<method>.csv,
         outputs/tables/pricing_scores.csv
"""
import json
import re
import statistics
from collections import defaultdict

from .common import DATA, OUT, files, write_csv
from pathlib import Path

from .common import TESSDATA, WORK, page_png
from .reading import TABLE_READING, best_reading, ocr_vision, page_source

MONEY = re.compile(r"(?:USD|\$)\s*([\d,]+(?:\.\d+)?)")
NUMBER = re.compile(r"^\d[\d,]*(?:\.\d+)?$")
OTHER_TABLE = re.compile(r"^(deliverable|product|metric|segment|purchase order information|billing summary)\b", re.I)


def column_name(label: str) -> str | None:
    """Map a header label to a column. 'Ext. Price' (the 2016-2017 forms) is the line amount, not the unit price."""
    low = label.lower()
    for pattern, name in [(r"\bext", "amount"), (r"\bstart", "start"), (r"\bend\b", "end"),
                          (r"\b(qty|aty|quantity)\b", "qty"), (r"\bpr[il]ce", "price"), (r"\bamount", "amount"),
                          (r"\bdescription", "description"), (r"\bmetric", "metric"), (r"\bcategory", "category"),
                          (r"\bref\b", "ref"), (r"\binvoice", "invoice")]:
        if re.search(pattern, low):
            return name
    return None


def money(text: str) -> float | None:
    """'USD 12,000.00' or '$53,166'. Failing that, a number with cents anywhere in the cell, because OCR
    sometimes misreads the currency ('USE 12,000.00', 'USO 23.00') or a wrapped cell comes out '20,000.00 USD'."""
    m = MONEY.search(text)
    if m:
        return float(m.group(1).replace(",", ""))
    m = re.search(r"\d[\d,]*\.\d{2}\b", text)
    return float(m.group().replace(",", "")) if m else None


def qty(text: str) -> float | None:
    t = text.strip().replace(" ", "")
    return float(t.replace(",", "")) if NUMBER.match(t) else None


def row_kind(text: str) -> str:
    low = text.lower()
    if "grand total" in low:
        return "grand"
    if re.search(r"sub[\s-]*total", low):
        return "subtotal"
    if re.search(r"\btotal\b", low):
        return "total"
    return "item"


# ---------------------------------------------------------------- method 1: Docling's tables

def docling_rows(file_id: str) -> list[dict]:
    rows = []
    blocks = [json.loads(l) for l in open(DATA / "baseline_docling_rapidocr" / f"{file_id}.jsonl")]
    for bi, b in enumerate(blocks):
        if b["label"] != "table":
            # a Grand Total printed outside the table: "Grand Total:" then the amount, maybe in the next block
            if "grand total" in b["text"].lower():
                txt = b["text"] + " " + " ".join(x["text"] for x in blocks[bi + 1:bi + 3])
                if money(txt) is not None:
                    rows.append({"file_id": file_id, "page": b["page"], "kind": "grand", "amount": money(txt),
                                 "raw": txt[:120]})
            continue
        cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in b["text"].splitlines()
                 if r.strip().startswith("|") and not set(r.strip()) <= set("|-: ")]
        cols = None
        for r in cells:
            names = [column_name(c) for c in r]
            if "qty" in names and ("amount" in names or "price" in names) and "description" in names:
                cols = names
                continue
            if cols is None:
                continue
            text = " ".join(dict.fromkeys(r))          # merged cells repeat their text; keep it once
            kind = row_kind(text)
            get = lambda name: next((r[i] for i, n in enumerate(cols) if n == name and i < len(r)), "")
            amt = money(get("amount")) if kind == "item" else money(text)
            if kind == "item" and amt is None and qty(get("qty")) is None:
                continue
            rows.append({"file_id": file_id, "page": b["page"], "kind": kind, "description": get("description"),
                         "qty": qty(get("qty")), "price": money(get("price")), "amount": amt, "raw": text[:160]})
    return rows


# ---------------------------------------------------------------- method 2: header-anchored geometry

def _page_rows(words: list[dict]) -> list[list[dict]]:
    """Group words into visual rows by their vertical centre."""
    words = sorted(words, key=lambda w: (w["box"][1] + w["box"][3]) / 2)
    rows, cur = [], []
    for w in words:
        yc, h = (w["box"][1] + w["box"][3]) / 2, w["box"][3] - w["box"][1]
        if cur and abs(yc - cur[-1]["_yc"]) > 0.5 * max(h, cur[-1]["_h"]):
            rows.append(cur)
            cur = []
        cur.append({**w, "_yc": yc, "_h": h})
    if cur:
        rows.append(cur)
    return [sorted(r, key=lambda w: w["box"][0]) for r in rows]


def _header(row: list[dict]) -> list[tuple[str, float]] | None:
    """If this visual row is a pricing-table header, return its columns as (name, centre x), left to right.
    Words close together form one label ("Start" "Date", "Ext." "Price"); a wide gap starts the next label."""
    labels = []
    for w in row:
        gap = w["box"][0] - labels[-1][-1]["box"][2] if labels else 1
        if gap < 1.2 * (w["box"][3] - w["box"][1]):
            labels[-1].append(w)
        else:
            labels.append([w])
    cols = []
    for lab in labels:
        name = column_name(" ".join(w["text"] for w in lab))
        if name:
            cols.append((name, (lab[0]["box"][0] + lab[-1]["box"][2]) / 2))
    names = [c[0] for c in cols]
    if "description" in names and "qty" in names and ("amount" in names or "price" in names):
        return cols
    return None


def _cells(lines: list[list[dict]], cols: list[tuple[str, float]]) -> dict[str, str]:
    """Put every word under the header whose centre is closest, then read each cell top to bottom."""
    centres = [c[1] for c in cols]
    cell = defaultdict(list)
    for line in lines:
        for w in line:
            xc = (w["box"][0] + w["box"][2]) / 2
            cell[cols[min(range(len(cols)), key=lambda i: abs(centres[i] - xc))][0]].append(w["text"])
    return {k: " ".join(v) for k, v in cell.items()}


def _table_rows(body: list[list[dict]], cols: list[tuple[str, float]], amount: str = "amount",
                is_amount=lambda cell: bool(re.search(r"\d", cell))) -> list[list[list[dict]]]:
    """Group a table's lines (top to bottom) into rows, whichever way its cells wrap (decisions.md, T2).
    Every row has exactly one amount, so between two lines holding an amount there is exactly one boundary between
    rows. Rows are set apart by extra space (cell padding), so the boundary is the widest gap between those two lines:
    a line above it belongs to the upper row, a line below it to the lower row. Lines above the first amount line or
    below the last one join the nearest row only if their gap is the size of a gap inside a row, judged against this
    table's own gaps, so a page number under the table stays out. No fixed spacing is assumed, as OCR engines
    measure text height differently. Joining each line to the nearest amount line instead put "(Minimums / Apply)"
    in two rows (what_failed.md, 42)."""
    yc = lambda line: sum(w["_yc"] for w in line) / len(line)
    anchors = [k for k, line in enumerate(body) if is_amount(_cells([line], cols).get(amount, ""))]
    if not anchors:
        return []
    gap = [yc(body[k + 1]) - yc(body[k]) for k in range(len(body) - 1)]      # gap[k] lies between lines k and k + 1
    cuts, inside = [], []
    for a, b in zip(anchors, anchors[1:]):
        widest = max(range(a, b), key=lambda k: gap[k])
        cuts.append(widest)
        inside += [gap[k] for k in range(a, b) if k != widest]
    bounds = [gap[k] for k in cuts]
    if inside and bounds:
        edge = (max(inside) + min(bounds)) / 2          # halfway between a gap inside a row and one between rows
    elif bounds:
        edge = 0.75 * min(bounds)                       # no wrapped cells to compare with: clearly less than a row
    else:
        edge = 2.5 * statistics.median(w["box"][3] - w["box"][1] for line in body for w in line)   # a lone row
    first, last = anchors[0], anchors[-1]
    while first > 0 and gap[first - 1] <= edge:
        first -= 1
    while last < len(body) - 1 and gap[last] <= edge:
        last += 1
    starts = [first] + [k + 1 for k in cuts]
    ends = [k + 1 for k in cuts] + [last + 1]
    return [body[s:e] for s, e in zip(starts, ends)]


_TESS_DIGIT = None


def reread_cell(file_id: str, page: int, cols: list[tuple[str, float]], name: str, lines: list[list[dict]],
                parse) -> tuple[str, str]:
    """Cut one cell out of the page picture and read it again on its own. Returns (text, how).
    OCR on a whole page tends to skip a lone character such as the "1" in a Qty cell (F06 p1). Read on its own
    the cell often comes out right, but not always, so three tries in a fixed order, keeping the first that
    gives a number: Apple Vision on the enlarged cell; the same with a white margin around it; Tesseract
    reading a single character, digits only. (This order was chosen on the 6 cells that needed it; decisions.md, T4.)
    The cell spans halfway to the neighbouring headers, trimmed so the table's ruling lines stay out, and from
    the top to the bottom of the row's lines. It is then cut down to the ink inside it: in a row made tall by a
    wrapped cell elsewhere, a lone "1" was too small a part of the cut-out to be read (what_failed.md, 42)."""
    global _TESS_DIGIT
    import numpy as np
    from PIL import Image, ImageOps
    centres = [c[1] for c in cols]
    i = [c[0] for c in cols].index(name)
    left = (centres[i - 1] + centres[i]) / 2 if i > 0 else centres[i] - 0.05
    right = (centres[i] + centres[i + 1]) / 2 if i + 1 < len(cols) else centres[i] + 0.05
    trim = 0.12 * (right - left)
    top = min(w["box"][1] for line in lines for w in line) - 0.006
    bottom = max(w["box"][3] for line in lines for w in line) + 0.006
    img = Image.open(page_png(file_id, page))
    W, H = img.size
    crop = img.crop((int((left + trim) * W), int(top * H), int((right - trim) * W), int(bottom * H))).convert("L")
    ink = np.asarray(crop) < 128
    ink[ink.mean(axis=1) > 0.5] = False                 # a ruling line caught at the top or bottom edge
    ys, xs = np.nonzero(ink)
    if len(ys):
        pad = 12
        crop = crop.crop((max(0, xs.min() - pad), max(0, ys.min() - pad),
                          min(crop.width, xs.max() + pad + 1), min(crop.height, ys.max() + pad + 1)))
    crop = crop.resize((crop.width * 2, crop.height * 2), Image.LANCZOS)
    base = WORK / "cells" / f"{file_id}_p{page}_{name}_{int(top * 1000)}_{int(bottom * 1000)}_ink"
    base.parent.mkdir(parents=True, exist_ok=True)
    padded = ImageOps.expand(crop, border=(crop.width, crop.height), fill=255)
    crop.save(f"{base}.png")
    padded.save(f"{base}_pad.png")
    for how, path in (("vision", f"{base}.png"), ("vision+margin", f"{base}_pad.png")):
        text = " ".join(l["text"] for l in sorted(ocr_vision(Path(path)), key=lambda l: l["box"][1]))
        if parse(text) is not None:
            return text, how
    if name == "qty":
        try:
            from tesserocr import PSM, PyTessBaseAPI
        except ImportError:
            return "", "none (tesserocr not installed)"
        if not (TESSDATA / "eng.traineddata").exists():
            return "", "none (no Tesseract English model in .tessdata/)"
        if _TESS_DIGIT is None:
            _TESS_DIGIT = PyTessBaseAPI(path=str(TESSDATA), lang="eng", psm=PSM.SINGLE_CHAR)
            _TESS_DIGIT.SetVariable("tessedit_char_whitelist", "0123456789")
        _TESS_DIGIT.SetImage(crop)
        text = _TESS_DIGIT.GetUTF8Text().strip()
        if parse(text) is not None:
            return text, "tesseract-digit"
    return "", "none"


def first_number(text: str) -> float | None:
    m = re.search(r"\d[\d,]*(?:\.\d+)?", text)
    return float(m.group().replace(",", "")) if m else None


def geometry_rows(file_id: str, n_pages: int, reread: bool = True, engine: str = TABLE_READING,
                  zones: list | None = None) -> list[dict]:
    """A table row can span several visual lines (a wrapped "USD / 12,000.00", a tall "20% of / Subscription /
    (Minimums Apply)" cell); _table_rows groups them.
    If `zones` is a list, each table's place on the page and its rows as text are added to it (bench/text.py
    uses them in place of reading the table a second time)."""
    out = []
    for page in range(1, n_pages + 1):
        words = [w for line in best_reading(file_id, page, engine) for w in line.get("words", [])]
        rows = _page_rows(words)
        i = 0
        while i < len(rows):
            cols = _header(rows[i])
            if not cols:
                i += 1
                continue
            body, j = [], i + 1                 # the table: lines after the header until it ends
            while j < len(rows):
                text = " ".join(w["text"] for w in rows[j])
                if _header(rows[j]) or OTHER_TABLE.match(text) or len(rows[j]) > 25:
                    break                       # another table, or a paragraph of running text
                body.append(rows[j])
                j += 1
                if row_kind(text) in ("total", "grand"):
                    break
            row_lines = _table_rows(body, cols)
            names = list(dict.fromkeys(c[0] for c in cols))
            zone = {"file_id": file_id, "page": page, "y0": min(w["box"][1] for w in rows[i]),
                    "y1": max([w["box"][3] for line in body for w in line] or [rows[i][0]["box"][3]]),
                    "rows": [" | ".join(n.capitalize() for n in names)]}
            for lines in row_lines:
                cells = _cells(lines, cols)
                text = " ".join(w["text"] for line in lines for w in line)
                kind = row_kind(text)
                row = {"file_id": file_id, "page": page, "kind": kind, "amount": money(cells.get("amount", "")),
                       "raw": text[:160]}
                if kind == "item":
                    row.update(description=cells.get("description", ""), qty=qty(cells.get("qty", "")),
                               price=money(cells.get("price", "")), reread="")
                    if reread and not page_source(file_id, page, engine).startswith("textlayer"):
                        for name, parse in (("qty", first_number), ("price", money)):
                            if row[name] is None and name in [c[0] for c in cols]:
                                again, how = reread_cell(file_id, page, cols, name, lines, parse)
                                row[name] = parse(again)
                                row["reread"] += f"{name} by {how}: {again!r}; "
                                if row[name] is not None:
                                    cells[name] = again
                zone["rows"].append(" | ".join(cells.get(n, "") for n in names) if kind == "item"
                                    else " ".join(dict.fromkeys(text.split(" "))))
                out.append(row)
            # a Grand Total sits under the table, outside its columns
            if j < len(rows) and row_kind(" ".join(w["text"] for w in rows[j])) == "grand" and not (
                    body and row_kind(" ".join(w["text"] for w in body[-1])) == "grand"):
                text = " ".join(w["text"] for w in rows[j])
                out.append({"file_id": file_id, "page": page, "kind": "grand", "amount": money(text), "raw": text[:160]})
                zone["rows"].append(text)
                zone["y1"] = max(w["box"][3] for w in rows[j])
            if zones is not None and row_lines:
                zones.append(zone)
            i = j
        # Grand Totals printed away from any table (another line further down the page)
        for row in rows:
            text = " ".join(w["text"] for w in row)
            if row_kind(text) == "grand" and not any(o["page"] == page and o["kind"] == "grand" for o in out
                                                      if o["file_id"] == file_id):
                out.append({"file_id": file_id, "page": page, "kind": "grand", "amount": money(text), "raw": text[:160]})
    return out


# ---------------------------------------------------------------- Billing Summary tables

def billing_summaries(file_id: str, n_pages: int, engine: str = TABLE_READING, zones: list | None = None) -> list[dict]:
    """The Billing Summary on the newer order forms (Segment | Recurring | Non-Recurring | Total) has no Qty or Price
    column, so it is found by its own header. Two checks: Recurring + Non-Recurring = Total on each row, and the
    Year rows add up to the Total row. (decisions.md, T7)"""
    checks = []
    for page in range(1, n_pages + 1):
        words = [w for line in best_reading(file_id, page, engine) for w in line.get("words", [])]
        rows = _page_rows(words)
        for i, row in enumerate(rows):
            names = [re.sub(r"[^a-z-]", "", w["text"].lower()) for w in row]
            if not {"segment", "recurring", "non-recurring", "total"} <= set(names):
                continue
            cols = [(n, (w["box"][0] + w["box"][2]) / 2) for n, w in zip(names, row)]
            order = [c[0] for c in cols]
            body, years, y1 = [], [], max(w["box"][3] for w in row)
            table = []                          # the lines below the header until another table or a paragraph
            for line in rows[i + 1:i + 12]:
                if _header(line) or OTHER_TABLE.match(" ".join(w["text"] for w in line)) or len(line) > 25:
                    break
                table.append(line)
            for lines in _table_rows(table, cols, "total", lambda cell: money(cell) is not None):
                cells = _cells(lines, cols)
                y1 = max(w["box"][3] for w in lines[-1])
                body.append(" | ".join(cells.get(n, "") for n in order))
                rec, non, tot = (money(cells.get(n, "")) for n in ("recurring", "non-recurring", "total"))
                is_total = cells.get("segment", "").lower().startswith("total")
                if None not in (rec, non):
                    checks.append({"check": "billing row", "ok": close(rec + non, tot), "file_id": file_id, "page": page,
                                   "detail": f"{rec:,.2f} + {non:,.2f} vs {tot:,.2f}", "raw": body[-1]})
                if is_total:
                    checks.append({"check": "billing total", "ok": close(sum(years), tot), "file_id": file_id,
                                   "page": page, "detail": f"years {sum(years):,.2f} vs printed {tot:,.2f}", "raw": body[-1]})
                    break
                years.append(tot)
            if zones is not None and body:
                zones.append({"file_id": file_id, "page": page, "y0": min(w["box"][1] for w in row), "y1": y1,
                              "rows": [" | ".join(n.capitalize() for n in order)] + body})
    return checks


# ---------------------------------------------------------------- the arithmetic checks

def close(a: float, b: float) -> bool:
    return abs(a - b) <= max(0.011, 0.0005 * abs(b))     # cents, or rounding on large sums


def check(rows: list[dict]) -> list[dict]:
    """Run the three checks over one file's rows (in reading order). Returns one result per check."""
    res = []
    since_sub, since_total, since_grand = [], [], []
    for r in rows:
        if r["kind"] == "item":
            if r["qty"] is None and r.get("price") is not None and r["amount"] is not None:
                ok = close(r["price"], r["amount"])     # a flat fee with no quantity: price = amount
                res.append({"check": "row", "ok": ok, "file_id": r["file_id"], "page": r["page"],
                            "detail": f"no qty: {r['price']:g} vs {r['amount']:g}", "raw": r["raw"]})
            elif r["qty"] is not None and r.get("price") is not None and r["amount"] is not None:
                ok = close(r["qty"] * r["price"], r["amount"])
                res.append({"check": "row", "ok": ok, "file_id": r["file_id"], "page": r["page"],
                            "detail": f"{r['qty']:g} x {r['price']:g} = {r['qty'] * r['price']:g} vs {r['amount']:g}",
                            "raw": r["raw"]})
            else:
                res.append({"check": "row", "ok": False, "file_id": r["file_id"], "page": r["page"],
                            "detail": f"missing value: qty={r['qty']} price={r.get('price')} amount={r['amount']}",
                            "raw": r["raw"]})
            amt = r["amount"] or 0.0
            since_sub.append(amt); since_total.append(amt); since_grand.append(amt)
        elif r["amount"] is None:
            res.append({"check": r["kind"], "ok": False, "file_id": r["file_id"], "page": r["page"],
                        "detail": "total row without a readable amount", "raw": r["raw"]})
        else:
            pool = {"subtotal": since_sub, "total": since_total, "grand": since_grand}[r["kind"]]
            if not pool:
                continue                                  # e.g. a Year Total right after its Sub-Total: nothing new
            ok = close(sum(pool), r["amount"])
            res.append({"check": "grand" if r["kind"] == "grand" else "subtotal", "ok": ok, "file_id": r["file_id"],
                        "page": r["page"], "detail": f"sum {sum(pool):,.2f} vs printed {r['amount']:,.2f}",
                        "raw": r["raw"]})
            since_sub = []
            if r["kind"] in ("total", "grand"):
                since_total = []
            if r["kind"] == "grand":
                since_grand = []
    return res


def main() -> None:
    import pypdfium2 as pdfium
    from .common import pdf_path
    scores = []
    # method name -> (table reader, OCR reading of scanned pages, cell re-read on?)
    methods = {"docling": ("docling", None, False),
               "geometry+tesseract": ("geometry", "tesseract", True),
               "geometry+tess+vision": ("geometry", "tess+vision", True),
               "geometry+vision, no re-read": ("geometry", "vision", False),
               "geometry+vision": ("geometry", "vision", True)}
    for method, (reader, engine, reread) in methods.items():
        all_rows, all_checks = [], []
        for f in files():
            n = len(pdfium.PdfDocument(str(pdf_path(f))))
            rows = (docling_rows(f["file_id"]) if reader == "docling"
                    else geometry_rows(f["file_id"], n, reread=reread, engine=engine))
            all_rows += rows
            all_checks += check(rows)
        tag = re.sub(r"[^a-z]+", "_", method).strip("_")
        write_csv(OUT / "tables" / f"pricing_rows_{tag}.csv", all_rows,
                  ["file_id", "page", "kind", "description", "qty", "price", "amount", "reread", "raw"])
        write_csv(OUT / "tables" / f"pricing_checks_{tag}.csv", all_checks,
                  ["file_id", "page", "check", "ok", "detail", "raw"])
        for c in ("row", "subtotal", "grand"):
            sel = [x for x in all_checks if x["check"] == c]
            scores.append({"method": method, "check": c, "checked": len(sel), "passed": sum(x["ok"] for x in sel),
                           "pass_rate": round(sum(x["ok"] for x in sel) / len(sel), 3) if sel else ""})
        items = [r for r in all_rows if r["kind"] == "item"]
        scores.append({"method": method, "check": "product rows found", "checked": len(items), "passed": "",
                       "pass_rate": ""})
        scores.append({"method": method, "check": "product rows with no Qty read", "checked": len(items),
                       "passed": sum(r["qty"] is None for r in items), "pass_rate": ""})
    billing = [c for f in files() for c in billing_summaries(f["file_id"], len(pdfium.PdfDocument(str(pdf_path(f)))))]
    write_csv(OUT / "tables" / "billing_checks.csv", billing, ["file_id", "page", "check", "ok", "detail", "raw"])
    for c in ("billing row", "billing total"):
        sel = [x for x in billing if x["check"] == c]
        scores.append({"method": "billing summary (vision)", "check": c, "checked": len(sel),
                       "passed": sum(x["ok"] for x in sel),
                       "pass_rate": round(sum(x["ok"] for x in sel) / len(sel), 3) if sel else ""})
    write_csv(OUT / "tables" / "pricing_scores.csv", scores)
    for s in scores:
        print("  ", s)
