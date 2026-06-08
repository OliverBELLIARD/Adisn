"""Memory manager optimized for compact, recoverable context."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class MemoryManager:
    """Manages structured memory files under `.remember/`."""

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.memory_dir = base_dir / ".adisn" / "chats"
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.now_file = self.memory_dir / "now.md"
        self.recent_file = self.memory_dir / "recent.md"
        self.mistakes_file = self.memory_dir / "past_mistakes.md"
        self.index_file = self.memory_dir / "index.json"
        if not self.now_file.exists():
            self.now_file.write_text("# Session Buffer\n", encoding="utf-8")
        if not self.recent_file.exists():
            self.recent_file.write_text("# Recent Notes\n", encoding="utf-8")
        if not self.mistakes_file.exists():
            self.mistakes_file.write_text("# Past Mistakes\nRecord failed approaches here to avoid repeating them.\n", encoding="utf-8")
        if not self.index_file.exists():
            self.index_file.write_text("[]", encoding="utf-8")

    def append_interaction(self, request: str, response: Dict[str, Any]) -> None:
        stamp = datetime.utcnow().isoformat() + "Z"
        block = (
            f"\n## {stamp}\n"
            f"- request: {request}\n"
            f"- response: {json.dumps(response, ensure_ascii=True)}\n"
        )
        with self.now_file.open("a", encoding="utf-8") as fh:
            fh.write(block)
        self._append_index("interaction", request[:160], block)
        self._compact_now()

    def append_note(self, category: str, content: str) -> None:
        stamp = datetime.utcnow().isoformat() + "Z"
        block = f"\n## {stamp} [{category}]\n{content}\n"
        with self.recent_file.open("a", encoding="utf-8") as fh:
            fh.write(block)
        self._append_index(category, content[:160], block)

    def count_entries(self) -> int:
        return len(json.loads(self.index_file.read_text(encoding="utf-8")))

    def get_distribution(self) -> Dict[str, Any]:
        entries = json.loads(self.index_file.read_text(encoding="utf-8"))
        dist = {}
        total_tokens = 0
        for e in entries:
            cat = e.get("category", "unknown")
            tokens = e.get("tokens_estimate", 0)
            dist[cat] = dist.get(cat, 0) + tokens
            total_tokens += tokens
        return {
            "total_entries": len(entries),
            "total_tokens_estimate": total_tokens,
            "categories": dist
        }

    def _append_index(self, category: str, summary: str, content: str) -> None:
        entries = json.loads(self.index_file.read_text(encoding="utf-8"))
        entries.append(
            {
                "time": datetime.utcnow().isoformat() + "Z",
                "category": category,
                "summary": summary,
                "tokens_estimate": max(1, len(content) // 4),
            }
        )
        entries = entries[-300:]
        self.index_file.write_text(json.dumps(entries, indent=2), encoding="utf-8")

    def _compact_now(self) -> None:
        lines = self.now_file.read_text(encoding="utf-8").splitlines()
        if len(lines) <= 240:
            return
        clipped = "\n".join(lines[-180:])
        self.now_file.write_text("# Session Buffer\n" + clipped + "\n", encoding="utf-8")

    def list_interactions(self, limit: int = 30) -> List[Dict[str, Any]]:
        """Parse conversation turns from now.md for /history."""
        if not self.now_file.exists():
            return []
        entries: List[Dict[str, Any]] = []
        current: Dict[str, Any] = {}
        for line in self.now_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("## "):
                if current.get("request"):
                    entries.append(current)
                current = {"time": line[3:].strip(), "request": "", "response_preview": ""}
            elif line.startswith("- request: "):
                current["request"] = line[len("- request: "):]
            elif line.startswith("- response: "):
                raw = line[len("- response: "):]
                try:
                    resp = json.loads(raw)
                    current["response_preview"] = str(resp.get("message", ""))[:160]
                except json.JSONDecodeError:
                    current["response_preview"] = raw[:160]
        if current.get("request"):
            entries.append(current)
        numbered = []
        start = max(1, len(entries) - limit + 1)
        for idx, entry in enumerate(entries[-limit:], start=start):
            numbered.append({"id": idx, **entry})
        return numbered

    def get_interaction(self, entry_id: int) -> Optional[Dict[str, Any]]:
        entries = self.list_interactions(limit=500)
        for entry in entries:
            if entry.get("id") == entry_id:
                return entry
        return None

    def record_mistake(self, task: str, approach: str, result: str) -> None:
        stamp = datetime.utcnow().isoformat() + "Z"
        block = (
            f"\n## {stamp}\n"
            f"- **Task**: {task}\n"
            f"- **Failed Approach**: {approach}\n"
            f"- **Result**: {result}\n"
        )
        with self.mistakes_file.open("a", encoding="utf-8") as fh:
            fh.write(block)
        self._append_index("mistake", task[:160], block)

    def read_memory(self, file_name: str = "now.md", limit_lines: int = 200) -> Dict[str, Any]:
        """Read content from a memory file."""
        target = self.memory_dir / file_name
        if not target.exists():
            return {"ok": False, "error": f"Memory file {file_name} not found"}

        content = target.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()
        body = "\n".join(lines[-limit_lines:])

        return {
            "ok": True,
            "file": file_name,
            "total_lines": len(lines),
            "content": body
        }
