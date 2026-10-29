#!/usr/bin/env bash
# Remove EVERYTHING this project put on the lab server:  bash benchmark_segmentation_extraction/server/cleanup_server.sh
# Deletes the whole folder (contract PDFs, OCR readings, outputs, the Python environment, caches, results zips)
# and the uploaded bundle zip next to it, then shows whether any of your processes from it are still running.
set -uo pipefail
PROJECT="$(cd "$(dirname "$0")/.." && pwd)"
PARENT="$(dirname "$PROJECT")"
BUNDLE="$PARENT/benchmark_bundle.zip"

echo "This permanently deletes:"
echo "  $PROJECT   ($(du -sh "$PROJECT" 2>/dev/null | cut -f1))"
[ -e "$BUNDLE" ] && echo "  $BUNDLE   ($(du -sh "$BUNDLE" | cut -f1))"
read -r -p "Type DELETE to confirm: " answer
[ "$answer" = "DELETE" ] || { echo "Cancelled; nothing deleted."; exit 1; }

pkill -u "$(id -u)" -f "benchmark_segmentation_extraction.*run.py" 2>/dev/null
sleep 2
cd "$PARENT"
rm -rf "$PROJECT" "$BUNDLE"
[ -e "$PROJECT" ] && echo "WARNING: could not fully delete $PROJECT" || echo "Deleted $PROJECT"
echo; echo "Your run.py processes still running (should be none):"
pgrep -u "$(id -u)" -a -f "run.py" || echo "  none"
