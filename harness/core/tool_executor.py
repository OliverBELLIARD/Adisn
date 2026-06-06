"""Runtime tool registry — file I/O, shell, skills, and custom tool creation."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from harness.core.capability_index import build_capability_catalog, format_tools_catalog
from harness.core.self_rewriter import SelfRewriter
from harness.core.skill_store import SkillStore


@dataclass
class ToolSpec:
    name: str
    description: str
    args: Dict[str, str]


class ToolExecutor:
    """Executes harness tools the model can invoke via the `run_tool` loop action."""

    MAX_READ_BYTES = 48_000
    MAX_GREP_MATCHES = 40
    SHELL_TIMEOUT_S = 45

    BUILTIN_INDEX: List[Dict[str, Any]] = [
        {
            "name": "read_file",
            "summary": "Read text from a file in the workspace",
            "args": {"path": "str", "offset": "int?", "limit": "int?"},
            "keywords": ["read", "file", "open", "view", "source", "cat"],
            "builtin": True,
        },
        {
            "name": "write_file",
            "summary": "Create or overwrite a file, including harness source code",
            "args": {"path": "str", "content": "str", "reason": "str?"},
            "keywords": ["write", "edit", "modify", "rewrite", "create", "patch", "code"],
            "builtin": True,
        },
        {
            "name": "list_dir",
            "summary": "List files and folders under a directory",
            "args": {"path": "str?"},
            "keywords": ["list", "dir", "directory", "files", "folder", "ls", "contents"],
            "builtin": True,
        },
        {
            "name": "grep",
            "summary": "Search file contents by regex pattern",
            "args": {"pattern": "str", "path": "str?"},
            "keywords": ["grep", "search", "find", "pattern", "match"],
            "builtin": True,
        },
        {
            "name": "shell",
            "summary": "Run a shell command in the workspace",
            "args": {"command": "str"},
            "keywords": ["shell", "run", "execute", "command", "terminal", "script"],
            "builtin": True,
        },
        {
            "name": "create_skill",
            "summary": "Create a skill markdown entry in skills/INDEX.json",
            "args": {"task": "str", "content": "str?"},
            "keywords": ["skill", "workflow", "procedure", "playbook"],
            "builtin": True,
        },
        {
            "name": "create_tool",
            "summary": "Register a new Python tool in tools/INDEX.json",
            "args": {"name": "str", "description": "str", "code": "str"},
            "keywords": ["tool", "register", "extend", "custom", "capability"],
            "builtin": True,
        },
        {
            "name": "read_skill",
            "summary": "Load a skill body from skills/ by name",
            "args": {"name": "str"},
            "keywords": ["skill", "read", "load", "procedure"],
            "builtin": True,
        },
    ]

    def __init__(
        self,
        workspace_root: Path,
        rewriter: SelfRewriter,
        skills: SkillStore,
    ):
        self.workspace_root = workspace_root
        self.rewriter = rewriter
        self.skills = skills
        self.custom_tools_dir = workspace_root / "tools" / "custom"
        self.custom_tools_dir.mkdir(parents=True, exist_ok=True)
        self.tools_index_file = workspace_root / "tools" / "INDEX.json"
        self.tools_index_file.parent.mkdir(parents=True, exist_ok=True)
        self.registry_file = workspace_root / ".adisn" / "tools" / "registry.json"
        self.registry_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.registry_file.exists():
            self.registry_file.write_text("[]", encoding="utf-8")
        self._ensure_tools_index()

    def _ensure_tools_index(self) -> None:
        entries = self._load_tools_index()
        by_name = {entry["name"]: entry for entry in entries}
        for builtin in self.BUILTIN_INDEX:
            by_name.setdefault(builtin["name"], dict(builtin))
        for custom in self._load_custom_registry():
            name = custom.get("name", "")
            if not name:
                continue
            by_name[name] = {
                "name": name,
                "summary": custom.get("description", "Custom tool"),
                "args": {"input": "str?"},
                "keywords": list(_terms_from_text(f"{name} {custom.get('description', '')}")),
                "module": custom.get("module"),
                "custom": True,
            }
        merged = sorted(by_name.values(), key=lambda item: item.get("name", ""))
        self.tools_index_file.write_text(json.dumps(merged, indent=2), encoding="utf-8")

    def _load_tools_index(self) -> List[Dict[str, Any]]:
        if not self.tools_index_file.exists():
            return []
        try:
            return json.loads(self.tools_index_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []

    def catalog_prompt(self, request: str) -> str:
        self._ensure_tools_index()
        return format_tools_catalog(self.tools_index_file, request)

    def tools_prompt(self) -> str:
        self._ensure_tools_index()
        entries = self._load_tools_index()
        lines = ["Tools index (tools/INDEX.json):"]
        for entry in entries:
            args = entry.get("args", {})
            arg_text = ", ".join(f"{k}: {v}" for k, v in args.items())
            lines.append(f"- {entry['name']}({arg_text}): {entry.get('summary', '')}")
        lines.append('Invoke via run_tool: {"tool":"<name>","args":{...}}')
        return "\n".join(lines)

    def list_tools(self) -> List[ToolSpec]:
        specs: List[ToolSpec] = []
        for entry in self._load_tools_index() or self.BUILTIN_INDEX:
            specs.append(
                ToolSpec(
                    str(entry.get("name", "")),
                    str(entry.get("summary", "")),
                    dict(entry.get("args") or {}),
                )
            )
        return specs

    @staticmethod
    def coerce_tool_input(raw: Union[str, Dict[str, Any], None]) -> str:
        """Normalize model output (JSON string or dict) for execute()."""
        if raw is None:
            return ""
        if isinstance(raw, dict):
            if "tool" in raw:
                return json.dumps(raw, ensure_ascii=True)
            nested = raw.get("input")
            if isinstance(nested, dict) and "tool" in nested:
                return json.dumps(nested, ensure_ascii=True)
            return json.dumps(raw, ensure_ascii=True)
        text = str(raw).strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        return text

    def execute(self, raw_input: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
        raw_input = self.coerce_tool_input(raw_input)
        try:
            payload = (
                json.loads(raw_input)
                if raw_input.strip().startswith("{")
                else {"tool": raw_input.strip(), "args": {}}
            )
        except json.JSONDecodeError as exc:
            return {"ok": False, "error": f"invalid tool JSON: {exc}"}

        tool = str(payload.get("tool", "")).strip()
        args = payload.get("args") or {}
        if not tool:
            return {"ok": False, "error": "missing tool name"}

        handlers: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
            "read_file": self._read_file,
            "write_file": self._write_file,
            "list_dir": self._list_dir,
            "grep": self._grep,
            "shell": self._shell,
            "create_skill": self._create_skill,
            "create_tool": self._create_tool,
            "read_skill": self._read_skill,
            "list_tools": lambda _a: {"ok": True, "tools": [s.name for s in self.list_tools()]},
        }
        handler = handlers.get(tool)
        if handler:
            return handler(args if isinstance(args, dict) else {})
        return self._run_custom_tool(tool, args if isinstance(args, dict) else {"input": args})

    def _resolve_path(self, raw: str) -> Path:
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = self.workspace_root / path
        return path.resolve()

    def _read_file(self, args: Dict[str, Any]) -> Dict[str, Any]:
        path = self._resolve_path(str(args.get("path", "")))
        if not path.exists():
            return {"ok": False, "error": f"File not found: {path}"}
        if not path.is_file():
            return {"ok": False, "error": f"Not a file: {path}"}
        text = path.read_text(encoding="utf-8", errors="replace")
        offset = max(0, int(args.get("offset", 0) or 0))
        limit = int(args.get("limit", 0) or 0) or 400
        lines = text.splitlines()
        slice_lines = lines[offset : offset + limit]
        body = "\n".join(slice_lines)
        if len(body.encode("utf-8")) > self.MAX_READ_BYTES:
            body = body[: self.MAX_READ_BYTES] + "\n… (truncated)"
        return {
            "ok": True,
            "path": str(path),
            "offset": offset,
            "total_lines": len(lines),
            "content": body,
        }

    def _write_file(self, args: Dict[str, Any]) -> Dict[str, Any]:
        path = str(args.get("path", ""))
        content = str(args.get("content", ""))
        reason = str(args.get("reason", "agent tool write"))
        if not path:
            return {"ok": False, "error": "missing path"}
        target = self._resolve_path(path)
        try:
            self.rewriter._resolve_target(path)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        created = not target.exists()
        if target.exists() and target.is_file():
            result = self.rewriter.rewrite_file(path, content, reason)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            result = {"ok": True, "target": str(target), "created": True}
        result["created"] = created
        return result

    def _list_dir(self, args: Dict[str, Any]) -> Dict[str, Any]:
        path = self._resolve_path(str(args.get("path", ".")))
        if not path.exists():
            return {"ok": False, "error": f"Not found: {path}"}
        if not path.is_dir():
            return {"ok": False, "error": f"Not a directory: {path}"}
        entries = []
        for child in sorted(path.iterdir())[:200]:
            kind = "dir" if child.is_dir() else "file"
            entries.append({"name": child.name, "type": kind})
        return {"ok": True, "path": str(path), "entries": entries}

    def _grep(self, args: Dict[str, Any]) -> Dict[str, Any]:
        pattern = str(args.get("pattern", ""))
        if not pattern:
            return {"ok": False, "error": "missing pattern"}
        root = self._resolve_path(str(args.get("path", ".")))
        if not root.exists():
            return {"ok": False, "error": f"Not found: {root}"}
        regex = re.compile(pattern, re.IGNORECASE)
        matches: List[Dict[str, str]] = []
        files = [root] if root.is_file() else list(root.rglob("*"))
        for file_path in files:
            if not file_path.is_file():
                continue
            if any(part.startswith(".") for part in file_path.parts):
                continue
            try:
                text = file_path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for line_no, line in enumerate(text.splitlines(), 1):
                if regex.search(line):
                    matches.append(
                        {
                            "file": str(file_path.relative_to(self.workspace_root)),
                            "line": str(line_no),
                            "text": line.strip()[:200],
                        }
                    )
                    if len(matches) >= self.MAX_GREP_MATCHES:
                        break
            if len(matches) >= self.MAX_GREP_MATCHES:
                break
        return {"ok": True, "pattern": pattern, "matches": matches}

    def _shell(self, args: Dict[str, Any]) -> Dict[str, Any]:
        command = str(args.get("command", "")).strip()
        if not command:
            return {"ok": False, "error": "missing command"}
        try:
            proc = subprocess.run(
                command,
                shell=True,
                cwd=str(self.workspace_root),
                capture_output=True,
                text=True,
                timeout=self.SHELL_TIMEOUT_S,
            )
            return {
                "ok": proc.returncode == 0,
                "exit_code": proc.returncode,
                "stdout": (proc.stdout or "")[-8000:],
                "stderr": (proc.stderr or "")[-4000:],
            }
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": f"command timed out after {self.SHELL_TIMEOUT_S}s"}

    def _create_skill(self, args: Dict[str, Any]) -> Dict[str, Any]:
        task = str(args.get("task", "")).strip()
        content = args.get("content")
        if not task:
            return {"ok": False, "error": "missing task"}
        try:
            descriptor = self.skills.generate_from_task(task)
        except ValueError:
            skill_type = self.skills._infer_type(task)
            name = self.skills._skill_name(task)
            path = self.skills._ensure_type_folder(skill_type) / f"{name}.md"
            path.write_text(str(content or f"# {name}\n\n{task}\n"), encoding="utf-8")
            descriptor = None
        if content and descriptor:
            path = self.workspace_root / descriptor.path
            path.write_text(str(content), encoding="utf-8")
        return {
            "ok": True,
            "skill": descriptor.name if descriptor else name,
            "path": descriptor.path if descriptor else str(path.relative_to(self.workspace_root)),
        }

    def _create_tool(self, args: Dict[str, Any]) -> Dict[str, Any]:
        name = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(args.get("name", "")).strip()).strip("-")
        description = str(args.get("description", "")).strip()
        code = str(args.get("code", "")).strip()
        if not name or not code:
            return {"ok": False, "error": "name and code required"}
        module_path = self.custom_tools_dir / f"{name}.py"
        module_path.write_text(code + "\n", encoding="utf-8")
        registry = self._load_custom_registry()
        registry = [e for e in registry if e.get("name") != name]
        registry.append({"name": name, "description": description, "module": str(module_path.relative_to(self.workspace_root))})
        self.registry_file.write_text(json.dumps(registry, indent=2), encoding="utf-8")
        self._ensure_tools_index()
        return {"ok": True, "name": name, "module": str(module_path.relative_to(self.workspace_root))}

    def _read_skill(self, args: Dict[str, Any]) -> Dict[str, Any]:
        name = str(args.get("name", "")).strip()
        if not name:
            return {"ok": False, "error": "missing skill name"}
        for skill_path in self.skills.skills_root.rglob("*.md"):
            if skill_path.stem == name or name in skill_path.name:
                return {"ok": True, "name": skill_path.stem, "content": skill_path.read_text(encoding="utf-8")[:12000]}
        return {"ok": False, "error": f"skill not found: {name}"}

    def _load_custom_registry(self) -> List[Dict[str, Any]]:
        try:
            return json.loads(self.registry_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []

    def _run_custom_tool(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        for entry in self._load_custom_registry():
            if entry.get("name") != name:
                continue
            module_path = self.workspace_root / entry["module"]
            if not module_path.exists():
                return {"ok": False, "error": f"custom tool module missing: {module_path}"}
            namespace: Dict[str, Any] = {}
            try:
                exec(module_path.read_text(encoding="utf-8"), namespace)
            except Exception as exc:
                return {"ok": False, "error": f"custom tool load failed: {exc}"}
            run_fn = namespace.get("run")
            if not callable(run_fn):
                return {"ok": False, "error": "custom tool must define run(args) -> dict"}
            try:
                result = run_fn(args)
                return result if isinstance(result, dict) else {"ok": True, "result": result}
            except Exception as exc:
                return {"ok": False, "error": str(exc)}
        return {"ok": False, "error": f"unknown tool: {name}"}


def _terms_from_text(text: str) -> List[str]:
    words = [w for w in re.split(r"[^a-zA-Z0-9]+", text.lower()) if len(w) > 2]
    dedup: List[str] = []
    for word in words:
        if word not in dedup:
            dedup.append(word)
    return dedup[:12]
