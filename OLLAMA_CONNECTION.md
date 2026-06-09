# Ollama Connection & Coding Capability

This document certifies the coding capability of the Adisn harness when connected to tool-calling Ollama models.

## Architecture: The Reasoning Loop

Adisn operates on a multi-step reasoning loop (think → decide → act → observe) that allows it to solve complex engineering tasks autonomously.

1.  **Thinking**: The model reasons through the task in a `<think>` block, identifying dependencies, potential risks, and step-by-step logic.
2.  **Decision**: The model outputs a structured JSON decision. Adisn supports multiple paradigms (Claude, Qwen, DeepSeek, Gemma) to ensure high-fidelity extraction of actions.
3.  **Action**: The harness executes the requested tool (e.g., `read_file`, `patch_file`, `shell`).
4.  **Observation**: The result of the tool execution is fed back into the model's context for the next step.

## Coding Toolset

Adisn provides a robust suite of tools that allow any capable Ollama model to manipulate codebases:

*   **`read_file` / `read_file_chunked`**: For full or incremental context gathering.
*   **`write_file`**: For creating new source files.
*   **`patch_file`**: For targeted, token-efficient edits using search-and-replace.
*   **`shell`**: For running compilers, linters, and test suites to verify changes.
*   **`grep` / `list_dir`**: For codebase exploration.

## Persistence and Self-Correction

To ensure user intent is satisfied, Adisn implements:

1.  **Self-Critique Phase**: Before finishing, the harness asks the model to audit its own response. If the solution is incomplete or incorrect, the loop continues with specific feedback.
2.  **Past Mistakes Tracking**: Failures are recorded in `.adisn/chats/past_mistakes.md`. The harness injects these "lessons learned" into the context of subsequent attempts to avoid repeating errors.
3.  **Automatic Compaction**: If the 50k token window is nearly full, Adisn automatically triggers history summarization to keep the "reasoning core" lean and functional.

## Certification

The Adisn harness is certified to provide full coding capabilities for any Ollama model that supports structured JSON tool calling. By providing a reliable bridge between LLM reasoning and local file system/shell execution, Adisn transforms a standard model into a productive software engineer.
