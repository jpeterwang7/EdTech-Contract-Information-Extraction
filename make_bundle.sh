#!/usr/bin/env bash
# On your Mac: make ../benchmark_bundle.zip to upload to the lab server.
# Contains the code, the answer keys, the earlier pipeline's output, the 14 contract PDFs (in contracts/) and the
# OCR already done on this Mac (Apple Vision exists only on macOS, so the server reuses its readings).
# Leaves out the Python environment and the page images: the server builds its own.
set -euo pipefail
cd "$(dirname "$0")"
HERE="$(pwd)"
PARENT="$(dirname "$HERE")"
NAME="$(basename "$HERE")"
OUT="$PARENT/benchmark_bundle.zip"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

rsync -a --exclude '.venv' --exclude '.tessdata' --exclude '.cache' --exclude '.git' --exclude '__pycache__' \
      --exclude '.DS_Store' --exclude 'contracts' --exclude 'results_*.zip' --exclude 'tools/vision_ocr' \
      --exclude 'work/pages' --exclude 'work/gold_sheets' --exclude 'work/*.png' --exclude 'work/*.log' \
      "$HERE/" "$TMP/$NAME/"
mkdir -p "$TMP/$NAME/contracts"
cp "$PARENT/Instructure Contracts/"*.[pP][dD][fF] "$TMP/$NAME/contracts/"
rm -f "$OUT"
(cd "$TMP" && zip -rq "$OUT" "$NAME" -x '*.DS_Store')
echo "Made $OUT ($(du -h "$OUT" | cut -f1)). Upload it with:"
echo "  scp \"$OUT\" YOUR_USERNAME@YOUR_SERVER:~/"
