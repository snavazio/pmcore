#!/usr/bin/env bash
# ============================================================
# PMCore v3 Retrain — Clean corpus + structured data
# ============================================================
set -euo pipefail
source ~/.pmcore_env

PYTHON="/home/snavazio/.local/bin/uv run python"
LOG_DIR="./retrain_logs_v3"
mkdir -p "$LOG_DIR"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

# ── Step 1: Clean corpus ──────────────────────────────────────
log "Step 1: Cleaning corpus..."
$PYTHON clean_corpus.py 2>&1 | tee "$LOG_DIR/clean.log"

# ── Step 2: Generate structured data ─────────────────────────
log "Step 2: Generating synthetic structured data..."
$PYTHON generate_structured.py 2>&1 | tee "$LOG_DIR/generate.log"

# ── Step 3: Rebuild master corpus ────────────────────────────
log "Step 3: Rebuilding v3 corpus..."
$PYTHON rebuild_corpus_v3.py 2>&1 | tee "$LOG_DIR/rebuild.log"

# Verify corpus
V3_PATH="corpus/master_corpus_v3.jsonl"
if [ ! -f "$V3_PATH" ]; then
    log "ERROR: $V3_PATH not found. Aborting."
    exit 1
fi
LINES=$(wc -l < "$V3_PATH")
SIZE=$(du -h "$V3_PATH" | cut -f1)
log "v3 corpus: $LINES records | $SIZE"

# Update train.py to point at v3 corpus
sed -i 's|corpus/master_corpus\.jsonl|corpus/master_corpus_v3.jsonl|g' pmcore/train.py
log "Updated train.py → corpus/master_corpus_v3.jsonl"

# ── Step 4: Stop API, free GPU ───────────────────────────────
log "Stopping API to free GPU memory..."
pkill -f "uvicorn api:app" 2>/dev/null || true
pkill -f "python3 api.py" 2>/dev/null || true
sleep 5

# ── Step 5: Backup v2 checkpoints ────────────────────────────
if [ -d "./checkpoints" ] && [ ! -d "./checkpoints_v2_backup" ]; then
    log "Backing up v2 checkpoints..."
    cp -r ./checkpoints ./checkpoints_v2_backup
fi

# ── Step 6: Train PMPlanner ───────────────────────────────────
log "========================================"
log "STAGE 1/3: Training PMPlanner..."
log "========================================"
$PYTHON -m pmcore.train --component planner 2>&1 | tee "$LOG_DIR/planner.log"
[ ${PIPESTATUS[0]} -ne 0 ] && { log "ERROR: PMPlanner failed"; exit 1; }
log "PMPlanner done."

# ── Step 7: Train PMReasoner ──────────────────────────────────
log "========================================"
log "STAGE 2/3: Training PMReasoner..."
log "========================================"
$PYTHON -m pmcore.train --component reasoner 2>&1 | tee "$LOG_DIR/reasoner.log"
[ ${PIPESTATUS[0]} -ne 0 ] && { log "ERROR: PMReasoner failed"; exit 1; }
log "PMReasoner done."

# ── Step 8: Train PMCommunicator ─────────────────────────────
log "========================================"
log "STAGE 3/3: Training PMCommunicator..."
log "========================================"
$PYTHON -m pmcore.train --component communicator 2>&1 | tee "$LOG_DIR/communicator.log"
[ ${PIPESTATUS[0]} -ne 0 ] && { log "ERROR: PMCommunicator failed"; exit 1; }
log "PMCommunicator done."

# ── Step 9: Restart API ───────────────────────────────────────
log "Restarting API..."
nohup $PYTHON -m uvicorn api:app --host 0.0.0.0 --port 8765 > api.log 2>&1 &
sleep 10
HTTP=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8765/health || echo "000")
if [ "$HTTP" = "200" ]; then
    log "API health check: OK"
else
    log "WARNING: API returned HTTP $HTTP"
fi

log "========================================"
log "PMCore v3 COMPLETE."
log "  Corpus: $LINES records ($SIZE)"
log "  Models: checkpoints/{planner,reasoner,communicator}/best.pt"
log "  API:    http://100.79.35.85:8765"
log "========================================"
