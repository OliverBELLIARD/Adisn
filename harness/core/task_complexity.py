"""Decide when a prompt needs skills, agent loop, or new skill files."""

from __future__ import annotations

import re

from harness.core.direct_reply import request_needs_skill_workflow, try_direct_reply

_COMPLEX_HINTS = (
    "refactor",
    "implement",
    "architecture",
    "migrate",
    "debug",
    "fix the",
    "step by step",
    "multi-step",
    "workflow",
    "integration",
    "deploy",
    "harness",
    "rewrite",
    "skill",
    "test suite",
    "root cause",
    "initialize",
    "configure",
    "optimize",
)


def is_complex_task(request: str) -> bool:
    """True for multi-step or engineering work; false for chat and one-shot asks."""
    text = request.strip()
    if not text:
        return False
    if try_direct_reply(text):
        return False

    low = text.lower()
    # Check for engineering intent hints
    has_hint = any(hint in low for hint in _COMPLEX_HINTS)

    if request_needs_skill_workflow(text):
        return True

    # Multi-sentence engineering requests
    if has_hint and (text.count("\n") >= 1 or len(re.findall(r"[.!?]", text)) >= 2):
        return True

    # Very long detailed requests with intent
    if has_hint and len(text) > 200:
        return True

    # Default to False for basic chat even if long, unless it has clear engineering hints
    if not has_hint:
        return False

    return True


def should_create_skill(request: str) -> bool:
    """Only persist new skill files for complex, unmatched work."""
    return is_complex_task(request)
