"""Context management tuned for constrained token windows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class ContextChunk:
    role: str
    content: str
    tokens: int


class ContextWindowManager:
    """Maintains a rolling prompt with deterministic compression."""

    def __init__(
        self,
        max_tokens: int = 50_000,
        reserve_tokens: int = 10_000,
        compact_threshold_ratio: float = 0.85,
    ):
        self.max_tokens = max_tokens
        self.reserve_tokens = reserve_tokens
        self.target_tokens = max_tokens - reserve_tokens
        self.compact_threshold_ratio = compact_threshold_ratio
        self.compact_threshold_tokens = int(max_tokens * compact_threshold_ratio)
        self._chunks: List[ContextChunk] = []

    @staticmethod
    def estimate_tokens(text: str) -> int:
        # Approximation for quick budgeting.
        return max(1, len(text) // 4)

    def add(self, role: str, content: str) -> None:
        self._chunks.append(
            ContextChunk(role=role, content=content, tokens=self.estimate_tokens(content))
        )
        self._compress_if_needed()

    def snapshot(self) -> List[ContextChunk]:
        return list(self._chunks)

    def clear(self) -> None:
        self._chunks = []

    def count(self) -> int:
        return len(self._chunks)

    def manual_summarize(self) -> Dict[str, Any]:
        """Manually trigger summarization of the oldest half of the history."""
        if len(self._chunks) < 4:
            return {"ok": False, "error": "History too short to summarize"}

        initial_count = len(self._chunks)
        to_summarize = initial_count // 2

        summarized_content = (
            "[manual-summarization]\n"
            "This block contains a compressed summary of the older conversation history "
            "to save context window space. Older turns are summarized below:\n\n"
        )
        for _ in range(to_summarize):
            chunk = self._chunks.pop(0)
            role_label = chunk.role.upper()
            summarized_content += f"### {role_label} Turn\n{self._clip(chunk.content, 300)}\n\n"

        new_chunk = ContextChunk(
            role="system",
            content=summarized_content,
            tokens=self.estimate_tokens(summarized_content)
        )
        self._chunks.insert(0, new_chunk)

        return {
            "ok": True,
            "removed_count": to_summarize,
            "new_count": len(self._chunks),
            "tokens": new_chunk.tokens
        }

    def format_for_prompt(self, max_chars: int = 6000) -> str:
        if not self._chunks:
            return ""
        lines: List[str] = []
        used = 0
        for chunk in self._chunks[-24:]:
            snippet = chunk.content
            if len(snippet) > 800:
                snippet = snippet[:800] + "…"
            line = f"{chunk.role}: {snippet}"
            if used + len(line) > max_chars:
                break
            lines.append(line)
            used += len(line)
        return "\n".join(lines)

    def _compress_if_needed(self) -> None:
        total = self._total_tokens()
        if total <= self.compact_threshold_tokens:
            return
        while self._total_tokens() > self.target_tokens and len(self._chunks) > 3:
            a = self._chunks.pop(0)
            b = self._chunks.pop(0)
            summary = self._summarize_pair(a, b)
            self._chunks.insert(0, summary)

    def _summarize_pair(self, a: ContextChunk, b: ContextChunk) -> ContextChunk:
        content = (
            "[compressed-history]\n"
            f"- {a.role}: {self._clip(a.content)}\n"
            f"- {b.role}: {self._clip(b.content)}"
        )
        return ContextChunk(
            role="system",
            content=content,
            tokens=self.estimate_tokens(content),
        )

    @staticmethod
    def _clip(text: str, length: int = 300) -> str:
        if len(text) <= length:
            return text
        return text[:length].rstrip() + "..."

    def _total_tokens(self) -> int:
        return sum(chunk.tokens for chunk in self._chunks)
