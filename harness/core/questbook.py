"""Questbook: local Ollama model management for Adisn."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from harness.core.ollama_url import resolve_ollama_hosts
from harness.core.thinking import (
    merge_chat_thinking,
    model_supports_native_thinking,
    ollama_think_parameter,
    split_thinking_and_response,
)


@dataclass
class OllamaModel:
    name: str
    model_id: str
    size: str
    modified: str


class Questbook:
    """Manages Ollama model lifecycle and lightweight local profiles."""

    DEFAULT_CHAT_TIMEOUT = 30.0
    SERVER_PROBE_TIMEOUT = 1.5
    SERVER_START_WAIT_SECONDS = 3.0

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.root = workspace_root / ".questbook"
        self.root.mkdir(exist_ok=True)
        self.index_file = self.root / "index.json"
        self.profiles_file = self.root / "profiles.json"
        self.server_state_file = self.root / "server_state.json"
        self.client_url, self.configured_host = resolve_ollama_hosts()
        self.host = self.client_url
        if not self.index_file.exists():
            self.index_file.write_text("[]", encoding="utf-8")
        if not self.profiles_file.exists():
            self.profiles_file.write_text(
                json.dumps(
                    {
                        "small_fast": ["qwen2.5:3b", "llama3.2:3b"],
                        "balanced": ["qwen2.5:7b", "llama3.1:8b"],
                        "reasoning_heavy": ["deepseek-r1:8b", "qwen2.5:14b"],
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        if not self.server_state_file.exists():
            self.server_state_file.write_text("{}", encoding="utf-8")

    def server_status(self) -> Dict:
        """Fast probe — never starts the Ollama server."""
        installed = self.is_ollama_installed()
        running = installed and self._is_server_healthy()
        return {
            "ollama_installed": installed,
            "server_running": running,
            "server_started": False,
            "host": self.client_url,
            "configured_host": self.configured_host,
        }

    def status(self) -> Dict:
        server = self.ensure_server_running(start_if_missing=False)
        models = self.list_models(start_server=False)
        return {
            "ollama_installed": self.is_ollama_installed(),
            "server_running": server["running"],
            "server_started": server["started"],
            "models_count": len(models),
            "questbook_index": str(self.index_file.relative_to(self.workspace_root)),
        }

    def is_ollama_installed(self) -> bool:
        return shutil.which("ollama") is not None

    def list_models(self, start_server: bool = False) -> List[Dict]:
        if not self.is_ollama_installed():
            return []
        server = self.ensure_server_running(start_if_missing=start_server)
        if not server["running"]:
            return self._read_cached_models()
        cp = self._run(["ollama", "list"], timeout=10)
        if not cp["ok"]:
            return self._read_cached_models()
        lines = cp["stdout"].splitlines()
        rows = lines[1:] if len(lines) > 1 else []
        models: List[Dict] = []
        for row in rows:
            parts = [p for p in row.split("  ") if p.strip()]
            if len(parts) < 4:
                continue
            model = OllamaModel(
                name=parts[0].strip(),
                model_id=parts[1].strip(),
                size=parts[2].strip(),
                modified=parts[3].strip(),
            )
            models.append(asdict(model))
        self._write_index(models)
        return models

    def pull(self, model: str) -> Dict:
        if not self.is_ollama_installed():
            return {"ok": False, "error": "ollama not found in PATH"}
        self.ensure_server_running(start_if_missing=True)
        cp = self._run(["ollama", "pull", model], long_running=True)
        self.list_models(start_server=True)
        return cp

    def remove(self, model: str) -> Dict:
        if not self.is_ollama_installed():
            return {"ok": False, "error": "ollama not found in PATH"}
        self.ensure_server_running(start_if_missing=True)
        cp = self._run(["ollama", "rm", model])
        self.list_models(start_server=True)
        return cp

    def ensure_profile(self, profile: str) -> Dict:
        profiles = json.loads(self.profiles_file.read_text(encoding="utf-8"))
        wanted = profiles.get(profile)
        if not wanted:
            return {"ok": False, "error": f"unknown profile: {profile}", "available": list(profiles)}
        current = {m["name"] for m in self.list_models(start_server=True)}
        pulled = []
        for model in wanted:
            if model in current:
                continue
            result = self.pull(model)
            if not result["ok"]:
                return {"ok": False, "error": f"failed pulling {model}", "details": result}
            pulled.append(model)
        return {"ok": True, "profile": profile, "pulled": pulled, "target": wanted}

    def profiles(self) -> Dict:
        return json.loads(self.profiles_file.read_text(encoding="utf-8"))

    def chat(
        self,
        prompt: str,
        *,
        model: Optional[str] = None,
        think: bool = True,
        timeout: Optional[float] = None,
        on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
        _allow_model_retry: bool = True,
        system_extra: str = "",
    ) -> Dict:
        """Call Ollama /api/chat. Never auto-starts the server."""
        if not self._is_server_healthy():
            return {"ok": False, "error": "server_unavailable"}
        chosen = self.resolve_model(model)
        if not chosen:
            return {"ok": False, "error": "no_local_models"}

        timeout = timeout if timeout is not None else self.DEFAULT_CHAT_TIMEOUT
        native_think = think and model_supports_native_thinking(chosen)
        system = "You are Adisn, a local coding harness assistant."
        if system_extra:
            system += "\n\n" + system_extra.strip()
        if think and not native_think:
            tag = "think"
            system += (
                f" Put private reasoning inside <{tag}>...</{tag}> "
                "before the user-visible answer."
            )
        payload: Dict[str, Any] = {
            "model": chosen,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "stream": bool(on_progress),
        }
        if native_think:
            payload["think"] = ollama_think_parameter(chosen, True)
        elif think:
            payload["think"] = False
        url = f"{self.host}/api/chat"
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as resp:
                if on_progress:
                    native_trace, content = self._read_streaming_chat(
                        resp,
                        on_progress=on_progress,
                        model=chosen,
                        native_think=native_think,
                    )
                else:
                    data = json.loads(resp.read().decode("utf-8"))
                    msg = data.get("message", {}) or {}
                    native_trace = msg.get("thinking", "")
                    content = msg.get("content", "")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            if (
                exc.code == 404
                and _allow_model_retry
                and "not found" in detail.lower()
            ):
                fallback = self.resolve_model(None)
                if fallback and fallback != chosen:
                    return self.chat(
                        prompt,
                        model=fallback,
                        think=think,
                        timeout=timeout,
                        on_progress=on_progress,
                        _allow_model_retry=False,
                        system_extra=system_extra,
                    )
            return {"ok": False, "error": f"http_{exc.code}", "details": detail[:500]}
        except (urllib.error.URLError, TimeoutError) as exc:
            return {"ok": False, "error": str(exc)}

        thinking, visible = merge_chat_thinking(native_trace, content)
        return {
            "ok": True,
            "model": chosen,
            "message": visible or content,
            "thinking": thinking,
            "thinking_native": bool(native_think and thinking),
            "raw": content,
        }

    @staticmethod
    def _read_streaming_chat(
        resp,
        *,
        on_progress: Callable[[Dict[str, Any]], None],
        model: str,
        native_think: bool = False,
    ) -> tuple[str, str]:
        """Read Ollama NDJSON stream; emit thinking then answer (Anthropic-style)."""
        thinking_parts: List[str] = []
        content_parts: List[str] = []
        on_progress({"kind": "model", "active": True, "model": model})
        for raw_line in resp:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg = chunk.get("message", {}) or {}
            trace = msg.get("thinking", "")
            token = msg.get("content", "")
            if trace:
                thinking_parts.append(trace)
                on_progress(
                    {
                        "kind": "thinking",
                        "text": "".join(thinking_parts),
                        "streaming": True,
                    }
                )
            if token:
                content_parts.append(token)
                on_progress({"kind": "token", "text": "".join(content_parts)})
            if chunk.get("done"):
                break
        on_progress({"kind": "model", "active": False, "model": model})
        return "".join(thinking_parts), "".join(content_parts)

    def start_server(self, wait_seconds: Optional[float] = None) -> Dict:
        """Start `ollama serve` in the background if not already healthy."""
        if not self.is_ollama_installed():
            return {
                "ok": False,
                "error": "ollama not found in PATH",
                "running": False,
                "started": False,
                "host": self.client_url,
                "configured_host": self.configured_host,
            }
        if self._is_server_healthy():
            return {
                "ok": True,
                "message": "Ollama server is already running",
                "running": True,
                "started": False,
                "host": self.client_url,
                "configured_host": self.configured_host,
            }
        started = self._start_server(wait_seconds=wait_seconds)
        state = self._read_server_state()
        if started:
            return {
                "ok": True,
                "message": "Ollama server started",
                "running": True,
                "started": True,
                "host": self.client_url,
                "configured_host": self.configured_host,
                "pid": state.get("pid"),
            }
        return {
            "ok": False,
            "error": "Ollama server did not become healthy in time",
            "running": False,
            "started": True,
            "host": self.client_url,
            "configured_host": self.configured_host,
            "pid": state.get("pid"),
            "hint": (
                "Ollama may be bound on 0.0.0.0 — Adisn probes "
                f"{self.client_url}. Try `curl {self.client_url}/api/tags`."
            ),
        }

    def ensure_server_running(self, start_if_missing: bool = True) -> Dict:
        if not self.is_ollama_installed():
            return {"running": False, "started": False, "error": "ollama not found"}
        if self._is_server_healthy():
            return {"running": True, "started": False}
        if not start_if_missing:
            return {"running": False, "started": False}
        result = self.start_server()
        return {
            "running": result.get("running", False),
            "started": result.get("started", False),
            "error": result.get("error"),
        }

    def _default_model(self) -> Optional[str]:
        return self.resolve_model(None)

    def installed_model_names(self) -> List[str]:
        """Names of models Ollama reports (live list, else cached index)."""
        if self._is_server_healthy():
            return [m["name"] for m in self.list_models(start_server=False)]
        return [m["name"] for m in self._read_cached_models()]

    def resolve_model(self, preferred: Optional[str]) -> Optional[str]:
        """Pick an installed model; ignore stale active/env names that 404."""
        names = self.installed_model_names()
        if not names:
            env = (
                os.environ.get("ADISN_OLLAMA_MODEL", "").strip()
                or os.environ.get("ALISON_OLLAMA_MODEL", "").strip()
            )
            return (preferred or env) or None

        def pick(name: Optional[str]) -> Optional[str]:
            if not name:
                return None
            if name in names:
                return name
            base = name.split(":", 1)[0]
            for candidate in names:
                if candidate == name or candidate.startswith(f"{base}:"):
                    return candidate
            return None

        resolved = pick(preferred)
        if resolved:
            return resolved
        env = (
            os.environ.get("ADISN_OLLAMA_MODEL", "").strip()
            or os.environ.get("ALISON_OLLAMA_MODEL", "").strip()
        )
        resolved = pick(env)
        if resolved:
            return resolved
        return names[0]

    def read_cached_models(self) -> List[Dict]:
        return self._read_cached_models()

    def _read_cached_models(self) -> List[Dict]:
        if not self.index_file.exists():
            return []
        try:
            data = json.loads(self.index_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
        if isinstance(data, list):
            return data
        return data.get("models", [])

    def _write_index(self, models: List[Dict]) -> None:
        data = {
            "updated_at": datetime.utcnow().isoformat() + "Z",
            "models": models,
        }
        self.index_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _is_server_healthy(self) -> bool:
        url = f"{self.host}/api/tags"
        try:
            with urllib.request.urlopen(url, timeout=self.SERVER_PROBE_TIMEOUT) as resp:
                return 200 <= resp.status < 300
        except (urllib.error.URLError, TimeoutError, OSError):
            return False

    def _read_server_state(self) -> Dict:
        if not self.server_state_file.exists():
            return {}
        try:
            return json.loads(self.server_state_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def _start_server(self, wait_seconds: Optional[float] = None) -> bool:
        kwargs = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "stdin": subprocess.DEVNULL,
            "cwd": str(self.workspace_root),
        }
        popen_kwargs: Dict[str, Any] = {**kwargs}
        if os.name == "nt":
            detached = getattr(subprocess, "DETACHED_PROCESS", 0)
            new_group = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            popen_kwargs["creationflags"] = detached | new_group
        else:
            popen_kwargs["start_new_session"] = True
        proc = subprocess.Popen(["ollama", "serve"], **popen_kwargs)
        self.server_state_file.write_text(
            json.dumps(
                {
                    "pid": proc.pid,
                    "started_at": datetime.utcnow().isoformat() + "Z",
                    "host": self.client_url,
                    "configured_host": self.configured_host,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        wait = self.SERVER_START_WAIT_SECONDS if wait_seconds is None else wait_seconds
        deadline = time.time() + wait
        while time.time() < deadline:
            if self._is_server_healthy():
                return True
            time.sleep(0.15)
        return False

    @staticmethod
    def _run(command: List[str], long_running: bool = False, timeout: Optional[float] = None) -> Dict:
        if timeout is None:
            timeout = 3600 if long_running else 30
        try:
            proc = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            return {
                "ok": proc.returncode == 0,
                "code": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
            }
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "timeout", "stdout": "", "stderr": "command timed out"}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "stdout": "", "stderr": str(exc)}
