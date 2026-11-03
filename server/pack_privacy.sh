#!/usr/bin/env bash
# Zip the privacy results:  bash benchmark_segmentation_extraction/server/pack_privacy.sh
set -euo pipefail
cd "$(dirname "$0")/.."
rm -f results_privacy.zip
zip -rq results_privacy.zip work/privacy work/run_privacy.log
echo "Made $(pwd)/results_privacy.zip ($(du -h results_privacy.zip | cut -f1))."
