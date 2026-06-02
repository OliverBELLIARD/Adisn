"""Normalize Ollama host URLs for client HTTP requests."""

from __future__ import annotations

import os
from typing import Tuple
from urllib.parse import urlparse, urlunparse


def resolve_ollama_hosts(raw: str | None = None) -> Tuple[str, str]:
    """Return (client_url, configured_url).

    Ollama often sets OLLAMA_HOST=0.0.0.0:11434 for *binding* on all interfaces.
    HTTP clients must use 127.0.0.1 (or localhost), not 0.0.0.0.
    """
    configured = (raw or os.environ.get("OLLAMA_HOST") or "http://127.0.0.1:11434").strip()
    if not configured.startswith(("http://", "https://")):
        configured = f"http://{configured}"
    configured = configured.rstrip("/")

    parsed = urlparse(configured)
    hostname = parsed.hostname or "127.0.0.1"
    port = parsed.port or 11434
    scheme = parsed.scheme or "http"

    client_host = hostname
    if hostname in {"0.0.0.0", "::", "[::]"}:
        client_host = "127.0.0.1"

    client_url = urlunparse((scheme, f"{client_host}:{port}", "", "", "", "")).rstrip("/")
    return client_url, configured
