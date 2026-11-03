# Sourced by the privacy scripts. Reuses Llama and its 16 GB download from the earlier project if they are still on this
# server (contract_pipeline, next to this folder); otherwise everything stays inside this folder.
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"
OLD="$(cd "$PROJECT/.." && pwd)/contract_pipeline"
if [ -x "$OLD/.venv-vllm/bin/vllm" ]; then
  export HF_HOME="$OLD/.cache/huggingface"
  VLLM_DIR="$OLD/.venv-vllm"
else
  export HF_HOME="$PROJECT/.cache/huggingface"
  VLLM_DIR="$PROJECT/.venv-vllm"
fi
export LLM_MODEL="meta-llama/Llama-3.1-8B-Instruct"
