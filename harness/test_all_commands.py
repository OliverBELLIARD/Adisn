"""Run every Adisn CLI command and report pass/fail (audit harness)."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _run_interactive(script: str, timeout: int = 45) -> tuple[int, str, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "adisn"],
        input=script,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _run_tool(action: str, value: str = "", timeout: int = 30) -> tuple[int, dict]:
    cmd = [sys.executable, "-m", "adisn", "tool", "--tool-flag", "--tool-action", action]
    if value:
        cmd.extend(["--tool-input", value])
    proc = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        data = {"parse_error": True, "raw": proc.stdout[:500]}
    return proc.returncode, data


def _run_cli(command: str) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "adisn", command],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    return proc.returncode, proc.stdout + proc.stderr


class TestAllCommandsAudit(unittest.TestCase):
    """End-to-end command audit (non-interactive / piped)."""

    def test_non_interactive_status(self) -> None:
        code, out = _run_cli("status")
        self.assertEqual(0, code)
        self.assertIn("model_token_window", out)

    def test_non_interactive_help(self) -> None:
        code, out = _run_cli("help")
        self.assertEqual(0, code)
        self.assertIn("adisn", out.lower())

    def test_slash_help(self) -> None:
        code, out, _ = _run_interactive("/help\n/quit\n")
        self.assertEqual(0, code)
        self.assertIn("Slash commands", out)

    def test_slash_status(self) -> None:
        code, out, _ = _run_interactive("/status\n/quit\n")
        self.assertEqual(0, code)
        self.assertIn("model_token_window", out)

    def test_slash_think(self) -> None:
        code, out, _ = _run_interactive("/think\n/quit\n")
        self.assertEqual(0, code)
        self.assertIn("Extended thinking", out)

    def test_slash_think_expand(self) -> None:
        code, out, _ = _run_interactive("/think expand\n/quit\n")
        self.assertEqual(0, code)
        self.assertIn("expanded", out.lower())

    def test_slash_scope(self) -> None:
        code, out, _ = _run_interactive("/scope workspace\n/scope global\n/quit\n")
        self.assertEqual(0, code)
        self.assertIn('"scope"', out)

    def test_slash_rollback(self) -> None:
        code, out, _ = _run_interactive("/rollback\n/quit\n")
        self.assertEqual(0, code)
        self.assertIn("ok", out.lower())

    def test_slash_ollama_serve(self) -> None:
        code, out, _ = _run_interactive("/ollama serve\n/quit\n")
        self.assertEqual(0, code)
        self.assertTrue(
            "already running" in out.lower() or "started" in out.lower() or "Ollama server" in out
        )

    def test_tool_ollama_serve(self) -> None:
        code, data = _run_tool("ollama_serve")
        self.assertEqual(0, code)
        self.assertIn("result", data)

    def test_slash_ollama_status(self) -> None:
        code, out, _ = _run_interactive("/ollama status\n/quit\n")
        self.assertEqual(0, code)
        self.assertIn("server_running", out)

    def test_slash_ollama_list(self) -> None:
        code, out, _ = _run_interactive("/ollama list\n/quit\n")
        self.assertEqual(0, code)
        self.assertTrue("installed" in out or "models" in out or "server_unavailable" in out)

    def test_slash_ollama_profiles(self) -> None:
        code, out, _ = _run_interactive("/ollama profiles\n/quit\n")
        self.assertEqual(0, code)
        self.assertIn("profiles", out)

    def test_slash_cookbook_scan(self) -> None:
        code, out, _ = _run_interactive("/cookbook scan\n/quit\n")
        self.assertEqual(0, code)
        self.assertIn("Cookbook hardware scan", out)

    def test_slash_cookbook_recommend(self) -> None:
        code, out, _ = _run_interactive("/cookbook recommend balanced\n/quit\n")
        self.assertEqual(0, code)
        self.assertTrue("Recommendations" in out or "recommendations" in out)

    def test_slash_cookbook_list(self) -> None:
        code, out, _ = _run_interactive("/cookbook list\n/quit\n")
        self.assertEqual(0, code)
        self.assertIn("qwen2.5", out)

    def test_slash_cookbook_installed(self) -> None:
        code, out, _ = _run_interactive("/cookbook installed\n/quit\n")
        self.assertEqual(0, code)
        self.assertIn("installed", out)

    def test_slash_cookbook_deps(self) -> None:
        code, out, _ = _run_interactive("/cookbook deps\n/quit\n")
        self.assertEqual(0, code)
        self.assertIn("Cookbook dependencies", out)

    def test_slash_cookbook_status(self) -> None:
        code, out, _ = _run_interactive("/cookbook status\n/quit\n")
        self.assertEqual(0, code)
        self.assertIn("active_model", out)

    def test_slash_cookbook_serves(self) -> None:
        code, out, _ = _run_interactive("/cookbook serves\n/quit\n")
        self.assertEqual(0, code)
        self.assertIn("serves", out)

    def test_slash_cookbook_use(self) -> None:
        code, out, _ = _run_interactive("/cookbook use llama3.2:3b\n/quit\n")
        self.assertEqual(0, code)
        self.assertIn("llama3.2:3b", out)

    def test_slash_cookbook_providers(self) -> None:
        code, out, _ = _run_interactive("/cookbook providers\n/quit\n")
        self.assertEqual(0, code)
        self.assertIn("providers", out)

    def test_slash_cookbook_provider_add_rm(self) -> None:
        script = (
            "/cookbook provider add testprov http://127.0.0.1:9999/v1\n"
            "/cookbook provider rm testprov\n"
            "/quit\n"
        )
        code, out, _ = _run_interactive(script)
        self.assertEqual(0, code)
        self.assertIn("testprov", out)

    def test_slash_cookbook_serve_ollama(self) -> None:
        code, out, _ = _run_interactive("/cookbook serve ollama llama3.2:3b\n/quit\n")
        self.assertEqual(0, code)
        self.assertTrue("ollama" in out.lower())

    def test_slash_rewrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "note.txt"
            script = (
                f"/rewrite {target}\n"
                "hello\n"
                "test\n"
                "/quit\n"
            )
            code, out, err = _run_interactive(script, timeout=30)
            self.assertEqual(0, code, msg=err)
            self.assertTrue(target.exists() or '"ok"' in out)

    def test_user_prompt_agent_loop(self) -> None:
        code, out, _ = _run_interactive("ping\n/quit\n")
        self.assertEqual(0, code)
        self.assertIn("agent loop", out.lower())

    def test_tool_status(self) -> None:
        code, data = _run_tool("status")
        self.assertEqual(0, code)
        self.assertIn("result", data)

    def test_tool_process(self) -> None:
        code, data = _run_tool("process", "hello tool mode")
        self.assertEqual(0, code)
        self.assertIn("result", data)

    def test_tool_scope(self) -> None:
        code, data = _run_tool("scope", "workspace")
        self.assertEqual(0, code)
        self.assertTrue(data.get("ok"))

    def test_tool_cookbook_scan(self) -> None:
        code, data = _run_tool("cookbook_scan")
        self.assertEqual(0, code)
        self.assertTrue(data.get("ok"))

    def test_tool_cookbook_recommend(self) -> None:
        code, data = _run_tool("cookbook_recommend", "fast")
        self.assertEqual(0, code)
        self.assertTrue(data.get("ok"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
