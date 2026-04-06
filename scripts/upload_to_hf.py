#!/usr/bin/env python3
"""
Upload PMCore model weights to HuggingFace.

Uploads all three models from ./checkpoints/:
  - checkpoints/planner/best.pt          → {org}/pmplanner
  - checkpoints/reasoner/best.pt         → {org}/pmreasoner
  - checkpoints/communicator_phi3/merged/ → {org}/pmcommunicator

Requires HF_TOKEN env var or --token argument with write access.

Usage:
    export HF_TOKEN=hf_xxx
    python scripts/upload_to_hf.py
    python scripts/upload_to_hf.py --org myorg --token hf_xxx
    python scripts/upload_to_hf.py --skip-communicator
"""

import argparse
import os
import sys
from pathlib import Path

PLANNER_CARD = """\
---
language: en
license: mit
tags:
  - project-management
  - planning
  - transformer
  - pytorch
pipeline_tag: text-generation
---

# PMPlanner

PMPlanner is a 171.8M parameter transformer trained from scratch on 28,000+ real-world
project management scenarios. It takes a plain-English project description and outputs a
structured JSON task graph with phases, milestones, dependencies, and resource allocations.

## Model Details

| Property | Value |
|---|---|
| Parameters | 171.8M |
| Architecture | Custom encoder-decoder transformer |
| Training data | 28,000+ PM scenarios across 16 industries |
| Output format | Structured JSON (phases, tasks, milestones, risks) |
| License | MIT |

## Usage

PMPlanner is part of the PMCore pipeline. Use via the API:

```bash
curl -X POST http://localhost:8765/plan/quick \\
  -H "Content-Type: application/json" \\
  -d '{"request": "Build a mobile payment app, Q2 deadline, team of 12, budget $2M."}'
```

Or use the full pipeline (planner + reasoner + communicator):
```bash
curl -X POST http://localhost:8765/plan \\
  -H "Content-Type: application/json" \\
  -d '{"request": "...", "comm_request": "Write a project kickoff email."}'
```

## Full Pipeline

PMCore chains three models:
1. **PMPlanner** (this model) — JSON task graph
2. **PMReasoner** — risk analysis
3. **PMCommunicator** — stakeholder prose (Phi-3.5-mini LoRA)

See [PMCore on GitHub](https://github.com/snavazio/pmcore) for full documentation.
"""

REASONER_CARD = """\
---
language: en
license: mit
tags:
  - project-management
  - risk-analysis
  - transformer
  - pytorch
pipeline_tag: text-generation
---

# PMReasoner

PMReasoner is a 125.3M parameter transformer trained from scratch to perform project risk
analysis. It takes a structured project plan (from PMPlanner) and outputs a JSON risk
assessment: overall health (green/yellow/red), top risks, critical path analysis, and
actionable recommendations.

## Model Details

| Property | Value |
|---|---|
| Parameters | 125.3M |
| Architecture | Custom encoder-decoder transformer |
| Training data | 28,000+ PM scenarios with risk annotations |
| Output format | Structured JSON (health, risks, critical_path, recommendations) |
| License | MIT |

## Usage

PMReasoner is part of the PMCore pipeline. Use via the API:

```bash
curl -X POST http://localhost:8765/plan/quick \\
  -H "Content-Type: application/json" \\
  -d '{"request": "Migrate enterprise from on-prem to cloud, 18 months, $15M budget."}'
```

Response includes both planner and reasoner output:
```json
{
  "planner": {"methodology": "hybrid", "num_tasks": 47, ...},
  "reasoner": {"overall_health": "yellow", "top_risks": ["vendor lock-in", ...], ...}
}
```

## Full Pipeline

See [PMCore on GitHub](https://github.com/snavazio/pmcore) for full documentation.
"""

COMMUNICATOR_CARD = """\
---
language: en
license: mit
base_model: microsoft/Phi-3.5-mini-instruct
tags:
  - project-management
  - communication
  - lora
  - peft
  - phi-3.5
pipeline_tag: text-generation
---

# PMCommunicator

PMCommunicator is a LoRA fine-tune of [Phi-3.5-mini-instruct](https://huggingface.co/microsoft/Phi-3.5-mini-instruct)
(3.8B parameters) specialized for generating professional project management communications.

Given a project context (from PMPlanner + PMReasoner), it generates stakeholder-ready prose:
kickoff emails, status reports, risk escalation memos, executive summaries, board updates,
and project closeout reports.

## Model Details

| Property | Value |
|---|---|
| Base model | microsoft/Phi-3.5-mini-instruct (3.8B) |
| Fine-tuning method | LoRA (PEFT) |
| LoRA rank | 16, alpha 32 |
| Trainable params | 25M / 3.82B (0.65%) |
| Training data | 28,000+ PM communication examples |
| Val loss | 0.0105 |
| License | MIT |

## Usage

```python
from transformers import AutoTokenizer, AutoModelForCausalLM
import torch

model_id = "pmcore/pmcommunicator"
tokenizer = AutoTokenizer.from_pretrained(model_id)
model = AutoModelForCausalLM.from_pretrained(model_id, torch_dtype=torch.float16, device_map="auto")

system = (
    "You are PMCommunicator, an expert project manager and communications specialist. "
    "Generate professional, stakeholder-ready project communications based on the provided "
    "project context. Be specific — use the actual project name, numbers, and timeline. "
    "Write in clear business English. Output only the communication document itself."
)
user = "Project: Cloud migration, 50 legacy apps, 18 months, $8M budget. 3 phases planned.\\n\\nWrite a weekly status report for stakeholders."

prompt = f"<|system|>\\n{system}<|end|>\\n<|user|>\\n{user}<|end|>\\n<|assistant|>\\n"
inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
outputs = model.generate(**inputs, max_new_tokens=512, temperature=0.3, do_sample=True)
print(tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True))
```

## Full Pipeline

Use PMCommunicator as part of the full PMCore pipeline for best results.
See [PMCore on GitHub](https://github.com/snavazio/pmcore).
"""


def create_repo_if_needed(api, repo_id: str, token: str):
    """Create HF repo if it doesn't exist."""
    try:
        api.repo_info(repo_id=repo_id, token=token)
        print(f"  Repo {repo_id} already exists.")
    except Exception:
        print(f"  Creating repo {repo_id}...")
        api.create_repo(repo_id=repo_id, token=token, repo_type="model", private=False)
        print(f"  ✓ Created {repo_id}")


def upload_pt_model(api, repo_id: str, src_path: Path, model_card: str, token: str):
    """Upload a .pt file and model card to a HF repo."""
    if not src_path.exists():
        print(f"  ERROR: {src_path} not found — skipping.")
        return False

    create_repo_if_needed(api, repo_id, token)

    print(f"  Uploading {src_path} ({src_path.stat().st_size / 1e6:.1f} MB)...")
    api.upload_file(
        path_or_fileobj=str(src_path),
        path_in_repo="best.pt",
        repo_id=repo_id,
        token=token,
        commit_message="Upload model weights",
    )

    print(f"  Uploading model card...")
    api.upload_file(
        path_or_fileobj=model_card.encode(),
        path_in_repo="README.md",
        repo_id=repo_id,
        token=token,
        commit_message="Add model card",
    )
    print(f"  ✓ Uploaded to https://huggingface.co/{repo_id}")
    return True


def upload_hf_model(api, repo_id: str, src_dir: Path, model_card: str, token: str):
    """Upload a full HF model directory (safetensors) to a HF repo."""
    if not src_dir.exists():
        print(f"  ERROR: {src_dir} not found — skipping.")
        return False

    create_repo_if_needed(api, repo_id, token)

    print(f"  Uploading directory {src_dir} ...")
    api.upload_folder(
        folder_path=str(src_dir),
        repo_id=repo_id,
        token=token,
        commit_message="Upload merged LoRA model",
        ignore_patterns=["*.msgpack", "flax_model*", "tf_model*"],
    )

    # Upload/overwrite README with our model card
    print(f"  Uploading model card...")
    api.upload_file(
        path_or_fileobj=model_card.encode(),
        path_in_repo="README.md",
        repo_id=repo_id,
        token=token,
        commit_message="Add model card",
    )
    print(f"  ✓ Uploaded to https://huggingface.co/{repo_id}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Upload PMCore models to HuggingFace")
    parser.add_argument("--org", default=os.environ.get("PMCORE_HF_ORG", "pmcore"),
                        help="HuggingFace organization (default: pmcore)")
    parser.add_argument("--dir", default="./checkpoints",
                        help="Local checkpoints directory (default: ./checkpoints)")
    parser.add_argument("--token", default=os.environ.get("HF_TOKEN"),
                        help="HuggingFace write token (or set HF_TOKEN env var)")
    parser.add_argument("--skip-communicator", action="store_true",
                        help="Skip uploading the large PMCommunicator model")
    args = parser.parse_args()

    if not args.token:
        print("ERROR: HuggingFace write token required.")
        print("  Set HF_TOKEN env var or pass --token hf_xxx")
        print("  Get a token at: https://huggingface.co/settings/tokens")
        sys.exit(1)

    try:
        from huggingface_hub import HfApi
    except ImportError:
        print("ERROR: huggingface-hub not installed. Run: pip install huggingface-hub")
        sys.exit(1)

    api = HfApi()
    checkpoints = Path(args.dir)
    org = args.org

    print(f"PMCore Model Uploader")
    print(f"  Organization : {org}")
    print(f"  Source       : {checkpoints.resolve()}")
    print()

    # --- PMPlanner ---
    print("1/3  PMPlanner → {org}/pmplanner ...")
    upload_pt_model(
        api=api,
        repo_id=f"{org}/pmplanner",
        src_path=checkpoints / "planner" / "best.pt",
        model_card=PLANNER_CARD,
        token=args.token,
    )

    # --- PMReasoner ---
    print(f"2/3  PMReasoner → {org}/pmreasoner ...")
    upload_pt_model(
        api=api,
        repo_id=f"{org}/pmreasoner",
        src_path=checkpoints / "reasoner" / "best.pt",
        model_card=REASONER_CARD,
        token=args.token,
    )

    # --- PMCommunicator ---
    if not args.skip_communicator:
        print(f"3/3  PMCommunicator → {org}/pmcommunicator ...")
        print("     This is a large upload (~7GB). This will take a while.")
        upload_hf_model(
            api=api,
            repo_id=f"{org}/pmcommunicator",
            src_dir=checkpoints / "communicator_phi3" / "merged",
            model_card=COMMUNICATOR_CARD,
            token=args.token,
        )
    else:
        print("3/3  PMCommunicator skipped (--skip-communicator).")

    print()
    print("✓ Upload complete!")
    print(f"  https://huggingface.co/{org}/pmplanner")
    print(f"  https://huggingface.co/{org}/pmreasoner")
    print(f"  https://huggingface.co/{org}/pmcommunicator")


if __name__ == "__main__":
    main()
