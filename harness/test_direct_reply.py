"""Tests for direct conversational replies and model resolution."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from harness.core.agent_loop import AgentLoop
from harness.core.direct_reply import try_direct_reply
from harness.core.questbook import Questbook
from harness.core.thinking import ThinkingMode


class TestDirectReply(unittest.TestCase):
    def test_reply_with_ok(self) -> None:
        self.assertEqual("OK", try_direct_reply("Reply with OK"))

    def test_where_is_reply(self) -> None:
        self.assertIsNotNone(try_direct_reply("Where's the reply?"))


class TestAgentLoopDirectReply(unittest.TestCase):
    def test_simple_prompt_returns_ok_without_meta(self) -> None:
        loop = AgentLoop(
            thinking=ThinkingMode(enabled=True),
            chat_fn=lambda *a, **k: {"ok": False},
            server_running=False,
        )
        result = loop.run(
            "Reply with OK",
            skill_context={"skill_name": "reply-with-ok", "next_action": "analyze", "scope": "global"},
            local_act_fn=lambda action, ctx: {"ok": True, "message": "ignored"},
        )
        self.assertEqual("OK", result["message"])
        self.assertEqual(0, result["loop_steps"])


class TestResolveModel(unittest.TestCase):
    def test_resolve_picks_installed_when_active_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            q = Questbook(Path(tmp))
            with patch.object(q, "installed_model_names", return_value=["qwen3.5:latest"]):
                self.assertEqual("qwen3.5:latest", q.resolve_model("llama3.2:3b"))


if __name__ == "__main__":
    unittest.main()
