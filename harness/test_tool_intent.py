"""Tests for tool intent detection and routing."""

from __future__ import annotations

import unittest

from harness.core.direct_reply import is_meta_question
from harness.core.task_complexity import is_complex_task
from harness.core.tool_intent import infer_tool_call, is_refusal_message, needs_tools


class TestToolIntent(unittest.TestCase):
    def test_needs_tools_for_directory_requests(self) -> None:
        self.assertTrue(needs_tools("list the files in this directory"))
        self.assertTrue(needs_tools("what's in the workspace folder"))
        self.assertFalse(needs_tools("hello"))

    def test_infer_list_dir(self) -> None:
        call = infer_tool_call("list files in the harness directory")
        self.assertIsNotNone(call)
        assert call is not None
        self.assertEqual("list_dir", call["tool"])

    def test_refusal_detection(self) -> None:
        self.assertTrue(
            is_refusal_message("I don't have direct access to files on your local system")
        )
        self.assertFalse(is_refusal_message("Directory listing:\n- agent.py"))

    def test_list_files_routes_to_agent_loop(self) -> None:
        self.assertTrue(needs_tools("list all files here"))

    def test_meta_question_skips_tools(self) -> None:
        q = "It's your harness. How does it work?"
        self.assertTrue(is_meta_question(q))
        self.assertFalse(needs_tools(q))
        self.assertFalse(is_complex_task(q))


if __name__ == "__main__":
    unittest.main()
