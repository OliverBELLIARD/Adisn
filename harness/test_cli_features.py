"""CLI integration tests (startup, warnings, /think)."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from harness.cli.cookbook_commands import format_cookbook_result
from harness.cli.display import OLLAMA_WARNING, print_agent_response
from harness.cli.main import _handle_user_prompt, _slash_command_specs
from harness.core.agent import HarnessAgent

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestCliFeatures(unittest.TestCase):
    def test_slash_specs_include_think_and_cookbook(self) -> None:
        commands = {spec.command for spec in _slash_command_specs()}
        self.assertIn("/think", commands)
        self.assertIn("/cookbook scan", commands)
        self.assertIn("/cookbook recommend", commands)

    @patch("harness.cli.main.print_agent_response")
    @patch("harness.cli.main.ActivityRenderer")
    @patch("harness.cli.main.print_ollama_warning")
    def test_handle_prompt_warns_when_ollama_down(
        self, mock_warn, mock_live_cls, mock_print
    ) -> None:
        live = mock_live_cls.return_value
        with tempfile.TemporaryDirectory() as tmp:
            agent = HarnessAgent(workspace_root=Path(tmp))
            with patch.object(agent, "is_ollama_server_running", return_value=False):
                with patch.object(agent, "process_request", return_value={"message": "ok"}):
                    _handle_user_prompt(agent, "hello world")
        mock_warn.assert_called_once()
        live.start.assert_called_once()
        live.finish.assert_called_once()
        mock_print.assert_called_once()

    def test_format_recommend_not_shown_as_scan(self) -> None:
        text = format_cookbook_result(
            {
                "ok": True,
                "profile": "balanced",
                "budget_gb": 6.0,
                "hardware": {"cpu": "x", "ram_gb": 16, "vram_budget_gb": 6, "gpus": []},
                "recommendations": [{"score": 80, "name": "qwen2.5:7b", "quant": "Q4_K_M", "vram_gb": 5.0}],
            }
        )
        self.assertIn("Recommendations", text)
        self.assertNotIn("Cookbook hardware scan", text)

    def test_print_agent_response_shows_message(self) -> None:
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            print_agent_response(
                {
                    "message": "hello",
                    "thinking": "step\nplan",
                    "warning": OLLAMA_WARNING,
                }
            )
        out = buf.getvalue()
        self.assertIn("hello", out)
        self.assertIn("step", out)

    def test_startup_shows_ollama_warning(self) -> None:
        import os

        env = {**os.environ, "OLLAMA_HOST": "127.0.0.1:19999"}
        proc = subprocess.run(
            [sys.executable, "-m", "adisn"],
            input="/quit\n",
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            env=env,
        )
        self.assertEqual(0, proc.returncode)
        combined = proc.stdout + proc.stderr
        self.assertIn("Warning: Ollama server is not available", combined)


if __name__ == "__main__":
    unittest.main()
