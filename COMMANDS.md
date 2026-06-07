# Adisn Command and Tool Index

This document provides a comprehensive guide to all slash commands and agent tools available in the Adisn harness.

## Slash Commands (CLI)

Slash commands are used directly by the user in the interactive CLI.

### System Commands
- `/help`: Show rich help for all slash commands.
- `/status`: Display the current Adisn runtime status, including token usage and model info.
- `/quit`: Exit the interactive mode.
- `/think`: Toggle the extended thinking mode (Claude Code style).
- `/think expand`: Show full thinking process text in the CLI.
- `/memory`: Show the distribution of memory entries and estimated token usage.
- `/history`: List recent prompt history.
- `/history <id>`: Inspect a specific history entry.
- `/history load <id>`: Re-run a previous prompt by ID.
- `/resume`: List available chat files in `.adisn/chats/`.
- `/resume <chat_name>`: Reload a conversation history into the current context.
- `/toolkit`: Show or set the tool-calling paradigm (e.g., `claude`, `qwen`, `deepseek`). Set to `qwen` for models like Qwen2.5-small.
- `/scope <global|workspace>`: Toggle between global (unsafe) and workspace-only rewrite scope.

### Self-Modification Commands
- `/rewrite <path>`: Manually rewrite a file with automatic snapshot safety.
- `/rollback`: Roll back the last file rewrite.

### Ollama Management
- `/ollama status`: Check if the Ollama server is running and reachable.
- `/ollama serve`: Start the Ollama daemon in the background.
- `/ollama list`: List all installed Ollama models.
- `/ollama pull <model>`: Download a new model from the Ollama library.
- `/ollama rm <model>`: Delete an installed Ollama model.
- `/ollama ensure-profile <name>`: Install all models for a specific Questbook profile.

### Cookbook Commands
- `/cookbook scan`: Scan hardware (GPU/VRAM) to determine the best model fit.
- `/cookbook recommend <profile>`: Get model recommendations (fast, balanced, coding, etc.).
- `/cookbook list`: Show the full catalog of supported models.
- `/cookbook pull <model>`: Download a model via the cookbook manager.
- `/cookbook use <model>`: Set the active model for the agent loop.
- `/cookbook status`: Show detailed status of cookbook providers and running serves.

---

## Agent Tools (Internal)

Tools are used by the agent during the reasoning loop to interact with the environment.

### File Operations
- `read_file(path, offset, limit)`: Read text from a file. Supports pagination.
- `write_file(path, content, reason)`: Create or overwrite a file. Triggers a safety snapshot.
- `patch_file(path, search, replace, reason)`: Efficient search-and-replace edit for a specific file.
- `read_file_chunked(path, chunk_index, chunk_size)`: Read large files in segments to manage the context window.
- `list_dir(path)`: List the contents of a directory.
- `grep(pattern, path)`: Search for a regex pattern in file contents.

### System & Evolution
- `shell(command)`: Execute a bash/cmd command in the workspace.
- `pip_install(package)`: Install a Python dependency.
- `create_tool(name, description, code)`: Register a new custom Python tool for the agent to use.
- `list_tools()`: List all available tools and their usage.

### Memory & Skills
- `read_memory(file_name, limit_lines)`: Recall information from markdown memory files in `.adisn/chats/`.
- `summarize_history()`: Manually trigger the compression of the current conversation context.
- `create_skill(task, content)`: Document a workflow or procedure as a reusable skill.
- `read_skill(name)`: Read the content of a previously created skill.
- `use_skill(skill_name)`: (Action) Explicitly switch the agent's context to a specific skill.
