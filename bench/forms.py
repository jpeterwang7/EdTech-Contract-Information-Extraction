"""Step forms: read eight fields from each of the 14 order forms, two ways, and score them.

Fields: order number, order date, customer, billing frequency, payment terms, grand total, and the name and
signing date of the person who signed for the customer. The answer key is data/gold/order_form_fields.csv
(typed from the page pictures; blacked-out values count as "not on the page").

Two methods, both reading the same text, so a difference comes from the method and not from the OCR:
  text rules  search the page's running text for each label ("Order #:", "Payment Terms:") and take what follows
  layout      find each label on the page and take the words printed to its right on the same line
              (or, if nothing is there, just below it)

Each answer is one of: correct; wrong (a value, but not the right one); missed (nothing found although the page
has a value); invented (a value found although the page has none, e.g. a blacked-out field).

Outputs: outputs/forms/form_fields_<method>.csv (every answer), outputs/forms/form_scores.csv
"""
import csv
import re
from collections import defaultdict
from datetime import date

from .common import DATA, OUT, normalize, write_csv
from .reading import TABLE_READING, best_reading, page_text
from .tables import _page_rows

FIELDS = ["order_number", "order_date", "customer", "billing_frequency", "payment_terms", "grand_total",
          "customer_signer", "customer_signed_date"]
MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                       "september", "october", "november", "december"], start=1)}
ORDER_NO = r"Q-?\s?\d{4,6}-\d{1,2}"
LABEL_END = re.compile(r":$")


# ---------------------------------------------------------------- turning raw text into comparable values

def parse_date(text: str) -> str | None:
    """The first date in the text, as YYYY-MM-DD. Handles 2016-07-25, 7/25/2016, 05.29.19, 4-21-2022, June 24, 2019."""
    if not text:
        return None
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if m:
        y, mo, d = map(int, m.groups())
    else:
        m = re.search(r"(\d{1,2})\s?[/.-]\s?(\d{1,2})\s?[/.-]\s?(\d{4}|\d{2})\b", text)
        if m:
            mo, d, y = map(int, m.groups())
            y += 2000 if y < 100 else 0
        else:
            m = re.search(r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})", text)
            if not m or m.group(1).lower() not in MONTHS:
                return None
            mo, d, y = MONTHS[m.group(1).lower()], int(m.group(2)), int(m.group(3))
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return None


def parse_money(text: str) -> str | None:
    m = re.search(r"\d[\d,]*\.\d{2}\b", text or "")
    return f"{float(m.group().replace(',', '')):.2f}" if m else None


def clean(text: str | None) -> str | None:
    """Trim a captured text value: single spaces, no stray punctuation at the ends."""
    if not text:
        return None
    t = normalize(text).strip(" .,;:|_-")
    return t or None


def same(field: str, gold: str, got: str | None) -> bool:
    if got is None:
        return False
    if field.endswith("date"):
        return parse_date(got) == gold
    if field == "grand_total":
        return parse_money(got) == gold
    simple = lambda s: re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()
    if field == "order_number":
        return re.sub(r"\s", "", got).replace("Q", "Q-").replace("--", "-") == gold
    return simple(got) == simple(gold)


# ---------------------------------------------------------------- method 1: text rules on the running text

def text_rules(form: dict) -> dict:
    fid, p1, ps, pl = form["file_id"], int(form["first_page"]), int(form["signature_page"]), int(form["last_page"])
    head = normalize(page_text(best_reading(fid, p1)))
    allp = normalize(" ".join(page_text(best_reading(fid, p)) for p in range(p1, pl + 1)))
    # money is read with the reading chosen for tables (decisions.md, T5)
    money_text = normalize(" ".join(page_text(best_reading(fid, p, TABLE_READING)) for p in range(p1, pl + 1)))
    sig = normalize(page_text(best_reading(fid, ps)))
    sig = sig[sig.lower().find("by executing"):] if "by executing" in sig.lower() else sig
    out = {}
    m = re.search(rf"Order\s*(?:#|No\.?)?\s*:?.{{0,60}}?({ORDER_NO})", head)
    out["order_number"] = m and m.group(1)
    m = re.search(r"\bDate:\s*(.{0,60})", head)
    out["order_date"] = m and parse_date(m.group(1))
    m = (re.search(r"Order Form [Ff]or\s+(.+?)(?=\s+(?:Address|Bill to|Entity Name|Order Information)\b)", head)
         or re.search(r"Customer:?\s+(?!Information\b)(.+?)(?=\s+(?:Contact|Address|Billing)\b)", head))
    out["customer"] = m and clean(m.group(1))
    m = re.search(r"Billing Frequency:\s*((?:(?!Term\b)[A-Za-z]+\s?){1,2})", head)
    out["billing_frequency"] = m and clean(m.group(1))
    m = re.search(r"Payment Terms:?.{0,250}?\b(Net\s?\d{1,3})\b", allp)
    out["payment_terms"] = m and m.group(1)
    m = (re.search(r"Grand Total:?\s*(?:USD|\$)?\s*(\d[\d,]*\.\d{2})", money_text)
         or re.search(r"Billing Summary.*?\bTotal\s+USD\s*[\d,.]+\s+USD\s*[\d,.]+\s+USD\s*(\d[\d,]*\.\d{2})",
                      money_text))
    out["grand_total"] = m and m.group(1)
    m = re.search(r"Name:\s*(.+?)(?=\s+(?:Name|Title|Date|Signature):|$)", sig)
    out["customer_signer"] = m and clean(m.group(1))
    m = re.search(r"Date:\s*(.{0,40})", sig)
    out["customer_signed_date"] = m and parse_date(m.group(1))
    return out


# ---------------------------------------------------------------- method 2: labels and positions on the page

def _rows(fid: str, page: int, engine: str | None = None) -> list[list[dict]]:
    lines = best_reading(fid, page, engine) if engine else best_reading(fid, page)
    words = [w for line in lines for w in line.get("words", [])]
    return _page_rows(words)


def _find(rows, pattern: str, below: float = -1, left_of: float = 2.0):
    """Every place a label appears: (row index, index of the label's last word). The label may span words."""
    hits = []
    for r, row in enumerate(rows):
        if row and row[0]["_yc"] < below:
            continue
        for i in range(len(row)):
            for j in range(i, min(i + 5, len(row))):
                if row[i]["box"][0] > left_of:
                    break
                if re.fullmatch(pattern, " ".join(w["text"] for w in row[i:j + 1]), re.I):
                    hits.append((r, j))
                    break
    return hits


def _right_of(rows, r: int, j: int, max_gap: float = 0.12, stop_x: float = 2.0) -> str | None:
    """Words to the right of the label on the same row, up to a wide gap, another label, or stop_x.
    If there are none, the nearest row just above or below that has words to the right of the label: typed
    values often sit a little above or below the label's line (a name typed on a signature line)."""
    def take(row, start_x):
        out, last = [], start_x
        for w in row:
            if w["box"][0] < start_x - 0.005:
                continue
            if w["box"][0] - last > max_gap or w["box"][0] >= stop_x or LABEL_END.search(w["text"]):
                break
            out.append(w["text"])
            last = w["box"][2]
        return " ".join(out) or None

    label = rows[r][j]
    same_row = take(rows[r][j + 1:], label["box"][2])
    if same_row:
        return same_row
    near = [(abs(rows[k][0]["_yc"] - label["_yc"]), k) for k in (r - 1, r + 1) if 0 <= k < len(rows)]
    for dist, k in sorted(near):
        if dist < 0.02 and not any(LABEL_END.search(w["text"]) and w["box"][0] < label["box"][2] for w in rows[k]):
            value = take(rows[k], label["box"][2])
            if value:
                return value
    return None


def layout(form: dict) -> dict:
    fid, p1, ps, pl = form["file_id"], int(form["first_page"]), int(form["signature_page"]), int(form["last_page"])
    head = _rows(fid, p1)
    out = {}
    # in the header the values stand in their own column, well to the right of the labels
    hit = _find(head, r"Order\s*(#|No\.?)?\s*:")
    v = hit and _right_of(head, *hit[0], max_gap=0.3)
    m = v and re.search(ORDER_NO, v)
    out["order_number"] = m and m.group()
    hit = _find(head, r"Date:")
    out["order_date"] = hit and parse_date(_right_of(head, *hit[0], max_gap=0.3))
    hit = _find(head, r"Order Form [Ff]or") or [
        (r, j) for r, j in _find(head, r"Customer:?")
        if not (j + 1 < len(head[r]) and head[r][j + 1]["text"].startswith("Information"))]   # the heading
    if hit:
        r, j = hit[0]
        value = _right_of(head, r, j, max_gap=0.2)
        # a long name can wrap onto the next row, under the value
        x_value = head[r][j + 1]["box"][0] if j + 1 < len(head[r]) else None
        if value and x_value and r + 1 < len(head):
            nxt = head[r + 1]
            if nxt and abs(nxt[0]["box"][0] - x_value) < 0.02 and nxt[0]["_yc"] - head[r][j]["_yc"] < 0.03:
                value += " " + " ".join(w["text"] for w in nxt if w["box"][0] < x_value + 0.25)
        out["customer"] = clean(value)
    hit = _find(head, r"Billing Frequency:")
    out["billing_frequency"] = hit and clean(_right_of(head, *hit[0]))
    hit = _find(head, r"Payment Terms:")
    v = hit and _right_of(head, *hit[0])
    m = v and re.search(r"Net\s?\d{1,3}", v)
    out["payment_terms"] = m and m.group()
    out["grand_total"] = None
    for p in range(p1, pl + 1):
        rows = _rows(fid, p, TABLE_READING)
        hit = _find(rows, r"Grand Total:?")
        if hit:
            out["grand_total"] = parse_money(" ".join(w["text"] for w in rows[hit[0][0]]))
            break
        seg = _find(rows, r"Segment")
        if seg:
            tot = [r for r, _ in _find(rows, r"Total", below=rows[seg[0][0]][0]["_yc"]) if r > seg[0][0]]
            if tot:
                monies = re.findall(r"\d[\d,]*\.\d{2}", " ".join(w["text"] for w in rows[tot[0]]))
                out["grand_total"] = monies and parse_money(monies[-1])
                break
    rows = _rows(fid, ps)
    start = _find(rows, r"By executing")
    top = rows[start[0][0]][0]["_yc"] if start else 0
    for field, label in (("customer_signer", r"Name:"), ("customer_signed_date", r"Date:")):
        hits = _find(rows, label, below=top)
        if not hits:
            out[field] = None
            continue
        r, j = min(hits, key=lambda h: rows[h[0]][h[1]]["box"][0])       # the left column is the customer's
        other = [rows[r2][j2]["box"][0] for r2, j2 in hits if rows[r2][j2]["box"][0] > rows[r][j]["box"][2] + 0.1]
        v = _right_of(rows, r, j, stop_x=min(other) - 0.02 if other else 2.0)
        out[field] = parse_date(v) if field.endswith("date") else clean(v)
    return out


# ---------------------------------------------------------------- scoring

METHODS = {"text rules": text_rules, "layout": layout}


def main() -> None:
    with open(DATA / "order_forms.csv") as fh:
        forms = list(csv.DictReader(fh))
    with open(DATA / "gold" / "order_form_fields.csv") as fh:
        gold = {(g["form_id"], g["field"]): g["gold_value"] for g in csv.DictReader(fh)}
    scores = []
    for name, method in METHODS.items():
        answers = []
        for form in forms:
            got = method(form)
            for field in FIELDS:
                g, v = gold[(form["form_id"], field)], got.get(field) or None
                if g and same(field, g, v):
                    outcome = "correct"
                elif g and v:
                    outcome = "wrong"
                elif g:
                    outcome = "missed"
                elif v:
                    outcome = "invented"
                else:
                    outcome = "correctly empty"
                answers.append({"form_id": form["form_id"], "field": field, "gold": g, "extracted": v or "",
                                "outcome": outcome})
        tag = re.sub(r"[^a-z]+", "_", name)
        write_csv(OUT / "forms" / f"form_fields_{tag}.csv", answers)
        by_field = defaultdict(list)
        for a in answers:
            by_field[a["field"]].append(a)
        for field in FIELDS + ["ALL"]:
            sel = answers if field == "ALL" else by_field[field]
            n = lambda o: sum(a["outcome"] == o for a in sel)
            present = sum(1 for a in sel if a["gold"])
            scores.append({"method": name, "field": field, "values_on_page": present, "correct": n("correct"),
                           "wrong": n("wrong"), "missed": n("missed"), "invented": n("invented"),
                           "accuracy": round(n("correct") / present, 3) if present else ""})
    write_csv(OUT / "forms" / "form_scores.csv", scores)
    for s in scores:
        if s["field"] == "ALL":
            print("  ", s)
