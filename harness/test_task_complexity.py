"""Tests for skill gating and task complexity."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from harness.core.skill_store import SkillStore
from harness.core.task_complexity import is_complex_task, should_create_skill


class TestTaskComplexity(unittest.TestCase):
    def test_simple_chat_not_complex(self) -> None:
        self.assertFalse(is_complex_task("Reply with OK"))
        self.assertFalse(is_complex_task("hello"))
        self.assertFalse(should_create_skill("Thanks!"))

    def test_engineering_task_is_complex(self) -> None:
        self.assertTrue(
            is_complex_task("Refactor the harness agent loop to add streaming and tests")
        )
        self.assertTrue(should_create_skill("Fix npm build failures in CI step by step"))

    def test_skill_store_skips_simple_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SkillStore(Path(tmp))
            self.assertIsNone(store.match("Reply with OK"))

    def test_skill_store_rejects_simple_generate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SkillStore(Path(tmp))
            with self.assertRaises(ValueError):
                store.generate_from_task("say hi")


if __name__ == "__main__":
    unittest.main()
