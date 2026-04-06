"""
PMCore Trainer
==============
Trains PMPlanner, PMReasoner, or PMCommunicator from scratch.

Usage:
    uv run python pmcore/train.py --component planner
    uv run python pmcore/train.py --component reasoner
    uv run python pmcore/train.py --component communicator

Each component trains on its own corpus with its own architecture config.
Checkpoints saved to ./checkpoints/<component>/
"""

import os
import sys
import math
import json
import time
import argparse
from pathlib import Path

import torch
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader
from transformers import AutoTokenizer

from pmcore.model import (
    PMCoreModel,
    build_pmplanner,
    build_pmreasoner,
    build_pmcommunicator,
)

# ── Configuration ─────────────────────────────────────────────────────────────

COMPONENT_MAP = {
    # All three components train on the master corpus (includes v4 harvest).
    # Falls back to combined_final if master not present.
    "planner":      (build_pmplanner,      "corpus/master_corpus.jsonl"),
    "reasoner":     (build_pmreasoner,     "corpus/master_corpus.jsonl"),
    "communicator": (build_pmcommunicator, "corpus/master_corpus.jsonl"),
}

TRAIN_CONFIG = {
    "batch_size":       4,
    "grad_accum":       8,           # Effective batch = 32
    "learning_rate":    3e-4,
    "min_lr":           3e-5,
    "num_epochs":       5,
    "warmup_steps":     200,
    "max_seq_len":      1024,        # PMCore uses shorter sequences
    "weight_decay":     0.1,
    "grad_clip":        1.0,
    "save_every_steps": 500,
    "log_every_steps":  50,
    "eval_every_steps": 250,
    "val_split":        0.05,
    "dtype":            torch.bfloat16,
}

# ── Tokenizer ─────────────────────────────────────────────────────────────────
# Reuse Llama tokenizer — proven BPE, handles JSON well, 32k vocab

TOKENIZER_ID = "hf-internal-testing/llama-tokenizer"
# Local fallback — thing2's trained PM model tokenizer (no download needed)
TOKENIZER_LOCAL = "/home/snavazio/autoresearch-v2/pm-model"

# PMCore special tokens
SPECIAL_TOKENS = [
    "<|pm_request|>",
    "<|task_graph|>",
    "<|analysis|>",
    "<|communication|>",
    "<|project_context|>",
    "<|end|>",
]


def get_tokenizer():
    from transformers import AutoTokenizer
    # Try local first (thing2's tokenizer — no download needed on LAN)
    for source in [TOKENIZER_LOCAL, TOKENIZER_ID]:
        try:
            tok = AutoTokenizer.from_pretrained(source)
            print(f"  Tokenizer loaded from: {source}")
            break
        except Exception as e:
            print(f"  Tokenizer {source} failed: {e}")
            continue
    else:
        raise RuntimeError("Could not load tokenizer from any source")

    tok.add_special_tokens({"additional_special_tokens": SPECIAL_TOKENS})
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    return tok


# ── Dataset ───────────────────────────────────────────────────────────────────

class PMDataset(Dataset):
    def __init__(self, path: str, tokenizer, max_seq_len: int):
        self.examples = []
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                # Handle both formats:
                #   synthetic format: {"text": "..."}
                #   real corpus format: {"input": "...", "output": "..."}
                if "text" in record:
                    text = record["text"]
                elif "input" in record and "output" in record:
                    inp = str(record["input"])
                    out = str(record["output"])
                    # Handle JSON output (PMPlanner task graphs etc.)
                    if isinstance(record["output"], (dict, list)):
                        out = json.dumps(record["output"])
                    text = f"<|pm_request|>\n{inp}\n<|response|>\n{out}\n<|end|>"
                else:
                    continue
                self.examples.append(text)

        print(f"  Tokenizing {len(self.examples)} examples...")
        self.input_ids = []
        for text in self.examples:
            ids = tokenizer.encode(text, truncation=True, max_length=max_seq_len)
            if len(ids) >= 16:  # skip very short examples
                self.input_ids.append(torch.tensor(ids, dtype=torch.long))

        print(f"  Kept {len(self.input_ids)} examples after filtering")

    def __len__(self):
        return len(self.input_ids)

    def __getitem__(self, idx):
        ids = self.input_ids[idx]
        return ids[:-1], ids[1:]   # input, target (next-token prediction)


def collate_fn(batch):
    inputs, targets = zip(*batch)
    max_len = max(x.size(0) for x in inputs)
    pad_inputs  = torch.zeros(len(inputs), max_len, dtype=torch.long)
    pad_targets = torch.full((len(targets), max_len), -100, dtype=torch.long)
    for i, (inp, tgt) in enumerate(zip(inputs, targets)):
        pad_inputs[i, :inp.size(0)]  = inp
        pad_targets[i, :tgt.size(0)] = tgt
    return pad_inputs, pad_targets


# ── LR Schedule ───────────────────────────────────────────────────────────────

def get_lr(step: int, total_steps: int, cfg: dict) -> float:
    if step < cfg["warmup_steps"]:
        return cfg["learning_rate"] * step / max(1, cfg["warmup_steps"])
    progress = (step - cfg["warmup_steps"]) / max(1, total_steps - cfg["warmup_steps"])
    cosine = 0.5 * (1.0 + math.cos(math.pi * progress))
    return cfg["min_lr"] + cosine * (cfg["learning_rate"] - cfg["min_lr"])


# ── Training Loop ─────────────────────────────────────────────────────────────

def train(component: str):
    assert component in COMPONENT_MAP, f"Unknown component: {component}"
    build_fn, corpus_path = COMPONENT_MAP[component]

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"\n{'='*60}")
    print(f"Training PMCore: {component.upper()}")
    print(f"Device: {device}")
    if device.type == "cuda":
        print(f"GPU: {torch.cuda.get_device_name(0)}")
        print(f"VRAM: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")
    print(f"{'='*60}\n")

    # Tokenizer
    print("Loading tokenizer...")
    tokenizer = get_tokenizer()

    # Dataset
    print(f"Loading corpus from {corpus_path}...")
    full_ds = PMDataset(corpus_path, tokenizer, TRAIN_CONFIG["max_seq_len"])

    val_size  = max(1, int(len(full_ds) * TRAIN_CONFIG["val_split"]))
    train_size = len(full_ds) - val_size
    train_ds, val_ds = torch.utils.data.random_split(
        full_ds, [train_size, val_size], generator=torch.Generator().manual_seed(42)
    )

    train_loader = DataLoader(
        train_ds, batch_size=TRAIN_CONFIG["batch_size"],
        shuffle=True, collate_fn=collate_fn, num_workers=4, pin_memory=True
    )
    val_loader = DataLoader(
        val_ds, batch_size=TRAIN_CONFIG["batch_size"],
        shuffle=False, collate_fn=collate_fn, num_workers=2, pin_memory=True
    )
    print(f"Train: {len(train_ds):,}  |  Val: {len(val_ds):,}")

    # Model
    print(f"\nBuilding {component} model...")
    model = build_fn()
    print(f"  {model}")
    model = model.to(device, dtype=TRAIN_CONFIG["dtype"])

    # Resize embeddings if tokenizer was extended with special tokens
    if len(tokenizer) > model.config.vocab_size:
        print(f"  Resizing vocab: {model.config.vocab_size} → {len(tokenizer)}")
        model.embed = torch.nn.Embedding(len(tokenizer), model.config.hidden_size).to(device)
        model.lm_head = torch.nn.Linear(model.config.hidden_size, len(tokenizer), bias=False).to(device)
        model.config.vocab_size = len(tokenizer)
        if model.config.tie_embeddings:
            model.lm_head.weight = model.embed.weight

    # Optimizer
    decay_params   = [p for n, p in model.named_parameters() if p.dim() >= 2]
    nodecay_params = [p for n, p in model.named_parameters() if p.dim() < 2]
    optimizer = torch.optim.AdamW(
        [{"params": decay_params, "weight_decay": TRAIN_CONFIG["weight_decay"]},
         {"params": nodecay_params, "weight_decay": 0.0}],
        lr=TRAIN_CONFIG["learning_rate"], betas=(0.9, 0.95), fused=True
    )

    # Checkpointing
    ckpt_dir = Path(f"checkpoints/{component}")
    ckpt_dir.mkdir(parents=True, exist_ok=True)

    # Resume if checkpoint exists
    global_step = 0
    best_val_loss = float("inf")
    ckpt_path = ckpt_dir / "latest.pt"
    if ckpt_path.exists():
        print(f"\nResuming from {ckpt_path}...")
        ckpt = torch.load(ckpt_path, map_location=device, weights_only=False)
        model.load_state_dict(ckpt["model"])
        optimizer.load_state_dict(ckpt["optimizer"])
        global_step = ckpt["step"]
        best_val_loss = ckpt.get("best_val_loss", float("inf"))
        print(f"  Resumed at step {global_step}, best val_loss={best_val_loss:.4f}")

    total_steps = len(train_loader) * TRAIN_CONFIG["num_epochs"] // TRAIN_CONFIG["grad_accum"]
    print(f"\nTotal steps: {total_steps:,}  |  Epochs: {TRAIN_CONFIG['num_epochs']}")
    print(f"Starting training...\n")

    scaler = torch.amp.GradScaler(enabled=(TRAIN_CONFIG["dtype"] == torch.float16))
    model.train()
    optimizer.zero_grad()

    t0 = time.time()
    for epoch in range(TRAIN_CONFIG["num_epochs"]):
        for micro_step, (inputs, targets) in enumerate(train_loader):
            inputs  = inputs.to(device, non_blocking=True)
            targets = targets.to(device, non_blocking=True)

            # Update LR
            lr = get_lr(global_step, total_steps, TRAIN_CONFIG)
            for g in optimizer.param_groups:
                g["lr"] = lr

            with torch.amp.autocast(device_type="cuda", dtype=TRAIN_CONFIG["dtype"]):
                logits, _ = model(inputs)
                loss = F.cross_entropy(
                    logits.view(-1, logits.size(-1)),
                    targets.view(-1),
                    ignore_index=-100,
                )
                loss = loss / TRAIN_CONFIG["grad_accum"]

            scaler.scale(loss).backward()

            if (micro_step + 1) % TRAIN_CONFIG["grad_accum"] == 0:
                scaler.unscale_(optimizer)
                torch.nn.utils.clip_grad_norm_(model.parameters(), TRAIN_CONFIG["grad_clip"])
                scaler.step(optimizer)
                scaler.update()
                optimizer.zero_grad()
                global_step += 1

                # Logging
                if global_step % TRAIN_CONFIG["log_every_steps"] == 0:
                    elapsed = time.time() - t0
                    tok_per_sec = (
                        TRAIN_CONFIG["batch_size"] * TRAIN_CONFIG["grad_accum"]
                        * TRAIN_CONFIG["max_seq_len"] * global_step / elapsed
                    )
                    print(
                        f"  step={global_step:5d} | epoch={epoch+1} | "
                        f"loss={loss.item()*TRAIN_CONFIG['grad_accum']:.4f} | "
                        f"lr={lr:.2e} | {tok_per_sec/1e3:.1f}k tok/s"
                    )

                # Validation
                if global_step % TRAIN_CONFIG["eval_every_steps"] == 0:
                    model.eval()
                    val_losses = []
                    with torch.no_grad():
                        for vi, (vinputs, vtargets) in enumerate(val_loader):
                            if vi >= 20:
                                break
                            vinputs  = vinputs.to(device, non_blocking=True)
                            vtargets = vtargets.to(device, non_blocking=True)
                            with torch.amp.autocast(device_type="cuda", dtype=TRAIN_CONFIG["dtype"]):
                                vlogits, _ = model(vinputs)
                                vloss = F.cross_entropy(
                                    vlogits.view(-1, vlogits.size(-1)),
                                    vtargets.view(-1),
                                    ignore_index=-100,
                                )
                            val_losses.append(vloss.item())
                    val_loss = sum(val_losses) / len(val_losses)
                    model.train()

                    marker = " ★ NEW BEST" if val_loss < best_val_loss else ""
                    print(f"  >>> val_loss={val_loss:.4f}{marker}")

                    if val_loss < best_val_loss:
                        best_val_loss = val_loss
                        torch.save({
                            "model": model.state_dict(),
                            "optimizer": optimizer.state_dict(),
                            "step": global_step,
                            "best_val_loss": best_val_loss,
                            "config": model.config,
                        }, ckpt_dir / "best.pt")

                # Checkpoint
                if global_step % TRAIN_CONFIG["save_every_steps"] == 0:
                    torch.save({
                        "model": model.state_dict(),
                        "optimizer": optimizer.state_dict(),
                        "step": global_step,
                        "best_val_loss": best_val_loss,
                        "config": model.config,
                    }, ckpt_dir / "latest.pt")
                    print(f"  Checkpoint saved at step {global_step}")

    print(f"\nTraining complete! Best val_loss: {best_val_loss:.4f}")
    print(f"Best model: {ckpt_dir / 'best.pt'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--component", required=True, choices=list(COMPONENT_MAP.keys()))
    args = parser.parse_args()
    train(args.component)
