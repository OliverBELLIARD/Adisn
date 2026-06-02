# Skills Generation Guide

The harness can dynamically generate skills from task descriptions. This guide explains how the skill generation system works and how to extend it.

## How Skill Generation Works

### Task-to-Skill Mapping

When a user provides a task like:

```
"search for git configuration"
"read the README file"
"write a new feature"
"git status"
```

The harness:

1. **Extracts action keywords** from the task description
2. **Matches to predefined skills** or generates a new skill
3. **Binds available tools** to the skill
4. **Executes the skill** with appropriate parameters

### Example: From Task to Skill

```python
# User task
task = "read the README file"

# Harness extracts action
action = "read"

# Maps to skill
skill = {
    "name": "read_skill",
    "description": "Read file contents",
    "tools_required": ["read"],
    "execute": lambda path: {"content": Path(path).read_text()}
}
```

## Skill Generation Process

### 1. Keyword Extraction

```python
def _extract_action(task: str) -> str:
    task_lower = task.lower()
    actions = {
        "search": "search",
        "read": "read",
        "write": "write",
        "git": "git",
        "docker": "docker",
        "terraform": "terraform",
        "npm": "npm",
        "pip": "pip",
        "browser": "browser",
        "build": "build",
        "edit": "edit",
    }
    
    for keyword, action in actions.items():
        if keyword in task_lower:
            return action
    
    return "general"
```

### 2. Skill Definition

```python
from harness.core.skills import SkillDefinitionBuilder

def create_skill(task: str) -> SkillDefinition:
    # Based on task, create appropriate skill
    if "git" in task.lower():
        return SkillDefinitionBuilder("git_operations", "Git operations") \
            .build()
```

### 3. Tool Binding

```python
def bind_tools(skill: Dict, task: str) -> Dict:
    # Determine which tools are needed
    task_lower = task.lower()
    
    if "git" in task_lower:
        skill["tools_required"] = ["git"]
    elif "docker" in task_lower:
        skill["tools_required"] = ["bash", "docker"]
    
    return skill
```

## Extending Skills

### Adding New Skills

```python
from harness.core.skills import SkillDefinitionBuilder
from harness.core.skills_registry import register_skill

# Define new skill
def my_skill(task: str):
    return {
        "name": "my_skill",
        "description": "My custom skill",
        "execute": lambda: {"status": "ready"},
        "parameters": {},
        "tools_required": ["bash"]
    }

register_skill(my_skill)
```

### Registering Tool Generators

```python
from harness.core.skills_registry import SkillRegistry

def git_skill_generator(task: str):
    """Generate git skill from task."""
    if "git" in task.lower():
        return {
            "name": "git_operations",
            "description": "Git repository management",
            "execute": lambda command=None: {
                "command": f"git {command or ''}",
                "status": "ready"
            }
        }
    return None

registry = SkillRegistry()
registry.register_generator("git", git_skill_generator)
```

## Skill Registry

The `SkillRegistry` class manages skill definitions:

```python
from harness.core.skills_registry import SkillRegistry, get_registry

# Get registry
registry = get_registry()

# Available skills
skills = registry.get_available_skills()
for skill in skills:
    print(f"{skill['name']}: {skill['description']}")

# Generate skill from task
task = "read the README"
skill = registry.generate(task)
if skill:
    print(f"Generated: {skill['name']}")

# Execute skill
result = registry.execute("git_operations")
```

## Skill Chaining

Complex tasks can be handled by chaining multiple skills:

```python
from harness.core.skill_executor import SkillChain

# Create chain
chain = SkillChain(executor) \
    .add("git", {"command": "status"}) \
    .add("read", {"path": "README.md"})

# Execute
result = chain.execute()
```

## Example Skills

### 1. Git Operations

```python
def git_operations(task: str):
    return {
        "name": "git_operations",
        "description": "Git repository management",
        "execute": lambda: {
            "status": "git_ready",
            "capabilities": ["status", "commit", "push", "pull"]
        },
        "tools_required": ["git"]
    }
```

### 2. Docker Operations

```python
def docker_operations(task: str):
    return {
        "name": "docker_operations",
        "description": "Docker container management",
        "execute": lambda: {
            "status": "docker_ready",
            "capabilities": ["ps", "run", "build", "logs"]
        },
        "tools_required": ["bash", "docker"]
    }
```

### 3. Browser Automation

```python
def browser_automation(task: str):
    return {
        "name": "browser_automation",
        "description": "Browser automation via DevTools/Playwright",
        "execute": lambda: {
            "status": "browser_ready",
            "capabilities": ["navigation", "interaction", "screenshot"]
        },
        "tools_required": ["chrome-devtools", "playwright"]
    }
```

## Skill Parameters

Skills can accept parameters:

```python
def param_skill(task: str):
    return {
        "name": "param_skill",
        "description": "Skill with parameters",
        "execute": lambda file=None, command=None: {
            "file": file,
            "command": command
        },
        "parameters": {
            "file": {"default": None, "required": False},
            "command": {"default": None, "required": False}
        },
        "tools_required": ["bash"]
    }
```

## Dynamic Skill Creation

Create skills on-the-fly:

```python
def dynamic_skill(task: str):
    """Create skill from any task description."""
    task_lower = task.lower()
    
    if "search" in task_lower or "find" in task_lower:
        return predefined_skills["search"]
    elif "read" in task_lower or "open" in task_lower:
        return predefined_skills["read"]
    elif "write" in task_lower or "create" in task_lower:
        return predefined_skills["write"]
    
    return None
```

## Skill Logging

Log skill generation for tracking:

```python
from harness.core.skills_registry import get_registry

registry = get_registry()
registry.log_generation(task, skill_name)
```

## Best Practices

1. **Keep skills simple** - One skill per action
2. **Clear descriptions** - Document what each skill does
3. **Appropriate tools** - Only bind needed tools
4. **Parameter validation** - Check required parameters
5. **Error handling** - Handle tool execution errors

## Testing Skills

```bash
python harness/test_harness.py skills
```

Tests:
- Check available skills
- Test skill generation
- Verify tool binding

## Summary

The skill generation system:
- **Automatically creates skills** from task descriptions
- **Binds appropriate tools** for each skill
- **Logs generation** for tracking
- **Supports extension** with custom generators

This enables the harness to handle any task by:
1. Parsing the task description
2. Generating or finding the appropriate skill
3. Binding needed tools
4. Executing the skill
5. Capturing and returning results
