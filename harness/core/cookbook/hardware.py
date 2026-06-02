"""Hardware scan for Cookbook (GPU / RAM / CPU)."""

from __future__ import annotations

import json
import platform
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class GpuInfo:
    name: str
    vram_gb: float
    vendor: str


@dataclass
class HardwareSnapshot:
    scanned_at: str
    os: str
    cpu: str
    ram_gb: float
    gpus: List[GpuInfo]
    vram_budget_gb: float
    cuda_available: bool
    metal_available: bool

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["gpus"] = [asdict(g) for g in self.gpus]
        return data


def scan_hardware(cache_path: Optional[Path] = None, max_age_seconds: int = 300) -> HardwareSnapshot:
    if cache_path and cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            scanned = datetime.fromisoformat(cached["scanned_at"].replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - scanned).total_seconds()
            if age < max_age_seconds:
                gpus = [GpuInfo(**g) for g in cached.get("gpus", [])]
                return HardwareSnapshot(
                    scanned_at=cached["scanned_at"],
                    os=cached["os"],
                    cpu=cached["cpu"],
                    ram_gb=cached["ram_gb"],
                    gpus=gpus,
                    vram_budget_gb=cached["vram_budget_gb"],
                    cuda_available=cached.get("cuda_available", False),
                    metal_available=cached.get("metal_available", False),
                )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            pass

    gpus = _scan_gpus()
    ram_gb = _scan_ram_gb()
    vram_budget = sum(g.vram_gb for g in gpus) if gpus else min(ram_gb * 0.6, 16.0)
    snap = HardwareSnapshot(
        scanned_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        os=platform.system(),
        cpu=platform.processor() or platform.machine(),
        ram_gb=round(ram_gb, 2),
        gpus=gpus,
        vram_budget_gb=round(vram_budget, 2),
        cuda_available=any(g.vendor == "nvidia" for g in gpus),
        metal_available=platform.system() == "Darwin",
    )
    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(snap.to_dict(), indent=2), encoding="utf-8")
    return snap


def _scan_ram_gb() -> float:
    try:
        import os

        if hasattr(os, "sysconf"):
            pages = os.sysconf("SC_PHYS_PAGES")
            size = os.sysconf("SC_PAGE_SIZE")
            return (pages * size) / (1024**3)
    except (AttributeError, ValueError, OSError):
        pass
    if platform.system() == "Windows":
        cp = subprocess.run(
            ["wmic", "computersystem", "get", "TotalPhysicalMemory"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        for line in cp.stdout.splitlines():
            line = line.strip()
            if line.isdigit():
                return int(line) / (1024**3)
    return 8.0


def _scan_gpus() -> List[GpuInfo]:
    gpus: List[GpuInfo] = []
    if shutil.which("nvidia-smi"):
        cp = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if cp.returncode == 0:
            for line in cp.stdout.strip().splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 2:
                    try:
                        mem = float(parts[1]) / 1024.0
                    except ValueError:
                        mem = 0.0
                    gpus.append(GpuInfo(name=parts[0], vram_gb=round(mem, 2), vendor="nvidia"))
    if not gpus and platform.system() == "Darwin":
        gpus.append(GpuInfo(name="Apple Silicon (unified)", vram_gb=0.0, vendor="apple"))
    return gpus


def try_llmfit_scan() -> Optional[Dict[str, Any]]:
    """Optional llmfit CLI integration when installed."""
    if not shutil.which("llmfit"):
        return None
    cp = subprocess.run(["llmfit", "--json"], capture_output=True, text=True, timeout=15)
    if cp.returncode != 0 or not cp.stdout.strip():
        return None
    try:
        return json.loads(cp.stdout)
    except json.JSONDecodeError:
        return {"raw": cp.stdout[:2000]}
