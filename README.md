# Alison

Alison is a self-evolving local agent harness designed for a 50k-token model runtime.

## What You Get

- dynamic skill generation and indexed skill storage
- context-window compression for long-running sessions
- unsafe-by-default self-rewrite (global scope) with snapshots and rollback
- built-in Questbook for Ollama model management
- tool-call mode so other models can invoke Alison as a tool

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
cd /path/to/Alison
```

### 3) Verify Alison command entry

Use any of these (preferred first):

```bash
python -m alison help
python -m alison status
```

Windows convenience wrapper:

```bat
alison.cmd status
```

Compatibility alias still supported:

```bash
python -m harness status
```

### 4) Start interactive mode

```bash
python -m alison
```

Use workspace-only mode when needed:

```bash
python -m alison --safe-global
```

Tune context compaction trigger:

```bash
python -m alison --compact-threshold-ratio 0.80
```

CLI behavior:

- first launch shows Alison CLI branding in the top-left output area
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
python -m alison tool --tool-flag --tool-action ollama_status
python -m alison tool --tool-flag --tool-action ollama_list
python -m alison tool --tool-flag --tool-action ollama_profiles
```

Ollama server behavior:

- Alison checks whether an Ollama server is already running (`127.0.0.1:11434`).
- If available, it reuses the existing server.
- If unavailable, it starts one automatically and waits for health before model operations.

Install a profile:

```bash
python -m alison tool --tool-flag --tool-action ollama_ensure_profile --tool-input balanced
```

### 6) Call Alison as a tool from other models

Direct CLI tool call:

```bash
python -m alison tool --tool-flag --tool-action process --tool-input "create a debugging skill"
python -m alison tool --tool-flag --tool-action scope --tool-input workspace
echo {"action":"rewrite","input":"C:\\temp\\note.txt","content":"hello","reason":"external write test"} | python -m alison tool --tool-flag --tool-stdin-json
```

JSON-over-stdin mode:

```bash
echo {"action":"ollama_profiles"} | python -m alison tool --tool-flag --tool-stdin-json
```

The tool-call response is always JSON:

- `ok`: success/failure
- `action`: executed tool action
- `result`: payload from Alison

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

