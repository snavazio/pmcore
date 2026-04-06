#!/usr/bin/env bash
# ============================================================
# PMCommunicator → GGUF + Ollama
# ============================================================
# Converts the merged Phi-3.5-mini LoRA model to GGUF format
# and optionally pushes it to the Ollama registry.
#
# Requirements:
#   - llama.cpp cloned and built (see below)
#   - ollama installed (for push step)
#   - ~14GB free disk space
#
# Usage:
#   bash scripts/convert_to_gguf.sh
#   bash scripts/convert_to_gguf.sh --push       # also push to Ollama
#   bash scripts/convert_to_gguf.sh --llama-cpp /path/to/llama.cpp
#
# llama.cpp setup (one time):
#   git clone https://github.com/ggml-org/llama.cpp
#   cd llama.cpp && pip install -r requirements.txt
# ============================================================

set -euo pipefail

# ---- Configuration -----------------------------------------
MERGED_DIR="${MERGED_DIR:-./checkpoints/communicator_phi3/merged}"
GGUF_OUT="${GGUF_OUT:-./checkpoints/communicator_phi3/pmcommunicator.Q4_K_M.gguf}"
LLAMA_CPP="${LLAMA_CPP:-./llama.cpp}"
OLLAMA_MODEL="${OLLAMA_MODEL:-pmcommunicator}"
OLLAMA_PUSH_TAG="${OLLAMA_PUSH_TAG:-pmcore/pmcommunicator}"
PUSH=0

# ---- Parse args --------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --push) PUSH=1 ;;
        --llama-cpp) LLAMA_CPP="$2"; shift ;;
        --merged-dir) MERGED_DIR="$2"; shift ;;
        --out) GGUF_OUT="$2"; shift ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
    shift
done

# ---- Checks ------------------------------------------------
echo "PMCommunicator → GGUF Converter"
echo "  Source  : $MERGED_DIR"
echo "  Output  : $GGUF_OUT"
echo "  llama.cpp: $LLAMA_CPP"
echo ""

if [ ! -f "$MERGED_DIR/config.json" ]; then
    echo "ERROR: Merged model not found at $MERGED_DIR"
    echo "  Run: python scripts/download_models.py"
    echo "  Or: python training/finetune_communicator_phi3.py (to train)"
    exit 1
fi

if [ ! -f "$LLAMA_CPP/convert_hf_to_gguf.py" ]; then
    echo "ERROR: llama.cpp not found at $LLAMA_CPP"
    echo ""
    echo "To set up llama.cpp:"
    echo "  git clone https://github.com/ggml-org/llama.cpp"
    echo "  cd llama.cpp && pip install -r requirements.txt"
    echo ""
    echo "Then run this script again, or:"
    echo "  bash scripts/convert_to_gguf.sh --llama-cpp /path/to/llama.cpp"
    exit 1
fi

# ---- Step 1: Convert to GGUF (Q4_K_M quantization) --------
echo "Step 1/3: Converting to GGUF (Q4_K_M)..."
mkdir -p "$(dirname "$GGUF_OUT")"

python "$LLAMA_CPP/convert_hf_to_gguf.py" \
    "$MERGED_DIR" \
    --outtype q4_k_m \
    --outfile "$GGUF_OUT"

echo "  ✓ GGUF saved to $GGUF_OUT ($(du -sh "$GGUF_OUT" | cut -f1))"

# ---- Step 2: Write Modelfile --------------------------------
MODELFILE_PATH="$(dirname "$GGUF_OUT")/Modelfile"
echo "Step 2/3: Writing Ollama Modelfile..."

cat > "$MODELFILE_PATH" << 'MODELFILE'
FROM ./pmcommunicator.Q4_K_M.gguf

SYSTEM """You are PMCommunicator, an expert project manager and communications specialist.
Generate professional, stakeholder-ready project communications based on the provided
project context. Be specific — use the actual project name, numbers, and timeline.
Write in clear business English. Output only the communication document itself."""

PARAMETER temperature 0.3
PARAMETER top_p 0.9
PARAMETER top_k 40
PARAMETER repeat_penalty 1.1
PARAMETER num_predict 800
MODELFILE

echo "  ✓ Modelfile written to $MODELFILE_PATH"

# ---- Step 3: Create Ollama model ----------------------------
echo "Step 3/3: Creating Ollama model '$OLLAMA_MODEL'..."

if ! command -v ollama &> /dev/null; then
    echo "  WARNING: ollama not found. Install from https://ollama.com"
    echo "  Then run manually:"
    echo "    ollama create $OLLAMA_MODEL -f $MODELFILE_PATH"
else
    (cd "$(dirname "$GGUF_OUT")" && ollama create "$OLLAMA_MODEL" -f Modelfile)
    echo "  ✓ Ollama model '$OLLAMA_MODEL' created"

    echo ""
    echo "Test it:"
    echo "  ollama run $OLLAMA_MODEL"

    if [ "$PUSH" = "1" ]; then
        echo ""
        echo "Pushing to Ollama registry as '$OLLAMA_PUSH_TAG'..."
        echo "  (Requires: ollama login)"
        ollama push "$OLLAMA_PUSH_TAG"
        echo "  ✓ Pushed to https://ollama.com/pmcore/pmcommunicator"
    else
        echo ""
        echo "To push to Ollama registry:"
        echo "  ollama login"
        echo "  ollama push $OLLAMA_PUSH_TAG"
    fi
fi

echo ""
echo "✓ Done!"
echo ""
echo "Note: PMPlanner and PMReasoner use a custom architecture and cannot be"
echo "converted to GGUF. Use them via the PMCore Docker API (port 8765)."
