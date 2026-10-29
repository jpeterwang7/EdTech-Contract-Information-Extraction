#!/usr/bin/env bash
# Run the reading, OCR scoring and pricing-table steps:  bash server/run_all.sh
# CPU only, about 10 minutes. Apple Vision is skipped (it exists only on a Mac); its readings came in the bundle.
set -euo pipefail
cd "$(dirname "$0")/.."
source server/env.sh
echo "Using $THREADS CPU threads (another number:  THREADS=4 bash server/run_all.sh)"
.venv/bin/python run.py read ocr-eval tables 2>&1 | grep --line-buffered -v "\[RapidOCR\]" | tee work/run_all.log
echo; echo "Done. Next:  bash server/pack_results.sh"
