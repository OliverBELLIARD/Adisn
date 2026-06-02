"""Claude Code-style think → decide → act → observe agent loop."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from harness.core.direct_reply import request_needs_skill_workflow, try_direct_reply
from harness.core.thinking import ThinkingMode, local_thinking_plan, split_thinking_and_response

LOOP_SYSTEM = """You are Alison, a coding harness agent. Work like Claude Code:
1) Think through the request in a  block before acting.
2) Decide ONE next step as JSON on its own line: {"action":"...","input":"...","reason":"..."}
Valid actions: respond, use_skill, note, finish
- respond: answer the user (input = message text)
- use_skill: apply matched skill plan (input = skill name)
- note: store observation (input = text)
- finish: complete with final message (input = message)
After JSON, you may add a short user-visible message."""


@dataclass
class LoopStep:
    phase: str
    thinking: str = ""
    decision: Dict[str, Any] = field(default_factory=dict)
    observation: str = ""
    duration_ms: int = 0


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
    ):
        self.thinking = thinking
        self.chat_fn = chat_fn
        self.server_running = server_running
        self.max_steps = max_steps
        self.step_timeout_s = step_timeout_s

    def run(
        self,
        request: str,
        *,
        skill_context: Dict[str, Any],
        local_act_fn: Callable[[str, Dict[str, Any]], Dict[str, Any]],
        on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        steps: List[LoopStep] = []
        observations: List[str] = []
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
            )
            step.decision = decision

            action = decision.get("action", "respond")
            action_input = decision.get("input", "")

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
                step.duration_ms = int((time.perf_counter() - t0) * 1000)
                steps.append(step)
                break
            if action == "respond":
                final_message = action_input or self._fallback_response(request, skill_context)
                step.observation = "responded"
                step.duration_ms = int((time.perf_counter() - t0) * 1000)
                steps.append(step)
                break
            if action == "use_skill":
                result = local_act_fn("use_skill", {"skill": action_input, **skill_context})
                obs = json.dumps(result, ensure_ascii=True)[:500]
                observations.append(obs)
                step.observation = obs
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
            thinking = chat.get("thinking") or ""
            if thinking:
                return thinking
            content = chat.get("message", "")
            t, _ = split_thinking_and_response(content)
            return t or local
        return local + f"\n(chat unavailable: {chat.get('error')})"

    def _decide_step(
        self,
        request: str,
        skill_context: Dict[str, Any],
        observations: List[str],
        thinking: str,
        *,
        on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        if self.server_running and self.thinking.enabled:
            prompt = (
                f"{LOOP_SYSTEM}\n\nRequest: {request}\n"
                f"Thinking:\n{thinking}\n"
                f"Observations: {observations}\n"
                "Output the JSON decision line now."
            )
            if on_progress:
                on_progress({"kind": "model", "active": True, "phase": "decide"})
            chat = self.chat_fn(prompt, think=False, on_progress=on_progress)
            if on_progress:
                on_progress({"kind": "model", "active": False, "phase": "decide"})
            if chat.get("ok"):
                parsed = _extract_decision(chat.get("message", "") + chat.get("raw", ""))
                if parsed:
                    return parsed

        return _heuristic_decision(request, skill_context, observations)

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


def _heuristic_decision(
    request: str, skill_context: Dict[str, Any], observations: List[str]
) -> Dict[str, Any]:
    direct = try_direct_reply(request)
    if direct:
        action = "finish" if observations else "respond"
        return {"action": action, "input": direct, "reason": "direct reply"}

    if observations:
        return {
            "action": "finish",
            "input": _heuristic_finish_message(request, skill_context, observations),
            "reason": "observations collected",
        }
    if skill_context.get("skill_name") and request_needs_skill_workflow(request):
        return {
            "action": "use_skill",
            "input": skill_context["skill_name"],
            "reason": "matched skill",
        }
    return {
        "action": "respond",
        "input": direct or _conversational_response(request, skill_context),
        "reason": "direct response",
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
    skill = skill_context.get("skill_name") or "generated"
    return (
        f"Done working on: {request[:100]}\n"
        f"(skill `{skill}`, {len(observations)} observation(s))"
    )
