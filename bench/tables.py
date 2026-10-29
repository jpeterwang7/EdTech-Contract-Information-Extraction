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


_TESS_DIGIT = None


def reread_cell(file_id: str, page: int, cols: list[tuple[str, float]], name: str, lines: list[list[dict]],
                parse) -> tuple[str, str]:
    """Cut one cell out of the page picture and read it again on its own. Returns (text, how).
    OCR on a whole page tends to skip a lone character such as the "1" in a Qty cell (F06 p1). Read on its own
    the cell often comes out right, but not always, so three tries in a fixed order, keeping the first that
    gives a number: Apple Vision on the enlarged cell; the same with a white margin around it; Tesseract
    reading a single character, digits only. (This order was chosen on the 6 cells that needed it; decisions.md, T4.)
    The cell spans halfway to the neighbouring headers, trimmed so the table's ruling lines stay out, and from
    the top to the bottom of the row's lines."""
    global _TESS_DIGIT
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
    crop = img.crop((int((left + trim) * W), int(top * H), int((right - trim) * W), int(bottom * H)))
    crop = crop.resize((crop.width * 2, crop.height * 2), Image.LANCZOS).convert("L")
    base = WORK / "cells" / f"{file_id}_p{page}_{name}_{int(top * 1000)}"
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


def geometry_rows(file_id: str, n_pages: int, reread: bool = True, engine: str = TABLE_READING) -> list[dict]:
    """A table row can span several visual lines (a wrapped "USD / 12,000.00", a tall "20% of / Subscription /
    (Minimums Apply)" cell). Every row has exactly one amount, printed once, so the visual lines that hold an
    amount are the row anchors and every other line joins the nearest anchor (if within MAX_JOIN of it)."""
    MAX_JOIN = 0.03
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
            yc = lambda line: sum(w["_yc"] for w in line) / len(line)
            anchors = [k for k, line in enumerate(body) if re.search(r"\d", _cells([line], cols).get("amount", ""))]
            groups = {k: [body[k]] for k in anchors}
            for k, line in enumerate(body):
                if k in groups or not anchors:
                    continue
                near = min(anchors, key=lambda a: abs(yc(body[a]) - yc(line)))
                if abs(yc(body[near]) - yc(line)) <= MAX_JOIN:
                    groups[near].append(line)
            for k in anchors:
                lines = sorted(groups[k], key=yc)
                cells = _cells(lines, cols)
                text = " ".join(w["text"] for line in lines for w in line)
                kind = row_kind(text)
                row = {"file_id": file_id, "page": page, "kind": kind, "amount": money(cells.get("amount", "")),
                       "raw": text[:160]}
                if kind == "item":
                    row.update(description=cells.get("description", ""), qty=qty(cells.get("qty", "")),
                               price=money(cells.get("price", "")), reread="")
                    if reread and page_source(file_id, page, engine) != "textlayer":
                        for name, parse in (("qty", first_number), ("price", money)):
                            if row[name] is None and name in [c[0] for c in cols]:
                                again, how = reread_cell(file_id, page, cols, name, lines, parse)
                                row[name] = parse(again)
                                row["reread"] += f"{name} by {how}: {again!r}; "
                out.append(row)
            # a Grand Total sits under the table, outside its columns
            if j < len(rows) and row_kind(" ".join(w["text"] for w in rows[j])) == "grand" and not (
                    body and row_kind(" ".join(w["text"] for w in body[-1])) == "grand"):
                text = " ".join(w["text"] for w in rows[j])
                out.append({"file_id": file_id, "page": page, "kind": "grand", "amount": money(text), "raw": text[:160]})
            i = j
        # Grand Totals printed away from any table (another line further down the page)
        for row in rows:
            text = " ".join(w["text"] for w in row)
            if row_kind(text) == "grand" and not any(o["page"] == page and o["kind"] == "grand" for o in out
                                                      if o["file_id"] == file_id):
                out.append({"file_id": file_id, "page": page, "kind": "grand", "amount": money(text), "raw": text[:160]})
    return out


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
    write_csv(OUT / "tables" / "pricing_scores.csv", scores)
    for s in scores:
        print("  ", s)
