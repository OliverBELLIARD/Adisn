"""Tests for Cookbook model management."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from harness.core.cookbook import Cookbook
from harness.core.questbook import Questbook
from harness.core.cookbook.quant import best_quant_for_budget, fit_score
from harness.core.cookbook.hardware import scan_hardware


class TestCookbookQuant(unittest.TestCase):
    def test_fit_score_positive_for_small_model(self) -> None:
        model = {"name": "qwen2.5:3b", "parameters_b": 3.0, "quality_score": 75}
        score = fit_score(model, budget_gb=8.0)
        self.assertGreater(score, 0)

    def test_best_quant_fits_budget(self) -> None:
        model = {"name": "llama3.1:8b", "parameters_b": 8.0, "quality_score": 78}
        q, ctx, mem = best_quant_for_budget(model, 6.0)
        self.assertIsNotNone(q)
        self.assertLessEqual(mem or 99, 6.0)


class TestCookbook(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cb = Cookbook(Path(self.tmp.name))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_scan_returns_hardware(self) -> None:
        result = self.cb.scan()
        self.assertTrue(result["ok"])
        self.assertIn("ram_gb", result["hardware"])

    def test_recommend_returns_ranked(self) -> None:
        result = self.cb.recommend("fast")
        self.assertTrue(result["ok"])
        self.assertIsInstance(result["recommendations"], list)

    def test_catalog_list(self) -> None:
        result = self.cb.list_catalog()
        self.assertGreater(len(result["models"]), 0)

    def test_deps_lists_tools(self) -> None:
        result = self.cb.deps()
        self.assertIn("ollama", result["dependencies"])

    @patch.object(Questbook, "installed_model_names", return_value=["qwen2.5:7b"])
    def test_set_active_model(self, _names) -> None:
        result = self.cb.set_active_model("qwen2.5:7b")
        self.assertTrue(result["ok"])
        self.assertEqual("qwen2.5:7b", self.cb.get_active_model())

    @patch.object(Cookbook, "catalog")
    def test_provider_add(self, _cat) -> None:
        result = self.cb.provider_add("remote", "http://10.0.0.5:8000/v1")
        self.assertTrue(result["ok"])
        providers = self.cb.providers()["providers"]
        names = [p["name"] for p in providers.get("custom", [])]
        self.assertIn("remote", names)


if __name__ == "__main__":
    unittest.main()
