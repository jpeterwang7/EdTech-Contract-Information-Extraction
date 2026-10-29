#!/usr/bin/env bash
# Zip the results so you can download them:  bash server/pack_results.sh
# The zip is made inside this folder, so the cleanup script deletes it too.
set -euo pipefail
cd "$(dirname "$0")/.."
NAME="results_$(date +%Y-%m-%d_%H%M).zip"
zip -rq "$NAME" outputs work/ocr/rapidocr work/run_all.log
echo "Made $(pwd)/$NAME ($(du -h "$NAME" | cut -f1))."
echo "On your Mac, download it with:"
echo "  scp $(whoami)@$(hostname -f 2>/dev/null || hostname):$(pwd)/$NAME ~/Desktop/"
