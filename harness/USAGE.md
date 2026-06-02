# Harness Usage Guide

## Quick Start

```bash
# Start the harness
python -m harness

# Or use the entry point
python harness/entry_point.py

# Show help
python -m harness --help
```

## Interactive Mode

```
============================================================
  HYBRID AGENT HARNESS
============================================================

Welcome! Available commands:
  /help          - Show help
  /status        - Show harness status
  /memory list   - List memory entries
  /tools         - List tools
  /quit          - Exit harness

Or just type commands directly:
  bash <cmd>     - Run bash command
  read <file>    - Read file
  write <file> <content> - Write to file
  git <cmd>      - Git command
  ... and more!
============================================================
```

## Commands

### Direct Commands

Type commands directly in the harness:

```
harness> bash --version
[Result] {
  "command": "--version",
  "output": "GNU bash, version 5.2.x"
}

harness> read README.md
[Result] {
  "content": "# Adisn\n...\n"
}

harness> write test.txt "Hello World"
[Result] {
  "success": true,
  "path": "test.txt",
  "size": 12
}

harness> git status
[Result] {
  "command": "git status",
  "output": "On branch main\nChanges not staged:\n...\n"
}
```

### Slash Commands

Use slash commands for harness operations:

```
harness> /help          # Show help
harness> /status        # Show harness status
harness> /tools         # List available tools
harness> /memory list   # List memory entries
harness> /quit          # Exit harness
```

### Memory Commands

```
harness> /memory list   # List all memory entries
harness> /memory clear  # Clear session memory
harness> /memory read   # Read memory entries
```

## Tools

The harness provides access to these tools:

### Terminal
- `bash <command>` - Execute bash commands
- `powershell <command>` - Execute PowerShell

### Files
- `read <path>` - Read file contents
- `write <path> <content>` - Write to file
- `edit <path> <find> <replace>` - Edit file

### Git
- `git <command>` - Git operations (status, add, commit, push, pull, etc.)

### Browser
- `chrome-devtools:<action>` - Chrome DevTools operations
- `playwright:<action>` - Playwright browser automation

### AWS
- `aws <command>` - AWS CLI commands

### Memory
- `memory:<action>` - Memory operations

## Examples

### Terminal Operations
```
harness> bash ls -la
harness> bash git status
harness> bash docker ps
harness> bash npm list
```

### File Operations
```
harness> read .claude/claude.md
harness> write notes.md "My notes"
harness> edit README.md "# Old" "# New title"
```

### Git Operations
```
harness> git status
harness> git add .
harness> git commit -m "Initial commit"
harness> git log --oneline -5
```

### Browser Automation
```
harness> chrome-devtools:list_pages
harness> playwright:browser_navigate https://example.com
harness> playwright:browser_take_screenshot
```

### Memory Operations
```
harness> /memory list
harness> /memory add my-task "Task description" "Task content here"
harness> /memory clear
```

## Programmatic Usage

Use the harness from Python code:

```python
from harness.harness import create_harness

# Create harness instance
harness = create_harness()

# Process a command
result = harness.process_request("bash whoami")
print(result)

# Get harness state
state = harness.get_state()
print(state)

# Register a custom skill
harness.skill_registry.register("my_skill", {
    "name": "my_skill",
    "description": "My custom skill",
    "execute": lambda: {"status": "ready"}
})

# Register a tool
from harness.harness import ToolDefinition

tool = ToolDefinition(
    name="mytool",
    description="My custom tool",
    execute=my_execute_function,
    sandboxed=True
)

harness.tool_catalog.register_tool(tool)
```

### Memory Usage

```python
from harness.memory.memory_manager import MemoryManager, MemoryEntry
from pathlib import Path

# Create memory manager
mm = MemoryManager(Path.cwd() / ".remember")

# Add memory entry
entry = MemoryEntry(
    name="my-memory",
    description="My memory entry",
    content="Content here"
)

mm.append_to_now(entry)
mm.save_entry(entry, "project")

# List memory
entries = mm.get_session_memory()
for entry in entries:
    print(f"{entry.name}: {entry.content}")
```

## Skills

Skills are generated dynamically from task descriptions:

```python
from harness.core.skills_registry import get_registry

# Get registry
registry = get_registry()

# Available skills
skills = registry.get_available_skills()
for skill in skills:
    print(f"{skill['name']}: {skill['description']}")

# Generate a skill from a task
task = "read the README file"
skill = registry.generate(task)
if skill:
    print(f"Generated skill: {skill['name']}")

# Execute a skill
result = registry.execute("git_operations")
print(result)
```

## Memory System

The harness uses a memory system to persist state:

### Memory Files

- `.remember/now.md` - Current session buffer
- `.remember/today-YYYY-MM-DD.md` - Daily logs
- `.remember/recent.md` - 7-day history
- `.remember/archive.md` - Historical data
- `.remember/core_memories.md` - Core memories

### Memory Categories

- `user` - User preferences and identity
- `feedback` - How to behave and learnings
- `project` - Project information
- `reference` - Documentation URLs

### Using Memory

```bash
# List memory entries
harness> /memory list

# Clear session memory
harness> /memory clear

# Add to memory
harness> /memory add my-task "Description" "Content"
```

## Troubleshooting

### Tool Not Found
```
Error: Tool not found: mytool
```
**Solution:** Register the tool with the harness or use an available tool.

### Skill Not Found
```
Error: Skill not found: my_skill
```
**Solution:** Use an available skill or generate one from a task description.

### Memory Error
```
Error: Memory file not found
```
**Solution:** Ensure the .remember directory exists.

### AWS Not Available
```
boto3 not available, skipping AWS tools
```
**Solution:** Install boto3: `pip install boto3`

## Tips

1. **Use memory** - Save important information in memory
2. **Check tools** - Use `/tools` to see available tools
3. **Generate skills** - Skills are created from task descriptions
4. **Read documentation** - Check README.md for more info
5. **Clear memory** - Use `/memory clear` to start fresh

## Next Steps

1. **Try commands** - Experiment with different commands
2. **Read files** - Use `read` to explore the codebase
3. **Write files** - Use `write` to create files
4. **Use git** - Manage version control
5. **Build skills** - Create custom skills for your needs
6. **Learn tools** - Discover available tools and capabilities

## Resources

- `README.md` - Main documentation
- `harness/README.md` - Harness documentation
- `harness/PROJECT.md` - Project summary
- `harness/core/ARCHITECTURE.md` - Architecture docs
- `harness/USAGE.md` - This guide

## License

Use responsibly.
