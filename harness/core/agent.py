"""Primary Adisn harness agent."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from harness.core.agent_loop import AgentLoop
from harness.core.context_window import ContextWindowManager
from harness.core.cookbook import Cookbook
from harness.core.messages import OLLAMA_WARNING
from harness.core.questbook import Questbook
from harness.core.self_rewriter import SelfRewriter
from harness.core.skill_store import SkillStore
from harness.core.direct_reply import try_direct_reply, is_meta_question, harness_context_blurb
from harness.core.task_complexity import is_complex_task, should_create_skill
from harness.core.capability_index import build_capability_catalog
from harness.core.tool_intent import is_refusal_message, needs_tools, tool_call_json
from harness.core.thinking import ThinkingMode, local_thinking_plan
from harness.core.agent_mandate import ADISN_TOOL_MANDATE
from harness.core.tool_executor import ToolExecutor
from harness.core.toolkit import get_toolkit
from harness.memory.memory_manager import MemoryManager


@dataclass
class AgentState:
    model_token_window: int
    context_tokens_used: int
    skill_count: int
    memory_entries: int
    ollama_installed: bool
    ollama_server_running: bool
    ollama_models: int
    rewrite_scope: str
    compact_threshold_ratio: float
    thinking_enabled: bool
    active_model: Optional[str]
    cookbook_serves: int
    workspace: str


class HarnessAgent:
    """Self-evolving agent runtime for local repository operations."""

    def __init__(
        self,
        workspace_root: Path | None = None,
        token_window: int = 50_000,
        compact_threshold_ratio: float = 0.85,
        safe_global: bool = False,
    ):
        self.workspace_root = workspace_root or Path.cwd()
        self.context = ContextWindowManager(
            max_tokens=token_window,
            reserve_tokens=10_000,
            compact_threshold_ratio=compact_threshold_ratio,
        )
        self.skills = SkillStore(self.workspace_root)
        self.memory = MemoryManager(self.workspace_root)
        self.rewriter = SelfRewriter(self.workspace_root, safe_global=safe_global)
        self.questbook = Questbook(self.workspace_root)
        self.cookbook = Cookbook(self.workspace_root, self.questbook)
        self.thinking = ThinkingMode(enabled=True)
        self.thinking_expanded = False
        self.tools = ToolExecutor(self.workspace_root, self.rewriter, self.skills, self.memory, self.context)

    def is_ollama_server_running(self) -> bool:
        return bool(self.questbook.server_status()["server_running"])

    def toggle_thinking(self) -> bool:
        return self.thinking.toggle()

    def process_request(
        self,
        request: str,
        thinking: Optional[bool] = None,
        on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict:
        use_thinking = self.thinking.enabled if thinking is None else thinking
        server_running = self.is_ollama_server_running()
        warning = None if server_running else OLLAMA_WARNING

        def emit(kind: str, **fields: Any) -> None:
            if on_progress:
                on_progress({"kind": kind, **fields})

        direct = try_direct_reply(request)
        if direct:
            emit("headline", text="Replying…")
            return self._finalize_request(
                request,
                message=direct,
                thinking="",
                use_thinking=use_thinking,
                warning=warning,
                server_running=server_running,
                matched=None,
                created=False,
                predicted=self._predict_action(request),
                loop_result={"steps": [], "loop_steps": 0, "ollama_used": False},
            )

        if is_meta_question(request):
            emit("headline", text="Explaining…")
            context = harness_context_blurb(self.workspace_root)
            turn = self._conversational_turn(
                request,
                use_thinking=use_thinking,
                on_progress=on_progress,
                system_extra=f"{ADISN_TOOL_MANDATE}\n\n{context}",
            )
            pseudo_steps = []
            if turn.get("thinking"):
                pseudo_steps.append(
                    {
                        "phase": "think",
                        "thinking": turn["thinking"],
                        "decision": {"action": "respond", "input": turn["message"]},
                        "observation": "meta explain",
                        "duration_ms": 0,
                    }
                )
            loop_result = {
                **turn,
                "steps": pseudo_steps,
                "loop_steps": len(pseudo_steps),
            }
            if on_progress:
                on_progress({"kind": "loop_start", "max_steps": 1, "request": request[:120]})
                on_progress(
                    {
                        "kind": "loop_done",
                        "steps": len(pseudo_steps),
                        "message_preview": turn["message"][:80],
                    }
                )
            return self._finalize_request(
                request,
                message=turn["message"],
                thinking=turn.get("thinking", ""),
                use_thinking=use_thinking,
                warning=warning,
                server_running=server_running,
                matched=None,
                created=False,
                predicted=self._predict_action(request),
                loop_result=loop_result,
            )

        if not is_complex_task(request) and not needs_tools(request):
            emit("headline", text="Replying…")
            turn = self._conversational_turn(
                request, use_thinking=use_thinking, on_progress=on_progress
            )

            # Convert single turn to a pseudo-loop for display/test purposes
            pseudo_steps = []
            if turn.get("thinking"):
                pseudo_steps.append({
                    "phase": "think",
                    "thinking": turn["thinking"],
                    "decision": {"action": "respond", "input": turn["message"]},
                    "observation": "conversational",
                    "duration_ms": 0
                })

            loop_result = {
                **turn,
                "steps": pseudo_steps,
                "loop_steps": len(pseudo_steps)
            }

            if on_progress:
                on_progress({"kind": "loop_start", "max_steps": 1, "request": request[:120]})
                on_progress({"kind": "loop_done", "steps": len(pseudo_steps), "message_preview": turn["message"][:80]})

            return self._finalize_request(
                request,
                message=turn["message"],
                thinking=turn.get("thinking", ""),
                use_thinking=use_thinking,
                warning=warning,
                server_running=server_running,
                matched=None,
                created=False,
                predicted=self._predict_action(request),
                loop_result=loop_result,
            )

        emit("headline", text="Matching skills…")
        matched = self.skills.match(request)
        created = None
        if matched is None and should_create_skill(request):
            created = self.skills.generate_from_task(request)
            matched = created

        predicted = self._predict_action(request)
        skill_context = {
            "skill_name": matched.name if matched else None,
            "skill_path": matched.path if matched else None,
            "next_action": predicted,
            "scope": self.rewriter.get_scope(),
            "created_new_skill": created is not None,
        }

        emit("headline", text="Running agent loop…")

        capability_catalog = build_capability_catalog(self.workspace_root, request)
        system_extra = (
            f"{ADISN_TOOL_MANDATE}\n\nWorkspace: {self.workspace_root}\n\n"
            f"{capability_catalog}"
        )

        def chat_fn(
            prompt: str,
            think: bool = True,
            on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
        ) -> Dict:
            model = self.cookbook.get_active_model() or "local"
            if on_progress:
                on_progress({"kind": "model", "active": True, "model": model})

            def relay(event: Dict[str, Any]) -> None:
                if on_progress:
                    on_progress(event)

            history = self.context.format_for_prompt()
            full_prompt = prompt
            if history:
                full_prompt = f"Conversation history:\n{history}\n\n---\n\n{prompt}"

            result = self.cookbook.chat(
                full_prompt,
                think=think and use_thinking,
                on_progress=relay if on_progress else None,
                system_extra=system_extra,
            )
            if on_progress:
                on_progress({"kind": "model", "active": False, "model": model})
            return result

        loop = AgentLoop(
            thinking=self.thinking,
            chat_fn=chat_fn,
            server_running=server_running,
            toolkit=get_toolkit(self.cookbook.get_toolkit_name()),
            context_manager=self.context,
            memory=self.memory,
        )

        skill_was_used = False

        def local_act(action: str, ctx: Dict) -> Dict:
            nonlocal skill_was_used
            if action == "run_tool":
                result = self.tools.execute(ctx.get("input"))
                if result.get("ok"):
                    self.memory.append_note("tool", json.dumps(result, ensure_ascii=True)[:500])
                return result
            if action == "use_skill":
                skill_was_used = True
                skill_name = str(ctx.get("skill") or ctx.get("skill_name") or "")
                skill_path = ctx.get("skill_path")
                skill_body = ""
                if skill_path:
                    path = self.workspace_root / skill_path
                    if path.exists():
                        skill_body = path.read_text(encoding="utf-8")[:4000]
                return {
                    "ok": True,
                    "message": (
                        f"Loaded skill `{skill_name}`.\n"
                        f"{skill_body[:1200] if skill_body else 'No skill body on disk.'}\n"
                        f"Use run_tool to read/write files and evolve the harness."
                    ),
                    "skill": skill_name,
                }
            return {"ok": False, "error": f"unknown local action {action}"}

        initial_observations: List[str] = []

        loop_result = loop.run(
            request,
            skill_context=skill_context,
            local_act_fn=local_act,
            on_progress=on_progress,
            tools_prompt=capability_catalog,
            initial_observations=initial_observations,
            workspace_root=self.workspace_root,
        )

        if created and not skill_was_used:
            # Delete newly created skill if it wasn't helpful (not used in the loop)
            self.skills.delete_skill(created.name)
            created = None
            matched = None

        return self._finalize_request(
            request,
            message=loop_result["message"],
            thinking=loop_result.get("thinking", "") if use_thinking else "",
            use_thinking=use_thinking,
            warning=warning,
            server_running=server_running,
            matched=matched,
            created=created is not None,
            predicted=predicted,
            loop_result=loop_result,
        )

    def _conversational_turn(
        self,
        request: str,
        *,
        use_thinking: bool,
        on_progress: Optional[Callable[[Dict[str, Any]], None]],
        system_extra: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Single model call for simple prompts (no skill file, no multi-step loop)."""
        server_running = self.is_ollama_server_running()
        if server_running:
            history = self.context.format_for_prompt()
            prompt = request
            if history:
                prompt = f"Conversation history:\n{history}\n\n---\n\n{request}"
            chat = self.cookbook.chat(
                prompt,
                think=use_thinking,
                on_progress=on_progress,
                system_extra=system_extra or ADISN_TOOL_MANDATE,
            )
            if chat.get("ok"):
                return {
                    "message": chat.get("message", ""),
                    "thinking": chat.get("thinking", "") if use_thinking else "",
                    "steps": [],
                    "loop_steps": 0,
                    "ollama_used": True,
                }
        plan = (
            local_thinking_plan(
                request,
                predicted_action=self._predict_action(request),
                skill_name=None,
                scope=self.rewriter.get_scope(),
                ollama_available=server_running,
            )
            if use_thinking
            else ""
        )
        return {
            "message": request.strip(),
            "thinking": plan,
            "steps": [],
            "loop_steps": 0,
            "ollama_used": False,
        }

    def _finalize_request(
        self,
        request: str,
        *,
        message: str,
        thinking: str,
        use_thinking: bool,
        warning: Optional[str],
        server_running: bool,
        matched,
        created: bool,
        predicted: str,
        loop_result: Dict[str, Any],
    ) -> Dict:
        self.context.add("user", request)
        response = {
            "request": request,
            "message": message,
            "thinking": thinking if use_thinking and thinking else None,
            "thinking_enabled": use_thinking,
            "agent_loop": {
                "steps": loop_result.get("steps", []),
                "step_count": loop_result.get("loop_steps", 0),
            },
            "skill": asdict(matched) if matched else None,
            "created_new_skill": created,
            "next_action": predicted,
            "ollama_used": loop_result.get("ollama_used", False),
            "ollama_server_running": server_running,
            "active_model": self.cookbook.get_active_model(),
            "warning": warning,
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        self.context.add("assistant", json.dumps(response))
        self.memory.append_interaction(request, response)
        return response

    def cookbook_command(self, args: str) -> Dict:
        """Dispatch /cookbook subcommands."""
        parts = args.strip().split()
        if not parts:
            return self.cookbook.status()
        cmd = parts[0].lower()
        rest = parts[1:]

        if cmd == "ollama" and rest and rest[0] == "serve":
            return self.ollama_serve()
        if cmd == "scan":
            refresh = "--refresh" in rest
            return self.cookbook.scan(refresh=refresh)
        if cmd == "recommend":
            profile = rest[0] if rest else "balanced"
            return self.cookbook.recommend(profile)
        if cmd == "list":
            return self.cookbook.list_catalog()
        if cmd == "installed":
            return self.cookbook.list_installed()
        if cmd == "pull" and rest:
            return self.cookbook.pull(rest[0])
        if cmd == "rm" and rest:
            return self.cookbook.remove(rest[0])
        if cmd == "serve":
            if len(rest) >= 2 and rest[0] == "stop":
                return self.cookbook.serve_stop(rest[1])
            if len(rest) >= 2:
                port = int(rest[2]) if len(rest) > 2 and rest[2].isdigit() else None
                return self.cookbook.serve(rest[0], rest[1], port=port)
            return {"ok": False, "error": "usage: /cookbook serve <backend> <model> [port]"}
        if cmd == "serves":
            return self.cookbook.list_serves()
        if cmd == "providers":
            return self.cookbook.providers()
        if cmd == "provider" and len(rest) >= 3 and rest[0] == "add":
            return self.cookbook.provider_add(rest[1], rest[2])
        if cmd == "provider" and len(rest) >= 2 and rest[0] == "rm":
            return self.cookbook.provider_remove(rest[1])
        if cmd == "use" and rest:
            return self.cookbook.set_active_model(rest[0])
        if cmd == "deps":
            return self.cookbook.deps()
        if cmd == "status":
            return self.cookbook.status()
        return {
            "ok": False,
            "error": f"unknown cookbook command: {cmd}",
            "usage": _COOKBOOK_USAGE,
        }

    def rewrite(self, relative_path: str, new_content: str, reason: str) -> Dict:
        try:
            result = self.rewriter.rewrite_file(relative_path, new_content, reason)
        except Exception as exc:
            result = {"ok": False, "error": str(exc)}
        self.memory.append_note("rewrite", f"{reason} -> {relative_path}: {result}")
        return result

    def set_scope(self, scope: str) -> Dict:
        if scope not in {"global", "workspace"}:
            return {"ok": False, "error": "scope must be 'global' or 'workspace'"}
        self.rewriter.set_safe_global(scope == "workspace")
        result = {"ok": True, "scope": self.rewriter.get_scope()}
        self.memory.append_note("scope", json.dumps(result))
        return result

    def rollback_last_rewrite(self) -> Dict:
        result = self.rewriter.rollback_last()
        self.memory.append_note("rollback", str(result))
        return result

    def get_state(self) -> Dict:
        tokens = sum(chunk.tokens for chunk in self.context.snapshot())
        skills_index = self.workspace_root / "skills" / "INDEX.json"
        skill_count = 0
        if skills_index.exists():
            skill_count = len(json.loads(skills_index.read_text(encoding="utf-8")))

        server = self.questbook.server_status()
        models = (
            self.questbook.list_models(start_server=False)
            if server["server_running"]
            else self.questbook.read_cached_models()
        )
        cb = self.cookbook.status()
        state = AgentState(
            model_token_window=self.context.max_tokens,
            context_tokens_used=tokens,
            skill_count=skill_count,
            memory_entries=self.memory.count_entries(),
            ollama_installed=server["ollama_installed"],
            ollama_server_running=server["server_running"],
            ollama_models=len(models),
            rewrite_scope=self.rewriter.get_scope(),
            compact_threshold_ratio=self.context.compact_threshold_ratio,
            thinking_enabled=self.thinking.enabled,
            active_model=self.cookbook.get_active_model(),
            cookbook_serves=len(cb.get("serves", [])),
            workspace=str(self.workspace_root),
        )
        return asdict(state)

    def ollama_status(self) -> Dict:
        result = self.questbook.status()
        self.memory.append_note("ollama-status", json.dumps(result))
        return result

    def ollama_serve(self) -> Dict:
        """Start the Ollama daemon (`ollama serve`) if it is not already running."""
        result = self.questbook.start_server(wait_seconds=10.0)
        self.memory.append_note("ollama-serve", json.dumps(result))
        return result

    def ollama_list(self) -> Dict:
        return self.cookbook.list_installed()

    def ollama_pull(self, model: str) -> Dict:
        result = self.cookbook.pull(model)
        self.memory.append_note("ollama-pull", f"{model}: {result.get('ok')}")
        return result

    def ollama_remove(self, model: str) -> Dict:
        result = self.cookbook.remove(model)
        self.memory.append_note("ollama-rm", f"{model}: {result.get('ok')}")
        return result

    def ollama_profiles(self) -> Dict:
        return {"ok": True, "profiles": self.questbook.profiles()}

    def ollama_ensure_profile(self, profile: str) -> Dict:
        result = self.questbook.ensure_profile(profile)
        self.memory.append_note("ollama-profile", f"{profile}: {result.get('ok')}")
        return result

    def list_history(self, limit: int = 20) -> Dict:
        entries = self.memory.list_interactions(limit=limit)
        return {"ok": True, "entries": entries, "count": len(entries)}

    def load_history_prompt(self, entry_id: int) -> Dict:
        entry = self.memory.get_interaction(entry_id)
        if not entry:
            return {"ok": False, "error": f"history entry #{entry_id} not found"}
        return {
            "ok": True,
            "id": entry_id,
            "time": entry.get("time"),
            "request": entry.get("request", ""),
            "response_preview": entry.get("response_preview", ""),
        }

    def list_chats(self) -> Dict:
        chats = []
        for f in self.memory.memory_dir.glob("*.md"):
            chats.append({"name": f.name, "path": str(f)})
        return {"ok": True, "chats": chats}

    def resume_chat(self, chat_name: str) -> Dict:
        path = self.memory.memory_dir / chat_name
        if not path.exists():
            return {"ok": False, "error": f"Chat {chat_name} not found"}

        content = path.read_text(encoding="utf-8")
        self.context.clear()
        loaded = 0

        for line in content.splitlines():
            if line.startswith("- request: "):
                self.context.add("user", line[len("- request: "):])
                loaded += 1
            elif line.startswith("- response: "):
                resp_json = line[len("- response: "):]
                try:
                    resp_data = json.loads(resp_json)
                    msg = resp_data.get("message", "")
                    self.context.add("assistant", msg)
                except json.JSONDecodeError:
                    self.context.add("assistant", resp_json)

        return {
            "ok": True,
            "message": f"Resumed from {chat_name}",
            "history_count": self.context.count(),
            "turns_loaded": loaded,
        }

    def select_model_by_index(self, choice: str) -> Dict:
        models = self.questbook.read_cached_models()
        if not models and self.is_ollama_server_running():
            models = self.questbook.list_models(start_server=False)

        if not models:
            return {"ok": False, "error": "no models installed or Ollama is offline"}

        target = None
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(models):
                target = models[idx]["name"]
            else:
                return {"ok": False, "error": f"index {choice} out of range (1-{len(models)})"}
        else:
            for m in models:
                if m["name"] == choice or m["name"].startswith(f"{choice}:"):
                    target = m["name"]
                    break

        if not target:
            return {"ok": False, "error": f"model '{choice}' not found"}

        return self.cookbook.set_active_model(target)

    @staticmethod
    def _predict_action(request: str) -> str:
        text = request.lower()
        if any(x in text for x in ("fix", "debug", "error")):
            return "debug"
        if any(x in text for x in ("write", "implement", "create", "build")):
            return "build"
        if any(x in text for x in ("deploy", "infra", "aws", "git")):
            return "ops"
        if any(x in text for x in ("memory", "context", "tokens")):
            return "optimize_context"
        return "analyze"


_COOKBOOK_USAGE = (
    "/cookbook scan [--refresh] | recommend [profile] | list | installed | "
    "pull <model> | rm <model> | serve <ollama|llama-cpp|vllm> <target> [port] | "
    "serve stop <id> | serves | providers | provider add <n> <url> | "
    "provider rm <n> | use <model> | deps | status"
)
