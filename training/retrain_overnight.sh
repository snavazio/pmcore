#!/usr/bin/env bash
# ============================================================
# PMCore Overnight Retrain
# Waits for harvest to finish, then retrains all 3 components.
# Run with: nohup bash retrain_overnight.sh > retrain_overnight.log 2>&1 &
# ============================================================

set -euo pipefail
source ~/.pmcore_env

PYTHON="/home/snavazio/.local/bin/uv run python"
LOG_DIR="./retrain_logs"
mkdir -p "$LOG_DIR"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

# ── Step 1: Wait for harvest to complete ─────────────────────
log "Waiting for harvest_v4b_jobs.py to finish..."
while true; do
    # Match on the script filename in any python process
    HARVEST_PIDS=$(pgrep -f "harvest_v4b_jobs" || true)
    if [ -z "$HARVEST_PIDS" ]; then
        log "Harvest process no longer running."
        break
    fi
    log "Harvest still running (PIDs: $HARVEST_PIDS) — sleeping 60s..."
    sleep 60
done

# Extra safety: verify the harvest output file has content
HARVEST_OUT="corpus/raw/v4b_harvest_corpus.jsonl"
if [ -f "$HARVEST_OUT" ]; then
    HARVEST_LINES=$(wc -l < "$HARVEST_OUT")
    log "Harvest output: $HARVEST_LINES records in $HARVEST_OUT"
else
    log "WARNING: $HARVEST_OUT not found — harvest may have failed or found 0 results"
fi

# Rebuild master corpus to include harvest results
log "Rebuilding master corpus to include all harvested data..."
$PYTHON - <<'PYEOF'
import json, hashlib
from pathlib import Path
from collections import Counter

sources = [
    "corpus/combined_final.jsonl",
    "corpus/raw/deloitte_premium_corpus.jsonl",
    "corpus/raw/retry_corpus.jsonl",
    "corpus/raw/v4_burn_corpus.jsonl",
    "corpus/raw/v4b_burn_corpus.jsonl",
    "corpus/raw/v4b_harvest_corpus.jsonl",
]

all_records = []
for fname in sources:
    p = Path(fname)
    if p.exists():
        batch = [json.loads(l) for l in p.open() if l.strip()]
        print(f"  {fname}: {len(batch):,}")
        all_records.extend(batch)

seen, merged = set(), []
for r in all_records:
    key = hashlib.md5(r.get("output","")[:300].lower().encode()).hexdigest()
    if key not in seen:
        seen.add(key)
        merged.append(r)

out = Path("corpus/master_corpus.jsonl")
with open(out, "w") as f:
    for r in merged:
        f.write(json.dumps(r) + "\n")

size_mb = out.stat().st_size / 1e6
print(f"\nMASTER CORPUS: {len(merged):,} unique examples | {size_mb:.1f} MB")
src_counts = Counter(r["source"].split("_")[0] for r in merged)
for s, c in src_counts.most_common():
    print(f"  {s:35s}: {c:,}")
PYEOF

# ── Step 1b: Free GPU memory — stop API during training ──────
log "Stopping API to free GPU memory for training..."
pkill -f "uvicorn api:app" 2>/dev/null || true
pkill -f "python3 api.py" 2>/dev/null || true
sleep 5
log "API stopped."

# Enable expandable segments to reduce fragmentation
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

# ── Step 2: Verify master corpus ─────────────────────────────
MASTER="corpus/master_corpus.jsonl"
if [ ! -f "$MASTER" ]; then
    log "ERROR: $MASTER not found. Aborting."
    exit 1
fi

LINES=$(wc -l < "$MASTER")
SIZE=$(du -h "$MASTER" | cut -f1)
log "Master corpus: $LINES examples | $SIZE"

# ── Step 3: Back up existing checkpoints ─────────────────────
BACKUP_DIR="./checkpoints_v1_backup"
if [ -d "./checkpoints" ] && [ ! -d "$BACKUP_DIR" ]; then
    log "Backing up existing checkpoints to $BACKUP_DIR..."
    cp -r ./checkpoints "$BACKUP_DIR"
    log "Backup complete."
fi

# ── Step 4: Train PMPlanner ───────────────────────────────────
log "========================================"
log "STAGE 1/3: Training PMPlanner..."
log "========================================"
$PYTHON -m pmcore.train --component planner 2>&1 | tee "$LOG_DIR/planner.log"
PLANNER_EXIT=${PIPESTATUS[0]}
if [ $PLANNER_EXIT -ne 0 ]; then
    log "ERROR: PMPlanner training failed (exit $PLANNER_EXIT). Aborting."
    exit 1
fi
log "PMPlanner done. Checkpoint: checkpoints/planner/best.pt"

# ── Step 5: Train PMReasoner ──────────────────────────────────
log "========================================"
log "STAGE 2/3: Training PMReasoner..."
log "========================================"
$PYTHON -m pmcore.train --component reasoner 2>&1 | tee "$LOG_DIR/reasoner.log"
REASONER_EXIT=${PIPESTATUS[0]}
if [ $REASONER_EXIT -ne 0 ]; then
    log "ERROR: PMReasoner training failed (exit $REASONER_EXIT). Aborting."
    exit 1
fi
log "PMReasoner done. Checkpoint: checkpoints/reasoner/best.pt"

# ── Step 6: Train PMCommunicator ─────────────────────────────
log "========================================"
log "STAGE 3/3: Training PMCommunicator..."
log "========================================"
$PYTHON -m pmcore.train --component communicator 2>&1 | tee "$LOG_DIR/communicator.log"
COMM_EXIT=${PIPESTATUS[0]}
if [ $COMM_EXIT -ne 0 ]; then
    log "ERROR: PMCommunicator training failed (exit $COMM_EXIT). Aborting."
    exit 1
fi
log "PMCommunicator done. Checkpoint: checkpoints/communicator/best.pt"

# ── Step 7: Restart API with new weights ─────────────────────
log "========================================"
log "Restarting API on port 8765..."
log "========================================"
pkill -f "uvicorn api:app" 2>/dev/null || true
sleep 3
nohup $PYTHON -m uvicorn api:app --host 0.0.0.0 --port 8765 > api.log 2>&1 &
API_PID=$!
log "API restarted. PID: $API_PID"
sleep 8

# Health check
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8765/health || echo "000")
if [ "$HTTP_STATUS" = "200" ]; then
    log "API health check: OK (HTTP 200)"
else
    log "WARNING: API health check returned HTTP $HTTP_STATUS — check api.log"
fi

# ── Done ─────────────────────────────────────────────────────
log "========================================"
log "ALL DONE. PMCore v2 fully retrained."
log "  Corpus:  $LINES examples ($SIZE)"
log "  Models:  checkpoints/{planner,reasoner,communicator}/best.pt"
log "  API:     http://100.79.35.85:8765/health"
log "========================================"
