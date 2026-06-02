# Harness Index

Complete file index for the Hybrid Agent Harness.

## Package Structure

```
Adisn/
├── harness/
│   ├── __init__.py              # Package init
│   ├── __main__.py              # Module entry point
│   ├── entry_point.py           # Standalone CLI launcher
│   ├── test_harness.py          # Test script
│   ├── USAGE.md                 # Usage guide
│   ├── PROJECT.md               # Project summary
│   ├── README.md                # Harness docs
│   └── .gitignore               # Git ignore rules
│
│   ├── core/
│   │   ├── __init__.py          # Core module init
│   │   ├── ARCHITECTURE.md      # Architecture documentation
│   │   ├── skill_executor.py    # Skill execution
│   │   ├── skills_registry.py   # Dynamic skill generation
│   │   ├── skills.py            # Predefined skills
│   │   └── mcp_server.py        # MCP server management
│   │
│   ├── cli/
│   │   ├── __init__.py          # CLI interface
│   │   ├── main.py              # CLI entry point
│   │   └── ...
│   │
│   └── memory/
│       ├── __init__.py          # Memory module init
│       ├── memory_manager.py    # Memory management
│       ├── cli.py               # Memory CLI
│       └── ...
│
└── .remember/
    ├── now.md                   # Session buffer
    ├── today-*.md               # Daily logs
    ├── recent.md                # 7-day history
    ├── archive.md               # Historical data
    └── core_memories.md         # Core memories
```

## File Descriptions

### Entry Points

| File | Purpose | Command |
|------|---------|---------|
| `harness/__init__.py` | Package init, main entry | `python -m harness` |
| `harness/__main__.py` | Module entry point | `python -m harness` |
| `harness/entry_point.py` | Standalone CLI | `python harness/entry_point.py` |
| `harness/test_harness.py` | Test harness | `python harness/test_harness.py` |
| `harness/memory/cli.py` | Memory CLI | `python harness/memory/cli.py` |

### Core Modules

| File | Purpose |
|------|---------|
| `core/ARCHITECTURE.md` | Architecture documentation |
| `core/skill_executor.py` | Execute skills with tool binding |
| `core/skills_registry.py` | Dynamic skill generation |
| `core/skills.py` | Predefined skill implementations |
| `core/mcp_server.py` | MCP server initialization |
| `core/__init__.py` | Core module exports |

### CLI

| File | Purpose |
|------|---------|
| `cli/__init__.py` | Interactive CLI interface |
| `cli/main.py` | CLI entry point with args |

### Memory

| File | Purpose |
|------|---------|
| `memory/memory_manager.py` | Memory management system |
| `memory/cli.py` | Memory CLI commands |

### Memory Files

| File | Purpose |
|------|---------|
| `.remember/now.md` | Current session buffer |
| `.remember/today-*.md` | Daily logs |
| `.remember/recent.md` | 7-day history |
| `.remember/archive.md` | Historical data |
| `.remember/core_memories.md` | Core memories |

### Documentation

| File | Purpose |
|------|---------|
| `README.md` | Harness documentation |
| `PROJECT.md` | Complete project summary |
| `USAGE.md` | Usage guide and examples |
| `HARNESS_INDEX.md` | This file - file index |
| `.gitignore` | Git ignore rules |

## Quick Reference

### Start the Harness

```bash
python -m harness
# or
python harness/entry_point.py
```

### Commands

```
harness> bash <command>         # Terminal command
harness> read <file>            # Read file
harness> write <file> <content> # Write file
harness> git <command>          # Git command
harness> /help                  # Show help
harness> /status                # Show status
harness> /memory list           # List memory
```

### Tests

```bash
python harness/test_harness.py all    # Run all tests
python harness/test_harness.py status # Test status
python harness/test_harness.py skills # Test skills
python harness/test_harness.py memory # Test memory
python harness/test_harness.py launch # Launch harness
```

### Memory Commands

```bash
python harness/memory/cli.py list     # List memory
python harness/memory/cli.py clear    # Clear memory
python harness/memory/cli.py read     # Read memory
python harness/memory/cli.py add <name> <desc> <content>
python harness/memory/cli.py reference <name> <url>
python harness/memory/cli.py feedback <name> <content>
python harness/memory/cli.py project <name> <content>
```

### Programmatic Usage

```python
from harness.harness import create_harness

# Create harness
harness = create_harness()

# Process command
result = harness.process_request("bash whoami")

# Get status
state = harness.get_state()
```

### Available Skills

- `codebase_understanding` - Analyze codebase
- `git_operations` - Git management
- `docker_operations` - Docker containers
- `terraform_operations` - Infrastructure
- `npm_operations` - NPM packages
- `pip_operations` - Python packages
- `browser_automation` - Browser tasks
- `self_modification` - Code rewriting

### Available Tools

- `bash` - Execute bash commands
- `powershell` - Execute PowerShell
- `read` - Read file contents
- `write` - Write file contents
- `edit` - Edit with find/replace
- `git` - Git operations
- `chrome-devtools` - Chrome DevTools
- `playwright` - Playwright
- `aws` - AWS services
- `mcp` - Model Context Protocol

## Summary

The Hybrid Agent Harness combines:
- **Claude Code** capabilities (terminal, browser, CLI)
- **Hermes** skill generation from tasks
- **OpenClaw** self-modification

**Ready to use:**
```bash
python -m harness
```
