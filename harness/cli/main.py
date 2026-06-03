"""Interactive CLI for the Adisn harness runtime."""

from __future__ import annotations

import argparse
import html
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.application.current import get_app
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.key_binding import KeyBindings

from harness import create_harness
from harness.cli.cookbook_commands import format_cookbook_result
from harness.cli.display import (
    print_agent_response,
    print_loop_steps_summary,
    print_ollama_warning,
    print_user_message,
)
from harness.cli.live import ActivityRenderer
from harness.cli.progress import progress_handler_for_live


def _ensure_utf8_stdout() -> None:
    """Prefer UTF-8 on Windows so block-art banner and prompt glyph render."""
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass


def _supports_unicode_art() -> bool:
    encoding = (sys.stdout.encoding or "").lower()
    return "utf" in encoding


def _cli_glyph() -> str:
    """Return a terminal-safe left glyph (prompt prefix)."""
    return "✻" if _supports_unicode_art() else "*"


# Left column matches Claude Code's documented startup banner (anthropics/claude-code#39557).
CLAUDE_CODE_LEFT_ART = [
    " ▐▛███▜▌",
    "▝▜█████▛▘",
    "  ▘▘ ▝▝",
]


def _ascii_art_left() -> list[str]:
    """Left-column startup art (same block glyphs as Claude Code interactive mode)."""
    if _supports_unicode_art():
        return list(CLAUDE_CODE_LEFT_ART)
    return [
        "  ___  ",
        " / _ \\ ",
        " \\___/ ",
    ]


ADISN_VERSION = "0.1.0"


def _startup_meta_lines(agent) -> list[str]:
    scope = "workspace-only" if agent.rewriter.get_scope() == "workspace" else "global-unsafe"
    cwd = Path(agent.workspace_root)
    try:
        cwd_display = f"~{cwd.as_posix()[len(Path.home().as_posix()):]}" if cwd.is_relative_to(Path.home()) else str(cwd)
    except (ValueError, AttributeError):
        cwd_display = str(cwd)
    compact_pct = int(agent.context.compact_threshold_ratio * 100)
    return [
        f"Adisn Code v{ADISN_VERSION}",
        f"{scope} · {agent.context.max_tokens} tokens (compact @{compact_pct}%)",
        cwd_display,
    ]


def _compose_startup_banner(agent) -> list[str]:
    """Compose left ASCII art and right metadata on the same rows."""
    art = _ascii_art_left()
    meta = _startup_meta_lines(agent)
    width = max(len(line) for line in art)
    rows = []
    for i in range(len(art)):
        rows.append(f"{art[i].ljust(width)}   {meta[i]}")
    return rows


class CtrlCExitState:
    """Tracks double-Ctrl+C quit; resets on any other key or shortcut."""

    pending: bool = False

    def reset(self) -> None:
        self.pending = False


def _attach_ctrl_c_reset_on_input(state: CtrlCExitState) -> None:
    """Reset double-Ctrl+C arming when the user types (does not block keys)."""
    from prompt_toolkit.application.current import get_app

    buf = get_app().current_buffer
    if getattr(buf, "_adisn_ctrl_c_reset_hook", False):
        return

    def _on_text_changed(_buffer) -> None:
        if state.pending:
            state.reset()

    buf.on_text_changed += _on_text_changed
    buf._adisn_ctrl_c_reset_hook = True


def _ctrl_c_key_bindings(state: CtrlCExitState) -> KeyBindings:
    kb = KeyBindings()

    @kb.add("c-c")
    def _handle_ctrl_c(event) -> None:
        if state.pending:
            event.app.exit(exception=KeyboardInterrupt())
        state.pending = True
        event.app.output.write(
            "\nInterrupted. Press Ctrl+C again or type /quit to exit.\n"
        )

    return kb


@dataclass(frozen=True)
class SlashCommandSpec:
    command: str
    group: str
    description: str
    usage: str
    example: str


class SlashCommandCompleter(Completer):
    """Rich completer that includes metadata and argument hints."""

    def __init__(self, specs: list[SlashCommandSpec]):
        self.specs = specs

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor.lstrip()
        if not text.startswith("/"):
            return

        # Suggest command stubs while typing slash commands.
        for spec in self.specs:
            if spec.command.startswith(text) or text in spec.command:
                display_meta = f"{spec.group} | {spec.description}"
                yield Completion(
                    spec.command,
                    start_position=-len(text),
                    display=spec.command,
                    display_meta=display_meta,
                )

        # Inline arg hints once command is complete and has args.
        for spec in self.specs:
            if text == spec.command and "<" in spec.usage:
                hint = spec.usage.replace(spec.command, "").strip()
                if hint:
                    yield Completion(
                        " " + hint,
                        start_position=0,
                        display=f"{spec.command} {hint}",
                        display_meta=f"hint | {spec.description}",
                    )



def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="adisn",
        description="Adisn - self-evolving AI harness"
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=["run", "status", "help", "tool"],
        default="run",
        help="Command to execute (default: run)"
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Quiet mode - less output"
    )
    parser.add_argument(
        "--tool-flag",
        action="store_true",
        help="Enable tool-call mode for other model runtimes"
    )
    parser.add_argument(
        "--tool-action",
        choices=[
            "status",
            "process",
            "scope",
            "rewrite",
            "ollama_status",
            "ollama_list",
            "ollama_profiles",
            "ollama_pull",
            "ollama_rm",
            "ollama_ensure_profile",
            "ollama_serve",
            "cookbook_scan",
            "cookbook_recommend",
            "cookbook_status",
            "cookbook_pull",
            "cookbook_use",
        ],
        help="Action to execute in tool-call mode"
    )
    parser.add_argument(
        "--tool-input",
        default="",
        help="Primary input for tool-call mode (request/model/profile)"
    )
    parser.add_argument(
        "--tool-stdin-json",
        action="store_true",
        help="Read a JSON payload from stdin in tool-call mode"
    )
    parser.add_argument(
        "--safe-global",
        action="store_true",
        help="Restrict rewrites to workspace paths only (default is unsafe global)"
    )
    parser.add_argument(
        "--compact-threshold-ratio",
        type=float,
        default=0.85,
        help="Compaction trigger ratio for context window (0.0-1.0)"
    )

    args = parser.parse_args()

    if args.tool_flag or args.command == "tool":
        run_tool_mode(args)
        return

    if args.command == "run" or args.command is None:
        # Run interactive mode
        run_interactive(args)

    elif args.command == "status":
        # Show status
        show_status(args)

    elif args.command == "help":
        parser.print_help()


def run_tool_mode(args: argparse.Namespace) -> None:
    """Machine-oriented tool call mode for model-to-model integration."""
    agent = create_harness(
        safe_global=args.safe_global,
        compact_threshold_ratio=args.compact_threshold_ratio,
    )
    payload = {}
    if args.tool_stdin_json:
        raw = sys.stdin.read().strip()
        if raw:
            payload = json.loads(raw)

    action = payload.get("action") or args.tool_action or "status"
    primary_input = payload.get("input", args.tool_input)
    result = execute_tool_action(agent, action, primary_input, payload)
    print(json.dumps({"ok": "error" not in result, "action": action, "result": result}))


def execute_tool_action(agent, action: str, value: str, payload: dict | None = None):
    payload = payload or {}
    if action == "status":
        return agent.get_state()
    if action == "process":
        return agent.process_request(value)
    if action == "scope":
        if not value:
            return {"error": "missing scope in --tool-input (global|workspace)"}
        return agent.set_scope(value)
    if action == "rewrite":
        if not value:
            return {"error": "missing target path in --tool-input"}
        content = payload.get("content", "")
        reason = payload.get("reason", "tool-call rewrite")
        return agent.rewrite(value, content, reason)
    if action == "ollama_status":
        return agent.ollama_status()
    if action == "ollama_list":
        return agent.ollama_list()
    if action == "ollama_profiles":
        return agent.ollama_profiles()
    if action == "ollama_pull":
        if not value:
            return {"error": "missing model in --tool-input"}
        return agent.ollama_pull(value)
    if action == "ollama_rm":
        if not value:
            return {"error": "missing model in --tool-input"}
        return agent.ollama_remove(value)
    if action == "ollama_ensure_profile":
        if not value:
            return {"error": "missing profile in --tool-input"}
        return agent.ollama_ensure_profile(value)
    if action == "ollama_serve":
        return agent.ollama_serve()
    if action == "cookbook_scan":
        return agent.cookbook.scan(refresh=value == "refresh")
    if action == "cookbook_recommend":
        return agent.cookbook.recommend(value or "balanced")
    if action == "cookbook_status":
        return agent.cookbook.status()
    if action == "cookbook_pull":
        if not value:
            return {"error": "missing model in --tool-input"}
        return agent.cookbook.pull(value)
    if action == "cookbook_use":
        if not value:
            return {"error": "missing model in --tool-input"}
        return agent.cookbook.set_active_model(value)
    if action.startswith("cookbook_"):
        sub = action.replace("cookbook_", "", 1)
        return agent.cookbook_command(sub + (f" {value}" if value else ""))
    return {"error": f"unknown action: {action}"}


def _format_ollama_serve(result: dict) -> str:
    if result.get("ok"):
        msg = result.get("message", "Ollama server ready")
        host = result.get("host", "")
        extra = f" (pid {result['pid']})" if result.get("pid") else ""
        return f"{msg} at {host}{extra}"
    return json.dumps(result, indent=2)


def _run_with_live(headline: str, work):
    """Run blocking work with a live status region."""
    live = ActivityRenderer()
    live.start(headline)
    try:
        return work(live)
    finally:
        live.finish(ok=True)


def _handle_user_prompt(agent, line: str) -> None:
    """Run a non-slash user prompt with live activity UI and Ollama warnings."""
    print_user_message(line)
    if not agent.is_ollama_server_running():
        print_ollama_warning()

    live = ActivityRenderer()
    on_progress = progress_handler_for_live(live)
    headline = "Thinking…" if agent.thinking.enabled else "Working…"
    live.start(headline)

    try:
        result = agent.process_request(line, on_progress=on_progress)
    finally:
        live.finish(ok=True)

    result["thinking_expanded"] = agent.thinking_expanded
    print_loop_steps_summary(result)
    print_agent_response(result, show_warning=False, live_shown=live.enabled)


def run_interactive(args: argparse.Namespace):
    """Run the harness in interactive mode."""
    _ensure_utf8_stdout()
    agent = create_harness(
        safe_global=args.safe_global,
        compact_threshold_ratio=args.compact_threshold_ratio,
    )
    _render_startup_cli(agent)
    if not agent.is_ollama_server_running():
        print_ollama_warning()

    specs = _slash_command_specs()
    ctrl_c_state = CtrlCExitState()
    session = _build_prompt_session(specs, ctrl_c_state)

    while True:
        try:
            line = _read_interactive_line(session, ctrl_c_state)
            ctrl_c_state.reset()
        except KeyboardInterrupt:
            print("\nExiting Adisn.")
            break
        except EOFError:
            print("Exiting Adisn.")
            break
        if not line:
            continue
        if line == "/help":
            _print_slash_help()
            continue
        if line == "/think":
            enabled = agent.toggle_thinking()
            state = "enabled" if enabled else "disabled"
            print(f"Extended thinking {state} for this session (Claude Code /think).")
            continue
        if line == "/think expand":
            agent.thinking_expanded = True
            print("Thinking blocks will show expanded text.")
            continue
        if line == "/quit":
            print("Exiting Adisn.")
            break
        if line == "/status":
            print(json.dumps(agent.get_state(), indent=2))
            continue
        if line.startswith("/scope "):
            _, scope = line.split(" ", 1)
            print(json.dumps(agent.set_scope(scope.strip()), indent=2))
            continue
        if line.startswith("/rewrite "):
            try:
                _, path = line.split(" ", 1)
                content = _read_subprompt_line(session, ctrl_c_state, "new content> ")
                reason = _read_subprompt_line(session, ctrl_c_state, "reason> ")
                print(json.dumps(agent.rewrite(path, content, reason), indent=2))
            except ValueError:
                print("usage: /rewrite <path>")
            continue
        if line == "/rollback":
            print(json.dumps(agent.rollback_last_rewrite(), indent=2))
            continue
        if line == "/ollama status":
            print(json.dumps(agent.ollama_status(), indent=2))
            continue
        if line == "/ollama serve":
            print(_format_ollama_serve(agent.ollama_serve()))
            continue
        if line == "/ollama list":
            print(json.dumps(agent.ollama_list(), indent=2))
            continue
        if line == "/ollama profiles":
            print(json.dumps(agent.ollama_profiles(), indent=2))
            continue
        if line.startswith("/ollama pull "):
            _, _, model = line.partition("/ollama pull ")

            def _pull(_live: ActivityRenderer):
                _live.set_headline(f"Pulling {model.strip()}…")
                return agent.ollama_pull(model.strip())

            result = _run_with_live(f"Pulling {model.strip()}…", _pull)
            print(json.dumps(result, indent=2))
            continue
        if line.startswith("/ollama rm "):
            _, _, model = line.partition("/ollama rm ")
            print(json.dumps(agent.ollama_remove(model.strip()), indent=2))
            continue
        if line.startswith("/ollama ensure-profile "):
            _, _, profile = line.partition("/ollama ensure-profile ")
            print(json.dumps(agent.ollama_ensure_profile(profile.strip()), indent=2))
            continue
        if line.startswith("/cookbook"):
            args = line[len("/cookbook") :].strip()
            slow = args.startswith(("scan", "pull", "recommend"))
            if slow:
                label = args.split()[0] if args else "cookbook"

                def _cookbook(_live: ActivityRenderer):
                    _live.set_headline(f"Cookbook · {label}…")
                    return agent.cookbook_command(args)

                result = _run_with_live(f"Cookbook · {label}…", _cookbook)
            else:
                result = agent.cookbook_command(args)
            print(format_cookbook_result(result))
            continue
        _handle_user_prompt(agent, line)


def show_status(args: argparse.Namespace):
    """Show harness status."""
    state = create_harness(
        safe_global=args.safe_global,
        compact_threshold_ratio=args.compact_threshold_ratio,
    ).get_state()
    print(json.dumps(state, indent=2))


def _read_interactive_line(session, ctrl_c_state: CtrlCExitState) -> str:
    if getattr(session, "is_fallback", False):
        return session.prompt(_plain_prompt_text(), ctrl_c_state).strip()
    glyph = _cli_glyph()
    return session.prompt(
        HTML(
            f"<ansibrightblack>{glyph}</ansibrightblack> "
            "<ansicyan>adisn</ansicyan> > "
        ),
        pre_run=lambda: _attach_ctrl_c_reset_on_input(ctrl_c_state),
    ).strip()


def _read_subprompt_line(session, ctrl_c_state: CtrlCExitState, prompt: str) -> str:
    if getattr(session, "is_fallback", False):
        line = session.prompt(prompt, ctrl_c_state)
    else:
        line = session.prompt(
            prompt,
            pre_run=lambda: _attach_ctrl_c_reset_on_input(ctrl_c_state),
        )
    ctrl_c_state.reset()
    return line


def _escape_html(text: str) -> str:
    """Escape dynamic text embedded in prompt_toolkit HTML toolbars."""
    return html.escape(text, quote=False)


def _build_prompt_session(
    specs: list[SlashCommandSpec], ctrl_c_state: CtrlCExitState
) -> PromptSession:
    """Prompt session with slash autocomplete and live command hints."""
    completer = SlashCommandCompleter(specs)
    by_group: dict[str, list[SlashCommandSpec]] = {}
    for spec in specs:
        by_group.setdefault(spec.group, []).append(spec)

    def _toolbar():
        text = get_app().current_buffer.document.text_before_cursor.strip()
        if not text.startswith("/"):
            return ""
        matches = [s for s in specs if s.command.startswith(text) or text in s.command]
        if not matches:
            return HTML("<ansired>No slash command matches</ansired>")

        if text == "/":
            lines = ["<ansicyan>Slash Command Panel</ansicyan>"]
            for group in sorted(by_group):
                group_cmds = ", ".join(item.command for item in by_group[group])
                lines.append(
                    f"<ansigreen>{_escape_html(group)}</ansigreen>: {_escape_html(group_cmds)}"
                )
            lines.append("<ansibrightblack>Tab: autocomplete · Enter: run · /help: full list</ansibrightblack>")
            return HTML("\n".join(lines))

        if len(matches) == 1:
            m = matches[0]
            return HTML(
                "<ansicyan>command</ansicyan>: "
                f"{_escape_html(m.command)} | <ansigreen>{_escape_html(m.description)}</ansigreen> | "
                f"<ansibrightblack>usage: {_escape_html(m.usage)}</ansibrightblack>"
            )

        shown = "  ".join(m.command for m in matches[:8])
        return HTML(
            "<ansicyan>matches</ansicyan>: "
            f"{_escape_html(shown)} "
            "<ansibrightblack>(press Tab to cycle)</ansibrightblack>"
        )

    try:
        return PromptSession(
            completer=completer,
            complete_while_typing=True,
            reserve_space_for_menu=12,
            bottom_toolbar=_toolbar,
            key_bindings=_ctrl_c_key_bindings(ctrl_c_state),
        )
    except Exception:
        class _FallbackPrompt:
            is_fallback = True

            def __init__(self, state: CtrlCExitState) -> None:
                self._state = state
                self._install_readline_reset()

            def _install_readline_reset(self) -> None:
                try:
                    import readline

                    state = self._state

                    def _hook() -> None:
                        state.reset()

                    readline.set_pre_input_hook(_hook)
                except ImportError:
                    pass

            def prompt(self, prompt_text: str, state: CtrlCExitState | None = None) -> str:
                exit_state = state or self._state
                try:
                    return input(str(prompt_text))
                except KeyboardInterrupt:
                    if exit_state.pending:
                        raise
                    exit_state.pending = True
                    print(
                        "\nInterrupted. Press Ctrl+C again or type /quit to exit."
                    )
                    return self.prompt(prompt_text, exit_state)

        return _FallbackPrompt(ctrl_c_state)


def _plain_prompt_text() -> str:
    return f"{_cli_glyph()} adisn > "


def _render_startup_cli(agent) -> None:
    """Render startup banner every launch (Claude Code-style left ASCII art)."""
    if os.environ.get("ADISN_NO_BANNER", "").strip() in {"1", "true", "yes"}:
        print("Adisn interactive mode")
        print("Type `/help` for commands.\n")
        return

    for line in _compose_startup_banner(agent):
        print(line)
    print("")


def _print_slash_help() -> None:
    print("Slash commands:")
    current_group = None
    for spec in _slash_command_specs():
        if spec.group != current_group:
            current_group = spec.group
            print(f"\n[{current_group}]")
        print(f"  {spec.usage}")
        print(f"    - {spec.description}")
        print(f"    - example: {spec.example}")


def _slash_command_specs() -> list[SlashCommandSpec]:
    return [
        SlashCommandSpec("/help", "System", "Show rich slash command help", "/help", "/help"),
        SlashCommandSpec(
            "/think",
            "System",
            "Toggle extended thinking (Claude Code /think)",
            "/think",
            "/think",
        ),
        SlashCommandSpec("/status", "System", "Show Adisn runtime status", "/status", "/status"),
        SlashCommandSpec("/scope", "System", "Switch rewrite scope mode", "/scope <global|workspace>", "/scope workspace"),
        SlashCommandSpec("/quit", "System", "Exit interactive mode", "/quit", "/quit"),
        SlashCommandSpec(
            "/rewrite",
            "Self-Modification",
            "Rewrite a file with snapshot safety (absolute paths supported)",
            "/rewrite <path>",
            "/rewrite README.md",
        ),
        SlashCommandSpec("/rollback", "Self-Modification", "Rollback last rewrite", "/rollback", "/rollback"),
        SlashCommandSpec("/ollama status", "Ollama", "Check Ollama availability", "/ollama status", "/ollama status"),
        SlashCommandSpec(
            "/ollama serve",
            "Ollama",
            "Start Ollama server (ollama serve) in the background",
            "/ollama serve",
            "/ollama serve",
        ),
        SlashCommandSpec("/ollama list", "Ollama", "List installed Ollama models", "/ollama list", "/ollama list"),
        SlashCommandSpec("/ollama profiles", "Ollama", "Show Questbook profiles", "/ollama profiles", "/ollama profiles"),
        SlashCommandSpec("/ollama pull", "Ollama", "Download an Ollama model", "/ollama pull <model>", "/ollama pull qwen2.5:7b"),
        SlashCommandSpec("/ollama rm", "Ollama", "Remove an Ollama model", "/ollama rm <model>", "/ollama rm qwen2.5:7b"),
        SlashCommandSpec(
            "/ollama ensure-profile",
            "Ollama",
            "Install all models required by a profile",
            "/ollama ensure-profile <name>",
            "/ollama ensure-profile balanced",
        ),
        SlashCommandSpec(
            "/cookbook scan",
            "Cookbook",
            "Scan GPU/RAM/CPU (VRAM-aware)",
            "/cookbook scan [--refresh]",
            "/cookbook scan",
        ),
        SlashCommandSpec(
            "/cookbook recommend",
            "Cookbook",
            "Recommend models for hardware profile",
            "/cookbook recommend <fast|balanced|reasoning|coding>",
            "/cookbook recommend balanced",
        ),
        SlashCommandSpec(
            "/cookbook list",
            "Cookbook",
            "List model catalog",
            "/cookbook list",
            "/cookbook list",
        ),
        SlashCommandSpec(
            "/cookbook installed",
            "Cookbook",
            "List installed Ollama models",
            "/cookbook installed",
            "/cookbook installed",
        ),
        SlashCommandSpec(
            "/cookbook pull",
            "Cookbook",
            "Download a model (Ollama)",
            "/cookbook pull <model>",
            "/cookbook pull qwen2.5:7b",
        ),
        SlashCommandSpec(
            "/cookbook serve",
            "Cookbook",
            "Serve model (ollama|llama-cpp|vllm)",
            "/cookbook serve <backend> <target> [port]",
            "/cookbook serve ollama qwen2.5:7b",
        ),
        SlashCommandSpec(
            "/cookbook serves",
            "Cookbook",
            "List running serve processes",
            "/cookbook serves",
            "/cookbook serves",
        ),
        SlashCommandSpec(
            "/cookbook use",
            "Cookbook",
            "Set active model for agent loop",
            "/cookbook use <model>",
            "/cookbook use qwen2.5:7b",
        ),
        SlashCommandSpec(
            "/cookbook deps",
            "Cookbook",
            "Check serve dependencies",
            "/cookbook deps",
            "/cookbook deps",
        ),
        SlashCommandSpec(
            "/cookbook status",
            "Cookbook",
            "Cookbook + Ollama status",
            "/cookbook status",
            "/cookbook status",
        ),
    ]


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nExiting Adisn.")
