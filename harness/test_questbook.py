"""Tests for Questbook Ollama integration (mocked network)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from harness.core.questbook import Questbook


class TestQuestbookServer(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.q = Questbook(Path(self.tmp.name))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    @patch.object(Questbook, "_is_server_healthy", return_value=False)
    @patch.object(Questbook, "is_ollama_installed", return_value=True)
    def test_list_models_no_start_returns_fast(self, _installed, _healthy) -> None:
        models = self.q.list_models(start_server=False)
        self.assertEqual([], models)

    @patch.object(Questbook, "_is_server_healthy", return_value=False)
    @patch.object(Questbook, "is_ollama_installed", return_value=True)
    def test_ensure_server_running_no_block_when_disabled(self, _installed, _healthy) -> None:
        result = self.q.ensure_server_running(start_if_missing=False)
        self.assertFalse(result["running"])
        self.assertFalse(result["started"])

    @patch.object(Questbook, "_is_server_healthy", return_value=True)
    @patch.object(Questbook, "is_ollama_installed", return_value=True)
    def test_start_server_when_already_running(self, _installed, _healthy) -> None:
        result = self.q.start_server()
        self.assertTrue(result["ok"])
        self.assertFalse(result["started"])
        self.assertIn("already running", result["message"])

    @patch.object(Questbook, "_start_server", return_value=True)
    @patch.object(Questbook, "_is_server_healthy", side_effect=[False, True])
    @patch.object(Questbook, "is_ollama_installed", return_value=True)
    def test_start_server_spawns_when_down(self, _installed, _healthy, _spawn) -> None:
        result = self.q.start_server()
        self.assertTrue(result["ok"])
        self.assertTrue(result["started"])

    @patch.object(Questbook, "_is_server_healthy", return_value=False)
    def test_chat_returns_error_when_server_down(self, _healthy) -> None:
        result = self.q.chat("hello")
        self.assertFalse(result["ok"])
        self.assertEqual("server_unavailable", result["error"])

    @patch.object(Questbook, "_is_server_healthy", return_value=True)
    @patch.object(Questbook, "_default_model", return_value="test-model")
    def test_chat_parses_thinking_tags(self, _model, _healthy) -> None:
        tag = "think"
        o, c = f"<{tag}>", f"</{tag}>"
        payload = {
            "message": {"content": f"Visible {o}hidden reasoning{c} tail"},
        }
        mock_resp = MagicMock()
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.read.return_value = json.dumps(payload).encode("utf-8")
        mock_resp.status = 200

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = self.q.chat("hello", think=True)

        self.assertTrue(result["ok"])
        self.assertIn("hidden reasoning", result["thinking"])
        self.assertIn("Visible", result["message"])


if __name__ == "__main__":
    unittest.main()
