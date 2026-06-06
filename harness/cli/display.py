"""Terminal display helpers for Adisn CLI."""

from __future__ import annotations

import json
import re
import sys

from harness.core.messages import OLLAMA_WARNING
from harness.core.thinking import format_thinking_for_display


def print_ollama_warning() -> None:
    print(OLLAMA_WARNING, file=sys.stderr)


def print_user_message(line: str) -> None:
    """Echo the user prompt (Claude Code conversation style)."""
    dim = _use_dim()
    reset = _reset()
    print(f"{dim}You:{reset} {line}")


def print_thinking_indicator() -> None:
    print("● Thinking…", flush=True)


def print_thinking_block(thinking: str, *, expanded: bool = False) -> None:
    if not thinking.strip():
        return
    dim = _use_dim()
    if expanded:
        body = "\n".join(f"  {line}" for line in thinking.strip().splitlines())
        print(f"{dim}Thinking{_reset()}")
        print(f"{dim}{body}{_reset()}\n")
        return
    body, truncated = format_thinking_for_display(thinking)
    if not body:
        return
    suffix = " (session: /think expand)" if truncated else ""
    print(f"{dim}Thinking{suffix}{_reset()}")
    print(f"{dim}{body}{_reset()}\n")


def print_agent_response(
    result: dict,
    *,
    show_json_fallback: bool = True,
    show_warning: bool = True,
    live_shown: bool = False,
) -> None:
    if show_warning and result.get("warning"):
        print(result["warning"], file=sys.stderr)

    loop = result.get("agent_loop")
    if loop and loop.get("step_count") and not live_shown:
        print(f"(agent loop: {loop['step_count']} step(s))")

    if result.get("thinking") and not live_shown:
        print_thinking_block(
            result["thinking"], expanded=result.get("thinking_expanded", False)
        )
    elif result.get("thinking") and live_shown and result.get("thinking_expanded"):
        print_thinking_block(result["thinking"], expanded=True)

    message = result.get("message")
    if message:
        print(_clean_markdown(message))
        return

def _clean_markdown(text: str) -> str:
    """Strip or simplify markdown that requires rich rendering (titles, hyperlinks)."""
    if not text:
        return ""
    # Convert titles to plain bold-ish text or just strip #
    lines = []
    for line in text.splitlines():
        if line.strip().startswith("#"):
            lines.append(line.lstrip("#").strip().upper())
        else:
            lines.append(line)
    text = "\n".join(lines)
    # Convert [text](url) to "text"
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    return text

    if show_json_fallback:
        print(json.dumps(result, indent=2))


def print_loop_steps_summary(result: dict) -> None:
    """Compact per-step trace after live activity (Claude Code-style transcript)."""
    loop = result.get("agent_loop") or {}
    steps = loop.get("steps") or []
    if not steps:
        return
    dim = _use_dim()
    reset = _reset()
    print(f"{dim}── agent loop ({len(steps)} step(s)) ──{reset}")
    for idx, step in enumerate(steps, start=1):
        phase = step.get("phase", "?")
        decision = step.get("decision") or {}
        action = decision.get("action", "")
        ms = step.get("duration_ms", 0)
        label = f"  {idx}. {phase}"
        if action:
            label += f" → {action}"
        if ms:
            label += f" ({ms}ms)"
        print(f"{dim}{label}{reset}")


def _use_dim() -> str:
    if not sys.stdout.isatty():
        return ""
    return "\033[2m"


def _reset() -> str:
    if not sys.stdout.isatty():
        return ""
    return "\033[0m"
