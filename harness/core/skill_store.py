"""Dynamic skill creation with folder indexes for low-token retrieval."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from harness.core.task_complexity import is_complex_task, should_create_skill
from harness.core.capability_index import format_skills_catalog


@dataclass
class SkillDescriptor:
    name: str
    skill_type: str
    description: str
    trigger_keywords: List[str]
    created_at: str
    path: str


class SkillStore:
    """Stores generated skills by type and keeps lightweight index files."""

    DEFAULT_TYPES = ("analysis", "build", "debug", "ops", "memory", "meta")
    STOPWORDS = {
        "the",
        "and",
        "for",
        "with",
        "from",
        "that",
        "this",
        "create",
        "build",
        "skill",
    }

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.skills_root = workspace_root / "skills"
        self.skills_root.mkdir(exist_ok=True)
        for item in self.DEFAULT_TYPES:
            self._ensure_type_folder(item)

    def catalog_prompt(self, request: str, *, limit: int = 8) -> str:
        self._update_global_index()
        return format_skills_catalog(self.skills_root / "INDEX.json", request, limit=limit)

    def generate_from_task(self, task: str) -> SkillDescriptor:
        if not should_create_skill(task):
            raise ValueError("task is not complex enough to persist a new skill")
        skill_type = self._infer_type(task)
        name = self._skill_name(task)
        path = self._ensure_type_folder(skill_type) / f"{name}.md"
        created_at = datetime.utcnow().isoformat() + "Z"
        keywords = self._keywords(task)

        body = (
            f"# {name}\n\n"
            f"Type: `{skill_type}`\n\n"
            "## Intent\n"
            f"{task}\n\n"
            "## Execution Outline\n"
            "- Parse objective and constraints.\n"
            "- Identify smallest valid action.\n"
            "- Execute one step and verify.\n"
            "- Persist result summary to memory.\n"
        )
        path.write_text(body, encoding="utf-8")

        summary = self._generate_summary(task)
        descriptor = SkillDescriptor(
            name=name,
            skill_type=skill_type,
            description=summary,
            trigger_keywords=keywords,
            created_at=created_at,
            path=str(path.relative_to(self.workspace_root)),
        )
        self._update_type_index(descriptor)
        self._update_global_index()
        return descriptor

    def match(self, task: str) -> Optional[SkillDescriptor]:
        if not is_complex_task(task):
            return None
        candidates = self._load_global_index()
        task_terms = set(self._keywords(task))
        task_l = task.lower()
        best: Optional[Dict] = None
        best_score = 0
        for item in candidates:
            # Keyword overlap score
            score = len(task_terms.intersection(set(item["trigger_keywords"]))) * 2
            # Contextual summary match bonus
            desc_l = item.get("description", "").lower()
            if any(term in desc_l for term in task_terms):
                score += 1
            if item["name"].lower() in task_l:
                score += 3

            if score > best_score:
                best = item
                best_score = score
        if not best or best_score < 3:
            return None
        return SkillDescriptor(**best)

    def _generate_summary(self, task: str) -> str:
        """Create a concise one-line summary of the skill's purpose."""
        clean = task.strip().replace("\n", " ")
        # Heuristic: extract the first sentence or first 120 chars
        match = re.match(r"^([^.!?]+[.!?])", clean)
        if match:
            summary = match.group(1)
        else:
            summary = clean[:120]
        if len(summary) > 150:
            summary = summary[:147] + "..."
        return summary

    def _ensure_type_folder(self, skill_type: str) -> Path:
        folder = self.skills_root / skill_type
        folder.mkdir(parents=True, exist_ok=True)
        index = folder / "INDEX.json"
        if not index.exists():
            index.write_text("[]", encoding="utf-8")
        return folder

    def _update_type_index(self, descriptor: SkillDescriptor) -> None:
        index_path = self.skills_root / descriptor.skill_type / "INDEX.json"
        entries = json.loads(index_path.read_text(encoding="utf-8"))
        entries = [e for e in entries if e["name"] != descriptor.name]
        entries.append(asdict(descriptor))
        entries.sort(key=lambda e: e["created_at"], reverse=True)
        index_path.write_text(json.dumps(entries, indent=2), encoding="utf-8")

    def _update_global_index(self) -> None:
        all_entries: List[Dict] = []
        for type_dir in self.skills_root.iterdir():
            if not type_dir.is_dir():
                continue
            idx = type_dir / "INDEX.json"
            if not idx.exists():
                continue
            all_entries.extend(json.loads(idx.read_text(encoding="utf-8")))
        all_entries.sort(key=lambda e: e["created_at"], reverse=True)
        (self.skills_root / "INDEX.json").write_text(
            json.dumps(all_entries, indent=2), encoding="utf-8"
        )

    def _load_global_index(self) -> List[Dict]:
        path = self.skills_root / "INDEX.json"
        if not path.exists():
            return []
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _skill_name(task: str) -> str:
        stem = re.sub(r"[^a-z0-9]+", "-", task.lower()).strip("-")
        return (stem or "generated-skill")[:60]

    @staticmethod
    def _keywords(task: str) -> List[str]:
        words = [w for w in re.split(r"[^a-zA-Z0-9]+", task.lower()) if len(w) > 2]
        dedup: List[str] = []
        for w in words:
            if w not in dedup and w not in SkillStore.STOPWORDS:
                dedup.append(w)
        return dedup[:12]

    def _infer_type(self, task: str) -> str:
        task_l = task.lower()
        if any(x in task_l for x in ("debug", "fix", "error", "trace")):
            return "debug"
        if any(x in task_l for x in ("deploy", "git", "docker", "infra", "aws")):
            return "ops"
        if any(x in task_l for x in ("refactor", "build", "create", "implement", "write")):
            return "build"
        if any(x in task_l for x in ("memory", "context", "summary", "compress")):
            return "memory"
        if any(x in task_l for x in ("self", "rewrite", "harness", "skill")):
            return "meta"
        return "analysis"
