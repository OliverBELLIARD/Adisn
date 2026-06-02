"""CLI helpers for /cookbook commands."""

from __future__ import annotations

import json
from typing import Any, Dict


def format_cookbook_result(result: Dict[str, Any]) -> str:
    if not result.get("ok", True) and result.get("error"):
        return json.dumps(result, indent=2)

    if "recommendations" in result:
        lines = [
            f"Recommendations ({result.get('profile')}, budget {result.get('budget_gb')} GB):",
        ]
        for rec in result["recommendations"]:
            lines.append(
                f"  [{rec['score']}] {rec['name']} — {rec['quant']} @ {rec['vram_gb']} GB VRAM"
            )
        return "\n".join(lines)

    if "hardware" in result and "recommendations" not in result:
        hw = result["hardware"]
        lines = [
            "Cookbook hardware scan",
            f"  CPU: {hw.get('cpu')}",
            f"  RAM: {hw.get('ram_gb')} GB",
            f"  VRAM budget: {hw.get('vram_budget_gb')} GB",
        ]
        for gpu in hw.get("gpus", []):
            lines.append(f"  GPU: {gpu.get('name')} ({gpu.get('vram_gb')} GB)")
        if result.get("llmfit"):
            lines.append("  llmfit: detected (see JSON for details)")
        return "\n".join(lines)

    if "dependencies" in result:
        lines = ["Cookbook dependencies:"]
        for name, ok in result["dependencies"].items():
            lines.append(f"  {'✓' if ok else '✗'} {name}")
        return "\n".join(lines)

    return json.dumps(result, indent=2)
