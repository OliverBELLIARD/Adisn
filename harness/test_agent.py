"""Tests for HarnessAgent behavior."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from harness.core.agent import HarnessAgent
from harness.core.messages import OLLAMA_WARNING


class TestHarnessAgent(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.agent = HarnessAgent(workspace_root=Path(self.tmp.name))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    @patch.object(HarnessAgent, "is_ollama_server_running", return_value=False)
    def test_process_request_fast_when_ollama_down(self, _running) -> None:
        start = time.perf_counter()
        result = self.agent.process_request("create a debug skill for tests")
        elapsed = time.perf_counter() - start
        self.assertLess(elapsed, 3.0, "prompt path must not block on Ollama")
        self.assertEqual(OLLAMA_WARNING, result["warning"])
        self.assertIn("message", result)
        self.assertIn("agent_loop", result)
        self.assertGreater(result["agent_loop"]["step_count"], 0)

    @patch.object(HarnessAgent, "is_ollama_server_running", return_value=False)
    @patch("harness.core.questbook.Questbook._is_server_healthy", return_value=False)
    def test_get_state_does_not_start_server(self, _healthy, _running) -> None:
        with patch.object(
            self.agent.questbook,
            "ensure_server_running",
            wraps=self.agent.questbook.ensure_server_running,
        ) as ensure:
            state = self.agent.get_state()
            ensure.assert_not_called()
        self.assertFalse(state["ollama_server_running"])

    def test_toggle_thinking(self) -> None:
        self.assertTrue(self.agent.thinking.enabled)
        self.agent.toggle_thinking()
        self.assertFalse(self.agent.thinking.enabled)

    @patch.object(HarnessAgent, "is_ollama_server_running", return_value=True)
    def test_process_request_runs_agent_loop(self, _running) -> None:
        with patch.object(
            self.agent.cookbook,
            "chat",
            return_value={
                "ok": True,
                "message": '{"action":"respond","input":"from model","reason":"ok"}',
                "thinking": "model reasoning",
            },
        ):
            result = self.agent.process_request("hello", thinking=True)
        self.assertIn("message", result)
        self.assertIn("agent_loop", result)


if __name__ == "__main__":
    unittest.main()
