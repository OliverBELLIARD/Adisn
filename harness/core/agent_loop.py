"""Claude Code-style think → decide → act → observe agent loop."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

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
    ):
        self.thinking = thinking
        self.chat_fn = chat_fn
        self.server_running = server_running
        self.max_steps = max_steps
        self.step_timeout_s = step_timeout_s
        self.toolkit = toolkit or get_toolkit("claude")

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
            step = LoopStep(phase="think")
            t0 = time.perf_counter()

            emit(
                "step",
                step=step_idx + 1,
                max_steps=self.max_steps,
                phase="think",
            )
            step.thinking = self._think_step(
                request,
                skill_context,
                observations,
                step_idx,
                on_progress=on_progress,
            )
            all_thinking.append(step.thinking)
            if step.thinking:
                emit("thinking", text=step.thinking)

            step.phase = "decide"
            emit(
                "step",
                step=step_idx + 1,
                max_steps=self.max_steps,
                phase="decide",
            )
            decision = self._decide_step(
                request,
                skill_context,
                observations,
                step.thinking,
                on_progress=on_progress,
                tools_prompt=tools_prompt,
                workspace_root=workspace_root,
            )
            step.decision = decision

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
                step.observation = "finished"
            elif action == "respond":
                final_message = action_input or self._fallback_response(request, skill_context)
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
                result = local_act_fn("run_tool", {"input": action_input, **skill_context})
                obs = _serialize_tool_observation(result if isinstance(result, dict) else {"result": result})
                observations.append(obs)
                step.observation = obs[:400]
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

    def _think_step(
        self,
        request: str,
        skill_context: Dict[str, Any],
        observations: List[str],
        step_idx: int,
        *,
        on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> str:
        local = local_thinking_plan(
            request if step_idx == 0 else f"Continue: {request}",
            predicted_action=skill_context.get("next_action", "analyze"),
            skill_name=skill_context.get("skill_name"),
            scope=skill_context.get("scope", "global"),
            ollama_available=self.server_running,
        )
        if not self.thinking.enabled or not self.server_running:
            if observations:
                local += "\nObservations:\n" + "\n".join(f"- {o}" for o in observations[-3:])
            return local

        prompt = (
            f"Request: {request}\n"
            f"Step: {step_idx + 1}\n"
            f"Skill: {skill_context.get('skill_name')}\n"
            f"Prior observations: {observations[-3:] if observations else 'none'}\n"
            "Think only — plan the next single action."
        )
        if on_progress:
            on_progress({"kind": "model", "active": True, "phase": "think"})
        chat = self.chat_fn(prompt, think=True, on_progress=on_progress)
        if on_progress:
            on_progress({"kind": "model", "active": False, "phase": "think"})
        if chat.get("ok"):
            native = (chat.get("thinking") or "").strip()
            if native:
                return native
            raw = chat.get("raw") or chat.get("message", "")
            t, _ = split_thinking_and_response(raw)
            if t:
                return t
            return local
        return local + f"\n(chat unavailable: {chat.get('error')})"

    def _decide_step(
        self,
        request: str,
        skill_context: Dict[str, Any],
        observations: List[str],
        thinking: str,
        *,
        on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
        tools_prompt: str = "",
        workspace_root: Optional[Path] = None,
    ) -> Dict[str, Any]:
        if self.server_running and self.thinking.enabled:
            tool_block = f"\n{tools_prompt}\n" if tools_prompt else ""
            prompt = (
                f"{self.toolkit.system_prompt}\n{tool_block}\nRequest: {request}\n"
                f"Thinking:\n{thinking}\n"
                f"Observations: {observations}\n"
                f"{self.toolkit.decision_prompt}"
            )
            if on_progress:
                on_progress({"kind": "model", "active": True, "phase": "decide"})
            chat = self.chat_fn(prompt, think=False, on_progress=on_progress)
            if on_progress:
                on_progress({"kind": "model", "active": False, "phase": "decide"})
            if chat.get("ok"):
                raw_text = chat.get("message", "") + chat.get("raw", "")
                parsed = self.toolkit.extract_decision(raw_text)
                if parsed:
                    return parsed

        return _heuristic_decision(
            request, skill_context, observations, workspace_root=workspace_root
        )

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

    for raw in reversed(observations):
        result = _parse_observation(raw)
        if not result:
            continue
        if result.get("entries"):
            lines = [f"- {e.get('name')} ({e.get('type')})" for e in result["entries"][:40]]
            return "Directory listing:\n" + "\n".join(lines)
        if result.get("content"):
            path = result.get("path", "file")
            body = str(result["content"]).strip()
            if len(body) > 4000:
                body = body[:3997] + "…"
            return f"Contents of {path}:\n{body}"
        if result.get("stdout") is not None:
            return f"$ command output\n{str(result.get('stdout', ''))[:4000]}"
        if result.get("message"):
            return str(result["message"])

    skill = skill_context.get("skill_name") or "generated"
    return (
        f"Finished: {request[:100]}\n"
        f"(matched skill `{skill}`, {len(observations)} tool step(s)). "
        "Ask a follow-up for details."
    )
