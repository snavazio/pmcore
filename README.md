# PMCore

A three-stage AI pipeline for intelligent project management. PMCore chains three purpose-built transformer models to take a raw PM request from structured planning through risk analysis to polished stakeholder communication — or lets you use each model independently.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         PMCore Pipeline                             │
└─────────────────────────────────────────────────────────────────────┘

  User Request (natural language)
        │
        ▼
┌───────────────────┐
│    PMPlanner      │  171.8M params · from-scratch Llama-style transformer
│                   │  Input:  natural-language project description
│  POST /plan       │  Output: structured JSON task graph
│  POST /plan/quick │          phases, tasks, methodology, timeline, budget
└────────┬──────────┘
         │  JSON task graph
         ▼
┌───────────────────┐
│   PMReasoner      │  125.3M params · from-scratch Llama-style transformer
│                   │  Input:  task graph JSON
│  POST /plan       │  Output: risk analysis JSON
│  POST /plan/quick │          critical path, EVM metrics, health (GREEN/YELLOW/RED)
└────────┬──────────┘
         │  Risk analysis JSON
         ▼
┌───────────────────┐
│  PMCommunicator   │  Phi-3.5-mini 3.8B · LoRA fine-tuned (MIT license)
│                   │  Input:  project context + communication request
│  POST /plan       │  Output: stakeholder-facing prose
│  POST /communicate│          status reports, kickoff emails, board updates, etc.
└────────┬──────────┘
         │
         ▼
  Stakeholder Output (prose)
```

All three models are kept separate and can be used or fine-tuned independently.

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

Or with `uv`:

```bash
uv sync
```

### 2. Download model checkpoints

Model weights are published separately on HuggingFace (too large for GitHub). Download them with:

```bash
python scripts/download_models.py
```

Or download individual models:

```bash
python scripts/download_models.py --models planner reasoner
```

### 3. Start the API

```bash
uvicorn api:app --host 0.0.0.0 --port 8765
```

Health check: `http://localhost:8765/health`

---

## Example Requests

### Full pipeline — plan + analyze + communicate in one call

```bash
curl -X POST http://localhost:8765/plan \
  -H "Content-Type: application/json" \
  -d '{
    "request": "Renovate the hotel lobby — new flooring, lighting, and front desk. Budget $2M, 12 weeks.",
    "comm_request": "Write a project kickoff summary for stakeholders."
  }'
```

### Planning + risk only (no prose generation — faster)

```bash
curl -X POST http://localhost:8765/plan/quick \
  -H "Content-Type: application/json" \
  -d '{
    "request": "Migrate our data warehouse to Snowflake over 12 weeks with a team of 4 engineers."
  }'
```

### Generate communication from an existing plan

```bash
curl -X POST http://localhost:8765/communicate \
  -H "Content-Type: application/json" \
  -d '{
    "project_request": "Hotel lobby renovation, $2M, 12 weeks.",
    "request": "Write a weekly status report for the project sponsor."
  }'
```

### Health check

```bash
curl http://localhost:8765/health
```

---

## API Reference

Base URL: `http://localhost:8765`

---

### `POST /plan`

Full PMCore pipeline: PMPlanner → PMReasoner → PMCommunicator.

**Request body**

```json
{
  "request":      "string  (required) — natural-language project description",
  "comm_request": "string  (optional) — communication task, e.g. 'Write a kickoff email'",
  "max_tokens":   512,
  "temperature":  0.7,
  "verbose":      false
}
```

**Response**

```json
{
  "request": "string",
  "planner": {
    "tasks":         {},
    "num_tasks":     12,
    "methodology":   "Agile | Waterfall | Hybrid",
    "duration_days": 84,
    "raw_output":    "string"
  },
  "reasoner": {
    "risk_analysis":  {},
    "overall_health": "GREEN | YELLOW | RED",
    "top_risks":      ["string"],
    "critical_path":  ["string"],
    "raw_output":     "string"
  },
  "communicator": {
    "communication": "string — stakeholder prose",
    "comm_type":     "string — detected communication type"
  },
  "latency_ms": { "planner_ms": 0, "reasoner_ms": 0, "communicator_ms": 0 },
  "total_ms":   0
}
```

---

### `POST /plan/quick`

PMPlanner + PMReasoner only — no prose generation. Faster; returns structured JSON.

**Request body**

```json
{
  "request": "string (required)"
}
```

**Response** — same as `/plan` but without the `communicator` field.

---

### `POST /communicate`

Run PMCommunicator only. Supports two calling conventions:

**Convention 1 — full pipeline context (simple)**

```json
{
  "project_request": "Hotel lobby renovation, $2M, 12 weeks.",
  "request":         "Write a weekly status report for the project sponsor."
}
```

**Convention 2 — pre-computed context**

```json
{
  "request":      "string — project description",
  "comm_request": "string — communication task",
  "context": {
    "task_graph":     {},
    "risk_analysis":  {},
    "methodology":    "string",
    "duration_days":  84,
    "overall_health": "GREEN",
    "top_risks":      ["string"],
    "critical_path":  ["string"]
  }
}
```

**Response**

```json
{
  "communication": "string — stakeholder prose",
  "comm_type":     "string"
}
```

---

### `GET /health`

```json
{
  "status":        "healthy",
  "uptime_s":      3600,
  "models_loaded": true,
  "gpu": {
    "name":       "NVIDIA GeForce RTX 5090",
    "vram_total": "24.0GB",
    "vram_used":  "6.2GB",
    "vram_free":  "17.8GB"
  },
  "version": "PMCore v1.0"
}
```

---

### `GET /models`

Returns parameter counts and architecture details for all loaded models.

---

## Model Cards

### PMPlanner

| Property | Value |
|---|---|
| Parameters | 171.8M |
| Architecture | From-scratch Llama-style (GQA, SwiGLU, RoPE) |
| Vocab | LLaMA tokenizer, 32,006 tokens |
| Task | Natural-language PM request → structured JSON task graph |
| Training corpus | 28K+ synthetic PM scenarios |
| HuggingFace | `pmcore/pmplanner` |

PMPlanner is a decoder-only transformer trained from scratch on synthetic project management scenarios. Given a natural-language project request, it outputs a fully structured JSON task graph: phases with dependencies, individual tasks with durations and owners, recommended methodology (Agile, Waterfall, Hybrid), timeline estimates, and budget breakdowns.

---

### PMReasoner

| Property | Value |
|---|---|
| Parameters | 125.3M |
| Architecture | From-scratch Llama-style (GQA, SwiGLU, RoPE) |
| Vocab | LLaMA tokenizer, 32,006 tokens |
| Task | Task graph JSON → risk analysis JSON |
| Output | Critical path, EVM metrics (SPI/CPI/EAC), risk items, overall health |
| Training corpus | 28K+ synthetic PM scenarios |
| HuggingFace | `pmcore/pmreasoner` |

PMReasoner specializes in project risk reasoning. It ingests a task graph and outputs structured risk analysis: critical path, earned value management (EVM) metrics, individual risks with severity and mitigation, and a GREEN/YELLOW/RED health classification.

---

### PMCommunicator

| Property | Value |
|---|---|
| Base model | Phi-3.5-mini-instruct (Microsoft, MIT license) |
| Parameters | 3.8B |
| Fine-tuning | LoRA (PEFT), rank 16 |
| Task | Structured project context → stakeholder prose |
| Output formats | Status reports, kickoff emails, risk escalations, board updates, executive summaries, closeout reports, and more |
| Training corpus | 28K curated PM communications |
| HuggingFace | `pmcore/pmcommunicator` |

PMCommunicator is a LoRA-fine-tuned Phi-3.5-mini that turns structured planning and risk data into polished stakeholder communication. It supports 13+ communication types and calibrates tone and detail level accordingly.

---

## Training

Each model can be retrained independently using `pmcore/train.py`.

### Retrain PMPlanner

```bash
python -m pmcore.train --component planner
```

### Retrain PMReasoner

```bash
python -m pmcore.train --component reasoner
```

### Retrain PMCommunicator (LoRA fine-tuning on Phi-3.5)

```bash
python finetune_communicator_phi3.py
```

Training corpora live in `corpus/`. Checkpoints are saved to `checkpoints/` and excluded from version control — weights are published separately on HuggingFace.

---

## HuggingFace

Model weights are published separately on HuggingFace. Each model has its own repo.

| Model | HuggingFace |
|---|---|
| PMPlanner | [pmcore/pmplanner](https://huggingface.co/pmcore/pmplanner) |
| PMReasoner | [pmcore/pmreasoner](https://huggingface.co/pmcore/pmreasoner) |
| PMCommunicator | [pmcore/pmcommunicator](https://huggingface.co/pmcore/pmcommunicator) |

---

## License

MIT — see [LICENSE](LICENSE).

PMCommunicator is built on [Phi-3.5-mini-instruct](https://huggingface.co/microsoft/Phi-3.5-mini-instruct) by Microsoft, also MIT licensed.
