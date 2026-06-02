"""Extended thinking (Anthropic-style: separate reasoning trace from answer)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional


def _think_tag_pairs() -> list[tuple[str, str]]:
    names = ("think", "redacted_reasoning", "thinking")
    return [(f"<{name}>", f"</{name}>") for name in names]


THINK_TAG_PAIRS = _think_tag_pairs()

# Substrings that indicate Ollama native `think` API support (see ollama.com/docs thinking).
_NATIVE_THINK_MODEL_HINTS = (
    "qwen3",
    "deepseek",
    "gpt-oss",
    "r1",
    "qwq",
)


@dataclass
class ThinkingMode:
    """Session extended-thinking settings (/think, /think expand)."""

    enabled: bool = True
    budget_tokens: int = 8_000

    def toggle(self) -> bool:
        self.enabled = not self.enabled
        return self.enabled


def model_supports_native_thinking(model: str) -> bool:
    """Whether to use Ollama's `think` field (separate message.thinking trace)."""
    low = model.lower()
    return any(hint in low for hint in _NATIVE_THINK_MODEL_HINTS)


def ollama_think_parameter(model: str, enabled: bool) -> Any:
    """Value for Ollama chat payload `think` (bool or gpt-oss level)."""
    if not enabled:
        return False
    if "gpt-oss" in model.lower():
        return "medium"
    return True


def split_thinking_and_response(text: str) -> tuple[str, str]:
    """Fallback: extract thinking blocks embedded in content (legacy tag format)."""
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


def merge_chat_thinking(
    native_thinking: Optional[str],
    content: str,
) -> tuple[str, str]:
    """Prefer Ollama message.thinking; fall back to tag parsing in content."""
    trace = (native_thinking or "").strip()
    tag_thinking, visible = split_thinking_and_response(content or "")
    if trace:
        return trace, (visible or content or "").strip()
    return tag_thinking, (visible or content or "").strip()


def local_thinking_plan(
    request: str,
    *,
    predicted_action: str,
    skill_name: str | None,
    scope: str,
    ollama_available: bool,
) -> str:
    """Short planner trace when the model is unavailable (not a substitute for native think)."""
    skill_line = skill_name if skill_name else "(no skill — conversational path)"
    backend = (
        "Ollama native think API"
        if ollama_available
        else "local planner (Ollama offline)"
    )
    return (
        f"Understanding the request: {request[:200]}\n"
        f"Routing workflow: {predicted_action}\n"
        f"Skill: {skill_line}\n"
        f"Rewrite scope: {scope}\n"
        f"Execution backend: {backend}"
    )


def format_thinking_for_display(
    thinking: str, *, max_collapsed_lines: int = 3
) -> tuple[str, bool]:
    """Return display text and whether content was truncated."""
    lines = [line for line in thinking.strip().splitlines() if line.strip()]
    if not lines:
        return "", False
    if len(lines) <= max_collapsed_lines:
        return "\n".join(f"  {line}" for line in lines), False
    collapsed = "\n".join(f"  {line}" for line in lines[:max_collapsed_lines])
    collapsed += f"\n  … ({len(lines) - max_collapsed_lines} more lines)"
    return collapsed, True
