#!/usr/bin/env bash
# PMCore v6 — Retrain 672M PMCommunicator only
set -euo pipefail

PYTHON="/home/snavazio/.local/bin/uv run python"
LOG_DIR="./retrain_logs_v6"
mkdir -p "$LOG_DIR"
cd /home/snavazio/pmcore

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

LINES=$(wc -l < corpus/communicator_clean_corpus.jsonl)
SIZE=$(du -h corpus/communicator_clean_corpus.jsonl | cut -f1)
log "Corpus: $LINES records | $SIZE"
log "Model: PMCommunicator 672M params"

log "Stopping API to free GPU memory..."
pkill -f "uvicorn api:app" 2>/dev/null || true
pkill -f "uv run python -m uvicorn" 2>/dev/null || true
sleep 5

# Ensure old checkpoints are gone (fresh start)
rm -f ./checkpoints/communicator/best.pt ./checkpoints/communicator/latest.pt
log "Old checkpoints cleared. Starting fresh training..."

log "======================================="
log "Training PMCommunicator 672M..."
log "======================================="
$PYTHON -m pmcore.train --component communicator 2>&1 | tee "$LOG_DIR/communicator.log"
[ ${PIPESTATUS[0]} -ne 0 ] && { log "ERROR: PMCommunicator training failed"; exit 1; }
log "PMCommunicator DONE."

log "Restarting API..."
nohup $PYTHON -m uvicorn api:app --host 0.0.0.0 --port 8765 > api.log 2>&1 &
sleep 15
HTTP=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8765/health || echo "000")
if [ "$HTTP" = "200" ]; then
    log "API health check: OK"
else
    log "WARNING: API returned HTTP $HTTP"
fi

log "======================================="
log "PMCore v6 PMCommunicator COMPLETE."
log "  Corpus: $LINES records ($SIZE)"
log "  Model:  checkpoints/communicator/best.pt (672M)"
log "  API:    http://100.79.35.85:8765"
log "======================================="
