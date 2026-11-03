#!/usr/bin/env bash
# Run the two server methods:  bash benchmark_segmentation_extraction/server/run_privacy.sh
#   1. meaning vectors for every block (CPU)
#   2. start Llama with vLLM, ask for section starts and yes-or-no answers, stop Llama (also on an error or Ctrl-C)
# Rerunning is safe: Llama's answers are saved as they arrive and are not asked again.
# Port taken?  PORT=8123 bash ...     Pick a GPU?  CUDA_VISIBLE_DEVICES=1 bash ...
set -euo pipefail
cd "$(dirname "$0")/.."
source server/env_privacy.sh
mkdir -p work/privacy
PORT="${PORT:-8000}"
export LLM_BASE_URL="http://localhost:$PORT/v1"
exec > >(tee -a work/run_privacy.log) 2>&1

echo "GPU memory now:"; nvidia-smi --query-gpu=index,name,memory.used,memory.total --format=csv || true
echo; echo "== 1. Meaning vectors"
.venv/bin/python run.py privacy-embed

DTYPE_ARGS=""
if [ "$("$VLLM_DIR/bin/python" -c 'import torch; print(torch.cuda.get_device_capability()[0])')" -lt 8 ]; then
  DTYPE_ARGS="--dtype half"
fi
echo; echo "== 2. Starting $LLM_MODEL on port $PORT (log: work/vllm.log)"
# shellcheck disable=SC2086
"$VLLM_DIR/bin/vllm" serve "$LLM_MODEL" --port "$PORT" --max-model-len 8192 --gpu-memory-utilization 0.90 \
    --enforce-eager $DTYPE_ARGS > work/vllm.log 2>&1 &
VLLM_PID=$!
stop_vllm() { kill "$VLLM_PID" 2>/dev/null || true; wait "$VLLM_PID" 2>/dev/null || true; }
trap stop_vllm EXIT
for _ in $(seq 1 180); do                      # up to 15 minutes (longer only if the model must download)
  if curl -sf "$LLM_BASE_URL/models" > /dev/null; then break; fi
  if ! kill -0 "$VLLM_PID" 2>/dev/null; then
    echo "vLLM stopped. The end of its log:"; grep " ERROR " work/vllm.log | tail -12 || tail -20 work/vllm.log; exit 1
  fi
  sleep 5
done
curl -sf "$LLM_BASE_URL/models" > /dev/null || { echo "vLLM did not answer within 15 minutes; see work/vllm.log"; exit 1; }
echo "Llama is up."
.venv/bin/python run.py privacy-llm
stop_vllm
trap - EXIT
echo; echo "Done. Next:  bash benchmark_segmentation_extraction/server/pack_privacy.sh"
