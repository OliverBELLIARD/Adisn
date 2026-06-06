"""Tests for live CLI activity renderer."""

from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from harness.cli.live import ActivityRenderer, run_with_live_activity
from harness.cli.progress import progress_handler_for_live


class TestActivityRenderer(unittest.TestCase):
    def test_disabled_renders_simple_start_line(self) -> None:
        buf = io.StringIO()
        with patch("harness.cli.live.sys.stdout", buf):
            live = ActivityRenderer(enabled=False)
            live.start("Planning…")
            live.set_step(1, 6, "think")
            live.finish()
        self.assertIn("Planning", buf.getvalue())

    def test_single_line_spinner_redraws_in_place(self) -> None:
        class TtyStringIO(io.StringIO):
            def isatty(self) -> bool:
                return True

        buf = TtyStringIO()
        with patch("harness.cli.live.sys.stdout", buf):
            with patch("harness.cli.live.enable_vt_processing", return_value=True):
                live = ActivityRenderer(enabled=True)
                live.start("Replying…")
                live._draw_once(final=False)
                live._frame_idx = 1
                live._draw_once(final=False)
                spinning = buf.getvalue()
                self.assertNotIn("\n", spinning)
                self.assertGreaterEqual(spinning.count("\r"), 2)
                live.finish()

    def test_progress_handler_updates_headline(self) -> None:
        live = ActivityRenderer(enabled=False)
        live.start("Working…")
        handler = progress_handler_for_live(live)
        handler({"kind": "headline", "text": "Running agent loop…"})
        handler({"kind": "step", "step": 2, "max_steps": 6, "phase": "decide"})
        handler({"kind": "thinking", "text": "line one\nline two"})
        live.finish()
        # No exception; disabled mode does not require visible multi-line output.

    def test_run_with_live_activity_returns_result(self) -> None:
        def work(on_progress):
            on_progress({"kind": "headline", "text": "Test"})
            return {"ok": True, "message": "done"}

        result = run_with_live_activity("Start", work, enabled=False)
        self.assertEqual("done", result["message"])


class TestAgentLoopProgress(unittest.TestCase):
    def test_loop_emits_progress_events(self) -> None:
        from harness.core.agent_loop import AgentLoop
        from harness.core.thinking import ThinkingMode

        events = []

        loop = AgentLoop(
            thinking=ThinkingMode(enabled=True),
            chat_fn=lambda *a, **k: {"ok": False},
            server_running=False,
            max_steps=2,
        )
        loop.run(
            "hello",
            skill_context={"skill_name": "t", "next_action": "analyze", "scope": "global"},
            local_act_fn=lambda action, ctx: {"ok": True, "message": "done"},
            on_progress=events.append,
        )
        kinds = [e["kind"] for e in events]
        self.assertIn("loop_start", kinds)
        self.assertIn("step", kinds)
        self.assertIn("thinking", kinds)
        self.assertIn("loop_done", kinds)


if __name__ == "__main__":
    unittest.main()
