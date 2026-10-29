# Sourced by the other server scripts. Keeps every download and cache inside this folder, so
# server/cleanup_server.sh can remove all of it. THREADS caps how many CPU cores OCR uses on the shared server.
PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export XDG_CACHE_HOME="$PROJECT/.cache"
export PIP_NO_CACHE_DIR=1
export TMPDIR="$PROJECT/.cache/tmp"
export THREADS="${THREADS:-8}"
export OMP_NUM_THREADS="$THREADS"
mkdir -p "$TMPDIR"
