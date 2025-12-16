"""
API Routes for Agent OS.

REST API endpoints for runtime control and monitoring.
"""

from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, HTTPException, Request, BackgroundTasks
from pydantic import BaseModel, Field
import structlog

from ..core import AgentConfig, AgentState, AgentSummary, SandboxPolicy

logger = structlog.get_logger()

router = APIRouter()


# === Request/Response Models ===

class SpawnAgentRequest(BaseModel):
    """Request to spawn a new agent."""
    goal: str = Field(..., description="The agent's goal")
    model: str = Field(default="claude-sonnet-4-20250514", description="Model to use")
    tools: Optional[List[str]] = Field(default=None, description="Tools to enable")
    max_iterations: int = Field(default=50, description="Maximum iterations")


class AgentResponse(BaseModel):
    """Agent information response."""
    id: str
    state: str
    goal: str
    model: str
    iterations: int
    created_at: datetime
    uptime_seconds: Optional[float] = None


class RunCommandRequest(BaseModel):
    """Request to run a sandboxed command."""
    command: str
    policy: Optional[str] = Field(default="standard", description="Sandbox policy")
    agent_id: Optional[str] = Field(default=None, description="Associated agent")


class CommandResponse(BaseModel):
    """Sandboxed command response."""
    success: bool
    output: str
    error: str
    exit_code: int
    duration_seconds: float
    violations: List[str]


class MessageRequest(BaseModel):
    """Request to send a message between agents."""
    from_agent: str
    to_agent: str
    payload: dict


class MemoryRequest(BaseModel):
    """Request to store/retrieve memory."""
    agent_id: str
    key: str
    value: Optional[dict] = None
    scope: str = Field(default="working")


# === Health & Info ===

@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


@router.get("/stats")
async def get_stats(request: Request):
    """Get runtime statistics."""
    runtime = request.app.state.runtime
    return runtime.get_stats()


@router.get("/info")
async def get_info():
    """Get system information."""
    from .. import __version__
    return {
        "name": "Agent OS",
        "version": __version__,
        "description": "An operating system for AI agents",
    }


# === Agent Management ===

@router.get("/agents", response_model=List[AgentResponse])
async def list_agents(request: Request):
    """List all agents."""
    runtime = request.app.state.runtime
    agents = runtime.list_agents()
    return [
        AgentResponse(
            id=a.id,
            state=a.state.value,
            goal=a.goal,
            model=a.model,
            iterations=a.iterations,
            created_at=a.created_at,
            uptime_seconds=a.uptime_seconds,
        )
        for a in agents
    ]


@router.post("/agents", response_model=AgentResponse)
async def spawn_agent(request: Request, body: SpawnAgentRequest, background_tasks: BackgroundTasks):
    """Spawn a new agent."""
    runtime = request.app.state.runtime

    config = AgentConfig(
        goal=body.goal,
        model=body.model,
        tools=body.tools,
        max_iterations=body.max_iterations,
    )

    agent = await runtime.spawn(config)

    # Run agent in background
    async def run_agent():
        try:
            await runtime.run(agent.id)
        except Exception as e:
            logger.error("background_agent_error", agent_id=agent.id, error=str(e))

    background_tasks.add_task(run_agent)

    return AgentResponse(
        id=agent.id,
        state=agent.state.value,
        goal=agent.config.goal,
        model=agent.config.model,
        iterations=agent.iterations,
        created_at=agent.created_at,
    )


@router.get("/agents/{agent_id}", response_model=AgentResponse)
async def get_agent(request: Request, agent_id: str):
    """Get agent by ID."""
    runtime = request.app.state.runtime
    agent = runtime.get_agent(agent_id)

    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    uptime = None
    if agent.started_at:
        end = agent.completed_at or datetime.now()
        uptime = (end - agent.started_at).total_seconds()

    return AgentResponse(
        id=agent.id,
        state=agent.state.value,
        goal=agent.config.goal,
        model=agent.config.model,
        iterations=agent.iterations,
        created_at=agent.created_at,
        uptime_seconds=uptime,
    )


@router.post("/agents/{agent_id}/pause")
async def pause_agent(request: Request, agent_id: str):
    """Pause an agent."""
    runtime = request.app.state.runtime
    try:
        agent = await runtime.pause(agent_id)
        return {"status": "paused", "agent_id": agent.id}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/agents/{agent_id}/resume")
async def resume_agent(request: Request, agent_id: str):
    """Resume a paused agent."""
    runtime = request.app.state.runtime
    try:
        agent = await runtime.resume(agent_id)
        return {"status": "resumed", "agent_id": agent.id}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/agents/{agent_id}/terminate")
async def terminate_agent(request: Request, agent_id: str):
    """Terminate an agent."""
    runtime = request.app.state.runtime
    try:
        agent = await runtime.terminate(agent_id)
        return {"status": "terminated", "agent_id": agent.id}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# === Sandbox ===

@router.post("/sandbox/execute", response_model=CommandResponse)
async def execute_sandboxed(request: Request, body: RunCommandRequest):
    """Execute a command in the sandbox."""
    runtime = request.app.state.runtime

    # Map policy string to enum
    policy_map = {
        "unrestricted": SandboxPolicy.UNRESTRICTED,
        "standard": SandboxPolicy.STANDARD,
        "strict": SandboxPolicy.STRICT,
    }
    policy = policy_map.get(body.policy, SandboxPolicy.STANDARD)

    result = await runtime.execute_sandboxed(
        command=body.command,
        agent_id=body.agent_id,
        policy=policy,
    )

    return CommandResponse(
        success=result.success,
        output=result.output,
        error=result.error,
        exit_code=result.exit_code,
        duration_seconds=result.duration_seconds,
        violations=result.violations,
    )


# === Memory ===

@router.post("/memory/store")
async def store_memory(request: Request, body: MemoryRequest):
    """Store a value in memory."""
    runtime = request.app.state.runtime
    from ..core import MemoryScope

    scope_map = {
        "context": MemoryScope.CONTEXT,
        "working": MemoryScope.WORKING,
        "long_term": MemoryScope.LONG_TERM,
        "shared": MemoryScope.SHARED,
    }
    scope = scope_map.get(body.scope, MemoryScope.WORKING)

    await runtime.store_memory(body.agent_id, body.key, body.value, scope)
    return {"status": "stored", "key": body.key}


@router.get("/memory/retrieve")
async def retrieve_memory(request: Request, agent_id: str, key: str, scope: str = "working"):
    """Retrieve a value from memory."""
    runtime = request.app.state.runtime
    from ..core import MemoryScope

    scope_map = {
        "context": MemoryScope.CONTEXT,
        "working": MemoryScope.WORKING,
        "long_term": MemoryScope.LONG_TERM,
        "shared": MemoryScope.SHARED,
    }
    memory_scope = scope_map.get(scope, MemoryScope.WORKING)

    value = await runtime.retrieve_memory(agent_id, key, memory_scope)
    return {"key": key, "value": value, "scope": scope}


# === Messaging ===

@router.post("/messages/send")
async def send_message(request: Request, body: MessageRequest):
    """Send a message between agents."""
    runtime = request.app.state.runtime

    message = await runtime.send_message(
        from_agent=body.from_agent,
        to_agent=body.to_agent,
        payload=body.payload,
    )

    return {
        "status": "sent",
        "message_id": message.id,
        "from": body.from_agent,
        "to": body.to_agent,
    }


@router.post("/messages/broadcast")
async def broadcast_event(request: Request, agent_id: str, event_type: str, data: dict):
    """Broadcast an event."""
    runtime = request.app.state.runtime

    event = await runtime.broadcast_event(agent_id, event_type, data)

    return {
        "status": "broadcast",
        "event_type": event_type,
        "from": agent_id,
    }


# === Audit ===

@router.get("/audit/events")
async def get_audit_events(
    request: Request,
    agent_id: Optional[str] = None,
    event_type: Optional[str] = None,
    limit: int = 100,
):
    """Get audit events."""
    runtime = request.app.state.runtime

    from ..core import AuditEventType

    # Parse event type if provided
    audit_type = None
    if event_type:
        try:
            audit_type = AuditEventType(event_type)
        except ValueError:
            pass

    events = await runtime.audit.get_events(
        agent_id=agent_id,
        event_type=audit_type,
        limit=limit,
    )

    return [e.to_dict() for e in events]


@router.get("/audit/security")
async def get_security_events(request: Request, limit: int = 50):
    """Get security-related audit events."""
    runtime = request.app.state.runtime
    events = await runtime.get_security_events(limit=limit)
    return [e.to_dict() for e in events]


@router.get("/audit/agent/{agent_id}")
async def get_agent_audit(request: Request, agent_id: str, limit: int = 50):
    """Get audit history for an agent."""
    runtime = request.app.state.runtime
    events = await runtime.get_agent_audit_history(agent_id, limit=limit)
    return [e.to_dict() for e in events]


# === Tools ===

@router.get("/tools")
async def list_tools(request: Request):
    """List available tools."""
    runtime = request.app.state.runtime
    tools = runtime.tool_registry.list_tools()

    return [
        {
            "name": t.name,
            "description": t.description,
            "parameters": [
                {"name": p.name, "type": p.type, "required": p.required}
                for p in t.parameters
            ],
            "required_capabilities": t.required_capabilities,
        }
        for t in tools
    ]
