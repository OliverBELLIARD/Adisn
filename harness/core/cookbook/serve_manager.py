"""Background model serve processes (Ollama / llama.cpp / vLLM)."""

from __future__ import annotations

import json
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class ServeManager:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.state_file = self.root / "serves.json"

    def list_serves(self) -> List[Dict[str, Any]]:
        return self._load().get("serves", [])

    def start_ollama(self, model: str) -> Dict[str, Any]:
        """Ollama serves via its daemon; record active model selection."""
        entry = {
            "id": f"ollama-{uuid.uuid4().hex[:8]}",
            "backend": "ollama",
            "model": model,
            "port": 11434,
            "pid": None,
            "status": "active",
            "started_at": _now(),
            "endpoint": "http://127.0.0.1:11434",
        }
        self._append(entry)
        return {"ok": True, "serve": entry, "note": "Ollama uses shared daemon on :11434"}

    def start_llama_cpp(self, model_path: str, port: int = 8080) -> Dict[str, Any]:
        binary = shutil.which("llama-server") or shutil.which("llama-cli")
        if not binary:
            return {"ok": False, "error": "llama-server not found in PATH"}
        cmd = [binary, "-m", model_path, "--port", str(port), "--host", "127.0.0.1"]
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )
        entry = {
            "id": f"llama-{uuid.uuid4().hex[:8]}",
            "backend": "llama-cpp",
            "model": model_path,
            "port": port,
            "pid": proc.pid,
            "status": "running",
            "started_at": _now(),
            "endpoint": f"http://127.0.0.1:{port}/v1",
        }
        self._append(entry)
        return {"ok": True, "serve": entry}

    def start_vllm(self, model: str, port: int = 8000) -> Dict[str, Any]:
        binary = shutil.which("vllm") or shutil.which("python")
        if not shutil.which("vllm") and not shutil.which("python"):
            return {"ok": False, "error": "vllm not found in PATH"}
        if shutil.which("vllm"):
            cmd = ["vllm", "serve", model, "--host", "127.0.0.1", "--port", str(port)]
        else:
            cmd = ["python", "-m", "vllm.entrypoints.openai.api_server", "--model", model, "--port", str(port)]
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )
        entry = {
            "id": f"vllm-{uuid.uuid4().hex[:8]}",
            "backend": "vllm",
            "model": model,
            "port": port,
            "pid": proc.pid,
            "status": "running",
            "started_at": _now(),
            "endpoint": f"http://127.0.0.1:{port}/v1",
        }
        self._append(entry)
        return {"ok": True, "serve": entry}

    def stop(self, serve_id: str) -> Dict[str, Any]:
        serves = self.list_serves()
        found = None
        remaining = []
        for item in serves:
            if item.get("id") == serve_id:
                found = item
            else:
                remaining.append(item)
        if not found:
            return {"ok": False, "error": f"unknown serve id: {serve_id}"}
        pid = found.get("pid")
        if pid:
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/F"],
                    capture_output=True,
                    timeout=5,
                )
            except Exception:
                try:
                    import os
                    import signal

                    os.kill(pid, signal.SIGTERM)
                except Exception:
                    pass
        data = self._load()
        data["serves"] = remaining
        self._write(data)
        return {"ok": True, "stopped": serve_id}

    def _append(self, entry: Dict[str, Any]) -> None:
        data = self._load()
        data.setdefault("serves", []).append(entry)
        self._write(data)

    def _load(self) -> Dict[str, Any]:
        if not self.state_file.exists():
            return {"serves": []}
        return json.loads(self.state_file.read_text(encoding="utf-8"))

    def _write(self, data: Dict[str, Any]) -> None:
        self.state_file.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
