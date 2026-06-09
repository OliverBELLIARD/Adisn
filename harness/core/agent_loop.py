"""Claude Code-style think → decide → act → observe agent loop."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from harness.core.context_window import ContextWindowManager
    from harness.memory.memory_manager import MemoryManager

from harness.core.direct_reply import request_needs_skill_workflow, try_direct_reply
from harness.core.tool_intent import is_refusal_message, tool_call_json
from harness.core.capability_index import suggest_tool_call
from harness.core.thinking import ThinkingMode, local_thinking_plan, split_thinking_and_response
from harness.core.toolkit import ToolkitParadigm, get_toolkit

@dataclass
class LoopStep:
    phase: str
    thinking: str = ""
    decision: Dict[str, Any] = field(default_factory=dict)
    observation: str = ""
    duration_ms: int = 0


def _serialize_tool_observation(result: Dict[str, Any], *, max_content: int = 3000) -> str:
    """JSON observation safe for parsing in finish heuristics (truncate inside fields)."""
    payload = dict(result)
    content = payload.get("content")
    if isinstance(content, str) and len(content) > max_content:
        payload["content"] = content[:max_content] + "\n… (truncated)"
    stdout = payload.get("stdout")
    if isinstance(stdout, str) and len(stdout) > max_content:
        payload["stdout"] = stdout[:max_content] + "\n… (truncated)"
    return json.dumps(payload, ensure_ascii=True)


def _parse_observation(raw: str) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if isinstance(data, dict):
        inner = data.get("result")
        if isinstance(inner, dict):
            return inner
        return data
    return None


class AgentLoop:
    """Multi-step reasoning loop with extended thinking (Claude Code pattern)."""

    def __init__(
        self,
        *,
        thinking: ThinkingMode,
        chat_fn: Callable[..., Dict[str, Any]],
        server_running: bool,
        max_steps: int = 6,
        step_timeout_s: float = 30.0,
        toolkit: Optional[ToolkitParadigm] = None,
        context_manager: Optional[ContextWindowManager] = None,
        memory: Optional[MemoryManager] = None,
    ):
        self.thinking = thinking
        self.chat_fn = chat_fn
        self.server_running = server_running
        self.max_steps = max_steps
        self.step_timeout_s = step_timeout_s
        self.toolkit = toolkit or get_toolkit("claude")
        self.context_manager = context_manager
        self.memory = memory

    def run(
        self,
        request: str,
        *,
        skill_context: Dict[str, Any],
        local_act_fn: Callable[[str, Dict[str, Any]], Dict[str, Any]],
        on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
        tools_prompt: str = "",
        initial_observations: Optional[List[str]] = None,
        workspace_root: Optional[Path] = None,
    ) -> Dict[str, Any]:
        steps: List[LoopStep] = []
        observations: List[str] = list(initial_observations or [])
        all_thinking: List[str] = []
        final_message = ""
        started = time.perf_counter()

        def emit(kind: str, **fields: Any) -> None:
            if on_progress:
                on_progress({"kind": kind, **fields})

        emit("loop_start", max_steps=self.max_steps, request=request[:120])

        # Consult past mistakes
        mistakes = ""
        continuation = ""
        if hasattr(self, "memory") and self.memory:
            res = self.memory.read_memory("past_mistakes.md", limit_lines=50)
            if res.get("ok"):
                mistakes = res.get("content", "")

            plan_path = self.memory.memory_dir / "continuation_plan.md"
            if plan_path.exists():
                continuation = plan_path.read_text(encoding="utf-8")
                plan_path.unlink() # Clear after loading

        if mistakes:
            observations.append(f"[Past Mistakes Log]:\n{mistakes}")

        if continuation:
            observations.append(f"[Continuation Plan Loaded]:\n{continuation}")

        direct = try_direct_reply(request)
        if direct:
            emit("headline", text="Replying…")
            return {
                "message": direct,
                "thinking": "",
                "steps": [],
                "loop_steps": 0,
                "ollama_used": False,
            }

        for step_idx in range(self.max_steps):
            if time.perf_counter() - started > self.step_timeout_s * self.max_steps:
                break
            t0 = time.perf_counter()

            emit(
                "step",
                step=step_idx + 1,
                max_steps=self.max_steps,
                phase="think",
            )

            # Combined think-decide step for memory efficiency
            thinking, decision = self._combined_step(
                request,
                skill_context,
                observations,
                step_idx,
                on_progress=on_progress,
                tools_prompt=tools_prompt,
                workspace_root=workspace_root,
            )

            step = LoopStep(phase="decide", thinking=thinking, decision=decision)
            all_thinking.append(thinking)
            if thinking:
                emit("thinking", text=thinking)

            action = decision.get("action", "respond")
            action_input = decision.get("input", "")
            if isinstance(action_input, dict):
                action_input = tool_call_json(action_input) if action == "run_tool" else json.dumps(
                    action_input, ensure_ascii=True
                )

            if action == "respond" and is_refusal_message(str(action_input)) and not _tools_were_used(observations):
                suggested = suggest_tool_call(workspace_root, request) if workspace_root else None
                payload = suggested or {"tool": "list_tools", "args": {}}
                action = "run_tool"
                action_input = tool_call_json(payload)
                step.decision = {
                    "action": action,
                    "input": action_input,
                    "reason": "refusal blocked — forcing tool attempt",
                }

            step.phase = "act"
            emit(
                "step",
                step=step_idx + 1,
                max_steps=self.max_steps,
                phase=action,
            )
            if action == "finish":
                final_message = action_input or decision.get("reason", "")
                if self.server_running and (_tools_were_used(observations) or step_idx > 0):
                    emit("headline", text="Analyzing result…")
                    critique = self._perform_critique(request, final_message, observations)
                    if not critique.get("satisfied", True):
                        feedback = critique.get("feedback", "Unsatisfied.")
                        observations.append(f"[Critique]: {feedback}")
                        if self.memory:
                            self.memory.record_mistake(request, f"Step {step_idx+1} approach", feedback)
                        emit("headline", text="Retrying…")
                        continue
                step.observation = "finished"
            elif action == "respond":
                final_message = action_input or self._fallback_response(request, skill_context)
                if self.server_running and not skill_context.get("skill_name"):
                    emit("headline", text="Analyzing result…")
                    critique = self._perform_critique(request, final_message, observations)
                    if not critique.get("satisfied", True):
                        feedback = critique.get("feedback", "Unsatisfied.")
                        observations.append(f"[Critique]: {feedback}")
                        if self.memory:
                            self.memory.record_mistake(request, f"Step {step_idx+1} response", feedback)
                        emit("headline", text="Retrying…")
                        continue
                step.observation = f"responded: {final_message[:50]}"
                if is_refusal_message(final_message) and not _tools_were_used(observations):
                    suggested = suggest_tool_call(workspace_root, request) if workspace_root else None
                    payload = suggested or {"tool": "list_tools", "args": {}}
                    result = local_act_fn(
                        "run_tool",
                        {"input": tool_call_json(payload), **skill_context},
                    )
                    obs = _serialize_tool_observation(result if isinstance(result, dict) else {"result": result})
                    observations.append(obs)
                    step.observation = f"refusal→tool: {obs[:200]}"
                    step.duration_ms = int((time.perf_counter() - t0) * 1000)
                    steps.append(step)
                    continue
            elif action == "run_tool":
                try:
                    tool_data = json.loads(action_input)
                    tool_name = tool_data.get("tool", "tool")
                except:
                    tool_name = "tool"
                emit("headline", text=f"Running {tool_name}…")
                emit("thinking", text=f"Executing tool: {tool_name}")

                if tool_name == "summarize_history" and hasattr(self, "context_manager"):
                    # Use the actual context manager if available
                    res = self.context_manager.manual_summarize()
                    obs = _serialize_tool_observation(res)
                else:
                    result = local_act_fn("run_tool", {"input": action_input, **skill_context})
                    obs = _serialize_tool_observation(result if isinstance(result, dict) else {"result": result})
                observations.append(obs)
                step.observation = obs[:400]
                emit("headline", text="Working…")
            elif action == "use_skill":
                result = local_act_fn("use_skill", {"skill": action_input, **skill_context})
                obs = _serialize_tool_observation(result if isinstance(result, dict) else {"result": result})
                observations.append(obs)
                step.observation = obs[:400]
                if result.get("message"):
                    final_message = result["message"]
            elif action == "note":
                observations.append(action_input)
                step.observation = action_input
            else:
                observations.append(f"unknown action {action}")
                step.observation = observations[-1]

            step.duration_ms = int((time.perf_counter() - t0) * 1000)
            steps.append(step)

            if action == "finish":
                break
            if action == "respond" and not skill_context.get("skill_name"):
                break

        # Persistence and Memory Management
        if hasattr(self, "context_manager") and self.context_manager:
            if self.context_manager._total_tokens() > self.context_manager.compact_threshold_tokens:
                emit("headline", text="Compacting memory…")
                self.context_manager.manual_summarize()

                # Create continuation plan if intent not satisfied and memory was compressed
                if self.server_running and self.memory:
                    plan_path = self.memory.memory_dir / "continuation_plan.md"
                    plan_content = (
                        f"# Continuation Plan\n\n"
                        f"**User Intent**: {request}\n"
                        f"**Status**: Memory threshold reached and compressed.\n"
                        f"**Progress**: {len(steps)} steps executed.\n"
                        f"**Last Observation**: {observations[-1] if observations else 'None'}\n\n"
                        "## Next Steps\n"
                        "Continue the analysis and execution from the last state."
                    )
                    plan_path.write_text(plan_content, encoding="utf-8")

        if not final_message:
            final_message = self._fallback_response(request, skill_context)

        emit("loop_done", steps=len(steps), message_preview=final_message[:80])

        return {
            "message": final_message,
            "thinking": "\n\n---\n\n".join(all_thinking) if all_thinking else "",
            "steps": [self._step_to_dict(s) for s in steps],
            "loop_steps": len(steps),
            "ollama_used": self.server_running and any(
                "ollama" in (s.thinking or "").lower() for s in steps
            ),
        }

    def _combined_step(
        self,
        request: str,
        skill_context: Dict[str, Any],
        observations: List[str],
        step_idx: int,
        *,
        on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
        tools_prompt: str = "",
        workspace_root: Optional[Path] = None,
    ) -> tuple[str, Dict[str, Any]]:
        """Combined think + decide step to minimize LLM roundtrips and token usage."""
        local_plan = local_thinking_plan(
            request if step_idx == 0 else f"Continue: {request}",
            predicted_action=skill_context.get("next_action", "analyze"),
            skill_name=skill_context.get("skill_name"),
            scope=skill_context.get("scope", "global"),
            ollama_available=self.server_running,
        )

        if not self.server_running:
            if observations:
                local_plan += "\nObservations:\n" + "\n".join(f"- {o}" for o in observations[-3:])
            decision = _heuristic_decision(request, skill_context, observations, workspace_root=workspace_root)
            return local_plan, decision

        tool_block = f"\n{tools_prompt}\n" if tools_prompt else ""
        obs_text = _format_observations_for_prompt(observations[-3:])
        continuation_hint = ""
        if step_idx > 0 and observations:
            files_read = sum(1 for o in observations if '"content"' in o)
            if files_read == 0:
                continuation_hint = (
                    "\nYou have listed a directory but not read any files yet. "
                    "Use run_tool with read_file to examine key source files before answering.\n"
                )
        prompt = (
            f"{self.toolkit.system_prompt}\n{tool_block}\n"
            f"Request: {request}\n"
            f"Step: {step_idx + 1}\n"
            f"Prior tool results:\n{obs_text}\n"
            f"{continuation_hint}"
            f"{self.toolkit.decision_prompt}"
        )

        if on_progress:
            on_progress({"kind": "model", "active": True, "phase": "think-decide"})

        # Ask for thinking and decision in one go
        chat = self.chat_fn(prompt, think=self.thinking.enabled, on_progress=on_progress)

        if on_progress:
            on_progress({"kind": "model", "active": False, "phase": "think-decide"})

        thinking = local_plan
        decision = {}

        if chat.get("ok"):
            # Extract native thinking if provided (e.g. by Ollama think API)
            thinking = (chat.get("thinking") or "").strip() or local_plan

            raw_text = chat.get("message", "") + chat.get("raw", "")
            # If thinking wasn't in the native field, it might be in the content
            if not chat.get("thinking"):
                t, _ = split_thinking_and_response(raw_text)
                if t:
                    thinking = t

            decision = self.toolkit.extract_decision(raw_text) or {}

        if not decision:
            decision = _heuristic_decision(request, skill_context, observations, workspace_root=workspace_root)

        return thinking, decision

    @staticmethod
    def _fallback_response(request: str, skill_context: Dict[str, Any]) -> str:
        skill = skill_context.get("skill_name") or "new skill"
        action = skill_context.get("next_action", "analyze")
        return (
            f"Handled `{request[:100]}` using skill `{skill}`.\n"
            f"Planned workflow: {action}."
        )

    @staticmethod
    def _step_to_dict(step: LoopStep) -> Dict[str, Any]:
        return {
            "phase": step.phase,
            "thinking": step.thinking[:400] if step.thinking else "",
            "decision": step.decision,
            "observation": step.observation[:400] if step.observation else "",
            "duration_ms": step.duration_ms,
        }

    def _perform_critique(self, request: str, response: str, observations: List[str]) -> Dict[str, Any]:
        prompt = (
            "You are an extremely critical auditor. Review the following task and response.\n"
            f"User Intent: {request}\n"
            f"Agent Response: {response}\n"
            f"Observations: {observations[-3:] if observations else 'None'}\n\n"
            "Does the response satisfy the user intent? Be extremely critical.\n"
            "Reject (satisfied=false) if:\n"
            "1. The agent's response only describes what it *will* do instead of having done it.\n"
            "2. The agent only completed a sub-task (like creating a skill) but didn't finish the main request.\n"
            "3. The agent failed to verbally verify that the intent was satisfied.\n"
            "4. The response is conversational but the task required tool use that wasn't completed.\n\n"
            "Return JSON: {\"satisfied\": true/false, \"feedback\": \"...\"}"
        )
        chat = self.chat_fn(prompt, think=False)
        if chat.get("ok"):
            text = chat.get("message", "")
            match = re.search(r"\{.*\"satisfied\".*\}", text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except:
                    pass
        return {"satisfied": True}


def _needs_file_analysis(request: str) -> bool:
    """True when the request requires reading/analyzing code, not just listing."""
    low = request.lower()
    return any(w in low for w in (
        "change", "improve", "what would", "analyze", "harness", "code",
        "modify", "implement", "fix", "explain", "how does", "tell me",
        "read", "review", "assess", "understand",
    ))


def _format_observations_for_prompt(observations: List[str]) -> str:
    """Format raw JSON observations into human-readable text for LLM prompts."""
    if not observations:
        return "none"
    parts = []
    for obs in observations:
        result = _parse_observation(obs)
        if not result:
            parts.append(obs[:300])
            continue
        if result.get("entries"):
            names = [f"{e.get('name')} ({e.get('type')})" for e in result["entries"][:20]]
            parts.append(f"[directory listing]: {', '.join(names)}")
        elif result.get("content") is not None:
            path = result.get("path", "file")
            snippet = str(result["content"])[:600]
            parts.append(f"[read {path}]:\n{snippet}")
        elif result.get("stdout") is not None:
            parts.append(f"[shell output]:\n{str(result.get('stdout', ''))[:400]}")
        elif result.get("message"):
            parts.append(f"[result]: {result['message'][:200]}")
        else:
            parts.append(obs[:300])
    return "\n\n".join(parts)


def _extract_decision(text: str) -> Optional[Dict[str, Any]]:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                data = json.loads(line)
                if "action" in data:
                    return data
            except json.JSONDecodeError:
                continue
    match = re.search(r"\{[^{}]*\"action\"[^{}]*\}", text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return None


def _tools_were_used(observations: List[str]) -> bool:
    for obs in observations:
        if '"bootstrap": "available_tools"' in obs:
            continue
        low = obs.lower()
        if any(
            marker in low
            for marker in (
                '"bootstrap": "preflight_tool"',
                '"entries"',
                '"content"',
                "read_file",
                "write_file",
                '"stdout"',
            )
        ):
            return True
    return False


def _heuristic_decision(
    request: str,
    skill_context: Dict[str, Any],
    observations: List[str],
    *,
    workspace_root: Optional[Path] = None,
) -> Dict[str, Any]:
    direct = try_direct_reply(request)
    if direct:
        action = "finish" if observations else "respond"
        return {"action": action, "input": direct, "reason": "direct reply"}

    if observations and _tools_were_used(observations):
        # After a directory listing alone, read key files before finishing if analysis is needed
        files_read = sum(1 for o in observations if '"content"' in o)
        if files_read == 0 and _needs_file_analysis(request) and workspace_root:
            last_obs = observations[-1] if observations else ""
            last_result = _parse_observation(last_obs)
            entries = last_result.get("entries", []) if last_result else []
            next_file = _suggest_next_read(request, entries, workspace_root, observations)
            if next_file:
                return {
                    "action": "run_tool",
                    "input": tool_call_json({"tool": "read_file", "args": {"path": next_file}}),
                    "reason": f"reading {next_file} to analyze codebase",
                }
        return {
            "action": "finish",
            "input": _heuristic_finish_message(request, skill_context, observations),
            "reason": "tool observations collected",
        }

    if skill_context.get("skill_name") and request_needs_skill_workflow(request):
        return {
            "action": "use_skill",
            "input": skill_context["skill_name"],
            "reason": "matched skill",
        }

    inferred = suggest_tool_call(workspace_root, request) if workspace_root else None
    if inferred and not _tools_were_used(observations):
        return {
            "action": "run_tool",
            "input": tool_call_json(inferred),
            "reason": "best match from tools/INDEX.json",
        }

    if not _tools_were_used(observations):
        return {
            "action": "run_tool",
            "input": tool_call_json({"tool": "list_tools", "args": {}}),
            "reason": "inspect tools/INDEX.json",
        }

    if observations:
        return {
            "action": "finish",
            "input": _heuristic_finish_message(request, skill_context, observations),
            "reason": "observations collected",
        }

    return {
        "action": "run_tool",
        "input": tool_call_json({"tool": "list_tools", "args": {}}),
        "reason": "must use tools before responding",
    }


def _suggest_next_read(
    request: str,
    entries: List[Dict[str, Any]],
    workspace_root: Path,
    observations: List[str],
) -> Optional[str]:
    """Pick the next key file to read for codebase analysis, skipping already-read files."""
    already_read = set()
    for obs in observations:
        result = _parse_observation(obs)
        if result and result.get("path"):
            already_read.add(result["path"])

    # Priority list for harness analysis requests
    priority = [
        "harness/core/agent_loop.py",
        "harness/core/agent.py",
        "harness/core/toolkit.py",
        "harness/core/direct_reply.py",
        "harness/core/task_complexity.py",
        "HARNESS_SUMMARY.md",
        "README.md",
    ]
    low = request.lower()
    if "tool" in low:
        priority = ["harness/core/tool_executor.py"] + priority
    if "skill" in low:
        priority = ["harness/core/skill_store.py"] + priority
    if "memory" in low:
        priority = ["harness/memory/memory_manager.py"] + priority

    for rel in priority:
        if rel not in already_read and (workspace_root / rel).exists():
            return rel

    # Fall back to any .py file in directory listing
    for e in entries:
        name = e.get("name", "")
        if name.endswith(".py") and name not in already_read:
            return name

    return None


def _conversational_response(request: str, skill_context: Dict[str, Any]) -> str:
    return request.strip() or (
        f"Next: {skill_context.get('next_action', 'analyze')}"
    )


def _heuristic_finish_message(
    request: str, skill_context: Dict[str, Any], observations: List[str]
) -> str:
    direct = try_direct_reply(request)
    if direct:
        return direct

    files_read: List[tuple] = []
    dir_listing: Optional[str] = None

    for raw in observations:
        result = _parse_observation(raw)
        if not result:
            continue
        if result.get("entries") and dir_listing is None:
            lines = [f"- {e.get('name')} ({e.get('type')})" for e in result["entries"][:40]]
            dir_listing = "Directory listing:\n" + "\n".join(lines)
        if result.get("content") is not None:
            path = result.get("path", "file")
            body = str(result["content"]).strip()
            files_read.append((path, body))
        elif result.get("stdout") is not None:
            files_read.append(("shell", str(result.get("stdout", ""))[:4000]))
        elif result.get("message") and not result.get("entries"):
            files_read.append(("result", str(result["message"])))

    if files_read:
        parts = []
        char_budget = 8000
        for path, body in files_read:
            allotment = min(char_budget, 3000)
            if len(body) > allotment:
                body = body[:allotment - 3] + "…"
            parts.append(f"[{path}]\n{body}")
            char_budget -= len(body)
            if char_budget <= 0:
                break
        return "\n\n---\n\n".join(parts)

    if dir_listing:
        return dir_listing

    skill = skill_context.get("skill_name") or "generated"
    return (
        f"Finished: {request[:100]}\n"
        f"(matched skill `{skill}`, {len(observations)} tool step(s)). "
        "Ask a follow-up for details."
    )
