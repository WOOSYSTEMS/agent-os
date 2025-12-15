"""
Core data models for Agent OS.

These are the fundamental building blocks:
- Agent: An AI entity that can perform tasks
- Tool: A capability an agent can use
- Capability: A permission token
- Message: Communication between agents
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field
import uuid


# =============================================================================
# Enums
# =============================================================================

class AgentState(str, Enum):
    """Possible states of an agent."""
    PENDING = "pending"      # Created but not started
    RUNNING = "running"      # Actively executing
    PAUSED = "paused"        # Temporarily suspended
    COMPLETED = "completed"  # Finished successfully
    FAILED = "failed"        # Terminated with error
    TERMINATED = "terminated"  # Manually stopped


class ToolResultStatus(str, Enum):
    """Result status of a tool execution."""
    SUCCESS = "success"
    ERROR = "error"
    DENIED = "denied"  # Permission denied
    TIMEOUT = "timeout"


class MessageType(str, Enum):
    """Types of inter-agent messages."""
    REQUEST = "request"    # Ask another agent to do something
    RESPONSE = "response"  # Reply to a request
    EVENT = "event"        # Broadcast notification
    STREAM = "stream"      # Continuous data


# =============================================================================
# Agent Models
# =============================================================================

class AgentConfig(BaseModel):
    """Configuration for creating an agent."""
    goal: str = Field(..., description="What the agent should accomplish")
    model: str = Field(default="claude-sonnet-4-20250514", description="LLM model to use")
    tools: list[str] = Field(default_factory=list, description="Tool names to enable")
    capabilities: list[str] = Field(default_factory=list, description="Capability strings")
    max_iterations: int = Field(default=100, description="Max tool calls before stopping")
    timeout_seconds: int = Field(default=300, description="Max runtime in seconds")
    parent_id: Optional[str] = Field(default=None, description="Parent agent ID if spawned by another")


class Agent(BaseModel):
    """
    An Agent is the primary executable unit in Agent OS.

    Agent = AI Model + Tools + Memory + Permissions + Goal
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    state: AgentState = Field(default=AgentState.PENDING)
    config: AgentConfig

    # Runtime state
    created_at: datetime = Field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Execution tracking
    iterations: int = Field(default=0)
    tool_calls: list[dict] = Field(default_factory=list)
    last_error: Optional[str] = None
    result: Optional[str] = None

    # Relationships
    children: list[str] = Field(default_factory=list, description="Child agent IDs")

    class Config:
        use_enum_values = True


class AgentSummary(BaseModel):
    """Lightweight agent info for listing."""
    id: str
    state: AgentState
    goal: str
    model: str
    iterations: int
    created_at: datetime
    uptime_seconds: Optional[float] = None


# =============================================================================
# Tool Models
# =============================================================================

class ToolParameter(BaseModel):
    """A parameter for a tool."""
    name: str
    type: str  # "string", "integer", "boolean", "array", "object"
    description: str
    required: bool = True
    default: Optional[Any] = None


class ToolSchema(BaseModel):
    """Schema defining a tool's interface."""
    name: str = Field(..., description="Unique tool name like 'shell.execute'")
    description: str = Field(..., description="What the tool does")
    parameters: list[ToolParameter] = Field(default_factory=list)
    required_capabilities: list[str] = Field(default_factory=list)

    def to_anthropic_tool(self) -> dict:
        """Convert to Anthropic API tool format."""
        properties = {}
        required = []

        for param in self.parameters:
            properties[param.name] = {
                "type": param.type,
                "description": param.description,
            }
            if param.required:
                required.append(param.name)

        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": properties,
                "required": required,
            }
        }


class ToolResult(BaseModel):
    """Result of executing a tool."""
    tool_name: str
    status: ToolResultStatus
    output: Optional[str] = None
    error: Optional[str] = None
    execution_time_ms: int = 0


# =============================================================================
# Capability Models
# =============================================================================

class Capability(BaseModel):
    """
    A capability is a permission token.

    Format: resource:action:constraints
    Examples:
        - file:/home/user/*:read
        - http:api.example.com:*
        - shell:*:execute{timeout:30s}
        - agent:spawn{max:5}
    """
    resource: str = Field(..., description="What resource (file, http, shell, etc.)")
    path: str = Field(default="*", description="Path or pattern within resource")
    actions: list[str] = Field(default_factory=lambda: ["*"], description="Allowed actions")
    constraints: dict[str, Any] = Field(default_factory=dict, description="Limits like timeout, rate")

    @classmethod
    def parse(cls, capability_string: str) -> "Capability":
        """Parse a capability string like 'file:/home/*:read,write'."""
        parts = capability_string.split(":")

        if len(parts) < 2:
            raise ValueError(f"Invalid capability format: {capability_string}")

        resource = parts[0]
        path = parts[1] if len(parts) > 1 else "*"
        actions = parts[2].split(",") if len(parts) > 2 else ["*"]

        return cls(resource=resource, path=path, actions=actions)

    def matches(self, resource: str, path: str, action: str) -> bool:
        """Check if this capability grants access."""
        # Check resource
        if self.resource != "*" and self.resource != resource:
            return False

        # Check path (simple glob matching)
        if self.path != "*":
            if self.path.endswith("*"):
                if not path.startswith(self.path[:-1]):
                    return False
            elif self.path != path:
                return False

        # Check action
        if "*" not in self.actions and action not in self.actions:
            return False

        return True

    def __str__(self) -> str:
        actions_str = ",".join(self.actions)
        return f"{self.resource}:{self.path}:{actions_str}"


class CapabilityCheck(BaseModel):
    """Result of checking a capability."""
    allowed: bool
    capability: Optional[Capability] = None
    reason: str = ""


# =============================================================================
# Message Models
# =============================================================================

class Message(BaseModel):
    """
    A message between agents.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    type: MessageType
    sender_id: str
    recipient_id: Optional[str] = None  # None for broadcasts
    payload: dict = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.now)
    reply_to: Optional[str] = None  # For responses


# =============================================================================
# Event Models
# =============================================================================

class Event(BaseModel):
    """System event for logging and monitoring."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    type: str  # "agent.spawned", "tool.executed", "capability.denied", etc.
    agent_id: Optional[str] = None
    data: dict = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.now)
