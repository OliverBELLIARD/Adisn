# Harness Runtime

This directory contains the active Adisn runtime.

## Design Goals

- keep active context under a token budget for a 50k model window
- create skills at runtime and persist them as files
- organize generated skills by type with low-cost index lookups
- support self-rewrite with snapshot backups and rollback
- manage Ollama models locally through Questbook

## Important Modules

- `core/agent.py`: orchestrates context, skills, memory, and rewrite operations
- `core/context_window.py`: rolling prompt compression
- `core/skill_store.py`: generated skill folders + indexes
- `core/self_rewriter.py`: rewrite + rollback
- `core/questbook.py`: Ollama model lifecycle + profile management
- `memory/memory_manager.py`: compact session memory
- `cli/main.py`: interactive shell
- `cli/main.py`: interactive shell + tool-call mode for model integration

## Runtime Data

- `../skills/` generated skill files and indexes
- `../.remember/` interaction memory and memory index
- `../.harness_snapshots/` backup files created before rewrites
- `../.questbook/` Ollama model index and profile catalog
