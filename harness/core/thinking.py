"""Extended thinking mode (Claude Code-style) for Alison."""

from __future__ import annotations

import re
from dataclasses import dataclass


def _think_tag_pairs() -> list[tuple[str, str]]:
    names = ("think", "redacted_reasoning", "thinking")
    return [(f"<{name}>", f"</{name}>") for name in names]


THINK_TAG_PAIRS = _think_tag_pairs()


@dataclass
class ThinkingMode:
    """Session-scoped extended thinking toggle (/think)."""

    enabled: bool = True

    def toggle(self) -> bool:
        self.enabled = not self.enabled
        return self.enabled


def split_thinking_and_response(text: str) -> tuple[str, str]:
    """Extract thinking blocks from model output (DeepSeek-R1 / Qwen style)."""
    if not text:
        return "", ""

    thinking_parts: list[str] = []
    visible = text

    for open_tag, close_tag in THINK_TAG_PAIRS:
        pattern = re.compile(
            re.escape(open_tag) + r"(.*?)" + re.escape(close_tag),
            re.DOTALL | re.IGNORECASE,
        )
        while True:
            match = pattern.search(visible)
            if not match:
                break
            thinking_parts.append(match.group(1).strip())
            visible = visible[: match.start()] + visible[match.end() :]

    visible = visible.strip()
    thinking = "\n\n".join(part for part in thinking_parts if part).strip()
    return thinking, visible


def local_thinking_plan(
    request: str,
    *,
    predicted_action: str,
    skill_name: str | None,
    scope: str,
    ollama_available: bool,
) -> str:
    """Visible reasoning when Ollama is unavailable or as a fast pre-plan."""
    skill_line = skill_name if skill_name else "generate a new skill from this task"
    backend = "Ollama model" if ollama_available else "local harness planner (Ollama offline)"
    return (
        f"Understanding the request: {request[:200]}\n"
        f"Routing workflow: {predicted_action}\n"
        f"Skill plan: {skill_line}\n"
        f"Rewrite scope: {scope}\n"
        f"Execution backend: {backend}"
    )


def format_thinking_for_display(thinking: str, *, max_collapsed_lines: int = 3) -> tuple[str, bool]:
    """Return display text and whether content was truncated."""
    lines = [line for line in thinking.strip().splitlines() if line.strip()]
    if not lines:
        return "", False
    if len(lines) <= max_collapsed_lines:
        return "\n".join(f"  {line}" for line in lines), False
    collapsed = "\n".join(f"  {line}" for line in lines[:max_collapsed_lines])
    collapsed += f"\n  … ({len(lines) - max_collapsed_lines} more lines)"
    return collapsed, True
