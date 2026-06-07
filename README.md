# Adisn

Adisn is a self-evolving local agent harness designed for a 50k-token model runtime, optimized for efficiency and autonomy.

## What You Get

- **Dynamic Skill Generation**: Indexed skill storage that grows with use.
- **Advanced Context Management**: 50k-token rolling window with deterministic compression and manual summarization.
- **Safety-First Rewriting**: Unsafe-by-default self-rewrite (global scope) with automatic snapshots and easy rollback.
- **Efficient Editing**: `patch_file` for targeted search-and-replace, saving tokens over full rewrites.
- **Rich UI**: Live CLI activity rendering with progress indicators for background tasks.
- **Memory Retrieval**: Markdown-based persistent memory that the agent can actively query.
- **Questbook**: Built-in Ollama model and lifecycle management.
- **Tool-Call Mode**: Machine-oriented interface for model-to-model integration.

## Get Started (Step by Step)

### 1) Prerequisites

- Python 3.11+ installed
- Ollama installed (optional but recommended for local models)

Install CLI dependency:

```bash
pip install -r requirements.txt
```

### 2) Open this repository in a terminal

```bash
cd /path/to/Adisn
```

### 3) Verify Adisn command entry

Use any of these (preferred first):

```bash
python -m adisn help
python -m adisn status
```

Windows convenience wrapper:

```bat
adisn.cmd status
```

Compatibility alias still supported:

```bash
python -m harness status
```

### 4) Start interactive mode

```bash
python -m adisn
```

Use workspace-only mode when needed:

```bash
python -m adisn --safe-global
```

Tune context compaction trigger:

```bash
python -m adisn --compact-threshold-ratio 0.80
```

CLI behavior:

- first launch shows Adisn CLI branding in the top-left output area
- slash commands (`/`) support autocomplete
- as soon as input starts with `/`, a rich slash-command panel appears with grouped commands, metadata, usage hints, and examples
- `/help` lists all slash commands

Inside the prompt:

- `/status`
- `/ollama status`
- `/ollama list`
- `/ollama profiles`
- `/ollama pull <model>`
- `/ollama rm <model>`
- `/ollama ensure-profile <name>`
- `/scope <global|workspace>`
- `/rewrite <path>` (absolute paths allowed in global scope)
- `/rollback`
- `/quit`

### 5) Manage Ollama models with Questbook

Check runtime state:

```bash
python -m adisn tool --tool-flag --tool-action ollama_status
python -m adisn tool --tool-flag --tool-action ollama_list
python -m adisn tool --tool-flag --tool-action ollama_profiles
```

Ollama server behavior:

- Adisn checks whether an Ollama server is already running (`127.0.0.1:11434`).
- If available, it reuses the existing server.
- If unavailable, it starts one automatically and waits for health before model operations.

Install a profile:

```bash
python -m adisn tool --tool-flag --tool-action ollama_ensure_profile --tool-input balanced
```

### 6) Call Adisn as a tool from other models

Direct CLI tool call:

```bash
python -m adisn tool --tool-flag --tool-action process --tool-input "create a debugging skill"
python -m adisn tool --tool-flag --tool-action scope --tool-input workspace
echo {"action":"rewrite","input":"C:\\temp\\note.txt","content":"hello","reason":"external write test"} | python -m adisn tool --tool-flag --tool-stdin-json
```

JSON-over-stdin mode:

```bash
echo {"action":"ollama_profiles"} | python -m adisn tool --tool-flag --tool-stdin-json
```

The tool-call response is always JSON:

- `ok`: success/failure
- `action`: executed tool action
- `result`: payload from Adisn

## Generated Runtime Data

- `skills/<type>/*.md` generated skills
- `skills/<type>/INDEX.json` per-type indexes
- `skills/INDEX.json` global index
- `.remember/` rolling memory and memory index
- `.harness_snapshots/` rewrite snapshots and rewrite log
- `.questbook/` Ollama model index and profiles

## Key Runtime Modules

- `harness/core/agent.py` orchestration loop
- `harness/core/context_window.py` token-budget compression
- `harness/core/skill_store.py` skill generation/indexing
- `harness/core/self_rewriter.py` safe rewrites + rollback
- `harness/core/questbook.py` Ollama lifecycle manager
- `harness/memory/memory_manager.py` compact persistent memory

