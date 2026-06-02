"""Safe harness self-rewrite with snapshots and rollback."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict


class SelfRewriter:
    def __init__(self, workspace_root: Path, safe_global: bool = False):
        self.workspace_root = workspace_root
        self.safe_global = safe_global
        self.snapshots_root = workspace_root / ".harness_snapshots"
        self.snapshots_root.mkdir(exist_ok=True)
        self.log_file = self.snapshots_root / "rewrite_log.json"
        if not self.log_file.exists():
            self.log_file.write_text("[]", encoding="utf-8")

    def rewrite_file(self, target_path: str, new_content: str, reason: str) -> Dict:
        target = self._resolve_target(target_path)
        if not target.exists():
            return {"ok": False, "error": f"File not found: {target_path}"}

        stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        snapshot = self.snapshots_root / f"{stamp}__{self._snapshot_name(target)}.bak"
        snapshot.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")

        target.write_text(new_content, encoding="utf-8")
        self._append_log(
            {
                "time": stamp,
                "target": str(target),
                "snapshot": str(snapshot.relative_to(self.workspace_root)),
                "reason": reason,
                "scope": "workspace" if self._is_in_workspace(target) else "global",
            }
        )
        return {"ok": True, "target": str(target), "snapshot": str(snapshot)}

    def rollback_last(self) -> Dict:
        logs = json.loads(self.log_file.read_text(encoding="utf-8"))
        if not logs:
            return {"ok": False, "error": "No rewrite history"}
        last = logs.pop()
        target = Path(last["target"])
        snapshot = self.workspace_root / last["snapshot"]
        target.write_text(snapshot.read_text(encoding="utf-8"), encoding="utf-8")
        self.log_file.write_text(json.dumps(logs, indent=2), encoding="utf-8")
        return {"ok": True, "rolled_back": last["target"]}

    def set_safe_global(self, value: bool) -> None:
        self.safe_global = value

    def get_scope(self) -> str:
        return "workspace" if self.safe_global else "global"

    def _append_log(self, item: Dict) -> None:
        logs = json.loads(self.log_file.read_text(encoding="utf-8"))
        logs.append(item)
        self.log_file.write_text(json.dumps(logs, indent=2), encoding="utf-8")

    def _resolve_target(self, target_path: str) -> Path:
        raw = Path(target_path).expanduser()
        target = raw if raw.is_absolute() else (self.workspace_root / raw)
        target = target.resolve()
        if self.safe_global and not self._is_in_workspace(target):
            raise ValueError(
                "Global writes are disabled in --safe-global mode. "
                f"Refusing outside path: {target}"
            )
        return target

    def _is_in_workspace(self, path: Path) -> bool:
        try:
            path.resolve().relative_to(self.workspace_root.resolve())
            return True
        except ValueError:
            return False

    @staticmethod
    def _snapshot_name(path: Path) -> str:
        return re.sub(r"[^a-zA-Z0-9._-]+", "_", str(path))
