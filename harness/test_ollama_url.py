"""Tests for Ollama host URL normalization."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from harness.core.ollama_url import resolve_ollama_hosts
from harness.core.questbook import Questbook


class TestResolveOllamaHosts(unittest.TestCase):
    def test_default_localhost(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OLLAMA_HOST", None)
            client, configured = resolve_ollama_hosts()
        self.assertEqual(client, "http://127.0.0.1:11434")
        self.assertEqual(configured, "http://127.0.0.1:11434")

    def test_bind_address_normalized_for_client(self) -> None:
        client, configured = resolve_ollama_hosts("0.0.0.0:11434")
        self.assertEqual(client, "http://127.0.0.1:11434")
        self.assertEqual(configured, "http://0.0.0.0:11434")

    def test_bind_address_with_scheme(self) -> None:
        client, configured = resolve_ollama_hosts("http://0.0.0.0:11434")
        self.assertEqual(client, "http://127.0.0.1:11434")
        self.assertEqual(configured, "http://0.0.0.0:11434")

    def test_explicit_localhost_unchanged(self) -> None:
        client, configured = resolve_ollama_hosts("http://127.0.0.1:11434")
        self.assertEqual(client, configured)


class TestQuestbookClientUrl(unittest.TestCase):
    @patch.dict(os.environ, {"OLLAMA_HOST": "0.0.0.0:11434"})
    def test_questbook_uses_loopback_for_health(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            q = Questbook(Path(tmp))
        self.assertEqual(q.client_url, "http://127.0.0.1:11434")
        self.assertEqual(q.configured_host, "http://0.0.0.0:11434")

    @patch.dict(os.environ, {"OLLAMA_HOST": "0.0.0.0:11434"})
    @patch("urllib.request.urlopen")
    def test_health_probe_hits_loopback(self, mock_urlopen) -> None:
        from unittest.mock import MagicMock

        mock_resp = MagicMock()
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.status = 200
        mock_urlopen.return_value = mock_resp
        with tempfile.TemporaryDirectory() as tmp:
            q = Questbook(Path(tmp))
            self.assertTrue(q._is_server_healthy())
        called_url = mock_urlopen.call_args[0][0]
        self.assertEqual(called_url, "http://127.0.0.1:11434/api/tags")


if __name__ == "__main__":
    unittest.main()
