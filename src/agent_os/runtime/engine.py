"""
Agent Runtime Engine for Agent OS.

The core engine that manages agent lifecycle and execution.
"""

import asyncio
from datetime import datetime
from typing import Optional, Callable, Awaitable
import anthropic
import structlog

from ..core.models import (
    Agent, AgentConfig, AgentState, AgentSummary,
    ToolResult, ToolResultStatus, Event
)
from ..core.capabilities import CapabilityManager, get_default_capabilities
from ..core.memory import MemoryManager, MemoryScope
from ..core.messaging import MessageBus
from ..tools import ToolRegistry, register_builtin_tools, BUILTIN_TOOLS

logger = structlog.get_logger()


class AgentRuntime:
    """
    The Agent Runtime manages all agents and their execution.

    Responsibilities:
    - Agent lifecycle (spawn, pause, resume, terminate)
    - Tool execution with capability checking
    - Memory management (context, working, long-term, shared)
    - Inter-agent messaging
    - Event emission for observability
    """

    def __init__(
        self,
        anthropic_api_key: Optional[str] = None,
        memory_db_path: Optional[str] = None,
    ):
        # Core managers
        self.capability_manager = CapabilityManager()
        self.tool_registry = ToolRegistry(self.capability_manager)

        # Memory and messaging (Phase 2)
        self.memory = MemoryManager(db_path=memory_db_path)
        self.message_bus = MessageBus()

        # Register built-in tools
        register_builtin_tools(self.tool_registry)

        # Anthropic client for LLM calls
        self._anthropic = anthropic.AsyncAnthropic(
            api_key=anthropic_api_key
        ) if anthropic_api_key else anthropic.AsyncAnthropic()

        # Agent storage
        self._agents: dict[str, Agent] = {}
        self._agent_tasks: dict[str, asyncio.Task] = {}

        # Event handlers
        self._event_handlers: list[Callable[[Event], Awaitable[None]]] = []

        # Runtime state
        self._running = False

    async def start(self) -> None:
        """Start the runtime."""
        self._running = True

        # Initialize memory system
        await self.memory.initialize()

        await self._emit_event("runtime.started", None, {})
        logger.info("agent_runtime_started")

    async def stop(self) -> None:
        """Stop the runtime and all agents."""
        self._running = False

        # Terminate all running agents
        for agent_id in list(self._agents.keys()):
            await self.terminate(agent_id)

        # Close memory database
        await self.memory.close()

        await self._emit_event("runtime.stopped", None, {})
        logger.info("agent_runtime_stopped")

    async def spawn(self, config: AgentConfig) -> Agent:
        """
        Spawn a new agent with the given configuration.

        Args:
            config: Agent configuration

        Returns:
            The created Agent
        """
        agent = Agent(config=config)

        # Grant capabilities
        if config.capabilities:
            self.capability_manager.grant_many(agent.id, config.capabilities)
        else:
            # Default capabilities
            default_caps = get_default_capabilities("basic")
            self.capability_manager.grant_many(agent.id, default_caps)

        # Register with message bus for inter-agent communication
        self.message_bus.register_agent(agent.id)

        # Store agent
        self._agents[agent.id] = agent

        await self._emit_event("agent.spawned", agent.id, {
            "goal": config.goal,
            "model": config.model,
        })

        logger.info("agent_spawned",
                   agent_id=agent.id,
                   goal=config.goal)

        return agent

    async def run(self, agent_id: str) -> Agent:
        """
        Run an agent until completion or termination.

        Args:
            agent_id: ID of agent to run

        Returns:
            The agent after completion
        """
        agent = self._agents.get(agent_id)
        if not agent:
            raise ValueError(f"Agent not found: {agent_id}")

        if agent.state != AgentState.PENDING:
            raise ValueError(f"Agent {agent_id} is not in PENDING state")

        # Update state
        agent.state = AgentState.RUNNING
        agent.started_at = datetime.now()

        await self._emit_event("agent.started", agent_id, {})

        try:
            await self._run_agent_loop(agent)

            if agent.state == AgentState.RUNNING:
                agent.state = AgentState.COMPLETED
                agent.completed_at = datetime.now()

        except Exception as e:
            agent.state = AgentState.FAILED
            agent.last_error = str(e)
            agent.completed_at = datetime.now()
            logger.error("agent_failed", agent_id=agent_id, error=str(e))

        await self._emit_event("agent.completed", agent_id, {
            "state": agent.state,
            "iterations": agent.iterations,
        })

        return agent

    async def spawn_and_run(self, config: AgentConfig) -> Agent:
        """Convenience method to spawn and run an agent."""
        agent = await self.spawn(config)
        return await self.run(agent.id)

    async def _run_agent_loop(self, agent: Agent) -> None:
        """The main agent execution loop."""
        config = agent.config

        # Build available tools
        tool_names = config.tools if config.tools else BUILTIN_TOOLS
        tools = self.tool_registry.get_tools_for_agent(tool_names)

        # Initial messages
        messages = [
            {
                "role": "user",
                "content": f"Your goal: {config.goal}\n\nYou have access to tools to help accomplish this. Use them as needed. When you've completed the goal, respond with your final result."
            }
        ]

        # Agent loop
        while agent.state == AgentState.RUNNING:
            # Check iteration limit
            if agent.iterations >= config.max_iterations:
                agent.result = "Reached maximum iterations"
                break

            agent.iterations += 1

            # Call LLM
            response = await self._anthropic.messages.create(
                model=config.model,
                max_tokens=4096,
                tools=tools,
                messages=messages
            )

            # Process response
            assistant_content = response.content
            messages.append({"role": "assistant", "content": assistant_content})

            # Check for tool use
            tool_uses = [block for block in assistant_content if block.type == "tool_use"]

            if not tool_uses:
                # No tool use - agent is done
                text_blocks = [block for block in assistant_content if block.type == "text"]
                if text_blocks:
                    agent.result = text_blocks[0].text
                break

            # Execute tools
            tool_results = []
            for tool_use in tool_uses:
                result = await self.tool_registry.execute(
                    agent_id=agent.id,
                    tool_name=tool_use.name,
                    parameters=tool_use.input
                )

                # Record tool call
                agent.tool_calls.append({
                    "tool": tool_use.name,
                    "input": tool_use.input,
                    "result": result.model_dump()
                })

                await self._emit_event("tool.executed", agent.id, {
                    "tool": tool_use.name,
                    "status": result.status,
                })

                # Build result content
                if result.status == ToolResultStatus.SUCCESS:
                    content = result.output or "(no output)"
                else:
                    content = f"Error: {result.error}"

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": content
                })

            # Add tool results to messages
            messages.append({"role": "user", "content": tool_results})

    async def pause(self, agent_id: str) -> Agent:
        """Pause a running agent."""
        agent = self._agents.get(agent_id)
        if not agent:
            raise ValueError(f"Agent not found: {agent_id}")

        if agent.state == AgentState.RUNNING:
            agent.state = AgentState.PAUSED
            await self._emit_event("agent.paused", agent_id, {})
            logger.info("agent_paused", agent_id=agent_id)

        return agent

    async def resume(self, agent_id: str) -> Agent:
        """Resume a paused agent."""
        agent = self._agents.get(agent_id)
        if not agent:
            raise ValueError(f"Agent not found: {agent_id}")

        if agent.state == AgentState.PAUSED:
            agent.state = AgentState.RUNNING
            await self._emit_event("agent.resumed", agent_id, {})
            logger.info("agent_resumed", agent_id=agent_id)

        return agent

    async def terminate(self, agent_id: str) -> Agent:
        """Terminate an agent."""
        agent = self._agents.get(agent_id)
        if not agent:
            raise ValueError(f"Agent not found: {agent_id}")

        if agent.state in (AgentState.RUNNING, AgentState.PAUSED, AgentState.PENDING):
            agent.state = AgentState.TERMINATED
            agent.completed_at = datetime.now()

            # Cancel the task if running
            if agent_id in self._agent_tasks:
                self._agent_tasks[agent_id].cancel()
                del self._agent_tasks[agent_id]

            # Revoke capabilities
            self.capability_manager.revoke_all(agent_id)

            # Clean up memory (context and working, preserve long-term)
            await self.memory.clear_agent(agent_id)

            # Unregister from message bus
            self.message_bus.unregister_agent(agent_id)

            await self._emit_event("agent.terminated", agent_id, {})
            logger.info("agent_terminated", agent_id=agent_id)

        return agent

    def get_agent(self, agent_id: str) -> Optional[Agent]:
        """Get an agent by ID."""
        return self._agents.get(agent_id)

    def list_agents(self) -> list[AgentSummary]:
        """List all agents."""
        summaries = []
        now = datetime.now()

        for agent in self._agents.values():
            uptime = None
            if agent.started_at:
                end = agent.completed_at or now
                uptime = (end - agent.started_at).total_seconds()

            summaries.append(AgentSummary(
                id=agent.id,
                state=agent.state,
                goal=agent.config.goal,
                model=agent.config.model,
                iterations=agent.iterations,
                created_at=agent.created_at,
                uptime_seconds=uptime
            ))

        return summaries

    def on_event(self, handler: Callable[[Event], Awaitable[None]]) -> None:
        """Register an event handler."""
        self._event_handlers.append(handler)

    async def _emit_event(self, event_type: str, agent_id: Optional[str], data: dict) -> None:
        """Emit an event to all handlers."""
        event = Event(type=event_type, agent_id=agent_id, data=data)

        for handler in self._event_handlers:
            try:
                await handler(event)
            except Exception as e:
                logger.error("event_handler_error", error=str(e))

    # === Memory convenience methods ===

    async def store_memory(
        self,
        agent_id: str,
        key: str,
        value: any,
        scope: MemoryScope = MemoryScope.WORKING
    ) -> None:
        """Store a value in agent memory."""
        await self.memory.store(agent_id, key, value, scope)

    async def retrieve_memory(
        self,
        agent_id: str,
        key: str,
        scope: MemoryScope = MemoryScope.WORKING
    ) -> any:
        """Retrieve a value from agent memory."""
        return await self.memory.retrieve(agent_id, key, scope)

    async def share_memory(
        self,
        from_agent: str,
        key: str,
        from_scope: MemoryScope = MemoryScope.WORKING
    ) -> bool:
        """Share an agent's memory to the shared scope."""
        return await self.memory.share(from_agent, key, from_scope)

    # === Messaging convenience methods ===

    async def send_message(
        self,
        from_agent: str,
        to_agent: str,
        payload: dict
    ):
        """Send a message between agents."""
        return await self.message_bus.send(from_agent, to_agent, payload)

    async def request_response(
        self,
        from_agent: str,
        to_agent: str,
        payload: dict,
        timeout: float = 30.0
    ):
        """Send a request and wait for response."""
        return await self.message_bus.request(from_agent, to_agent, payload, timeout)

    async def broadcast_event(
        self,
        agent_id: str,
        event_type: str,
        data: dict
    ):
        """Broadcast an event to all subscribers."""
        return await self.message_bus.broadcast(agent_id, event_type, data)

    def subscribe_to_event(
        self,
        agent_id: str,
        event_type: str,
        handler
    ) -> None:
        """Subscribe an agent to an event type."""
        self.message_bus.subscribe(agent_id, event_type, handler)

    # === Statistics ===

    def get_stats(self) -> dict:
        """Get comprehensive runtime statistics."""
        agent_states = {}
        for agent in self._agents.values():
            state = agent.state.value
            agent_states[state] = agent_states.get(state, 0) + 1

        return {
            "agents": {
                "total": len(self._agents),
                "by_state": agent_states,
            },
            "memory": self.memory.get_stats(),
            "messaging": self.message_bus.get_stats(),
            "capabilities": {
                "total_grants": sum(
                    len(caps) for caps in self.capability_manager._agent_capabilities.values()
                ),
            },
            "running": self._running,
        }
