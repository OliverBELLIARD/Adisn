# Adisn Harness Summary

## Current Status: ✓ OPTIMIZED & ENHANCED

Adisn is a self-evolving local agent harness designed for a 50k-token model runtime, featuring advanced autonomy, memory, and efficiency.

## Key Features

### 1. Advanced Agent Loop
- **Think → Decide → Act → Observe**: Multi-step reasoning with extended thinking (Claude Code pattern).
- **Combined Steps**: Think and Decide phases are merged for maximum token efficiency.
- **Live Progress**: Real-time CLI feedback with animated progress indicators for background tasks.
- **Tool Fallbacks**: Heuristic fallback and forced tool attempts to bypass model refusals.

### 2. Efficiency & Context Management
- **50k Token Window**: Large rolling prompt window with deterministic recursive compression.
- **Manual Summarization**: `summarize_history` tool to compress context on demand.
- **Targeted Edits**: `patch_file` tool for search-and-replace, significantly reducing token usage compared to full file rewrites.
- **Large File Handling**: `read_file_chunked` for reading large files in segments.

### 3. Persistent Memory & Skills
- **Markdown Memory**: Interaction history and notes stored in `.adisn/chats/`.
- **Active Recall**: `read_memory` tool allows the agent to query its own history.
- **Dynamic Skills**: Procedural knowledge stored in `skills/`.
- **Skill Templates**: Automated structured template generation for new skills.

### 4. Hardware-Aware Model Management
- **Cookbook**: VRAM-aware model scanning and recommendations.
- **Questbook**: Lifecycle management for Ollama models.
- **Multi-Backend**: Support for Ollama, llama.cpp, and vLLM.

### 5. Self-Modification & Safety
- **Safe Rewriting**: File writes trigger automatic snapshots in `.harness_snapshots/`.
- **Rollback**: Instant restoration of previous file states.
- **Global vs Workspace Scope**: Configurable safety boundaries for file operations.

## Core Modules

- `harness/core/agent_loop.py`: The primary reasoning engine.
- `harness/core/context_window.py`: Context budgeting and compression.
- `harness/core/tool_executor.py`: Registry and implementation of agent capabilities.
- `harness/memory/memory_manager.py`: Persistent storage and retrieval.
- `harness/cli/live.py`: Animated activity renderer.

## Usage Guide

Refer to `COMMANDS.md` for a full list of slash commands and agent tools.
Refer to `README.md` for getting started and installation instructions.
