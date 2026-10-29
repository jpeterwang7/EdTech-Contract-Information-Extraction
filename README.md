# Instructure contracts: segmentation and information-extraction benchmark

My benchmark project for Q4 2026. It uses the 14 contract files between Instructure Inc. and Nebraska
universities and colleges (one file, F09, is a California college's agreement that was in the same folder). It
has two goals:
1. Split each contract into meaningful sections and label each section's topic (data privacy, pricing, liability…).
2. On the data-governance and privacy sections, compare several ways of extracting specific facts (data
   ownership, data use, data deletion).

The work is kept separate from the earlier `../contract_pipeline` and `../segmentation_pilot`, which covered both
vendors at the clause level. Instructure's files are the harder test: 9 of 14 are scans, and they are mostly
tables and forms.

**Where to read:**
- [docs/decisions.md](docs/decisions.md): every decision, in plain language, with the numbers behind it.
- [docs/what_failed.md](docs/what_failed.md): what did not work, with examples.

## Status

| Step | What it does | State |
|---|---|---|
| `read` | Turn every page into text: the PDF's own text on digital pages; OCR on the 47 scanned pages | done (final run on the lab server, Oct 29) |
| `ocr-eval` | Score each OCR reading against two answer keys | done; answer key 1 needs a human check |
| `tables` | Read the pricing tables two ways; check them with arithmetic | done |
| `forms` | Read 8 fields from each of the 14 order forms two ways (text rules, layout) and score them | done; its answer key needs a human check |
| sections | Split into sections and label topics (goal 1) | later |
| extraction | Privacy facts (goal 2) | later |

Headline results so far:
- **Reading scanned pages:**
  - The earlier pipeline got 8.8% of characters wrong and 61% of numbers exactly right.
  - Tesseract with Apple Vision filling its gaps gets 0.37% wrong and 100% of numbers right.
  - A second test on 785 lines from digital pages, not used to design anything, ranks the readings in the same
    order (0.45% of characters wrong).
- **Pricing tables:**
  - 88 product rows found.
  - Every subtotal (63/63) and grand total (12/12) adds up.
  - The 7 row checks that fail are arithmetic errors printed in the contracts themselves.
- **Order-form fields:**
  - Reading by position on the page (layout) gets 89 of 99 values right.
  - Searching the running text (text rules) gets 84.
  - Layout is far better on signer names and dates. Handwriting defeats both.

## Running it on the lab server (recommended: keeps your laptop cool)

No GPU is needed for these steps. Apple Vision runs only on a Mac; its readings travel inside the bundle.

On your Mac, make the bundle (code, answer keys, the 14 PDFs, the OCR already done):
```bash
bash "$HOME/Desktop/Educational Contracts/benchmark_segmentation_extraction/make_bundle.sh"
```
Upload it, then log in:
```bash
scp "$HOME/Desktop/Educational Contracts/benchmark_bundle.zip" YOUR_USERNAME@YOUR_SERVER:~/
```
```bash
ssh YOUR_USERNAME@YOUR_SERVER
```
On the server, unpack and set up (first time only):
```bash
unzip -q benchmark_bundle.zip && bash benchmark_segmentation_extraction/server/setup_server.sh
```
Run inside `tmux`, so a dropped connection does not stop it (`tmux attach -t bench` to come back):
```bash
tmux new -s bench
```
```bash
bash benchmark_segmentation_extraction/server/run_all.sh
```
It uses 8 CPU threads by default. On a busy server, use fewer:
```bash
THREADS=4 bash benchmark_segmentation_extraction/server/run_all.sh
```
Zip the results; the script prints an `scp` line to copy into a terminal **on your Mac**:
```bash
bash benchmark_segmentation_extraction/server/pack_results.sh
```
Back on the Mac, unpack the results into this folder (replace the zip name with the one you downloaded):
```bash
unzip -o ~/Desktop/results_DATE.zip -d "$HOME/Desktop/Educational Contracts/benchmark_segmentation_extraction"
```
When the project is finished, remove everything from the server (it asks you to type DELETE):
```bash
bash benchmark_segmentation_extraction/server/cleanup_server.sh
```

## Running it on the Mac

```bash
.venv/bin/python run.py read ocr-eval tables forms
```
`read` skips pages already read, so only missing pages cost time. Setup on a new Mac:
1. Create the environment and install the packages:
   ```bash
   python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
   ```
2. Download Tesseract's English model into `.tessdata/` (the link is in `requirements.txt`).

## Checking the answer key (to do)

Open `data/gold/ocr_lines.csv` next to the pictures in `data/gold/ocr_crops/`. For each line:
- Compare `gold_text` with the picture, and fix the text if it is wrong.
- Write `yes` in `human_checked`.
- Note any change in `notes`.

Then run `.venv/bin/python run.py ocr-eval` again.

Do the same for `data/gold/order_form_fields.csv`, comparing it with the order-form pages. Then run
`.venv/bin/python run.py forms`.

## Folder map

```
run.py              the entry point: python run.py <steps>
bench/              one file per step: reading.py, ocr_eval.py, tables.py, forms.py, common.py (shared helpers)
tools/              vision_ocr.swift (Apple Vision OCR, compiled on first use)
data/files.csv      the 14 files and their short IDs F01..F14
data/order_forms.csv  the 14 order forms: file, first page, signature page
data/gold/          answer keys: ocr_lines.csv (+ the line pictures), order_form_fields.csv
data/baseline_docling_rapidocr/   the earlier pipeline's output, for comparison
docs/               decisions.md, what_failed.md
outputs/            scores and results (made by run.py)
server/             setup, run, pack and cleanup scripts for the lab server
work/               page pictures and raw OCR (made by run.py; not in git)
```
The contract PDFs are not in the repo. They are read from `../Instructure Contracts/`, or from `contracts/` inside
the server bundle.
