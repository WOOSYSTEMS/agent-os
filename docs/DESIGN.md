# Agent OS - Design Document

> An operating system where AI agents are first-class citizens, not afterthoughts.

**Version:** 0.1.0-alpha
**License:** Apache 2.0
**Started:** December 2024

---

## Table of Contents

1. [Vision](#vision)
2. [Problem Statement](#problem-statement)
3. [Core Concepts](#core-concepts)
4. [Architecture](#architecture)
5. [Components](#components)
6. [Security Model](#security-model)
7. [Development Phases](#development-phases)
8. [Technical Decisions](#technical-decisions)
9. [Open Questions](#open-questions)

---

## Vision

**Agent OS** is a runtime environment designed specifically for AI agents to operate autonomously. Unlike traditional operating systems built for humans interacting via GUI/CLI, Agent OS treats AI agents as the primary users.

### What We're Building

```
NOT a replacement for macOS/Linux/Windows
BUT a runtime layer that runs ON those systems
FOR AI agents to operate safely and efficiently
```

### The Pitch

> "Traditional OSes ask: How does a human use this computer?"
> "Agent OS asks: How does an AI agent use this computer?"

---

## Problem Statement

### Current State of AI Agents

1. **Agents run as afterthoughts** - They're just processes in terminals, with no special support
2. **No standard agent lifecycle** - Each framework reinvents spawn/pause/resume/kill
3. **Security is bolted on** - Sandboxing is manual, permissions are ad-hoc
4. **No agent-to-agent communication** - Agents can't easily collaborate
5. **Memory is fragmented** - Context windows, vector DBs, files - all disconnected
6. **Observability is poor** - Hard to know what agents are doing
7. **Resource management is primitive** - No intelligent scheduling for agent workloads

### What We Need

A unified runtime that provides:
- First-class agent lifecycle management
- Built-in security and sandboxing
- Native agent communication protocols
- Unified memory/context management
- Deep observability
- Intelligent resource allocation

---

## Core Concepts

### 1. Agent

An **Agent** is the primary executable unit in Agent OS (analogous to a "process" in Unix).

```
Agent = AI Model + Tools + Memory + Permissions + Goal
```

Properties:
- **ID**: Unique identifier
- **Model**: The AI model powering the agent (Claude, GPT, local, etc.)
- **Tools**: What the agent can do
- **Memory**: Short-term (context) + long-term (persistent)
- **Permissions**: Capability tokens for what it's allowed to access
- **State**: pending | running | paused | completed | failed
- **Goal**: What the agent is trying to accomplish

### 2. Tool

A **Tool** is a capability that agents can invoke (analogous to a "syscall" in Unix).

```
Tool = Name + Schema + Implementation + Required Permissions
```

Examples:
- `shell.execute` - Run shell commands
- `http.fetch` - Make HTTP requests
- `file.read` / `file.write` - File operations
- `browser.navigate` - Control browser
- `agent.spawn` - Create child agents

### 3. Memory

**Memory** is how agents persist and recall information.

```
Memory Types:
├── Context (short-term): Current conversation/task
├── Working (medium-term): Current session state
├── Long-term: Persistent across sessions
└── Shared: Accessible by multiple agents
```

### 4. Capability

A **Capability** is a permission token (analogous to Unix file permissions, but more granular).

```
Capability = Resource + Actions + Constraints
```

Examples:
- `file:/home/user/data/*:read` - Read files in data directory
- `http:api.example.com:*` - Any HTTP to specific domain
- `shell:*:execute{timeout:30s}` - Shell with 30s timeout
- `agent:spawn{max:5}` - Spawn up to 5 child agents

### 5. Message

A **Message** is how agents communicate.

```
Message = Sender + Recipient + Type + Payload
```

Types:
- `request` - Ask another agent to do something
- `response` - Reply to a request
- `event` - Broadcast an event
- `stream` - Continuous data flow

---

## Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         AGENT OS                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐              │
│  │ Agent 1 │ │ Agent 2 │ │ Agent 3 │ │ Agent N │   AGENTS     │
│  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘              │
│       │          │          │          │                      │
│  ═════╪══════════╪══════════╪══════════╪═══════════════════   │
│       │          │          │          │                      │
│  ┌────┴──────────┴──────────┴──────────┴────┐                 │
│  │              AGENT RUNTIME                │                 │
│  │  ┌──────────────────────────────────┐    │                 │
│  │  │ Lifecycle │ Scheduler │ Registry │    │                 │
│  │  └──────────────────────────────────┘    │                 │
│  │  ┌──────────────────────────────────┐    │                 │
│  │  │ Memory    │ Messaging │ Events   │    │                 │
│  │  └──────────────────────────────────┘    │                 │
│  └────┬─────────────────────────────────────┘                 │
│       │                                                        │
│  ═════╪════════════════════════════════════════════════════   │
│       │                                                        │
│  ┌────┴─────────────────────────────────────┐                 │
│  │              SECURITY LAYER               │                 │
│  │  Capability Manager │ Sandbox │ Audit    │                 │
│  └────┬─────────────────────────────────────┘                 │
│       │                                                        │
│  ═════╪════════════════════════════════════════════════════   │
│       │                                                        │
│  ┌────┴─────────────────────────────────────┐                 │
│  │              TOOL LAYER                   │                 │
│  │  Shell │ HTTP │ Files │ Browser │ ...    │                 │
│  └────┬─────────────────────────────────────┘                 │
│       │                                                        │
│  ═════╪════════════════════════════════════════════════════   │
│       │                                                        │
│  ┌────┴─────────────────────────────────────┐                 │
│  │           HOST OS (macOS/Linux)           │                 │
│  │  Processes │ Files │ Network │ Hardware  │                 │
│  └──────────────────────────────────────────┘                 │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Component Interaction

```
User/API Request
       │
       ▼
┌──────────────┐
│   Gateway    │  (HTTP/WebSocket API)
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  Scheduler   │  (Decides which agent handles request)
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   Agent      │  (AI model makes decisions)
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Tool Call    │  (Agent wants to use a tool)
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Capability   │  (Check: Is agent allowed?)
│   Check      │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   Sandbox    │  (Execute in isolated environment)
└──────┬───────┘
       │
       ▼
┌──────────────┐
│    Tool      │  (Actually do the thing)
│ Execution    │
└──────┬───────┘
       │
       ▼
     Result
```

---

## Components

### 1. Agent Runtime (`src/runtime/`)

The core orchestrator managing agent lifecycles.

```python
class AgentRuntime:
    def spawn(agent_config) -> AgentID
    def pause(agent_id) -> None
    def resume(agent_id) -> None
    def terminate(agent_id) -> None
    def get_status(agent_id) -> AgentStatus
    def list_agents() -> List[AgentInfo]
```

### 2. Scheduler (`src/core/scheduler.py`)

Decides agent execution order based on goals and priorities.

```python
class Scheduler:
    def submit(goal) -> AgentID
    def prioritize(agent_id, priority) -> None
    def get_queue() -> List[PendingGoal]
```

### 3. Memory Manager (`src/core/memory.py`)

Unified memory across context, working, and long-term storage.

```python
class MemoryManager:
    def store(agent_id, key, value, scope) -> None
    def retrieve(agent_id, key, scope) -> Value
    def search(agent_id, query, scope) -> List[Result]
    def share(from_agent, to_agent, key) -> None
```

### 4. Capability Manager (`src/core/capabilities.py`)

Security through capability tokens.

```python
class CapabilityManager:
    def grant(agent_id, capability) -> Token
    def revoke(agent_id, capability) -> None
    def check(agent_id, action) -> bool
    def audit(agent_id) -> List[AccessLog]
```

### 5. Message Bus (`src/core/messaging.py`)

Agent-to-agent communication.

```python
class MessageBus:
    def send(from_agent, to_agent, message) -> None
    def broadcast(from_agent, event) -> None
    def subscribe(agent_id, event_type, handler) -> None
    def request(from_agent, to_agent, request) -> Response
```

### 6. Tool Registry (`src/tools/registry.py`)

Available tools and their implementations.

```python
class ToolRegistry:
    def register(tool) -> None
    def get(tool_name) -> Tool
    def list() -> List[ToolInfo]
    def execute(tool_name, params, agent_id) -> Result
```

---

## Security Model

### Principle: Capability-Based Security

Unlike Unix (user/group permissions) or mobile (install-time permissions), Agent OS uses **capability tokens** - unforgeable references to resources with specific allowed actions.

### Why Capabilities?

1. **Least Privilege** - Agents only get exactly what they need
2. **Delegatable** - Agents can pass capabilities to child agents
3. **Revocable** - Capabilities can be revoked at any time
4. **Auditable** - Every capability use is logged

### Capability Format

```
capability://resource/path?action=read,write&constraint=timeout:30s
```

Examples:
```
capability://file/Users/data/*?action=read
capability://http/api.anthropic.com/*?action=request&rate=100/min
capability://shell?action=execute&timeout=30s&allowlist=ls,cat,grep
capability://agent?action=spawn&max=3
```

### Sandbox Execution

All tool executions happen in sandboxed environments:

```
┌─────────────────────────────────────┐
│            SANDBOX                  │
│  ┌─────────────────────────────┐   │
│  │     Tool Execution          │   │
│  │  - Limited filesystem view  │   │
│  │  - Network restrictions     │   │
│  │  - Resource limits (CPU,RAM)│   │
│  │  - Timeout enforcement      │   │
│  └─────────────────────────────┘   │
└─────────────────────────────────────┘
```

---

## Development Phases

### Phase 1: Foundation (Weeks 1-2)

**Goal:** Basic agent lifecycle and tool execution

Deliverables:
- [ ] Project structure and tooling
- [ ] Agent data model
- [ ] Basic runtime (spawn, run, terminate)
- [ ] Simple tool system (shell, file, http)
- [ ] Basic capability checking
- [ ] CLI for interacting with runtime

### Phase 2: Memory & Messaging (Weeks 3-4)

**Goal:** Agents can remember and communicate

Deliverables:
- [ ] Context memory (per-session)
- [ ] Long-term memory (persistent)
- [ ] Message bus for agent communication
- [ ] Event system
- [ ] Memory search/retrieval

### Phase 3: Security & Sandboxing (Weeks 5-6)

**Goal:** Secure multi-agent execution

Deliverables:
- [ ] Full capability system
- [ ] Sandbox execution
- [ ] Audit logging
- [ ] Resource limits
- [ ] Agent isolation

### Phase 4: Dashboard & Observability (Weeks 7-8)

**Goal:** See what agents are doing

Deliverables:
- [ ] Web dashboard
- [ ] Real-time agent monitoring
- [ ] Memory inspection
- [ ] Capability visualization
- [ ] Performance metrics

### Phase 5: Agent Ecosystem (Ongoing)

**Goal:** Build useful agents

Deliverables:
- [ ] Port trading bot as agent
- [ ] Research agent
- [ ] Code agent
- [ ] Agent templates
- [ ] Agent marketplace concept

---

## Technical Decisions

### Language: Python

**Why:**
- Rapid prototyping
- Rich AI/ML ecosystem
- Easy integration with LLM APIs
- Your existing bots are Python

**Future:** Consider Rust for performance-critical paths

### Storage: SQLite + Files

**Why:**
- No external dependencies
- ACID transactions
- Good enough for single-machine
- Easy backup/restore

### API: FastAPI + WebSocket

**Why:**
- Async-native
- Auto-generated OpenAPI docs
- WebSocket for real-time updates
- You already know it (Solana bot dashboard)

### LLM Integration: Model-Agnostic

Support multiple providers:
- Anthropic (Claude)
- OpenAI (GPT)
- Local (Ollama, llama.cpp)
- Custom endpoints

---

## Open Questions

1. **How do we handle agent crashes?**
   - Restart automatically?
   - Notify and wait?
   - Checkpoint and resume?

2. **How granular should capabilities be?**
   - Per-file? Per-directory?
   - Per-API-endpoint? Per-domain?

3. **How do agents learn/improve?**
   - Store successful patterns?
   - Fine-tune models?
   - Just log for human review?

4. **How do we handle secrets?**
   - Inject at runtime?
   - Encrypted storage?
   - Never let agents see raw secrets?

5. **Multi-machine distribution?**
   - Phase 1: Single machine only
   - Future: Distributed agent runtime?

---

## Appendix: Inspirations

- **Unix** - Everything is a file, simple primitives
- **Plan 9** - Everything is a file, but better
- **Erlang/OTP** - Actor model, fault tolerance
- **Docker** - Containerization, isolation
- **Capability-based systems** - seL4, Capsicum
- **MCP (Model Context Protocol)** - Tool standardization

---

*This is a living document. Update as we learn.*
