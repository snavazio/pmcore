#!/usr/bin/env bash
# PMCore v5 Quick Retrain — corpus already rebuilt with fixed synthetic data
set -euo pipefail

PYTHON="/home/snavazio/.local/bin/uv run python"
LOG_DIR="./retrain_logs_v5"
mkdir -p "$LOG_DIR"
cd /home/snavazio/pmcore

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

LINES=$(wc -l < corpus/master_corpus_v4.jsonl)
SIZE=$(du -h corpus/master_corpus_v4.jsonl | cut -f1)
log "Corpus: $LINES records | $SIZE"

log "Stopping API to free GPU memory..."
pkill -f "uvicorn api:app" 2>/dev/null || true
pkill -f "uv run python -m uvicorn" 2>/dev/null || true
pkill -f "python3 api.py" 2>/dev/null || true
sleep 8

# Backup current (v4) checkpoints
if [ -d "./checkpoints" ]; then
    log "Backing up current checkpoints to checkpoints_v4_backup..."
    rm -rf ./checkpoints_v4_backup
    cp -r ./checkpoints ./checkpoints_v4_backup
fi

log "======================================="
log "STAGE 1/3: Training PMPlanner..."
log "======================================="
$PYTHON -m pmcore.train --component planner 2>&1 | tee "$LOG_DIR/planner.log"
[ ${PIPESTATUS[0]} -ne 0 ] && { log "ERROR: PMPlanner training failed"; exit 1; }
log "PMPlanner DONE."

log "======================================="
log "STAGE 2/3: Training PMReasoner..."
log "======================================="
$PYTHON -m pmcore.train --component reasoner 2>&1 | tee "$LOG_DIR/reasoner.log"
[ ${PIPESTATUS[0]} -ne 0 ] && { log "ERROR: PMReasoner training failed"; exit 1; }
log "PMReasoner DONE."

log "======================================="
log "STAGE 3/3: Training PMCommunicator..."
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
log "PMCore v5 COMPLETE."
log "  Corpus: $LINES records ($SIZE)"
log "  Models: checkpoints/{planner,reasoner,communicator}/best.pt"
log "  API:    http://100.79.35.85:8765"
log "======================================="
