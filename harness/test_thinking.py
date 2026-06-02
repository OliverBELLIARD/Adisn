"""Tests for extended thinking mode."""

from __future__ import annotations

import unittest

from harness.core.thinking import (
    ThinkingMode,
    format_thinking_for_display,
    local_thinking_plan,
    split_thinking_and_response,
)


class TestThinkingMode(unittest.TestCase):
    def test_toggle(self) -> None:
        mode = ThinkingMode(enabled=True)
        self.assertFalse(mode.toggle())
        self.assertFalse(mode.enabled)
        self.assertTrue(mode.toggle())

    def test_split_redacted_reasoning_tags(self) -> None:
        tag = "think"
        o, c = f"<{tag}>", f"</{tag}>"
        raw = f"Before {o}inner thought{c} After"
        thinking, visible = split_thinking_and_response(raw)
        self.assertIn("inner thought", thinking)
        self.assertIn("Before", visible)
        self.assertIn("After", visible)

    def test_split_xml_thinking_tags(self) -> None:
        raw = "Answer <thinking>step one</thinking> done"
        thinking, visible = split_thinking_and_response(raw)
        self.assertEqual("step one", thinking)
        self.assertIn("done", visible)

    def test_local_plan_mentions_offline_backend(self) -> None:
        plan = local_thinking_plan(
            "fix npm build",
            predicted_action="debug",
            skill_name=None,
            scope="global",
            ollama_available=False,
        )
        self.assertIn("offline", plan.lower())
        self.assertIn("debug", plan)

    def test_format_collapses_long_thinking(self) -> None:
        text = "\n".join(f"line {i}" for i in range(10))
        body, truncated = format_thinking_for_display(text, max_collapsed_lines=3)
        self.assertTrue(truncated)
        self.assertIn("line 0", body)
        self.assertIn("more lines", body)


if __name__ == "__main__":
    unittest.main()
