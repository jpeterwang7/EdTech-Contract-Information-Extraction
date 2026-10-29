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
import sys

from PIL import Image

from .common import OUT, WORK, files, page_png

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


if __name__ == "__main__":
    for fid in sys.argv[1:] or ["F02"]:
        print(build(fid))
