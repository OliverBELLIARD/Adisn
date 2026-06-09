"""Tool-calling paradigms for different model families."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class ToolkitParadigm:
    name: str
    system_prompt: str
    decision_prompt: str
    extraction_regex: Optional[str] = None

    def extract_decision(self, text: str) -> Optional[Dict[str, Any]]:
        if self.extraction_regex:
            match = re.search(self.extraction_regex, text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass

        # Fallback to standard line-by-line JSON search
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                try:
                    data = json.loads(line)
                    if "action" in data:
                        return data
                except json.JSONDecodeError:
                    continue

        # Last ditch regex search for any JSON-like object with "action"
        match = re.search(r"\{[^{}]*\"action\"[^{}]*\}", text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return None
        return None


CLAUDE_PARADIGM = ToolkitParadigm(
    name="claude",
    system_prompt=(
        "You are Adisn, a self-evolving coding harness agent. Work like Claude Code:\n"
        "1) Identify the user's specific intent and execute systematically.\n"
        "2) Reason through the task in a <think> block before acting.\n"
        "3) Decide ONE next step as JSON on its own line: {\"action\":\"...\",\"input\":\"...\",\"reason\":\"...\"}\n"
        "Valid actions: respond, use_skill, run_tool, note, finish\n"
        "- respond: answer the user (input = message text)\n"
        "- use_skill: apply matched skill plan (input = skill name)\n"
        "- run_tool: invoke a harness tool (input = JSON {\"tool\":\"...\",\"args\":{...}})\n"
        "  Tools include read_file, write_file (modify harness source), list_dir, grep, shell,\n"
        "  create_skill, create_tool, read_skill, list_tools, pip_install.\n"
        "- note: store observation (input = text)\n"
        "- finish: complete with final message (input = message)\n"
        "Use run_tool to read/write code, create new tools, and evolve the harness.\n"
        "Proactively use `create_skill` to automate repetitive tasks or complex multi-step workflows. Ensure skills are general and reusable.\n"
        "NEVER claim you cannot access files or run commands — you run locally with full tool access.\n"
        "Read skills/INDEX.json and tools/INDEX.json; pick the best-matching skill or tool for the request.\n"
        "Consult .adisn/chats/past_mistakes.md to avoid repeating previous failures.\n"
        "You are NOT allowed to finish until you have truly satisfied the user's intent. Verbally verify this satisfaction in your final message."
    ),
    decision_prompt="Output the JSON decision line now."
)

DEEPSEEK_PARADIGM = ToolkitParadigm(
    name="deepseek",
    system_prompt=(
        "You are Adisn. Identify the user's intent and execute systematically. You use <think> for reasoning.\n"
        "After reasoning, provide your decision as a single JSON object in a markdown code block.\n"
        "Actions: respond, use_skill, run_tool, note, finish.\n"
        "run_tool input is JSON: {\"tool\":\"read_file|write_file|shell|...\",\"args\":{...}}\n"
        "Proactively use `create_skill` for multi-step work; ensure they are general.\n"
        "Consult .adisn/chats/past_mistakes.md to avoid repeating failures.\n"
        "Format: ```json\n{\"action\": \"...\", \"input\": \"...\", \"reason\": \"...\"}\n```\n"
        "You are NOT allowed to finish until you have truly satisfied the user's intent. Verbally verify this satisfaction in your final message."
    ),
    decision_prompt="Provide your JSON decision in a ```json code block.",
    extraction_regex=r"```json\s*(\{.*?\})\s*```"
)

QWEN_PARADIGM = ToolkitParadigm(
    name="qwen",
    system_prompt=(
        "You are Adisn, a self-evolving coding harness agent optimized for Qwen.\n"
        "1) Identify the user's intent and execute systematically.\n"
        "2) Reason through the task in a <think> block first.\n"
        "3) Provide your decision as a single JSON object: {\"action\":\"...\",\"input\":\"...\",\"reason\":\"...\"}\n"
        "Valid actions: respond, use_skill, run_tool, note, finish\n"
        "- respond: conversational reply (input = text)\n"
        "- use_skill: activate a procedure (input = skill name)\n"
        "- run_tool: execute a harness tool (input = JSON {\"tool\":\"name\",\"args\":{...}})\n"
        "  Available tools: read_file, write_file, patch_file, read_file_chunked, list_dir, grep, shell,\n"
        "  create_skill, create_tool, read_skill, read_memory, summarize_history, list_tools, pip_install.\n"
        "- note: record an observation (input = text)\n"
        "- finish: end the task with a final report (input = report text)\n"
        "Proactively use `create_skill` to automate multi-step work. Ensure skills are general and reusable, avoiding overfitting to specific filenames or paths unless necessary.\n"
        "Use `patch_file` for targeted code edits to save context space.\n"
        "NEVER claim you lack permissions or tool access. You run locally with full capabilities.\n"
        "Read skills/INDEX.json and tools/INDEX.json to select the best capabilities.\n"
        "Consult .adisn/chats/past_mistakes.md to avoid repeating previous failures.\n"
        "You are NOT allowed to finish until you have truly satisfied the user's intent. Verbally verify this satisfaction in your final message."
    ),
    decision_prompt="Return a JSON object with 'action', 'input', and 'reason'.",
)

GEMMA_PARADIGM = ToolkitParadigm(
    name="gemma",
    system_prompt=(
        "You are Adisn. Identify the user's intent and execute systematically. You must decide the next action.\n"
        "Actions: respond, use_skill, run_tool, note, finish.\n"
        "run_tool input is JSON with tool name and args (read_file, write_file, shell, create_tool, etc.).\n"
        "Proactively use `create_skill` for multi-step work; keep them general.\n"
        "Consult .adisn/chats/past_mistakes.md to avoid failures.\n"
        "Use the following XML-like format for your decision:\n"
        "<decision>\n{\"action\": \"...\", \"input\": \"...\", \"reason\": \"...\"}\n</decision>\n"
        "You are NOT allowed to finish until you have truly satisfied the user's intent. Verbally verify this satisfaction in your final message."
    ),
    decision_prompt="Output your decision inside <decision>...</decision> tags.",
    extraction_regex=r"<decision>\s*(\{.*?\})\s*</decision>"
)

TOOLKITS = {
    "claude": CLAUDE_PARADIGM,
    "deepseek": DEEPSEEK_PARADIGM,
    "qwen": QWEN_PARADIGM,
    "gemma": GEMMA_PARADIGM,
}

TOOLKIT_SUMMARIES: Dict[str, str] = {
    "claude": "Single-line JSON decision after optional thinking (Claude Code style)",
    "deepseek": "JSON decision inside a ```json markdown code block",
    "qwen": "Raw JSON object with action, input, and reason fields",
    "gemma": "JSON decision wrapped in <decision>...</decision> tags",
}


def list_toolkit_names() -> list[str]:
    return list(TOOLKITS.keys())


def format_toolkits_display(active: str) -> str:
    """Human-readable list of tool-calling paradigms for /toolkit."""
    active = (active or "claude").lower().strip()
    lines = [
        "Tool-calling paradigms (agent loop decision output format):",
        "",
    ]
    for name in list_toolkit_names():
        marker = " (active)" if name == active else ""
        summary = TOOLKIT_SUMMARIES.get(name, "")
        lines.append(f"  {name}{marker}")
        lines.append(f"    {summary}")
        lines.append("")
    lines.append("Set paradigm: /toolkit <name>")
    lines.append(f"Available: {', '.join(list_toolkit_names())}")
    return "\n".join(lines).rstrip()


def get_toolkit(name: str) -> ToolkitParadigm:
    return TOOLKITS.get(name.lower().strip(), CLAUDE_PARADIGM)
