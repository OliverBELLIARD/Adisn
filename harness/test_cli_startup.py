"""Verify Adisn interactive startup banner matches Claude Code layout."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

from harness.cli.main import (
    CLAUDE_CODE_LEFT_ART,
    _compose_startup_banner,
    _ensure_utf8_stdout,
)
from harness import create_harness

REPO_ROOT = Path(__file__).resolve().parent.parent

# Public reference: anthropics/claude-code issue #39557 (startup banner screenshot).
CLAUDE_CODE_REFERENCE_BANNER = [
    " ▐▛███▜▌   Claude Code v2.1.84",
    "▝▜█████▛▘  Opus 4.6 (1M context) · Claude Max",
    "  ▘▘ ▝▝    ~/Documents/bhd/monorepo",
]


class TestCliStartupBanner(unittest.TestCase):
    def test_left_art_uses_claude_code_block_glyphs(self) -> None:
        self.assertIn("█", CLAUDE_CODE_LEFT_ART[0])
        self.assertIn("█", CLAUDE_CODE_LEFT_ART[1])
        self.assertEqual(len(CLAUDE_CODE_LEFT_ART), 3)

    def test_banner_has_three_rows_with_shared_left_column(self) -> None:
        _ensure_utf8_stdout()
        rows = _compose_startup_banner(create_harness())
        self.assertEqual(len(rows), 3)
        for row, art in zip(rows, CLAUDE_CODE_LEFT_ART):
            self.assertTrue(row.startswith(art), msg=f"row missing left art: {row!r}")

    def test_left_column_matches_claude_reference_glyphs(self) -> None:
        """Left-column glyphs are the same as Claude Code's documented startup art."""
        _ensure_utf8_stdout()
        rows = _compose_startup_banner(create_harness())
        adisn_left = [r.split("   ", 1)[0].rstrip() for r in rows]
        self.assertEqual(CLAUDE_CODE_LEFT_ART, adisn_left)

    def test_module_entrypoint_prints_block_art_on_launch(self) -> None:
        proc = subprocess.run(
            [sys.executable, "-m", "adisn"],
            input="/quit\n",
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        out = proc.stdout
        for art_line in CLAUDE_CODE_LEFT_ART:
            self.assertIn(art_line, out, msg=f"missing art line in stdout:\n{out}")
        self.assertIn("Adisn Code v", out)
        self.assertIn("Exiting Adisn.", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
