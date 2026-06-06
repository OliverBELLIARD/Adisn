"""Format skills/INDEX.json and tools/INDEX.json for intent-based selection."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _terms(text: str) -> set[str]:
    words = [w for w in re.split(r"[^a-zA-Z0-9]+", text.lower()) if len(w) > 2]
    stop = {"the", "and", "for", "with", "from", "that", "this", "you", "your", "how", "what"}
    return {w for w in words if w not in stop}


def _score_entry(terms: set[str], name: str, summary: str, keywords: List[str]) -> int:
    score = len(terms.intersection(set(keywords))) * 2
    name_l = name.lower()
    summary_l = summary.lower()
    if any(term in name_l for term in terms):
        score += 3
    if any(term in summary_l for term in terms):
        score += 1
    return score


def rank_index_entries(request: str, entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    terms = _terms(request)
    scored: List[Tuple[int, Dict[str, Any]]] = []
    for entry in entries:
        keywords = entry.get("trigger_keywords") or entry.get("keywords") or []
        if not keywords:
            keywords = list(
                _terms(f"{entry.get('name', '')} {entry.get('summary', entry.get('description', ''))}")
            )
        score = _score_entry(
            terms,
            str(entry.get("name", "")),
            str(entry.get("summary", entry.get("description", ""))),
            list(keywords),
        )
        scored.append((score, entry))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [entry for score, entry in scored if score > 0] or [entry for _, entry in scored]


def format_skills_catalog(skills_index_path: Path, request: str, *, limit: int = 8) -> str:
    if not skills_index_path.exists():
        return "(no skills indexed yet)"
    entries = json.loads(skills_index_path.read_text(encoding="utf-8"))
    ranked = rank_index_entries(request, entries)[:limit]
    lines = []
    for entry in ranked:
        name = entry.get("name", "?")
        summary = entry.get("description", entry.get("summary", ""))[:120]
        action = entry.get("skill_type", "analysis")
        lines.append(f"- {name} [{action}]: {summary}")
    return "\n".join(lines) if lines else "(no skills indexed yet)"


def format_tools_catalog(tools_index_path: Path, request: str, *, limit: int = 12) -> str:
    if not tools_index_path.exists():
        return "(no tools indexed yet)"
    entries = json.loads(tools_index_path.read_text(encoding="utf-8"))
    ranked = rank_index_entries(request, entries)[:limit]
    lines = []
    for entry in ranked:
        name = entry.get("name", "?")
        summary = entry.get("summary", "")[:120]
        args = entry.get("args", {})
        arg_text = ", ".join(f"{k}: {v}" for k, v in args.items()) if args else ""
        arg_suffix = f" ({arg_text})" if arg_text else ""
        lines.append(f"- {name}{arg_suffix}: {summary}")
    return "\n".join(lines) if lines else "(no tools indexed yet)"


def build_capability_catalog(
    workspace_root: Path,
    request: str,
    *,
    skills_limit: int = 8,
    tools_limit: int = 12,
) -> str:
    skills_path = workspace_root / "skills" / "INDEX.json"
    tools_path = workspace_root / "tools" / "INDEX.json"
    skills_block = format_skills_catalog(skills_path, request, limit=skills_limit)
    tools_block = format_tools_catalog(tools_path, request, limit=tools_limit)
    return (
        "Choose capabilities based on user intent. Prefer the best-matching skill or tool.\n"
        "Skills (action use_skill with skill name, or read_skill tool):\n"
        f"{skills_block}\n\n"
        "Tools (action run_tool with JSON {{\"tool\":\"name\",\"args\":{{...}}}}):\n"
        f"{tools_block}\n\n"
        "Read skills/INDEX.json or tools/INDEX.json for the full catalog."
    )


def suggest_tool_call(workspace_root: Path, request: str) -> Optional[Dict[str, Any]]:
    """Pick the best-matching tool from tools/INDEX.json for offline/refusal fallback."""
    from harness.core.direct_reply import is_meta_question

    if is_meta_question(request):
        return None
    tools_path = workspace_root / "tools" / "INDEX.json"
    if not tools_path.exists():
        return None
    entries = json.loads(tools_path.read_text(encoding="utf-8"))
    ranked = rank_index_entries(request, entries)
    if not ranked:
        return None
    name = str(ranked[0].get("name", ""))
    if name == "list_dir":
        return {"tool": "list_dir", "args": {"path": "."}}
    if name == "read_file":
        return {"tool": "read_file", "args": {"path": str(ranked[0].get("default_path", "README.md"))}}
    if name == "grep":
        return {"tool": "grep", "args": {"pattern": ".", "path": "."}}
    if name == "read_skill":
        skill_name = ranked[0].get("default_skill") or ranked[0].get("name")
        return {"tool": "read_skill", "args": {"name": skill_name}}
    return {"tool": name, "args": {}}
