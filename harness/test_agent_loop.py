"""Tests for Claude Code-style agent loop."""

from __future__ import annotations

import unittest

from harness.core.agent_loop import AgentLoop, _extract_decision, _heuristic_decision
from harness.core.thinking import ThinkingMode


class TestAgentLoop(unittest.TestCase):
    def test_extract_decision_json(self) -> None:
        text = 'Planning...\n{"action":"respond","input":"hello","reason":"done"}'
        d = _extract_decision(text)
        self.assertEqual("respond", d["action"])

    def test_heuristic_decision_uses_skill(self) -> None:
        d = _heuristic_decision(
            "fix bug",
            {"skill_name": "debug-skill", "next_action": "debug"},
            [],
        )
        self.assertEqual("use_skill", d["action"])

    def test_loop_completes_offline_fast(self) -> None:
        loop = AgentLoop(
            thinking=ThinkingMode(enabled=True),
            chat_fn=lambda *a, **k: {"ok": False},
            server_running=False,
            max_steps=3,
        )
        result = loop.run(
            "hello",
            skill_context={"skill_name": "test", "next_action": "analyze", "scope": "global"},
            local_act_fn=lambda action, ctx: {"ok": True, "message": "done"},
        )
        self.assertIn("message", result)
        self.assertGreater(result["loop_steps"], 0)
        self.assertTrue(result.get("thinking"))


if __name__ == "__main__":
    unittest.main()
