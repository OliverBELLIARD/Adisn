"""Cookbook: CLI-local model management (Odysseus Cookbook feature parity)."""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from harness.core.cookbook.hardware import scan_hardware, try_llmfit_scan
from harness.core.cookbook.quant import (
    best_quant_for_budget,
    fit_score,
    infer_quantization_from_name,
)
from harness.core.cookbook.serve_manager import ServeManager
from harness.core.ollama_url import resolve_ollama_hosts
from harness.core.questbook import Questbook

_CATALOG_PATH = Path(__file__).parent / "data" / "models.json"


class Cookbook:
    """Hardware-aware model catalog, pull/serve, and provider registry."""

    PROFILE_GOALS = {
        "fast": {"use_cases": {"chat", "general"}, "max_params_b": 4.0},
        "balanced": {"use_cases": {"chat", "general", "coding"}, "max_params_b": 9.0},
        "reasoning": {"use_cases": {"reasoning"}, "max_params_b": 15.0},
        "coding": {"use_cases": {"coding"}, "max_params_b": 9.0},
    }

    def __init__(self, workspace_root: Path, questbook: Optional[Questbook] = None):
        self.workspace_root = workspace_root
        self.root = workspace_root / ".cookbook"
        self.root.mkdir(exist_ok=True)
        self.questbook = questbook or Questbook(workspace_root)
        self.serves = ServeManager(self.root)
        self.hardware_cache = self.root / "hardware.json"
        self.providers_file = self.root / "providers.json"
        self.active_file = self.root / "active.json"
        self._ensure_providers()

    def scan(self, *, refresh: bool = False) -> Dict[str, Any]:
        max_age = 0 if refresh else 300
        hw = scan_hardware(cache_path=self.hardware_cache, max_age_seconds=max_age)
        llmfit = try_llmfit_scan()
        return {"ok": True, "hardware": hw.to_dict(), "llmfit": llmfit}

    def recommend(self, profile: str = "balanced", limit: int = 8) -> Dict[str, Any]:
        hw = scan_hardware(cache_path=self.hardware_cache)
        budget = hw.vram_budget_gb if hw.vram_budget_gb > 0 else hw.ram_gb * 0.5
        goal = self.PROFILE_GOALS.get(profile, self.PROFILE_GOALS["balanced"])
        ranked: List[Dict[str, Any]] = []
        for model in self.catalog():
            if model.get("use_case") not in goal["use_cases"] and profile != "balanced":
                continue
            if params_b(model) > goal["max_params_b"]:
                continue
            quant = model.get("quantization") or infer_quantization_from_name(model["name"])
            q, ctx, mem = best_quant_for_budget(model, budget)
            if not q:
                continue
            score = fit_score(model, budget)
            ranked.append(
                {
                    "name": model["name"],
                    "score": round(score, 2),
                    "quant": q,
                    "context": ctx,
                    "vram_gb": round(mem or 0.0, 2),
                    "use_case": model.get("use_case"),
                    "ollama": model.get("ollama", False),
                    "backends": model.get("backends", []),
                }
            )
        ranked.sort(key=lambda x: x["score"], reverse=True)
        return {
            "ok": True,
            "profile": profile,
            "budget_gb": budget,
            "hardware": hw.to_dict(),
            "recommendations": ranked[:limit],
        }

    def list_catalog(self) -> Dict[str, Any]:
        return {"ok": True, "models": self.catalog()}

    def pull(self, model: str, *, background: bool = False) -> Dict[str, Any]:
        if model in {m["name"] for m in self.catalog() if m.get("ollama")}:
            return self.questbook.pull(model)
        return self.questbook.pull(model)

    def remove(self, model: str) -> Dict[str, Any]:
        return self.questbook.remove(model)

    def list_installed(self) -> Dict[str, Any]:
        models = self.questbook.list_models(start_server=False)
        return {"ok": True, "installed": models, "server": self.questbook.server_status()}

    def serve(self, backend: str, target: str, port: Optional[int] = None) -> Dict[str, Any]:
        backend = backend.lower().replace("_", "-")
        if backend == "ollama":
            self.set_active_model(target)
            return self.serves.start_ollama(target)
        if backend in {"llama-cpp", "llamacpp", "llama.cpp"}:
            return self.serves.start_llama_cpp(target, port or 8080)
        if backend == "vllm":
            return self.serves.start_vllm(target, port or 8000)
        return {"ok": False, "error": f"unknown backend: {backend}"}

    def serve_stop(self, serve_id: str) -> Dict[str, Any]:
        return self.serves.stop(serve_id)

    def list_serves(self) -> Dict[str, Any]:
        return {"ok": True, "serves": self.serves.list_serves()}

    def providers(self) -> Dict[str, Any]:
        return {"ok": True, "providers": self._load_providers()}

    def provider_add(self, name: str, base_url: str, provider_type: str = "openai") -> Dict[str, Any]:
        data = self._load_providers()
        custom = data.setdefault("custom", [])
        custom = [p for p in custom if p.get("name") != name]
        custom.append({"name": name, "type": provider_type, "base_url": base_url})
        data["custom"] = custom
        self._write_providers(data)
        return {"ok": True, "added": name, "base_url": base_url}

    def provider_remove(self, name: str) -> Dict[str, Any]:
        data = self._load_providers()
        before = len(data.get("custom", []))
        data["custom"] = [p for p in data.get("custom", []) if p.get("name") != name]
        self._write_providers(data)
        return {"ok": True, "removed": before - len(data["custom"])}

    def deps(self) -> Dict[str, Any]:
        return {
            "ok": True,
            "dependencies": {
                "ollama": bool(shutil.which("ollama")),
                "llama-server": bool(shutil.which("llama-server")),
                "llama-cli": bool(shutil.which("llama-cli")),
                "vllm": bool(shutil.which("vllm")),
                "llmfit": bool(shutil.which("llmfit")),
                "nvidia-smi": bool(shutil.which("nvidia-smi")),
            },
        }

    def status(self) -> Dict[str, Any]:
        active = self.get_active_model()
        hw = scan_hardware(cache_path=self.hardware_cache)
        return {
            "ok": True,
            "active_model": active,
            "hardware_summary": {
                "vram_budget_gb": hw.vram_budget_gb,
                "ram_gb": hw.ram_gb,
                "gpus": [asdict(g) for g in hw.gpus],
            },
            "ollama": self.questbook.server_status(),
            "installed_count": len(self.questbook.read_cached_models()),
            "serves": self.serves.list_serves(),
            "providers": self._load_providers(),
        }

    def set_active_model(self, model: str) -> Dict[str, Any]:
        payload = {
            "model": model,
            "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        self.active_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.environ["ALISON_OLLAMA_MODEL"] = model
        return {"ok": True, "active_model": model}

    def get_active_model(self) -> Optional[str]:
        preferred: Optional[str] = None
        if self.active_file.exists():
            try:
                data = json.loads(self.active_file.read_text(encoding="utf-8"))
                preferred = data.get("model")
            except json.JSONDecodeError:
                pass
        if not preferred:
            preferred = os.environ.get("ALISON_OLLAMA_MODEL", "").strip() or None
        resolved = self.questbook.resolve_model(preferred)
        if resolved and resolved != preferred:
            self.set_active_model(resolved)
        return resolved

    def chat(
        self,
        prompt: str,
        *,
        think: bool = True,
        on_progress: Optional[Any] = None,
    ) -> Dict[str, Any]:
        model = self.get_active_model()
        return self.questbook.chat(
            prompt, model=model, think=think, on_progress=on_progress
        )

    def catalog(self) -> List[Dict[str, Any]]:
        if not _CATALOG_PATH.exists():
            return []
        models = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
        for m in models:
            q = infer_quantization_from_name(m.get("name", ""))
            if q:
                m.setdefault("quantization", q)
        return models

    def _ensure_providers(self) -> None:
        if self.providers_file.exists():
            return
        client_url, _configured = resolve_ollama_hosts()
        default = {
            "ollama": {
                "type": "ollama",
                "base_url": client_url,
            },
            "custom": [],
        }
        self.providers_file.write_text(json.dumps(default, indent=2), encoding="utf-8")

    def _load_providers(self) -> Dict[str, Any]:
        self._ensure_providers()
        return json.loads(self.providers_file.read_text(encoding="utf-8"))

    def _write_providers(self, data: Dict[str, Any]) -> None:
        self.providers_file.write_text(json.dumps(data, indent=2), encoding="utf-8")


def params_b(model: Dict[str, Any]) -> float:
    raw = model.get("parameters_b")
    if raw:
        return float(raw)
    from harness.core.cookbook.quant import params_b as _pb

    return _pb(model)
