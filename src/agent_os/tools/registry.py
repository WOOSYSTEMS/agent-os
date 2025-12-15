"""
Tool Registry for Agent OS.

Manages tool registration and execution with capability checking.
"""

import time
from typing import Any, Callable, Optional, Awaitable
from ..core.models import ToolSchema, ToolResult, ToolResultStatus
from ..core.capabilities import CapabilityManager
import structlog

logger = structlog.get_logger()


# Type for tool implementation functions
ToolFunction = Callable[..., Awaitable[str]]


class ToolRegistry:
    """
    Central registry for all available tools.

    Tools are registered with schemas and implementations.
    Execution includes capability checking and result wrapping.
    """

    def __init__(self, capability_manager: CapabilityManager):
        self._tools: dict[str, ToolSchema] = {}
        self._implementations: dict[str, ToolFunction] = {}
        self._capability_manager = capability_manager

    def register(
        self,
        schema: ToolSchema,
        implementation: ToolFunction
    ) -> None:
        """Register a tool with its schema and implementation."""
        self._tools[schema.name] = schema
        self._implementations[schema.name] = implementation
        logger.info("tool_registered", name=schema.name)

    def get_schema(self, name: str) -> Optional[ToolSchema]:
        """Get a tool's schema by name."""
        return self._tools.get(name)

    def list_tools(self) -> list[ToolSchema]:
        """List all registered tools."""
        return list(self._tools.values())

    def list_tool_names(self) -> list[str]:
        """List all registered tool names."""
        return list(self._tools.keys())

    def get_tools_for_agent(self, tool_names: list[str]) -> list[dict]:
        """Get tool schemas in Anthropic format for an agent."""
        tools = []
        for name in tool_names:
            schema = self._tools.get(name)
            if schema:
                tools.append(schema.to_anthropic_tool())
        return tools

    async def execute(
        self,
        agent_id: str,
        tool_name: str,
        parameters: dict[str, Any]
    ) -> ToolResult:
        """
        Execute a tool with capability checking.

        Args:
            agent_id: ID of the agent calling the tool
            tool_name: Name of the tool to execute
            parameters: Parameters to pass to the tool

        Returns:
            ToolResult with status and output/error
        """
        start_time = time.time()

        # Check if tool exists
        if tool_name not in self._tools:
            return ToolResult(
                tool_name=tool_name,
                status=ToolResultStatus.ERROR,
                error=f"Unknown tool: {tool_name}",
                execution_time_ms=0
            )

        schema = self._tools[tool_name]

        # Check capabilities for required permissions
        for cap_string in schema.required_capabilities:
            parts = cap_string.split(":")
            resource = parts[0]
            path = parts[1] if len(parts) > 1 else "*"
            action = parts[2] if len(parts) > 2 else "*"

            check = self._capability_manager.check(agent_id, resource, path, action)
            if not check.allowed:
                return ToolResult(
                    tool_name=tool_name,
                    status=ToolResultStatus.DENIED,
                    error=f"Permission denied: {check.reason}",
                    execution_time_ms=int((time.time() - start_time) * 1000)
                )

        # Execute the tool
        try:
            implementation = self._implementations[tool_name]
            output = await implementation(**parameters)

            return ToolResult(
                tool_name=tool_name,
                status=ToolResultStatus.SUCCESS,
                output=output,
                execution_time_ms=int((time.time() - start_time) * 1000)
            )

        except TimeoutError:
            return ToolResult(
                tool_name=tool_name,
                status=ToolResultStatus.TIMEOUT,
                error="Tool execution timed out",
                execution_time_ms=int((time.time() - start_time) * 1000)
            )

        except Exception as e:
            logger.error("tool_execution_error",
                        tool=tool_name,
                        agent_id=agent_id,
                        error=str(e))
            return ToolResult(
                tool_name=tool_name,
                status=ToolResultStatus.ERROR,
                error=str(e),
                execution_time_ms=int((time.time() - start_time) * 1000)
            )
