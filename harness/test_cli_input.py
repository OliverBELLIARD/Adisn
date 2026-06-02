"""Regression: interactive prompt must accept typing."""

from __future__ import annotations

import inspect
import subprocess
import sys
import unittest
from pathlib import Path

from harness.cli.main import _ctrl_c_key_bindings

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestCliInput(unittest.TestCase):
    def test_ctrl_c_bindings_do_not_use_keys_any(self) -> None:
        """Keys.Any handlers swallow printable input — never register them."""
        source = inspect.getsource(_ctrl_c_key_bindings)
        self.assertNotIn("Keys.Any", source)

    def test_piped_prompt_accepts_line(self) -> None:
        proc = subprocess.run(
            [sys.executable, "-m", "adisn"],
            input="/status\n/quit\n",
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        self.assertEqual(0, proc.returncode, msg=proc.stderr)
        self.assertIn("model_token_window", proc.stdout)
        self.assertIn("Exiting Adisn.", proc.stdout)

    def test_piped_user_prompt_runs_agent_loop(self) -> None:
        proc = subprocess.run(
            [sys.executable, "-m", "adisn"],
            input="say hello\n/quit\n",
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        self.assertEqual(0, proc.returncode, msg=proc.stderr)
        self.assertIn("agent loop", proc.stdout.lower())
        self.assertIn("Exiting Adisn.", proc.stdout)

    def test_piped_cookbook_scan(self) -> None:
        proc = subprocess.run(
            [sys.executable, "-m", "adisn"],
            input="/cookbook scan\n/quit\n",
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        self.assertEqual(0, proc.returncode)
        self.assertIn("Cookbook hardware scan", proc.stdout)


if __name__ == "__main__":
    unittest.main()
