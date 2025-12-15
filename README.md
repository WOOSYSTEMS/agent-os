# Agent OS

> An operating system where AI agents are first-class citizens.

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

## What is Agent OS?

Agent OS is a runtime environment designed specifically for AI agents to operate autonomously. Unlike traditional operating systems built for humans interacting via GUI/CLI, Agent OS treats AI agents as the primary users.

```
Traditional OS: Human → GUI → Application → Result
Agent OS:       Goal  → Agent → Tools → Result
```

## Key Features

- **Agent Lifecycle Management** - Spawn, pause, resume, terminate agents
- **Capability-Based Security** - Fine-grained permissions for what agents can do
- **Unified Memory** - Context, working, and long-term memory for agents
- **Agent Communication** - Native protocols for agent-to-agent messaging
- **Tool System** - Extensible tools (shell, http, files, browser, etc.)
- **Observability** - See exactly what your agents are doing

## Quick Start

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/agent-os.git
cd agent-os

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the runtime
python -m agent_os.cli run

# In another terminal, spawn an agent
python -m agent_os.cli spawn --goal "List files in current directory"
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      AGENT OS                           │
├─────────────────────────────────────────────────────────┤
│  Agents    │ Your AI agents (trading bot, research, etc) │
├────────────┼────────────────────────────────────────────┤
│  Runtime   │ Lifecycle, scheduler, memory, messaging    │
├────────────┼────────────────────────────────────────────┤
│  Security  │ Capabilities, sandboxing, audit            │
├────────────┼────────────────────────────────────────────┤
│  Tools     │ Shell, HTTP, files, browser, custom        │
├────────────┼────────────────────────────────────────────┤
│  Host OS   │ macOS, Linux (runs on top of these)        │
└─────────────────────────────────────────────────────────┘
```

## Documentation

- [Design Document](docs/DESIGN.md) - Full architecture and concepts
- [Roadmap](docs/ROADMAP.md) - Development phases and milestones
- [Contributing](CONTRIBUTING.md) - How to contribute
- [Changelog](CHANGELOG.md) - Version history

## Project Status

**Current Phase:** 1 - Foundation

See [ROADMAP.md](docs/ROADMAP.md) for detailed progress.

## Why Agent OS?

Current AI agents run as afterthoughts on traditional OSes:
- No standard lifecycle management
- Security is bolted on, not built in
- Agents can't easily communicate
- Memory is fragmented across systems
- Hard to observe what agents are doing

Agent OS fixes this by making agents the primary abstraction.

## License

Apache License 2.0 - See [LICENSE](LICENSE) for details.

## Acknowledgments

Inspired by Unix, Plan 9, Erlang/OTP, and the emerging AI agent ecosystem.
