"""
PMCore Model Architecture
=========================
Three purpose-built transformer components:

  PMPlanner      (~180M params) - Decomposes requests into structured JSON task graphs
  PMReasoner     (~120M params) - Risk analysis, critical path, constraint checking
  PMCommunicator (~672M params) - Stakeholder-facing prose generation

Architecture: Modern Llama-style (RoPE, SwiGLU, RMSNorm, GQA)
Output: Always valid JSON via constrained decoding
"""

import math
import torch
import torch.nn as nn
import torch.nn.functional as F
from dataclasses import dataclass
from typing import Optional


# ── Model Configurations ──────────────────────────────────────────────────────

@dataclass
class ModelConfig:
    vocab_size:      int   = 32000
    hidden_size:     int   = 1024
    num_layers:      int   = 16
    num_heads:       int   = 16
    num_kv_heads:    int   = 8       # GQA: fewer KV heads = faster inference
    intermediate_size: int = 2816
    max_seq_len:     int   = 4096
    rope_theta:      float = 10000.0
    norm_eps:        float = 1e-5
    dropout:         float = 0.0
    tie_embeddings:  bool  = True
    name:            str   = "pmcore"


def PMPlannerConfig() -> ModelConfig:
    """~175M parameters. Decomposes PM requests into task graphs."""
    return ModelConfig(
        hidden_size=896,
        num_layers=16,
        num_heads=14,
        num_kv_heads=7,
        intermediate_size=2432,
        name="PMPlanner",
    )


def PMReasonerConfig() -> ModelConfig:
    """~120M parameters. Risk analysis and critical path reasoning."""
    return ModelConfig(
        hidden_size=768,
        num_layers=16,
        num_heads=12,
        num_kv_heads=4,
        intermediate_size=2048,
        name="PMReasoner",
    )


def PMCommunicatorConfig() -> ModelConfig:
    """~672M parameters. Stakeholder-facing prose generation (Llama-scale capacity)."""
    return ModelConfig(
        hidden_size=1536,
        num_layers=24,
        num_heads=12,
        num_kv_heads=6,
        intermediate_size=4096,
        dropout=0.1,
        name="PMCommunicator",
    )


# ── Building Blocks ───────────────────────────────────────────────────────────

class RMSNorm(nn.Module):
    def __init__(self, dim: int, eps: float = 1e-5):
        super().__init__()
        self.eps = eps
        self.weight = nn.Parameter(torch.ones(dim))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        norm = x * torch.rsqrt(x.pow(2).mean(-1, keepdim=True) + self.eps)
        return norm * self.weight


class RotaryEmbedding(nn.Module):
    def __init__(self, dim: int, max_seq_len: int = 4096, theta: float = 10000.0):
        super().__init__()
        inv_freq = 1.0 / (theta ** (torch.arange(0, dim, 2).float() / dim))
        self.register_buffer("inv_freq", inv_freq)
        self._build_cache(max_seq_len)

    def _build_cache(self, seq_len: int):
        t = torch.arange(seq_len, device=self.inv_freq.device).float()
        freqs = torch.outer(t, self.inv_freq)
        emb = torch.cat([freqs, freqs], dim=-1)
        self.register_buffer("cos_cached", emb.cos()[None, None, :, :])
        self.register_buffer("sin_cached", emb.sin()[None, None, :, :])

    def forward(self, x: torch.Tensor, seq_len: int):
        if seq_len > self.cos_cached.shape[2]:
            self._build_cache(seq_len)
        return (
            self.cos_cached[:, :, :seq_len, :].to(x.dtype),
            self.sin_cached[:, :, :seq_len, :].to(x.dtype),
        )


def rotate_half(x: torch.Tensor) -> torch.Tensor:
    x1, x2 = x[..., : x.shape[-1] // 2], x[..., x.shape[-1] // 2 :]
    return torch.cat([-x2, x1], dim=-1)


def apply_rotary(q, k, cos, sin):
    q = (q * cos) + (rotate_half(q) * sin)
    k = (k * cos) + (rotate_half(k) * sin)
    return q, k


class GQAttention(nn.Module):
    """Grouped Query Attention — fewer KV heads = 2-4x faster inference."""

    def __init__(self, config: ModelConfig):
        super().__init__()
        self.num_heads    = config.num_heads
        self.num_kv_heads = config.num_kv_heads
        self.head_dim     = config.hidden_size // config.num_heads
        self.kv_groups    = config.num_heads // config.num_kv_heads

        self.q_proj = nn.Linear(config.hidden_size, config.num_heads * self.head_dim, bias=False)
        self.k_proj = nn.Linear(config.hidden_size, config.num_kv_heads * self.head_dim, bias=False)
        self.v_proj = nn.Linear(config.hidden_size, config.num_kv_heads * self.head_dim, bias=False)
        self.o_proj = nn.Linear(config.num_heads * self.head_dim, config.hidden_size, bias=False)

        self.rotary = RotaryEmbedding(self.head_dim, config.max_seq_len, config.rope_theta)
        self.dropout = config.dropout

    def forward(
        self,
        x: torch.Tensor,
        attention_mask: Optional[torch.Tensor] = None,
        past_kv: Optional[tuple] = None,
    ):
        B, T, C = x.shape

        q = self.q_proj(x).view(B, T, self.num_heads, self.head_dim).transpose(1, 2)
        k = self.k_proj(x).view(B, T, self.num_kv_heads, self.head_dim).transpose(1, 2)
        v = self.v_proj(x).view(B, T, self.num_kv_heads, self.head_dim).transpose(1, 2)

        cos, sin = self.rotary(q, T)
        q, k = apply_rotary(q, k, cos, sin)

        if past_kv is not None:
            k = torch.cat([past_kv[0], k], dim=2)
            v = torch.cat([past_kv[1], v], dim=2)

        # Expand KV heads to match Q heads (GQA)
        k = k.repeat_interleave(self.kv_groups, dim=1)
        v = v.repeat_interleave(self.kv_groups, dim=1)

        # Flash attention when available
        out = F.scaled_dot_product_attention(
            q, k, v,
            attn_mask=attention_mask,
            dropout_p=self.dropout if self.training else 0.0,
            is_causal=(past_kv is None),
        )

        out = out.transpose(1, 2).contiguous().view(B, T, -1)
        return self.o_proj(out), (k[:, ::self.kv_groups], v[:, ::self.kv_groups])


class SwiGLUFFN(nn.Module):
    """SwiGLU feed-forward. More expressive than standard FFN."""

    def __init__(self, config: ModelConfig):
        super().__init__()
        self.gate_proj = nn.Linear(config.hidden_size, config.intermediate_size, bias=False)
        self.up_proj   = nn.Linear(config.hidden_size, config.intermediate_size, bias=False)
        self.down_proj = nn.Linear(config.intermediate_size, config.hidden_size, bias=False)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.down_proj(F.silu(self.gate_proj(x)) * self.up_proj(x))


class TransformerBlock(nn.Module):
    def __init__(self, config: ModelConfig):
        super().__init__()
        self.norm1 = RMSNorm(config.hidden_size, config.norm_eps)
        self.attn  = GQAttention(config)
        self.norm2 = RMSNorm(config.hidden_size, config.norm_eps)
        self.ffn   = SwiGLUFFN(config)

    def forward(self, x, attention_mask=None, past_kv=None):
        attn_out, new_kv = self.attn(self.norm1(x), attention_mask, past_kv)
        x = x + attn_out
        x = x + self.ffn(self.norm2(x))
        return x, new_kv


# ── Core Model ────────────────────────────────────────────────────────────────

class PMCoreModel(nn.Module):
    """
    The base transformer used for all three PMCore components.
    Configured differently for PMPlanner, PMReasoner, PMCommunicator.
    """

    def __init__(self, config: ModelConfig):
        super().__init__()
        self.config = config

        self.embed = nn.Embedding(config.vocab_size, config.hidden_size)
        self.layers = nn.ModuleList([TransformerBlock(config) for _ in range(config.num_layers)])
        self.norm   = RMSNorm(config.hidden_size, config.norm_eps)
        self.lm_head = nn.Linear(config.hidden_size, config.vocab_size, bias=False)

        if config.tie_embeddings:
            self.lm_head.weight = self.embed.weight

        self.apply(self._init_weights)

    def _init_weights(self, module):
        if isinstance(module, nn.Linear):
            nn.init.normal_(module.weight, mean=0.0, std=0.02)
            if module.bias is not None:
                nn.init.zeros_(module.bias)
        elif isinstance(module, nn.Embedding):
            nn.init.normal_(module.weight, mean=0.0, std=0.02)

    def forward(
        self,
        input_ids: torch.Tensor,
        attention_mask: Optional[torch.Tensor] = None,
        past_kvs: Optional[list] = None,
        return_logits: bool = True,
    ):
        x = self.embed(input_ids)

        new_kvs = []
        for i, layer in enumerate(self.layers):
            past_kv = past_kvs[i] if past_kvs else None
            x, kv = layer(x, attention_mask, past_kv)
            new_kvs.append(kv)

        x = self.norm(x)

        if return_logits:
            return self.lm_head(x), new_kvs
        return x, new_kvs

    def count_params(self) -> int:
        return sum(p.numel() for p in self.parameters() if p.requires_grad)

    def __repr__(self):
        p = self.count_params()
        return (
            f"{self.config.name}("
            f"layers={self.config.num_layers}, "
            f"hidden={self.config.hidden_size}, "
            f"heads={self.config.num_heads}/{self.config.num_kv_heads} GQA, "
            f"params={p/1e6:.1f}M)"
        )


# ── Factory ───────────────────────────────────────────────────────────────────

def build_pmplanner()      -> PMCoreModel: return PMCoreModel(PMPlannerConfig())
def build_pmreasoner()     -> PMCoreModel: return PMCoreModel(PMReasonerConfig())
def build_pmcommunicator() -> PMCoreModel: return PMCoreModel(PMCommunicatorConfig())


if __name__ == "__main__":
    print("PMCore Architecture Verification\n" + "="*40)
    for fn in [build_pmplanner, build_pmreasoner, build_pmcommunicator]:
        m = fn()
        print(m)
    total = sum(
        fn().count_params()
        for fn in [build_pmplanner, build_pmreasoner, build_pmcommunicator]
    )
    print(f"\nTotal PMCore parameters: {total/1e6:.1f}M")
