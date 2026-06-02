# Hybrid Agent Harness Architecture

## Overview

The Hybrid Agent Harness combines:
- **Claude Code** capabilities (CLI tools, terminal agent, codebase understanding)
- **Hermes** dynamic skill generation from tasks
- **OpenClaw** self-modification and environment rewriting

## Core Capabilities

### 1. Tool Calling (Claude Code-style)
- MCP (Model Context Protocol) server integration
- Browser automation via Chrome DevTools
- AWS service interactions
- File system operations
- Web scraping and automation

### 2. Skill Generation (Hermes-style)
- Dynamic skill creation from task descriptions
- Skill registry with versioning
- Skill composition and chaining
- Context-aware skill dispatching

### 3. Self-Modification (OpenClaw-style)
- Real-time harness code rewriting
- Environment state persistence
- Capability discovery and registration
- Safe execution sandboxing

## Architecture Layers

```
┌─────────────────────────────────────────────────┐
│                   User Input                     │
└─────────────┬────────────────────────────────────┘
              │
┌─────────────▼────────────────────────────────────┐
│           Capability Router                      │
│  - Skill Resolution                              │
│  - Tool Selection                                │
│  - Parameter Binding                             │
└─────────────┬────────────────────────────────────┘
              │
    ┌──────────┴──────────┐
    ▼                     ▼
┌──────────────┐   ┌──────────────────┐
│ Skill Engine │   │  Tool Executor   │
│ (Hermes)     │   │  (Claude Code)   │
└──────────────┘   └──────────────────┘
         │                │
    ┌────▼────────┬───────┴───────┐
    ▼             ▼               ▼
┌──────────┐  ┌──────────┐  ┌──────────────┐
│ Memory   │  │ Sandbox  │  │ Self-Write   │
│ Manager  │  │ Engine   │  │ Engine       │
└──────────┘  └──────────┘  └──────────────┘
```

## Key Components

### Harness Core
- `HarnessAgent` - Main orchestration class
- `SkillRegistry` - Dynamic skill management
- `ToolCatalog` - Available tools discovery
- `EnvironmentState` - Persistent state tracking

### Skill System
- `BaseSkill` - Abstract skill definition
- `TaskParser` - Extract actions from natural language
- `SkillGenerator` - Create skills from requirements
- `SkillCompositor` - Chain skills for complex tasks

### Tool Interface
- `ToolDefinition` - Tool metadata (name, params, effects)
- `ToolAdapter` - Wrap external APIs as tools
- `MCPManager` - Model Context Protocol handling
- `ExecutionContext` - Tool execution environment

### Self-Modification
- `WriteGuard` - Safe file modification
- `DependencyChecker` - Verify imports before write
- `VersionManager` - Track harness evolution
- `RollbackHandler` - Undo failed modifications

## Execution Flow

```
1. Parse user request
2. Match to existing skill OR generate new skill
3. Bind available tools to skill
4. Execute in sandboxed environment
5. Capture results and update memory
6. Optionally modify harness for future tasks
```

## Memory System

- `.remember/` - Session state and context
- Memory categories:
  - `now.md` - Current buffer
  - `today-*.md` - Daily logs
  - `recent.md` - 7-day history
  - `archive.md` - Historical data

## Tool Categories

1. **CLI Tools** - Terminal commands, git, docker, terraform
2. **Browser Tools** - Chrome DevTools, Playwright
3. **AWS Tools** - All AWS service interactions
4. **System Tools** - File operations, networking
5. **Custom Tools** - User-defined capabilities

## Safety Guards

- Execution timeout per action
- Sandbox environment for tool runs
- File operation confirmation for critical ops
- Memory capacity management
