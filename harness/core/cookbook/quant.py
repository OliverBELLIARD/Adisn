"""VRAM fit scoring (Odysseus Cookbook / llmfit-compatible heuristics)."""

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

QUANT_HIERARCHY = ["Q8_0", "Q6_K", "Q5_K_M", "Q4_K_M", "Q3_K_M", "Q2_K"]

QUANT_BPP = {
    "F16": 2.0,
    "BF16": 2.0,
    "FP8": 1.0,
    "Q8_0": 1.05,
    "Q6_K": 0.80,
    "Q5_K_M": 0.68,
    "Q4_K_M": 0.58,
    "Q3_K_M": 0.48,
    "Q2_K": 0.37,
    "AWQ-4bit": 0.50,
    "GPTQ-Int4": 0.50,
    "mlx-4bit": 0.55,
}

QUANT_QUALITY_PENALTY = {
    "F16": 0.0,
    "Q8_0": 0.0,
    "Q6_K": -1.0,
    "Q5_K_M": -2.0,
    "Q4_K_M": -5.0,
    "Q3_K_M": -8.0,
    "Q2_K": -12.0,
    "AWQ-4bit": -3.0,
    "GPTQ-Int4": -3.0,
    "mlx-4bit": -4.0,
}

PREQUANTIZED_PREFIXES = ("AWQ-", "GPTQ-", "mlx-", "FP8", "INT4", "INT8")


def infer_quantization_from_name(name: str) -> str:
    n = (name or "").lower()
    if "awq" in n:
        return "AWQ-4bit"
    if "gptq" in n:
        return "GPTQ-Int4"
    if "mlx" in n:
        return "mlx-4bit"
    if "fp8" in n:
        return "FP8"
    if "q8" in n:
        return "Q8_0"
    if "q6" in n:
        return "Q6_K"
    if "q5" in n:
        return "Q5_K_M"
    if "q3" in n:
        return "Q3_K_M"
    if "q2" in n:
        return "Q2_K"
    if "q4" in n or "gguf" in n:
        return "Q4_K_M"
    return ""


def params_b(model: Dict[str, Any]) -> float:
    raw = model.get("parameters_b")
    if raw:
        return float(raw)
    pc = str(model.get("parameter_count", "")).strip().upper()
    m = re.match(r"^([\d.]+)\s*([BKM]?)$", pc)
    if not m:
        return 0.0
    val = float(m.group(1))
    suffix = m.group(2)
    if suffix == "B":
        return val
    if suffix == "M":
        return val / 1000.0
    if suffix == "K":
        return val / 1_000_000.0
    if val >= 1_000_000:
        return val / 1_000_000_000.0
    return val / 1000.0


def estimate_memory_gb(model: Dict[str, Any], quant: str, ctx: int) -> float:
    pb = params_b(model)
    bpp = QUANT_BPP.get(quant, 0.58)
    kv = model.get("active_parameters_b", pb)
    return pb * bpp + 0.000008 * kv * ctx + 0.5


def is_prequantized(model: Dict[str, Any]) -> bool:
    q = model.get("quantization", "")
    return any(q.startswith(p) for p in PREQUANTIZED_PREFIXES)


def best_quant_for_budget(
    model: Dict[str, Any], budget_gb: float, ctx: int = 8192
) -> Tuple[Optional[str], Optional[int], Optional[float]]:
    if is_prequantized(model):
        q = model.get("quantization", "Q4_K_M")
        mem = estimate_memory_gb(model, q, ctx)
        if mem <= budget_gb:
            return q, ctx, mem
        cur = ctx // 2
        while cur >= 1024:
            mem = estimate_memory_gb(model, q, cur)
            if mem <= budget_gb:
                return q, cur, mem
            cur //= 2
        return None, None, None
    for q in QUANT_HIERARCHY:
        mem = estimate_memory_gb(model, q, ctx)
        if mem <= budget_gb:
            return q, ctx, mem
    cur = ctx // 2
    while cur >= 1024:
        for q in QUANT_HIERARCHY:
            mem = estimate_memory_gb(model, q, cur)
            if mem <= budget_gb:
                return q, cur, mem
        cur //= 2
    return None, None, None


def fit_score(model: Dict[str, Any], budget_gb: float, ctx: int = 8192) -> float:
    quant, fit_ctx, mem = best_quant_for_budget(model, budget_gb, ctx)
    if not quant:
        return -100.0
    base = float(model.get("quality_score", 70))
    penalty = QUANT_QUALITY_PENALTY.get(quant, -5.0)
    headroom = max(0.0, budget_gb - (mem or 0.0))
    return base + penalty + min(10.0, headroom * 2.0) + (fit_ctx or ctx) / 8192.0
