"""Memory manager optimized for compact, recoverable context."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict


class MemoryManager:
    """Manages structured memory files under `.remember/`."""

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.memory_dir = base_dir / ".remember"
        self.memory_dir.mkdir(exist_ok=True)
        self.now_file = self.memory_dir / "now.md"
        self.recent_file = self.memory_dir / "recent.md"
        self.index_file = self.memory_dir / "index.json"
        if not self.now_file.exists():
            self.now_file.write_text("# Session Buffer\n", encoding="utf-8")
        if not self.recent_file.exists():
            self.recent_file.write_text("# Recent Notes\n", encoding="utf-8")
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
