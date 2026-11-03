"""Review page: each PDF page next to its clean text, to check by eye.

Usage: python -m bench.review F02   ->  work/review/F02.html (open it in a browser)

Left: the page picture. Right: the clean-text blocks that start on that page (headings bold, table and form rows
as rows, paragraphs joined across a page break marked), and below them, struck through in grey, everything the
clean-text step removed from that page and why.
"""
import base64
import csv
import html
import io
import json
import re
import sys

from PIL import Image

from .common import DATA, OUT, WORK, files, page_png

CSS = """
body{font-family:-apple-system,Segoe UI,Arial,sans-serif;margin:0;background:#f4f4f4;color:#1a1a1a}
header{padding:16px 24px;background:#fff;border-bottom:1px solid #ddd;position:sticky;top:0;z-index:2}
header h1{font-size:18px;margin:0 0 6px} header p{margin:2px 0;font-size:13px;color:#444}
.page{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px;padding:16px 24px;border-bottom:2px solid #ccc}
.page img{width:100%;border:1px solid #bbb;background:#fff}
.text{background:#fff;border:1px solid #bbb;padding:12px 16px;font-size:14px;line-height:1.45;overflow-wrap:anywhere}
.tag{font-size:11px;color:#777;margin-top:10px}
.heading{font-weight:700}
.rows{font-family:Menlo,Consolas,monospace;font-size:12px;white-space:pre-wrap;background:#f7f7f7;padding:6px;border-radius:4px}
.joined{border-left:3px solid #2a7ae2;padding-left:8px}
.removed{margin-top:16px;padding-top:8px;border-top:1px dashed #bbb;font-size:12px;color:#888}
.removed s{color:#999}
h2{font-size:14px;margin:0 0 8px}
@media (max-width:900px){.page{grid-template-columns:1fr}}
"""


def picture(file_id: str, page: int) -> str:
    """The page picture inside the HTML itself (a smaller JPEG), so the file works on its own in any browser.
    Safari will not show pictures a local file points to in another folder."""
    img = Image.open(page_png(file_id, page)).convert("RGB")
    img.thumbnail((1300, 1800))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=80)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def build(file_id: str) -> str:
    f = next(x for x in files() if x["file_id"] == file_id)
    blocks = [b for b in map(json.loads, open(OUT / "text" / "blocks.jsonl")) if b["file_id"] == file_id]
    with open(OUT / "text" / "removed.csv") as fh:
        removed = [r for r in csv.DictReader(fh) if r["file_id"] == file_id]
    pages = sorted({p for b in blocks for p in b["pages"]} | {int(r["page"]) for r in removed})
    out = [f"<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'>"
           f"<title>Clean text review {file_id}</title><style>{CSS}</style></head><body>",
           f"<header><h1>{file_id}: {html.escape(f['description'])}</h1>",
           "<p>Left: the page. Right: the clean text that starts on that page, then (struck through) what was "
           "removed. Blue bar = a paragraph continued from the previous page.</p>",
           "<p>Please note: any sentence missing or cut off, any page number or scrap left in, any table row that "
           "is wrong, anything removed that should have stayed.</p></header>"]
    for p in pages:
        img = picture(file_id, p)
        out.append(f"<section class='page' id='p{p}'><div><h2>Page {p}</h2><img src='{img}' alt='page {p}'></div>"
                   "<div class='text'>")
        for b in [b for b in blocks if b["pages"][0] == p]:
            span = f"pages {b['pages'][0]}–{b['pages'][-1]}" if len(b["pages"]) > 1 else f"page {p}"
            out.append(f"<div class='tag'>{b['kind']}, {span}</div>")
            if b["kind"] in ("grid", "table"):
                out.append(f"<div class='rows'>{html.escape(chr(10).join(b['rows']))}</div>")
            else:
                cls = "heading" if b["kind"] == "heading" else ("joined" if len(b["pages"]) > 1 else "")
                out.append(f"<div class='{cls}'>{html.escape(b['text'])}</div>")
        gone = [r for r in removed if int(r["page"]) == p]
        if gone:
            out.append("<div class='removed'><b>Removed from this page:</b><br>" + "<br>".join(
                f"<s>{html.escape(r['text'][:120])}</s> — {html.escape(r['reason'])}" for r in gone) + "</div>")
        out.append("</div></section>")
    out.append("</body></html>")
    path = WORK / "review" / f"{file_id}.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out))
    return str(path)


def privacy_key() -> str:
    """The privacy answer key over the contract text: green = core, must be found; yellow = borderline, a person
    checks it; grey = not in the category. Only the marked words of an excerpt are coloured. The non-binding
    security brochure in F09 is left out, as it is from all scoring."""
    from .privacy import BROCHURE, contract_blocks, load_blocks, load_gold
    blocks, gold = load_blocks(), load_gold(load_blocks())
    marks = {}
    for g in gold:
        if g["binding"] == "no":
            continue
        cls = "core" if g["strength"] == "core" else "bord"
        for n, (k, a, b) in enumerate(g["spans"]):
            marks.setdefault((g["file_id"], k), []).append((a, b, cls, g["passage_id"] if n == 0 else ""))
    out = ["<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'>"
           "<title>Privacy answer key</title><style>"
           "body{font-family:-apple-system,Segoe UI,Arial,sans-serif;margin:0 auto;max-width:980px;padding:16px;line-height:1.45;font-size:14px}"
           "h2{margin-top:32px;border-bottom:2px solid #333}p{margin:8px 0}.other{color:#777;font-size:12px}.core{background:#c6f0c6}.bord{background:#fff0b3}"
           ".tag{font:11px Menlo,monospace;color:#333;background:#eee;padding:0 4px;margin-right:4px}"
           "header{position:sticky;top:0;background:#fff;padding:8px 0;border-bottom:1px solid #ccc}</style></head><body><header>"
           "<b>Privacy answer key.</b> <span class='core'>green: must be found</span> <span class='bord'>yellow: a person checks it</span> "
           "<span class='other'>grey: not in the category (long blocks cut at 45 words)</span></header>"]
    for f, bs in blocks.items():
        out.append(f"<h2>{f}</h2>")
        if f == BROCHURE[0]:
            out.append("<p class='other'>The security brochure attached to this file is not contract terms and is not shown.</p>")
        for k in contract_blocks(blocks, f):
            b = bs[k]
            ms = marks.get((f, k))
            label = f"<span class='tag'>{k} p{b['pages'][0]}</span>"
            if not ms:
                out.append(f"<p class='other'>{label}{html.escape(' '.join(b['words'][:45]))}{' …' if len(b['words']) > 45 else ''}</p>")
                continue
            w, parts, pos = b["words"], [], 0
            for a, e, cls, tag in sorted(ms):
                parts.append(html.escape(" ".join(w[pos:a])))
                t = f"<span class='tag'>{html.escape(tag)}</span>" if tag else ""
                parts.append(f"{t}<span class='{cls}'>{html.escape(' '.join(w[a:e]))}</span>")
                pos = e
            parts.append(html.escape(" ".join(w[pos:])))
            out.append(f"<p>{label}{' '.join(parts)}</p>")
    path = WORK / "review" / "privacy_key.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "</body></html>")
    return str(path)


RELEVANT = re.compile(r"\b(data|information|records?|privacy|private|secur\w*|personal\w*|student\w*|confidential\w*|breach\w*"
                      r"|delet\w*|destr\w*|retain\w*|retention|export\w*|ferpa|coppa|hipaa|gdpr|consent\w*|artificial|ai"
                      r"|anonymi\w*|aggregat\w*|usage|encrypt\w*|disclos\w*|third[- ]part\w*|subprocessor\w*|content)\b", re.I)
SKIP_ROW = re.compile(r"envelope|signer events|ip address|electronic record and signature|docusign", re.I)


def mentor_sheet() -> str:
    """A workbook for an outside reader to check the key, contract text only: one answer per row, In or Out."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation
    from .privacy import DEFINITION, contract_blocks, load_blocks, load_gold
    blocks = load_blocks()
    gold = [g for g in load_gold(blocks) if g["binding"] == "yes"]
    info = {f["file_id"]: f for f in files()}
    marked = {(g["file_id"], k) for g in gold for k, _, _ in g["spans"]}
    arial = Font(name="Arial", size=10)
    bold = Font(name="Arial", size=10, bold=True)
    white = Font(name="Arial", size=10, bold=True, color="FFFFFF")
    head = PatternFill("solid", fgColor="444444")
    answer = PatternFill("solid", fgColor="FFF8C6")
    wrap = Alignment(wrap_text=True, vertical="top")

    wb = Workbook()
    me = wb.active
    me.title = "Read me"
    lines = [("Checking which contract text is about data governance and privacy", bold), ("", arial),
             ("Why: this project pulls one category of text out of contracts between Instructure (the company behind the "
              "Canvas learning platform) and universities. A later step extracts facts from it, so the category needs to "
              "be right. The first pass below needs a person's judgment.", arial),
             ("", arial), ("The category", bold), (DEFINITION, arial), ("", arial), ("How to answer", bold),
             ("Pick In or Out in the yellow 'Your answer' column, and add a reason under 'Comment' if useful. Those two "
              "columns are the only ones to fill in.", arial),
             ("To check: the closest decisions. Please start here, and answer every row: In or Out.", arial),
             ("Marked In: must be found. Answer only if you disagree; a blank counts as agreeing.", arial),
             ("Marked Out: text left out that mentions a related word such as data, security or student. Answer only if "
              "you disagree. Other text (prices, mailing details, signing logs) is not listed.", arial),
             ("'Same text as' means the wording repeats an earlier row, so it can be skipped.", arial), ("", arial),
             ("Text comes from scanned contracts, so expect a few spelling slips.", arial), ("", arial),
             ("Example of a filled-in row", bold),
             ("Tab To check.  Text: 'Customer must keep passwords secure...'   First answer: Check   Your answer: Out   "
              "Comment: Account security duty, not about the data itself", arial)]
    for i, (t, font) in enumerate(lines, 1):
        c = me.cell(i, 1, t)
        c.font, c.alignment = font, wrap
    me.column_dimensions["A"].width = 110

    def sheet(title, first, rows):
        ws = wb.create_sheet(title)
        cols = [("Row", 7), ("Contract", 8), ("Page", 7), ("Institution and year", 26), ("Text", 90), ("Note", 24),
                ("First answer", 9), ("Your answer", 9), ("Comment", 36)]
        for j, (name, width) in enumerate(cols, 1):
            c = ws.cell(1, j, name)
            c.font, c.fill, c.alignment = white, head, wrap
            ws.column_dimensions[c.column_letter].width = width
        seen = {}
        for i, (fid, page, text, note) in enumerate(rows, 2):
            key = re.sub(r"[^a-z]+", " ", text.lower())[:300]
            if key in seen:
                note = "; ".join(x for x in (note, f"Same text as row {seen[key]}") if x)
            else:
                seen[key] = i - 1
            vals = [i - 1, fid, page, f"{info[fid]['institution']}, {info[fid]['year']}", text[:32000], note, first, None, None]
            for j, v in enumerate(vals, 1):
                c = ws.cell(i, j, v)
                c.font, c.alignment = arial, wrap
            ws.cell(i, 8).fill = answer
            ws.cell(i, 9).fill = answer
        dv = DataValidation(type="list", formula1='"In,Out"', allow_blank=True)
        dv.add(f"H2:H{len(rows) + 1}")
        ws.add_data_validation(dv)
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = f"A1:I{len(rows) + 1}"
        return len(rows)

    def passage_row(g):
        bs = blocks[g["file_id"]]
        text = " ".join(" ".join(bs[k]["words"][a:b]) for k, a, b in g["spans"])
        part = any(a > 0 or b < len(bs[k]["words"]) for k, a, b in g["spans"])
        return g["file_id"], bs[g["spans"][0][0]]["pages"][0], text, "Part of a longer clause" if part else ""

    rows_check = [passage_row(g) for g in gold if g["strength"] == "borderline"]
    rows_in = [passage_row(g) for g in gold if g["strength"] == "core"]
    rows_out = []
    for fid, bs in blocks.items():
        for k in contract_blocks(blocks, fid):
            b = bs[k]
            text = " ".join(b["words"])
            if (fid, k) not in marked and b["kind"] != "table" and len(b["words"]) >= 6 \
                    and RELEVANT.search(text) and not SKIP_ROW.search(text):
                rows_out.append((fid, b["pages"][0], text, ""))
    n = [sheet("To check", "Check", rows_check), sheet("Marked In", "In", rows_in), sheet("Marked Out", "Out", rows_out)]
    path = OUT / "privacy" / "privacy_key_for_review.xlsx"
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    print(f"  {n[0]} rows to check, {n[1]} marked In, {n[2]} marked Out")
    return str(path)


if __name__ == "__main__":
    for fid in sys.argv[1:] or ["F02"]:
        print(mentor_sheet() if fid == "sheet" else privacy_key() if fid == "privacy" else build(fid))
