"""Fast direct replies for simple conversational prompts (no loop metadata)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

_REPLY_WITH = re.compile(
    r"^(?:please\s+)?(?:reply|respond|say)\s+with\s+(.+?)\s*[\.\?!]*$",
    re.IGNORECASE,
)
_WHERE_REPLY = re.compile(r"^where(?:'s| is) the reply\??$", re.IGNORECASE)
_META_QUESTION = re.compile(
    r"(?:how does (?:it|this|adisn|the harness|your harness) work"
    r"|what is adisn"
    r"|explain (?:the )?(?:harness|adisn|how (?:it|this|your harness) works)"
    r"|how (?:do you|does adisn) work"
    r"|tell me about (?:adisn|the harness|this harness))",
    re.IGNORECASE,
)

_CONTEXT_FILES = (
    "README.md",
    "harness/core/ARCHITECTURE.md",
    "HARNESS_SUMMARY.md",
    "harness/README.md",
)


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


def is_meta_question(request: str) -> bool:
    """True for questions about Adisn itself (architecture, purpose), not repo tasks."""
    text = request.strip()
    if not text:
        return False
    return bool(_META_QUESTION.search(text))


def harness_context_blurb(workspace_root: Path, *, max_chars: int = 6000) -> str:
    """Load concise harness docs for explaining how Adisn works."""
    blocks: list[str] = [
        "The user is asking how Adisn works. Explain clearly in plain language.",
        "Adisn is a local self-evolving agent harness: skills, tools, memory, cookbook/Ollama, agent loop.",
        "",
    ]
    used = 0
    for rel in _CONTEXT_FILES:
        path = workspace_root / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            continue
        chunk = f"--- {rel} ---\n{text[: max_chars - used - len(rel) - 20]}"
        blocks.append(chunk)
        used += len(chunk)
        if used >= max_chars:
            break
    return "\n".join(blocks)


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
