"""Tests for harness tool executor and prompt history."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from harness.core.agent import HarnessAgent
from harness.core.self_rewriter import SelfRewriter
from harness.core.skill_store import SkillStore
from harness.core.tool_executor import ToolExecutor
from harness.memory.memory_manager import MemoryManager


class TestToolExecutor(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.rewriter = SelfRewriter(self.root, safe_global=False)
        self.skills = SkillStore(self.root)
        self.tools = ToolExecutor(self.root, self.rewriter, self.skills)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_read_and_write_file(self) -> None:
        target = self.root / "harness" / "sample.py"
        target.parent.mkdir(parents=True)
        target.write_text("x = 1\n", encoding="utf-8")
        read = self.tools.execute(json.dumps({"tool": "read_file", "args": {"path": "harness/sample.py"}}))
        self.assertTrue(read["ok"])
        self.assertIn("x = 1", read["content"])

        write = self.tools.execute(
            json.dumps(
                {
                    "tool": "write_file",
                    "args": {"path": "harness/sample.py", "content": "x = 2\n", "reason": "test"},
                }
            )
        )
        self.assertTrue(write["ok"])
        self.assertEqual("x = 2\n", target.read_text(encoding="utf-8"))

    def test_create_tool_registers_module(self) -> None:
        code = "def run(args):\n    return {'ok': True, 'echo': args.get('input', '')}\n"
        result = self.tools.execute(
            json.dumps(
                {
                    "tool": "create_tool",
                    "args": {"name": "echo-tool", "description": "echo", "code": code},
                }
            )
        )
        self.assertTrue(result["ok"])
        custom = self.tools.execute(json.dumps({"tool": "echo-tool", "args": {"input": "hi"}}))
        self.assertTrue(custom["ok"])
        self.assertEqual("hi", custom["echo"])

    def test_list_tools_includes_builtins(self) -> None:
        names = {spec.name for spec in self.tools.list_tools()}
        self.assertIn("write_file", names)
        self.assertIn("create_tool", names)


class TestPromptHistory(unittest.TestCase):
    def test_list_and_load_interactions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = MemoryManager(root)
            memory.append_interaction("first prompt", {"message": "first reply"})
            memory.append_interaction("second prompt", {"message": "second reply"})
            entries = memory.list_interactions()
            self.assertEqual(2, len(entries))
            self.assertEqual("second prompt", entries[-1]["request"])
            loaded = memory.get_interaction(entries[-1]["id"])
            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual("second prompt", loaded["request"])

    def test_resume_chat_populates_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            agent = HarnessAgent(workspace_root=Path(tmp))
            agent.memory.append_interaction("hello", {"message": "world"})
            result = agent.resume_chat("now.md")
            self.assertTrue(result["ok"])
            self.assertGreaterEqual(result["history_count"], 1)
            self.assertIn("hello", agent.context.format_for_prompt())


if __name__ == "__main__":
    unittest.main()
