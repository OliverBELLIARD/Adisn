"""Detect when a prompt requires harness tools (filesystem, shell, code changes)."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

from harness.core.direct_reply import try_direct_reply, is_meta_question

_TOOL_HINTS = (
    "list",
    "file",
    "files",
    "directory",
    "folder",
    "dir ",
    " read ",
    "write",
    "grep",
    "search",
    "find ",
    "show me",
    "what's in",
    "whats in",
    "contents",
    "workspace",
    "harness",
    "source code",
    "codebase",
    "run ",
    "execute",
    "shell",
    "command",
    "tool",
    "create ",
    "modify",
    "edit ",
    "fix ",
    "implement",
    "path",
    "python -m",
    "ollama",
    "skill",
    "rewrite",
    "ls ",
    "pwd",
    "cat ",
    "tree",
)

_REFUSAL_HINTS = (
    "don't have access",
    "do not have access",
    "don't possess",
    "do not possess",
    "i can't",
    "i cannot",
    "unable to",
    "cannot directly",
    "no direct access",
    "lack access",
    "without specific permissions",
    "direct access to files",
    "direct access",
)


def needs_tools(request: str) -> bool:
    """True when the user expects filesystem, shell, or harness mutation."""
    text = request.strip()
    if not text or try_direct_reply(text):
        return False
    if is_meta_question(text):
        return False
    low = text.lower()
    return any(hint in low for hint in _TOOL_HINTS)


def is_refusal_message(text: str) -> bool:
    low = text.lower()
    return any(hint in low for hint in _REFUSAL_HINTS)


_INVALID_PATH_TOKENS = {
    "this",
    "the",
    "directory",
    "folder",
    "here",
    "workspace",
    "files",
    "file",
    "local",
    "system",
}


def _normalize_tool_path(raw: str) -> str:
    token = raw.strip().strip("`\"'./\\")
    if not token or token.lower() in _INVALID_PATH_TOKENS:
        return "."
    return raw.strip().strip("`\"'")


def _extract_path_from_request(request: str) -> str:
    quoted = re.search(r'["\']([a-zA-Z]:\\[^"\']*)["\']', request)
    if quoted:
        return quoted.group(1).rstrip("\\/")
    path_match = re.search(
        r"(?:in|at|under|from|path|directory)\??\s+[`\"']?([a-zA-Z]:\\[^\s`\"']+|/[^\s`\"']+|[\w./-]+)[`\"']?",
        request,
        re.IGNORECASE,
    )
    if path_match:
        return _normalize_tool_path(path_match.group(1))
    return "."


def infer_tool_call(request: str) -> Optional[Dict[str, Any]]:
    """Best-effort mapping from natural language to a harness tool invocation."""
    low = request.lower()
    path = _extract_path_from_request(request)

    if any(
        w in low
        for w in (
            "list",
            "files",
            "directory",
            "folder",
            "contents",
            "what's in",
            "whats in",
            "see the contents",
            "ls ",
            "dir",
        )
    ):
        return {"tool": "list_dir", "args": {"path": path}}
    if any(w in low for w in ("read ", "open file", "show file", "cat ")):
        if path != ".":
            return {"tool": "read_file", "args": {"path": path}}
    if "grep" in low or "search for" in low:
        pattern_match = re.search(r"search for\s+[`\"']?([^\s`\"']+)", request, re.IGNORECASE)
        pattern = pattern_match.group(1) if pattern_match else "."
        return {"tool": "grep", "args": {"pattern": pattern, "path": path}}
    if any(w in low for w in ("run ", "execute", "shell", "command")):
        cmd_match = re.search(r"(?:run|execute)\s+[`\"']?(.+)[`\"']?$", request, re.IGNORECASE)
        if cmd_match:
            return {"tool": "shell", "args": {"command": cmd_match.group(1).strip()}}
    if any(w in low for w in ("write", "edit", "modify", "rewrite", "change code", "implement")):
        return None
    return None


def tool_call_json(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=True)
