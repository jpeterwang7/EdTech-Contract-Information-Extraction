#!/usr/bin/env bash
# One-time setup on the lab server. Run from anywhere:  bash benchmark_segmentation_extraction/server/setup_server.sh
# Installs one Python environment (.venv) inside this folder. No GPU and no Hugging Face token needed for these steps.
set -euo pipefail
cd "$(dirname "$0")/.."
source server/env.sh

PY="${PYTHON:-$(command -v python3.12 || command -v python3.11 || command -v python3.10 || command -v python3)}"
"$PY" -c 'import sys; assert sys.version_info >= (3, 10), f"Python 3.10+ needed, found {sys.version.split()[0]}"'
echo "Python: $("$PY" --version) at $PY"

"$PY" -m venv .venv
.venv/bin/pip install --upgrade pip
grep -v '^tesserocr' requirements.txt > .cache/requirements_core.txt
.venv/bin/pip install -r .cache/requirements_core.txt

# Tesseract has already read all 156 pages on the Mac (the results are in the bundle), so the server only needs it
# for one small fallback in the table step. If it will not install, everything still runs.
if .venv/bin/pip install tesserocr==2.12.0 && .venv/bin/python -c "import tesserocr" 2>/dev/null; then
  mkdir -p .tessdata
  curl -sSL -o .tessdata/eng.traineddata https://github.com/tesseract-ocr/tessdata_best/raw/main/eng.traineddata
  echo "8280aed0782fe27257a68ea10fe7ef324ca0f8d85bd2fd145d1c2b560bcb66ba  .tessdata/eng.traineddata" | sha256sum -c -
  echo "Tesseract: installed"
else
  echo "NOTE: Tesseract (tesserocr) could not be installed here. That is fine: its page readings came in the bundle."
fi
echo; echo "Setup done. Next:  bash server/run_all.sh"
