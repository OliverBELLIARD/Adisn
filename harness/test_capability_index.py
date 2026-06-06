"""Tests for skills/tools index catalogs."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from harness.core.capability_index import build_capability_catalog, suggest_tool_call
from harness.core.tool_executor import ToolExecutor
from harness.core.self_rewriter import SelfRewriter
from harness.core.skill_store import SkillStore


class TestCapabilityIndex(unittest.TestCase):
    def test_tools_index_created_with_summaries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tools = ToolExecutor(root, SelfRewriter(root), SkillStore(root))
            tools._ensure_tools_index()
            index = json.loads((root / "tools" / "INDEX.json").read_text(encoding="utf-8"))
            names = {entry["name"] for entry in index}
            self.assertIn("list_dir", names)
            self.assertTrue(all(entry.get("summary") for entry in index))

    def test_catalog_ranks_tools_for_list_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tools = ToolExecutor(root, SelfRewriter(root), SkillStore(root))
            tools._ensure_tools_index()
            suggested = suggest_tool_call(root, "list files in workspace")
            self.assertIsNotNone(suggested)
            assert suggested is not None
            self.assertEqual("list_dir", suggested["tool"])

    def test_build_capability_catalog_includes_both_indexes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skills = SkillStore(root)
            skills.generate_from_task("Document the toolkit command usage for operators")
            tools = ToolExecutor(root, SelfRewriter(root), skills)
            tools._ensure_tools_index()
            catalog = build_capability_catalog(root, "read toolkit docs")
            self.assertIn("Skills", catalog)
            self.assertIn("Tools", catalog)
            self.assertIn("read_file", catalog)


if __name__ == "__main__":
    unittest.main()
