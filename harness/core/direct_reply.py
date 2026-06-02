"""Fast direct replies for simple conversational prompts (no loop metadata)."""

from __future__ import annotations

import re
from typing import Optional

_REPLY_WITH = re.compile(
    r"^(?:please\s+)?(?:reply|respond|say)\s+with\s+(.+?)\s*[\.\?!]*$",
    re.IGNORECASE,
)
_WHERE_REPLY = re.compile(r"^where(?:'s| is) the reply\??$", re.IGNORECASE)


def try_direct_reply(request: str) -> Optional[str]:
    """Return a user-visible answer when the prompt is plainly conversational."""
    text = request.strip()
    if not text:
        return None

    match = _REPLY_WITH.match(text)
    if match:
        return match.group(1).strip().strip("\"'")

    low = text.lower()
    if low in ("ok", "okay"):
        return "OK"

    if _WHERE_REPLY.match(text):
        return (
            "The previous line was an internal harness status message, not your answer. "
            "I should reply with plain text instead — try again, or run "
            "`/cookbook use <model>` if chat shows http_404 (model missing)."
        )

    return None


def request_needs_skill_workflow(request: str) -> bool:
    """True when the prompt looks like a coding/harness task, not small talk."""
    if try_direct_reply(request):
        return False
    low = request.lower()
    hints = (
        "fix",
        "bug",
        "implement",
        "refactor",
        "deploy",
        "test",
        "build",
        "rewrite",
        "rollback",
        "skill",
        "file",
        "code",
        "error",
        "npm",
        "git",
        "docker",
    )
    return any(word in low for word in hints)
