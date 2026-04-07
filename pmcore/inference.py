"""
PMCore Inference Engine
=======================
Chains PMPlanner → PMReasoner → PMCommunicator into a single pipeline.

JSON Output Strategy:
  1. JSON prefix injection — prompt ends with opening JSON so the model
     is forced to complete a structure, not prose.
  2. JSON repair — closes truncated braces, fixes trailing commas, etc.
  3. Entity extraction fallback — regex pulls values from hallucinated
     prose and builds a valid JSON structure.

Usage:
    from pmcore.inference import PMCorePipeline
    pipeline = PMCorePipeline()
    result = pipeline.run("Plan a hotel renovation with a 12-week deadline.")
    print(result)
"""

import os
import json
import time
import re
from pmcore.math_validator import validate as math_validate, MathAudit
import torch
import torch.nn.functional as F
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from transformers import AutoTokenizer

from pmcore.model import (
    PMCoreModel,
    build_pmplanner,
    build_pmreasoner,
    build_pmcommunicator,
    ModelConfig,
)

# ── Paths ─────────────────────────────────────────────────────────────────────

CHECKPOINT_DIR = Path("./checkpoints")
TOKENIZER_PATH = "/home/snavazio/autoresearch-v2/pm-model"
TOKENIZER_HF   = "hf-internal-testing/llama-tokenizer"

SPECIAL_TOKENS = [
    "<|pm_request|>",
    "<|response|>",
    "<|task_graph|>",
    "<|analysis|>",
    "<|communication|>",
    "<|project_context|>",
    "<|end|>",
]

# ── Generation Config ─────────────────────────────────────────────────────────

@dataclass
class GenerationConfig:
    max_new_tokens:     int   = 512
    min_new_tokens:     int   = 32    # Prevents early { } collapse
    temperature:        float = 0.7
    top_p:              float = 0.9
    top_k:              int   = 50
    repetition_penalty: float = 1.1
    do_sample:          bool  = True


# ── Token Generation ──────────────────────────────────────────────────────────

def generate(
    model: PMCoreModel,
    input_ids: torch.Tensor,
    tokenizer,
    config: GenerationConfig,
    stop_token_id: Optional[int] = None,
) -> str:
    """Autoregressive token generation with sampling."""
    model.eval()
    device = next(model.parameters()).device

    generated  = input_ids.clone().to(device)
    past_kvs   = None
    new_tokens = []
    token_counts = {}

    with torch.no_grad():
        for step in range(config.max_new_tokens):
            if step == 0:
                logits, past_kvs = model(generated)
            else:
                last_token = generated[:, -1:]
                logits, past_kvs = model(last_token, past_kvs=past_kvs)

            next_logits = logits[:, -1, :]

            # Repetition penalty
            if config.repetition_penalty != 1.0:
                for tid, count in token_counts.items():
                    penalty = config.repetition_penalty ** count
                    if next_logits[0, tid] > 0:
                        next_logits[0, tid] /= penalty
                    else:
                        next_logits[0, tid] *= penalty

            # Temperature + sampling
            if config.temperature > 0 and config.do_sample:
                next_logits = next_logits / config.temperature

                if config.top_k > 0:
                    topk_vals, _ = torch.topk(next_logits, config.top_k)
                    min_val = topk_vals[:, -1].unsqueeze(-1)
                    next_logits = next_logits.masked_fill(next_logits < min_val, float('-inf'))

                if config.top_p < 1.0:
                    sorted_logits, sorted_idx = torch.sort(next_logits, descending=True)
                    cum_probs = torch.cumsum(F.softmax(sorted_logits, dim=-1), dim=-1)
                    remove_mask = cum_probs - F.softmax(sorted_logits, dim=-1) > config.top_p
                    sorted_logits[remove_mask] = float('-inf')
                    next_logits = torch.zeros_like(next_logits).scatter_(1, sorted_idx, sorted_logits)

                probs = F.softmax(next_logits, dim=-1)
                next_token = torch.multinomial(probs, num_samples=1)
            else:
                next_token = next_logits.argmax(dim=-1, keepdim=True)

            tid = next_token.item()
            token_counts[tid] = token_counts.get(tid, 0) + 1

            generated = torch.cat([generated, next_token], dim=1)
            new_tokens.append(tid)

            # Enforce minimum output before stopping
            if len(new_tokens) < config.min_new_tokens:
                continue

            if stop_token_id and tid == stop_token_id:
                break
            if tokenizer.eos_token_id and tid == tokenizer.eos_token_id:
                break

    return tokenizer.decode(new_tokens, skip_special_tokens=False)


# ── Model Loader ──────────────────────────────────────────────────────────────

class ModelLoader:
    """Loads and caches PMCore models."""

    def __init__(self, device: str = "cuda"):
        self.device = torch.device(device if torch.cuda.is_available() else "cpu")
        self.dtype  = torch.bfloat16
        self._models = {}
        self._tokenizer = None

    def get_tokenizer(self):
        if self._tokenizer is None:
            for src in [TOKENIZER_PATH, TOKENIZER_HF]:
                try:
                    tok = AutoTokenizer.from_pretrained(src)
                    tok.add_special_tokens({"additional_special_tokens": SPECIAL_TOKENS})
                    if tok.pad_token is None:
                        tok.pad_token = tok.eos_token
                    self._tokenizer = tok
                    print(f"  Tokenizer: {src}")
                    break
                except Exception:
                    continue
        return self._tokenizer

    def load_model(self, component: str) -> PMCoreModel:
        if component in self._models:
            return self._models[component]

        builders = {
            "planner":      build_pmplanner,
            "reasoner":     build_pmreasoner,
            "communicator": build_pmcommunicator,
        }

        ckpt_path = CHECKPOINT_DIR / component / "best.pt"
        if not ckpt_path.exists():
            raise FileNotFoundError(f"Checkpoint not found: {ckpt_path}")

        print(f"  Loading {component} from {ckpt_path}...")
        t0 = time.time()

        tok  = self.get_tokenizer()
        ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)

        # Use config stored in checkpoint when available (handles models trained
        # with different dimensions than the factory default)
        if "config" in ckpt and ckpt["config"] is not None:
            model = PMCoreModel(ckpt["config"])
        else:
            model = builders[component]()

        # Always match vocab to checkpoint — single source of truth
        import torch.nn as nn
        ckpt_vocab = ckpt["model"]["embed.weight"].shape[0]
        if ckpt_vocab != model.config.vocab_size:
            model.embed   = nn.Embedding(ckpt_vocab, model.config.hidden_size)
            model.lm_head = nn.Linear(model.config.hidden_size, ckpt_vocab, bias=False)
            model.config.vocab_size = ckpt_vocab
            if model.config.tie_embeddings:
                model.lm_head.weight = model.embed.weight

        model.load_state_dict(ckpt["model"])
        model = model.to(self.device, dtype=self.dtype)
        model.eval()

        elapsed = time.time() - t0
        print(f"  {component} loaded in {elapsed:.1f}s ({model.count_params()/1e6:.1f}M params)")

        self._models[component] = model
        return model

    def load_all(self):
        self.get_tokenizer()
        for comp in ["planner", "reasoner", "communicator"]:
            self.load_model(comp)
        return self


# ── Result Types ──────────────────────────────────────────────────────────────

@dataclass
class PlannerResult:
    raw_output:    str
    task_graph:    Optional[dict]
    num_tasks:     int
    methodology:   str
    duration_days: int

@dataclass
class ReasonerResult:
    raw_output:     str
    risk_analysis:  Optional[dict]
    overall_health: str
    top_risks:      list
    critical_path:  list

@dataclass
class CommunicatorResult:
    raw_output:    str
    communication: str
    comm_type:     str

@dataclass
class PMCoreResult:
    request:      str
    planner:      PlannerResult
    reasoner:     ReasonerResult
    communicator: CommunicatorResult
    math_audit:   Optional[MathAudit]
    latency_ms:   dict
    total_ms:     float


# ── JSON Recovery Stack ───────────────────────────────────────────────────────

def _close_json(text: str) -> str:
    """
    Attempt to close an incomplete JSON string by counting open
    brackets/braces and appending the correct closers.
    """
    stack = []
    in_str = False
    escape = False
    for ch in text:
        if escape:
            escape = False
            continue
        if ch == '\\' and in_str:
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch in '{[':
            stack.append('}' if ch == '{' else ']')
        elif ch in '}]':
            if stack and stack[-1] == ch:
                stack.pop()

    # Remove trailing comma before closing
    stripped = text.rstrip()
    if stripped.endswith(','):
        stripped = stripped[:-1]

    return stripped + ''.join(reversed(stack))


def repair_json(text: str) -> Optional[dict]:
    """
    Multi-strategy JSON recovery:
      1. Direct parse
      2. Extract largest JSON block and direct parse
      3. Close truncated JSON and parse
      4. json_repair library (if installed)
    Returns parsed dict/list, or None if all strategies fail.
    """
    # Strategy 1: direct parse
    try:
        return json.loads(text)
    except Exception:
        pass

    # Strategy 2: find the largest {...} or [...] block
    for pattern in [r'\{[\s\S]*\}', r'\[[\s\S]*\]']:
        matches = re.findall(pattern, text)
        for m in sorted(matches, key=len, reverse=True):
            try:
                return json.loads(m)
            except Exception:
                pass
            # Strategy 3: close truncated block
            try:
                closed = _close_json(m)
                return json.loads(closed)
            except Exception:
                pass

    # Strategy 4: json_repair (pip install json-repair)
    try:
        import json_repair
        result = json_repair.repair(text)
        if isinstance(result, (dict, list)):
            return result
        parsed = json.loads(result)
        return parsed
    except Exception:
        pass

    return None


def normalise_duration_in_request(text: str) -> str:
    """
    Rewrite week/month mentions to explicit working-day counts before
    the request is sent to the planner model.

    Examples:
      "8 week deadline"  -> "8-week (40 working days) deadline"
      "3-month project"  -> "3-month (60 working days) project"
    """
    def replace_weeks(m):
        n = int(m.group(1))
        wd = n * 5
        sep = m.group(2)  # the separator between number and "week"
        return f"{n}{sep}week ({wd} working days)"

    def replace_months(m):
        n = int(m.group(1))
        wd = n * 20
        sep = m.group(2)
        return f"{n}{sep}month ({wd} working days)"

    text = re.sub(r'(\d+)([\s\-]*)week', replace_weeks, text, flags=re.IGNORECASE)
    text = re.sub(r'(\d+)([\s\-]*)month', replace_months, text, flags=re.IGNORECASE)
    return text


def extract_entities_from_text(text: str) -> dict:
    """
    Last-resort extraction: pull structured values from hallucinated prose
    using regex and keyword heuristics.
    """
    entities = {
        "duration_days": 0,
        "budget": None,
        "methodology": "Hybrid",
        "tasks": [],
        "risks": [],
        "phases": [],
    }

    # Duration
    dur_match = re.search(
        r'(\d+)\s*(?:-\s*\d+\s*)?(?:week|wk|day|month)',
        text, re.IGNORECASE
    )
    if dur_match:
        val = int(dur_match.group(1))
        unit = dur_match.group(0).lower()
        if 'week' in unit or 'wk' in unit:
            entities["duration_days"] = val * 5   # 5 working days per week
        elif 'month' in unit:
            entities["duration_days"] = val * 20  # ~20 working days per month
        else:
            entities["duration_days"] = val

    # Budget
    bud_match = re.search(
        r'\$\s*([\d,]+(?:\.\d+)?)\s*([MBKk])?',
        text
    )
    if bud_match:
        raw = float(bud_match.group(1).replace(',', ''))
        mult = {'M': 1_000_000, 'B': 1_000_000_000, 'K': 1_000, 'k': 1_000}.get(
            bud_match.group(2) or '', 1
        )
        entities["budget"] = int(raw * mult)

    # Methodology
    for meth in ["Agile", "Scrum", "Waterfall", "PRINCE2", "Kanban", "Hybrid", "PMP"]:
        if meth.lower() in text.lower():
            entities["methodology"] = meth
            break

    # Task-like sentences (numbered lists, bullets)
    task_lines = re.findall(
        r'(?:^\d+\.\s+|^[-•]\s+|(?:phase|task|step)\s+\d+[:.]?\s+)(.+)',
        text, re.MULTILINE | re.IGNORECASE
    )
    entities["tasks"] = [t.strip()[:80] for t in task_lines[:12]]

    # Risk keywords
    risk_kws = [
        "schedule", "budget", "scope", "resource", "technical", "vendor",
        "regulatory", "weather", "supply chain", "stakeholder", "quality",
    ]
    found_risks = [kw for kw in risk_kws if kw in text.lower()]
    entities["risks"] = found_risks[:5]

    return entities


def build_planner_json(request: str, entities: dict, raw_text: str) -> dict:
    """
    Build a minimal valid PMPlanner JSON from extracted entities
    when the model fails to output structured JSON.
    """
    # Derive project name from request
    name_match = re.search(r'(?:plan|design|manage|build|develop|deliver)\s+(?:a\s+|an\s+)?(.{5,60}?)(?:\.|,|with|for|\n|$)', request, re.IGNORECASE)
    proj_name = name_match.group(1).strip().title() if name_match else "Project"

    tasks = []
    if entities["tasks"]:
        for i, t in enumerate(entities["tasks"], 1):
            tasks.append({
                "id": f"T{i:02d}",
                "name": t,
                "duration_days": max(3, entities["duration_days"] // max(len(entities["tasks"]), 1)),
                "dependencies": [f"T{i-1:02d}"] if i > 1 else [],
                "owner": "Project Team",
                "phase": "Execution",
                "status": "not_started",
            })
    else:
        # Minimal generic breakdown
        generic_phases = [
            ("Initiation & Planning", 14),
            ("Design & Procurement", 21),
            ("Execution", max(14, entities["duration_days"] - 42)),
            ("Testing & Handover", 7),
        ]
        for i, (name, dur) in enumerate(generic_phases, 1):
            tasks.append({
                "id": f"T{i:02d}",
                "name": name,
                "duration_days": dur,
                "dependencies": [f"T{i-1:02d}"] if i > 1 else [],
                "owner": "Project Manager",
                "phase": name.split("&")[0].strip(),
                "status": "not_started",
            })

    return {
        "project": {
            "name": proj_name,
            "description": request[:200],
            "methodology": entities["methodology"],
            "estimated_duration_days": entities["duration_days"] or sum(t["duration_days"] for t in tasks),
            "budget_usd": entities["budget"],
            "status": "planning",
        },
        "tasks": tasks,
        "_fallback": True,
        "_note": "Structured fallback — model output was unstructured prose.",
    }


def build_reasoner_json(request: str, entities: dict, planner: "PlannerResult") -> dict:
    """
    Build a minimal valid PMReasoner JSON from extracted entities.
    """
    task_names = []
    if planner.task_graph and "tasks" in planner.task_graph:
        task_names = [t.get("name", "") for t in planner.task_graph["tasks"][:6]]

    risk_map = {
        "schedule": ("Schedule Delay", "medium", "Add buffer and monitor velocity weekly"),
        "budget":   ("Budget Overrun", "high", "Implement EVM and review costs bi-weekly"),
        "scope":    ("Scope Creep", "medium", "Enforce change control board approval"),
        "resource": ("Resource Availability", "medium", "Identify backups and cross-train"),
        "vendor":   ("Vendor/Supply Chain Risk", "medium", "Qualify alternate suppliers"),
        "regulatory": ("Regulatory/Permit Risk", "high", "Engage authorities in phase 1"),
        "technical": ("Technical Complexity", "medium", "Prototype critical components early"),
        "stakeholder": ("Stakeholder Alignment", "low", "Weekly status reports and sign-offs"),
        "quality": ("Quality Defects", "medium", "Define QA checkpoints at each phase gate"),
    }

    risks = []
    for kw in entities["risks"]:
        if kw in risk_map:
            rtype, severity, mitigation = risk_map[kw]
            risks.append({
                "type": rtype,
                "severity": severity,
                "probability": "medium",
                "mitigation": mitigation,
            })

    if not risks:
        risks = [
            {"type": "Schedule Delay", "severity": "medium", "probability": "medium",
             "mitigation": "Build 15% buffer and track weekly velocity"},
            {"type": "Budget Overrun", "severity": "medium", "probability": "low",
             "mitigation": "Baseline costs and review at each phase gate"},
        ]

    high_risks = [r for r in risks if r["severity"] == "high"]
    health = "red" if len(high_risks) >= 2 else ("yellow" if risks else "green")

    critical_tasks = task_names[:4] if task_names else ["Planning", "Procurement", "Execution", "Testing"]

    return {
        "overall_health": health,
        "risks": risks,
        "critical_path": {
            "tasks": critical_tasks,
            "total_duration_days": planner.duration_days or 0,
            "float_days": max(0, (planner.duration_days or 30) // 10),
        },
        "constraints": [
            f"Deadline: {planner.duration_days} days" if planner.duration_days else "Timeline TBD",
            f"Budget: ${entities['budget']:,}" if entities.get("budget") else "Budget TBD",
        ],
        "recommendations": [
            "Establish PMO governance structure before kickoff",
            "Lock scope with signed charter before procurement",
            "Weekly steering committee reviews during execution",
        ],
        "_fallback": True,
        "_note": "Structured fallback — model output was unstructured prose.",
    }


# ── Output Cleaners & Parsers ─────────────────────────────────────────────────

def clean_output(text: str) -> str:
    """Remove special tokens from generated text."""
    for token in SPECIAL_TOKENS:
        text = text.replace(token, "")
    return text.strip()


def parse_planner_output(raw: str, request: str = "") -> "PlannerResult":
    cleaned = clean_output(raw)
    graph   = repair_json(cleaned)

    if not graph or not isinstance(graph, dict):
        # Full fallback
        entities = extract_entities_from_text(request + " " + cleaned)
        graph = build_planner_json(request, entities, cleaned)

    num_tasks     = len(graph.get("tasks", []))
    methodology   = graph.get("project", {}).get("methodology", "Hybrid")
    duration_days = graph.get("project", {}).get("estimated_duration_days", 0)

    # Patch missing duration from task sum
    if not duration_days and graph.get("tasks"):
        duration_days = sum(t.get("duration_days", 0) for t in graph["tasks"])
        graph["project"]["estimated_duration_days"] = duration_days

    # Extract the stated deadline from the original request (working days)
    # and enforce it: if task durations overrun, scale them down to fit.
    if request:
        stated = extract_entities_from_text(request).get("duration_days", 0)
        if stated:
            # Always lock the project-level duration to the stated deadline
            if not duration_days or duration_days != stated:
                duration_days = stated
                graph.setdefault("project", {})["estimated_duration_days"] = stated

            # Clamp individual task durations if they sum over the deadline
            tasks = graph.get("tasks", [])
            task_sum = sum(t.get("duration_days", 0) for t in tasks)
            if tasks and task_sum > stated:
                scale = stated / task_sum
                running = 0
                for i, t in enumerate(tasks):
                    if i < len(tasks) - 1:
                        clamped = max(1, round(t.get("duration_days", 1) * scale))
                        t["duration_days"] = clamped
                        running += clamped
                    else:
                        t["duration_days"] = max(1, stated - running)

    return PlannerResult(
        raw_output=cleaned,
        task_graph=graph,
        num_tasks=num_tasks,
        methodology=methodology,
        duration_days=duration_days,
    )


def parse_reasoner_output(raw: str, request: str = "", planner: Optional["PlannerResult"] = None) -> "ReasonerResult":
    cleaned  = clean_output(raw)
    analysis = repair_json(cleaned)

    if not analysis or not isinstance(analysis, dict):
        entities = extract_entities_from_text(request + " " + cleaned)
        from pmcore.inference import PlannerResult as _PR
        dummy_planner = planner or PlannerResult(
            raw_output="", task_graph=None, num_tasks=0,
            methodology="Hybrid", duration_days=0
        )
        analysis = build_reasoner_json(request, entities, dummy_planner)

    top_risks     = []
    critical_path = []
    health        = analysis.get("overall_health", "yellow")

    risks_list = analysis.get("risks", [])
    if isinstance(risks_list, list):
        top_risks = [r.get("type", "") for r in risks_list[:3] if isinstance(r, dict)]

    cp_data = analysis.get("critical_path", {})
    if isinstance(cp_data, dict):
        critical_path = cp_data.get("tasks", [])
    elif isinstance(cp_data, list):
        critical_path = cp_data

    return ReasonerResult(
        raw_output=cleaned,
        risk_analysis=analysis,
        overall_health=health,
        top_risks=top_risks,
        critical_path=critical_path,
    )


def parse_communicator_output(raw: str) -> "CommunicatorResult":
    cleaned = clean_output(raw)

    comm_type = "project_update"
    lower = cleaned.lower()
    if "subject:" in lower or "dear " in lower:
        comm_type = "email"
    elif "## weekly" in lower or "status report" in lower:
        comm_type = "status_report"
    elif "executive summary" in lower:
        comm_type = "executive_summary"
    elif "risk" in lower and "escalat" in lower:
        comm_type = "risk_escalation"

    return CommunicatorResult(
        raw_output=cleaned,
        communication=cleaned,
        comm_type=comm_type,
    )


# ── The Pipeline ──────────────────────────────────────────────────────────────

class PMCorePipeline:
    """
    End-to-end PMCore inference pipeline.
    PMPlanner → PMReasoner → PMCommunicator
    """

    def __init__(self, device: str = "cuda", preload: bool = True):
        print("Initializing PMCore Pipeline...")
        self.loader = ModelLoader(device)
        self.gen_config = GenerationConfig()
        if preload:
            self.loader.load_all()
        print("PMCore ready.\n")

    def _encode(self, text: str) -> torch.Tensor:
        tok = self.loader.get_tokenizer()
        return tok.encode(text, return_tensors="pt")

    def _run_planner(self, request: str) -> tuple[str, PlannerResult]:
        """Stage 1: Generate structured task graph from PM request."""
        tok   = self.loader.get_tokenizer()
        model = self.loader.load_model("planner")

        # Match exactly the format used during training:
        # <|pm_request|>\n{input}\n<|response|>\n{output}<|end|>
        prompt = (
            f"<|pm_request|>\n{request}\n"
            f"<|response|>\n"
        )

        # Find the <|end|> token id to use as stop token
        end_token_id = tok.convert_tokens_to_ids("<|end|>")

        cfg = GenerationConfig(
            max_new_tokens=800,
            min_new_tokens=100,
            temperature=0.2,   # Very low — deterministic JSON
            top_p=0.9,
            top_k=20,          # Tight — stays on schema
            repetition_penalty=1.3,  # Strong — kills looping
        )

        input_ids = self._encode(prompt)
        raw = generate(model, input_ids, tok, cfg,
                       stop_token_id=end_token_id)
        result = parse_planner_output(raw, request)
        return prompt, result

    def _run_reasoner(self, request: str, planner_result: PlannerResult) -> tuple[str, ReasonerResult]:
        """Stage 2: JSON prefix injection forces risk analysis structure."""
        tok   = self.loader.get_tokenizer()
        model = self.loader.load_model("reasoner")

        task_graph_str = (
            json.dumps(planner_result.task_graph, indent=2)
            if planner_result.task_graph
            else planner_result.raw_output[:600]
        )

        prompt = (
            f"<|pm_request|>\n"
            f"Analyze the risks, critical path, and constraints for this project:\n{request}\n"
            f"<|task_graph|>\n{task_graph_str}\n"
            f"<|response|>\n"
        )

        end_token_id = tok.convert_tokens_to_ids("<|end|>")

        cfg = GenerationConfig(
            max_new_tokens=700,
            min_new_tokens=100,
            temperature=0.2,
            top_p=0.9,
            top_k=20,
            repetition_penalty=1.3,
        )

        input_ids = self._encode(prompt)
        raw = generate(model, input_ids, tok, cfg,
                       stop_token_id=end_token_id)
        result = parse_reasoner_output(raw, request, planner_result)
        return prompt, result

    def _run_communicator(
        self,
        request: str,
        planner_result: PlannerResult,
        reasoner_result: ReasonerResult,
        comm_request: str = "Write a project kickoff summary for stakeholders.",
    ) -> tuple[str, CommunicatorResult]:
        """Stage 3: Natural language output via Ollama (pmcommunicator model).

        Calls the local Ollama REST API at http://localhost:11434 so the
        Phi-3.5-mini LoRA handles prose generation instead of the from-scratch
        communicator model (which was not trained for open-ended prose).
        Falls back to the from-scratch model if Ollama is unavailable.
        """
        import urllib.request

        health_emoji = {"green": "\U0001f7e2", "yellow": "\U0001f7e1", "red": "\U0001f534"}.get(
            reasoner_result.overall_health, "\U0001f7e1"
        )
        context = {
            "project_summary":     request,
            "num_tasks":           planner_result.num_tasks,
            "methodology":         planner_result.methodology,
            "duration_days":       planner_result.duration_days,
            "health":              f"{health_emoji} {reasoner_result.overall_health.upper()}",
            "top_risks":           reasoner_result.top_risks,
            "critical_path_tasks": reasoner_result.critical_path,
        }

        prompt = (
            f"<|pm_request|>\n{comm_request}\n"
            f"<|project_context|>\n{json.dumps(context, indent=2)}\n"
            f"<|response|>\n"
        )

        ollama_url = os.environ.get("OLLAMA_URL", "http://localhost:11434")

        try:
            payload = json.dumps({
                "model":  "pmcommunicator",
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature":        0.3,
                    "top_p":              0.9,
                    "repeat_penalty":     1.1,
                    "num_predict":        600,
                },
            }).encode()

            req = urllib.request.Request(
                f"{ollama_url}/api/generate",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode())
            raw = data.get("response", "").strip()
            result = parse_communicator_output(raw)
            return prompt, result

        except Exception as e:
            # Ollama unavailable — fall back to from-scratch model
            print(f"  [PMCommunicator] Ollama unavailable ({e}), using from-scratch model.")
            tok   = self.loader.get_tokenizer()
            model = self.loader.load_model("communicator")
            cfg = GenerationConfig(
                max_new_tokens=600,
                min_new_tokens=60,
                temperature=0.75,
                top_p=0.92,
                top_k=50,
                repetition_penalty=1.12,
            )
            input_ids = self._encode(prompt)
            raw = generate(model, input_ids, tok, cfg)
            result = parse_communicator_output(raw)
            return prompt, result

    def run(
        self,
        request: str,
        comm_request: str = "Write a professional project kickoff summary for stakeholders.",
        verbose: bool = True,
    ) -> PMCoreResult:
        if verbose:
            print(f"\n{'='*60}")
            print(f"PMCore Pipeline")
            print(f"Request: {request}")
            print(f"{'='*60}")

        latency = {}
        t_total = time.time()

        # ── Stage 1: PMPlanner ────────────────────────────────────────
        if verbose: print("\n[Stage 1: PMPlanner — decomposing request...]")
        t0 = time.time()
        _, planner_result = self._run_planner(request)
        latency["planner_ms"] = round((time.time() - t0) * 1000)

        if verbose:
            is_fallback = (planner_result.task_graph or {}).get("_fallback", False)
            print(f"  Tasks: {planner_result.num_tasks}  {'(fallback)' if is_fallback else '(model JSON)'}")
            print(f"  Methodology: {planner_result.methodology}")
            print(f"  Duration: {planner_result.duration_days} days")
            print(f"  Latency: {latency['planner_ms']}ms")

        # ── Stage 2: PMReasoner ───────────────────────────────────────
        if verbose: print("\n[Stage 2: PMReasoner — analyzing risks & critical path...]")
        t0 = time.time()
        _, reasoner_result = self._run_reasoner(request, planner_result)
        latency["reasoner_ms"] = round((time.time() - t0) * 1000)

        if verbose:
            is_fallback = (reasoner_result.risk_analysis or {}).get("_fallback", False)
            print(f"  Health: {reasoner_result.overall_health.upper()}  {'(fallback)' if is_fallback else '(model JSON)'}")
            print(f"  Top risks: {', '.join(reasoner_result.top_risks[:3]) or 'none identified'}")
            print(f"  Critical path: {' → '.join(str(t) for t in reasoner_result.critical_path[:5]) or 'TBD'}")
            print(f"  Latency: {latency['reasoner_ms']}ms")

        # ── Stage 3: PMCommunicator ───────────────────────────────────
        if verbose: print(f"\n[Stage 3: PMCommunicator — '{comm_request[:50]}...']")
        t0 = time.time()
        _, comm_result = self._run_communicator(request, planner_result, reasoner_result, comm_request)
        latency["communicator_ms"] = round((time.time() - t0) * 1000)

        if verbose:
            print(f"  Type: {comm_result.comm_type}")
            print(f"  Latency: {latency['communicator_ms']}ms")

        # ── Stage 4: PMMath ───────────────────────────────────────────
        if verbose: print(f"\n[Stage 4: PMMath — validating numbers...]")
        t0 = time.time()
        math_audit = math_validate(
            planner_result,
            reasoner_result,
            comm_text=comm_result.communication,
        )
        latency["math_ms"] = round((time.time() - t0) * 1000)

        if verbose:
            icon = {"pass": "✓", "warn": "⚠", "fail": "✗"}.get(math_audit.overall, "?")
            print(f"  {icon} {math_audit.overall.upper()}: {math_audit.summary[:120]}")
            if math_audit.corrections:
                print(f"  Corrections: {math_audit.corrections}")
            print(f"  Latency: {latency['math_ms']}ms")

        latency["total_ms"] = round((time.time() - t_total) * 1000)

        if verbose:
            print(f"\nTotal pipeline latency: {latency['total_ms']}ms")
            print(f"\n{'='*60}")
            print("COMMUNICATION OUTPUT:")
            print(f"{'='*60}")
            print(comm_result.communication)
            print(f"{'='*60}\n")

        return PMCoreResult(
            request=request,
            planner=planner_result,
            reasoner=reasoner_result,
            communicator=comm_result,
            math_audit=math_audit,
            latency_ms=latency,
            total_ms=latency["total_ms"],
        )
