"""Shared paths and small helpers used by every step."""
import csv
import json
import os
import platform
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# The PDFs stay outside the repo. On the server they arrive inside the bundle, in contracts/.
PDF_DIR = ROOT / "contracts" if (ROOT / "contracts").is_dir() else ROOT.parent / "Instructure Contracts"
DATA = ROOT / "data"
WORK = ROOT / "work"                              # big in-between files (page images, raw OCR); not in git
OUT = ROOT / "outputs"
TESSDATA = ROOT / ".tessdata"

DPI = 300                                          # resolution for page images (see docs/decisions.md, R2)
ON_MAC = platform.system() == "Darwin"            # Apple Vision OCR exists only on macOS
THREADS = int(os.environ.get("THREADS", "-1"))     # CPU threads for OCR; -1 = all. Set lower on a shared server.


def files() -> list[dict]:
    """The 14 contract files, with short IDs (F01..F14), from data/files.csv."""
    with open(DATA / "files.csv", newline="") as fh:
        return list(csv.DictReader(fh))


def pdf_path(f: dict) -> Path:
    return PDF_DIR / f["file"]


def page_png(file_id: str, page: int) -> Path:
    return WORK / "pages" / file_id / f"p{page:03d}.png"


def read_json(path: Path):
    with open(path) as fh:
        return json.load(fh)


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as fh:          # write then rename, so a crash never leaves half a file behind
        json.dump(obj, fh)
    tmp.replace(path)


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fields or list(rows[0].keys())
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


_QUOTES = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'", "–": "-", "—": "-",
                         " ": " ", "ﬁ": "fi", "ﬂ": "fl"})


def normalize(text: str) -> str:
    """Make two readings comparable: same quote and dash characters, single spaces.
    Curly vs straight quotes are typesetting, not reading errors (decisions.md, R5)."""
    return re.sub(r"\s+", " ", text.translate(_QUOTES)).strip()
