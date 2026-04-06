#!/usr/bin/env python3
"""
PMCommunicator — LoRA fine-tune Phi-3-mini-4k-instruct (3.8B, MIT license)
on the 28K PM communications corpus.

Output: checkpoints/communicator_phi3/merged/   (merged model + tokenizer)
        checkpoints/communicator_phi3/adapter/   (LoRA adapter only, for HF Hub)

Usage:
    uv run python finetune_communicator_phi3.py
"""

import json, os, sys, time, random
from pathlib import Path

import torch
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import LoraConfig, get_peft_model, TaskType

# ── Hyper-parameters ──────────────────────────────────────────────────────────
BASE_MODEL   = "microsoft/Phi-3.5-mini-instruct"
CORPUS_PATH  = "corpus/communicator_clean_corpus.jsonl"
OUTPUT_DIR   = "checkpoints/communicator_phi3"
LOG_DIR      = "retrain_logs_v6"

LORA_RANK    = 16
LORA_ALPHA   = 32
LORA_DROPOUT = 0.05
# Target all linear projections in Phi-3 attention + MLP
LORA_TARGETS = ["qkv_proj", "o_proj", "gate_up_proj", "down_proj"]

BATCH_SIZE   = 1
GRAD_ACCUM   = 32   # effective batch = 32
LR           = 2e-4
MIN_LR_RATIO = 0.1
NUM_EPOCHS   = 3
MAX_SEQ_LEN  = 768   # training outputs ~400-800 tokens; 768 fits 95%+
VAL_SPLIT    = 0.05
WARMUP_RATIO = 0.05
GRAD_CLIP    = 1.0
GRAD_CKPT    = True  # gradient checkpointing — trades compute for memory

LOG_EVERY    = 25
EVAL_EVERY   = 200
SAVE_EVERY   = 400

SYSTEM_PROMPT = (
    "You are PMCommunicator, an expert project manager and communications specialist. "
    "Generate professional, stakeholder-ready project communications based on the provided "
    "project context. Be specific — use the actual project name, numbers, and timeline. "
    "Write in clear business English. Output only the communication document itself."
)

# ─────────────────────────────────────────────────────────────────────────────

def log(msg: str) -> None:
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def parse_record(text: str):
    """Extract (request, context_str, response) from a corpus record text."""
    try:
        if "<|response|>" not in text:
            return None
        prompt_part, response_part = text.split("<|response|>\n", 1)
        response = response_part.replace("<|end|>", "").strip()
        if not response or len(response) < 30:
            return None
        if "<|pm_request|>" not in prompt_part or "<|project_context|>" not in prompt_part:
            return None
        after_req  = prompt_part.split("<|pm_request|>\n", 1)[1]
        req_text, ctx_part = after_req.split("<|project_context|>\n", 1)
        request    = req_text.strip()
        context_str = ctx_part.strip()
        if not request or not context_str:
            return None
        return request, context_str, response
    except Exception:
        return None


def build_phi3_text(request: str, context_str: str, response: str) -> str:
    """Format as Phi-3 chat template (system/user/assistant)."""
    user_msg = f"{request}\n\nProject Context:\n{context_str}"
    return (
        f"<|system|>\n{SYSTEM_PROMPT}<|end|>\n"
        f"<|user|>\n{user_msg}<|end|>\n"
        f"<|assistant|>\n{response}<|end|>"
    )


class CommunicatorDataset(Dataset):
    def __init__(self, records, tokenizer, max_len: int):
        self.samples = []
        skipped = 0
        for request, context_str, response in records:
            full_text = build_phi3_text(request, context_str, response)
            full_ids  = tokenizer.encode(full_text, truncation=True, max_length=max_len,
                                         add_special_tokens=False)

            # Find where <|assistant|> response begins — mask prompt with -100
            assist_prefix_ids = tokenizer.encode("<|assistant|>\n", add_special_tokens=False)
            split_pos = len(full_ids)  # default: mask all (shouldn't happen)
            for i in range(len(full_ids) - len(assist_prefix_ids), -1, -1):
                if full_ids[i : i + len(assist_prefix_ids)] == assist_prefix_ids:
                    split_pos = i + len(assist_prefix_ids)
                    break

            labels = [-100] * split_pos + full_ids[split_pos:]
            # Sanity: must have ≥ 10 response tokens
            resp_tokens = sum(1 for l in labels if l != -100)
            if resp_tokens < 10:
                skipped += 1
                continue

            self.samples.append({
                "input_ids": full_ids,
                "labels":    labels,
            })

        log(f"  Dataset: {len(self.samples)} samples ({skipped} skipped)")

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        return self.samples[idx]


def collate_fn(batch, pad_id: int):
    max_len = max(len(x["input_ids"]) for x in batch)
    B = len(batch)
    input_ids    = torch.full((B, max_len), pad_id,   dtype=torch.long)
    labels       = torch.full((B, max_len), -100,     dtype=torch.long)
    attn_mask    = torch.zeros(B, max_len,             dtype=torch.long)
    for i, x in enumerate(batch):
        n = len(x["input_ids"])
        input_ids[i, :n] = torch.tensor(x["input_ids"],  dtype=torch.long)
        labels[i,    :n] = torch.tensor(x["labels"],     dtype=torch.long)
        attn_mask[i, :n] = 1
    return input_ids, labels, attn_mask


def cosine_lr(step: int, total: int, warmup: int) -> float:
    if step < warmup:
        return step / max(1, warmup)
    t = (step - warmup) / max(1, total - warmup)
    return MIN_LR_RATIO + (1 - MIN_LR_RATIO) * 0.5 * (1.0 + torch.cos(torch.tensor(t * 3.14159)).item())


def evaluate(model, val_loader, device, max_batches=60):
    model.eval()
    losses = []
    with torch.no_grad():
        for i, (ids, lbl, msk) in enumerate(val_loader):
            if i >= max_batches:
                break
            ids, lbl, msk = ids.to(device), lbl.to(device), msk.to(device)
            with torch.amp.autocast(device_type="cuda", dtype=torch.bfloat16):
                out = model(input_ids=ids, attention_mask=msk, labels=lbl)
            losses.append(out.loss.item())
    model.train()
    return sum(losses) / len(losses) if losses else float("inf")


def main():
    os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    log("=" * 60)
    log("PMCommunicator — LoRA fine-tune Phi-3-mini-4k-instruct")
    log("=" * 60)
    log(f"Device: {device}")
    if device.type == "cuda":
        props = torch.cuda.get_device_properties(0)
        log(f"GPU: {props.name}  VRAM: {props.total_memory / 1e9:.1f} GB")

    # ── Tokenizer ─────────────────────────────────────────────────────────────
    log(f"Loading tokenizer: {BASE_MODEL}")
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # ── Corpus ────────────────────────────────────────────────────────────────
    log(f"Loading corpus: {CORPUS_PATH}")
    records = []
    with open(CORPUS_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            parsed = parse_record(d.get("text", ""))
            if parsed:
                records.append(parsed)
    log(f"  Parsed {len(records)} valid records from corpus")

    random.seed(42)
    random.shuffle(records)
    val_n = max(1, int(len(records) * VAL_SPLIT))
    val_records   = records[:val_n]
    train_records = records[val_n:]
    log(f"  Train: {len(train_records)} | Val: {len(val_records)}")

    # ── Datasets ──────────────────────────────────────────────────────────────
    log("Tokenizing...")
    train_ds = CommunicatorDataset(train_records, tokenizer, MAX_SEQ_LEN)
    val_ds   = CommunicatorDataset(val_records,   tokenizer, MAX_SEQ_LEN)

    pad_id = tokenizer.pad_token_id
    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True,
                              collate_fn=lambda b: collate_fn(b, pad_id),
                              num_workers=0, pin_memory=True)
    val_loader   = DataLoader(val_ds,   batch_size=BATCH_SIZE, shuffle=False,
                              collate_fn=lambda b: collate_fn(b, pad_id),
                              num_workers=0)

    # ── Base model ────────────────────────────────────────────────────────────
    log(f"Loading base model: {BASE_MODEL}")
    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        torch_dtype=torch.bfloat16,
        attn_implementation="eager",   # safe on all setups
    ).to(device)
    total_params = sum(p.numel() for p in model.parameters())
    log(f"  Base model: {total_params / 1e9:.2f}B parameters")

    # ── LoRA ──────────────────────────────────────────────────────────────────
    lora_cfg = LoraConfig(
        task_type     = TaskType.CAUSAL_LM,
        r             = LORA_RANK,
        lora_alpha    = LORA_ALPHA,
        lora_dropout  = LORA_DROPOUT,
        target_modules= LORA_TARGETS,
        bias          = "none",
        inference_mode= False,
    )
    model = get_peft_model(model, lora_cfg)
    model.print_trainable_parameters()

    # Gradient checkpointing — recomputes activations during backward pass
    # instead of storing them. Cuts activation VRAM by ~60% at ~25% speed cost.
    if GRAD_CKPT:
        model.enable_input_require_grads()
        model.gradient_checkpointing_enable()

    # ── Optimizer ─────────────────────────────────────────────────────────────
    trainable = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.AdamW(trainable, lr=LR, betas=(0.9, 0.95), weight_decay=0.01)

    total_steps  = len(train_loader) * NUM_EPOCHS // GRAD_ACCUM
    warmup_steps = max(1, int(total_steps * WARMUP_RATIO))
    scheduler    = torch.optim.lr_scheduler.LambdaLR(
        optimizer, lambda s: cosine_lr(s, total_steps, warmup_steps)
    )
    log(f"Total steps: {total_steps} | Warmup: {warmup_steps} | Epochs: {NUM_EPOCHS}")
    log("Starting training...")

    # ── Training loop ─────────────────────────────────────────────────────────
    best_val_loss = float("inf")
    global_step   = 0
    t0            = time.time()
    optimizer.zero_grad()

    for epoch in range(NUM_EPOCHS):
        model.train()
        for micro_step, (ids, lbl, msk) in enumerate(train_loader):
            ids, lbl, msk = ids.to(device), lbl.to(device), msk.to(device)

            with torch.amp.autocast(device_type="cuda", dtype=torch.bfloat16):
                out  = model(input_ids=ids, attention_mask=msk, labels=lbl)
                loss = out.loss / GRAD_ACCUM

            loss.backward()

            if (micro_step + 1) % GRAD_ACCUM == 0:
                torch.nn.utils.clip_grad_norm_(model.parameters(), GRAD_CLIP)
                optimizer.step()
                scheduler.step()
                optimizer.zero_grad()
                global_step += 1

                if global_step % LOG_EVERY == 0:
                    elapsed = time.time() - t0
                    tok_s   = BATCH_SIZE * GRAD_ACCUM * MAX_SEQ_LEN * global_step / elapsed
                    cur_lr  = scheduler.get_last_lr()[0] * LR
                    log(f"  step={global_step:5d} | epoch={epoch+1} | "
                        f"loss={loss.item()*GRAD_ACCUM:.4f} | lr={cur_lr:.2e} | "
                        f"{tok_s/1000:.1f}k tok/s")

                if global_step % EVAL_EVERY == 0:
                    val_loss = evaluate(model, val_loader, device)
                    marker   = ""
                    if val_loss < best_val_loss:
                        best_val_loss = val_loss
                        # Save adapter only (lightweight checkpoint)
                        adapter_dir = f"{OUTPUT_DIR}/adapter"
                        model.save_pretrained(adapter_dir)
                        tokenizer.save_pretrained(adapter_dir)
                        marker = " ★ NEW BEST"
                    log(f"  >>> val_loss={val_loss:.4f}{marker}")
                    model.train()

                if global_step % SAVE_EVERY == 0:
                    log(f"  Checkpoint saved at step {global_step}")

    log(f"Training complete! Best val_loss: {best_val_loss:.4f}")

    # ── Merge LoRA into base weights ──────────────────────────────────────────
    log("Merging LoRA weights into base model...")
    merged = model.merge_and_unload()

    merged_dir = f"{OUTPUT_DIR}/merged"
    os.makedirs(merged_dir, exist_ok=True)
    log(f"Saving merged model to {merged_dir}/")
    merged.save_pretrained(merged_dir, safe_serialization=True)
    tokenizer.save_pretrained(merged_dir)

    log("=" * 60)
    log(f"PMCommunicator Phi-3 COMPLETE")
    log(f"  Best val_loss : {best_val_loss:.4f}")
    log(f"  Adapter       : {OUTPUT_DIR}/adapter/")
    log(f"  Merged model  : {OUTPUT_DIR}/merged/")
    log("=" * 60)


if __name__ == "__main__":
    main()
