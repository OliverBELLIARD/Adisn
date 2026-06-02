"""Bridge agent progress events to the live CLI renderer."""

from __future__ import annotations

from typing import Callable, Dict, Optional

from harness.cli.live import ActivityRenderer


def progress_handler_for_live(live: ActivityRenderer) -> Callable[[Dict], None]:
    """Translate agent/loop events into live UI updates."""

    def on_progress(event: Dict) -> None:
        kind = event.get("kind", "")
        if kind == "headline":
            live.set_headline(str(event.get("text", "Working…")))
        elif kind == "step":
            live.set_step(
                int(event.get("step", 1)),
                int(event.get("max_steps", 6)),
                str(event.get("phase", "think")),
            )
        elif kind == "model":
            live.set_model(
                str(event.get("model", "ollama")),
                active=bool(event.get("active")),
            )
        elif kind == "thinking":
            text = str(event.get("text", ""))
            if event.get("streaming"):
                live.set_thinking_stream(text)
            else:
                live.push_thinking(text)
        elif kind == "token":
            live.set_response_preview(str(event.get("text", "")))
        elif kind == "loop_start":
            live.set_headline("Running agent loop…")
        elif kind == "loop_done":
            live.set_headline("Finishing…")

    return on_progress


def dispatch_progress(
    on_progress: Optional[Callable[[Dict], None]],
    event: Dict,
) -> None:
    if on_progress:
        on_progress(event)
