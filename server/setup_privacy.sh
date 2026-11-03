#!/usr/bin/env bash
# One-time setup for the privacy step:  bash benchmark_segmentation_extraction/server/setup_privacy.sh
set -euo pipefail
cd "$(dirname "$0")/.."
source server/env_privacy.sh
[ -x .venv/bin/python ] || { echo "Run server/setup_server.sh first."; exit 1; }
echo "== Meaning model: sentence-transformers (CPU version of PyTorch, so it never competes for the GPU)"
.venv/bin/pip install torch --index-url https://download.pytorch.org/whl/cpu
.venv/bin/pip install sentence-transformers
.venv/bin/python -c "import sentence_transformers; print('sentence-transformers', sentence_transformers.__version__)"
echo; echo "== Llama"
if [ -x "$VLLM_DIR/bin/vllm" ]; then
  echo "Reusing the earlier project's vLLM: $VLLM_DIR"
  echo "Model cache: $HF_HOME"
else
  echo "No earlier vLLM found; installing one in this folder."
  PY="${PYTHON:-$(command -v python3.12 || command -v python3.11 || command -v python3.10 || command -v python3)}"
  CUDA_MAJOR=$(nvidia-smi | grep -o "CUDA Version: [0-9]*" | grep -o "[0-9]*$" || echo 0)
  if [ "${CUDA_MAJOR:-0}" -lt 13 ]; then PINS=("vllm==0.11.0" "transformers<5"); else PINS=("vllm"); fi
  "$PY" -m venv .venv-vllm
  .venv-vllm/bin/pip install --upgrade pip
  .venv-vllm/bin/pip install "${PINS[@]}"
  echo "Llama 3.1 needs your Hugging Face token, and you must have accepted Meta's license at"
  echo "https://huggingface.co/meta-llama/Llama-3.1-8B-Instruct . The token is saved inside this folder."
  .venv-vllm/bin/python -c "from huggingface_hub import login; login()"
fi
echo; echo "Setup done. Next:  bash benchmark_segmentation_extraction/server/run_privacy.sh"
