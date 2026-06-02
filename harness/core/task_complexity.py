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
)


def is_complex_task(request: str) -> bool:
    """True for multi-step or engineering work; false for chat and one-shot asks."""
    text = request.strip()
    if not text:
        return False
    if try_direct_reply(text):
        return False
    if request_needs_skill_workflow(text):
        return True
    if len(text) > 140:
        return True
    if text.count("\n") >= 2:
        return True
    if len(re.findall(r"[.!?]", text)) >= 2:
        return True
    low = text.lower()
    if any(hint in low for hint in _COMPLEX_HINTS):
        return True
    # Short conversational prompts (hello, thanks, single question)
    if len(text) < 48 and "?" not in text:
        return False
    return False


def should_create_skill(request: str) -> bool:
    """Only persist new skill files for complex, unmatched work."""
    return is_complex_task(request)
