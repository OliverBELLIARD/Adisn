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
        "You are Adisn, a coding harness agent. Work like Claude Code:\n"
        "1) Think through the request in a <think> block before acting.\n"
        "2) Decide ONE next step as JSON on its own line: {\"action\":\"...\",\"input\":\"...\",\"reason\":\"...\"}\n"
        "Valid actions: respond, use_skill, note, finish\n"
        "- respond: answer the user (input = message text)\n"
        "- use_skill: apply matched skill plan (input = skill name)\n"
        "- note: store observation (input = text)\n"
        "- finish: complete with final message (input = message)"
    ),
    decision_prompt="Output the JSON decision line now."
)

DEEPSEEK_PARADIGM = ToolkitParadigm(
    name="deepseek",
    system_prompt=(
        "You are Adisn. You use <think> for reasoning.\n"
        "After reasoning, provide your decision as a single JSON object in a markdown code block.\n"
        "Actions: respond, use_skill, note, finish.\n"
        "Format: ```json\n{\"action\": \"...\", \"input\": \"...\", \"reason\": \"...\"}\n```"
    ),
    decision_prompt="Provide your JSON decision in a ```json code block.",
    extraction_regex=r"```json\s*(\{.*?\})\s*```"
)

QWEN_PARADIGM = ToolkitParadigm(
    name="qwen",
    system_prompt=(
        "You are Adisn. Respond with a JSON action to perform.\n"
        "Actions: respond, use_skill, note, finish.\n"
        "Always output valid JSON."
    ),
    decision_prompt="Return a JSON object with 'action', 'input', and 'reason'.",
)

GEMMA_PARADIGM = ToolkitParadigm(
    name="gemma",
    system_prompt=(
        "You are Adisn. You must decide the next action.\n"
        "Use the following XML-like format for your decision:\n"
        "<decision>\n{\"action\": \"...\", \"input\": \"...\", \"reason\": \"...\"}\n</decision>"
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

def get_toolkit(name: str) -> ToolkitParadigm:
    return TOOLKITS.get(name, CLAUDE_PARADIGM)
