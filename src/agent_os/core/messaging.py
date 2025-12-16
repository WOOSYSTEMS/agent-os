"""
Message Bus for Agent OS.

Enables agent-to-agent communication with:
- Direct messages
- Request/response patterns
- Event broadcasts
- Subscriptions
"""

import asyncio
from datetime import datetime
from typing import Any, Callable, Awaitable, Optional
from collections import defaultdict
import uuid
import structlog

from .models import Message, MessageType, Event

logger = structlog.get_logger()

# Type aliases
MessageHandler = Callable[[Message], Awaitable[None]]
EventHandler = Callable[[Event], Awaitable[None]]


class PendingRequest:
    """A pending request waiting for response."""

    def __init__(self, message: Message, timeout: float):
        self.message = message
        self.timeout = timeout
        self.future: asyncio.Future = asyncio.get_event_loop().create_future()
        self.created_at = datetime.now()


class MessageBus:
    """
    Central message bus for agent communication.

    Features:
    - Point-to-point messaging
    - Request/response with timeout
    - Event broadcasting
    - Topic-based subscriptions
    """

    def __init__(self):
        # Message queues per agent
        self._queues: dict[str, asyncio.Queue] = {}

        # Event subscriptions: event_type -> list of (agent_id, handler)
        self._event_subscriptions: dict[str, list[tuple[str, EventHandler]]] = defaultdict(list)

        # Pending requests waiting for response
        self._pending_requests: dict[str, PendingRequest] = {}

        # Message handlers per agent
        self._handlers: dict[str, MessageHandler] = {}

        # Message history for debugging
        self._history: list[Message] = []
        self._max_history = 1000

    def register_agent(self, agent_id: str, handler: Optional[MessageHandler] = None) -> None:
        """Register an agent to receive messages."""
        self._queues[agent_id] = asyncio.Queue()
        if handler:
            self._handlers[agent_id] = handler
        logger.debug("agent_registered_for_messaging", agent_id=agent_id)

    def unregister_agent(self, agent_id: str) -> None:
        """Unregister an agent from messaging."""
        if agent_id in self._queues:
            del self._queues[agent_id]
        if agent_id in self._handlers:
            del self._handlers[agent_id]

        # Remove from subscriptions
        for event_type in self._event_subscriptions:
            self._event_subscriptions[event_type] = [
                (aid, h) for aid, h in self._event_subscriptions[event_type]
                if aid != agent_id
            ]

        logger.debug("agent_unregistered_from_messaging", agent_id=agent_id)

    async def send(
        self,
        sender_id: str,
        recipient_id: str,
        payload: dict,
        message_type: MessageType = MessageType.REQUEST
    ) -> Message:
        """
        Send a message to another agent.

        Args:
            sender_id: Sending agent
            recipient_id: Receiving agent
            payload: Message content
            message_type: Type of message

        Returns:
            The sent message
        """
        message = Message(
            type=message_type,
            sender_id=sender_id,
            recipient_id=recipient_id,
            payload=payload
        )

        # Add to history
        self._add_to_history(message)

        # Check if recipient exists
        if recipient_id not in self._queues:
            logger.warning("message_recipient_not_found",
                          sender=sender_id,
                          recipient=recipient_id)
            return message

        # Add to recipient's queue
        await self._queues[recipient_id].put(message)

        logger.debug("message_sent",
                    sender=sender_id,
                    recipient=recipient_id,
                    type=message_type.value)

        return message

    async def request(
        self,
        sender_id: str,
        recipient_id: str,
        payload: dict,
        timeout: float = 30.0
    ) -> Optional[Message]:
        """
        Send a request and wait for response.

        Args:
            sender_id: Sending agent
            recipient_id: Receiving agent
            payload: Request content
            timeout: Seconds to wait for response

        Returns:
            Response message or None if timeout
        """
        message = await self.send(
            sender_id=sender_id,
            recipient_id=recipient_id,
            payload=payload,
            message_type=MessageType.REQUEST
        )

        # Create pending request
        pending = PendingRequest(message, timeout)
        self._pending_requests[message.id] = pending

        try:
            # Wait for response
            response = await asyncio.wait_for(pending.future, timeout=timeout)
            return response
        except asyncio.TimeoutError:
            logger.warning("request_timeout",
                          sender=sender_id,
                          recipient=recipient_id,
                          message_id=message.id)
            return None
        finally:
            if message.id in self._pending_requests:
                del self._pending_requests[message.id]

    async def respond(
        self,
        original_message: Message,
        payload: dict
    ) -> Message:
        """
        Respond to a request message.

        Args:
            original_message: The request being responded to
            payload: Response content

        Returns:
            The response message
        """
        response = Message(
            type=MessageType.RESPONSE,
            sender_id=original_message.recipient_id,
            recipient_id=original_message.sender_id,
            payload=payload,
            reply_to=original_message.id
        )

        # Add to history
        self._add_to_history(response)

        # Check for pending request
        if original_message.id in self._pending_requests:
            pending = self._pending_requests[original_message.id]
            if not pending.future.done():
                pending.future.set_result(response)
        else:
            # No pending request, send normally
            if response.recipient_id in self._queues:
                await self._queues[response.recipient_id].put(response)

        logger.debug("response_sent",
                    to=response.recipient_id,
                    reply_to=original_message.id)

        return response

    async def broadcast(
        self,
        sender_id: str,
        event_type: str,
        data: dict
    ) -> Event:
        """
        Broadcast an event to all subscribers.

        Args:
            sender_id: Agent emitting the event
            event_type: Type of event (e.g., "price.updated")
            data: Event data

        Returns:
            The emitted event
        """
        event = Event(
            type=event_type,
            agent_id=sender_id,
            data=data
        )

        # Call all subscribers
        handlers = self._event_subscriptions.get(event_type, [])
        for agent_id, handler in handlers:
            try:
                await handler(event)
            except Exception as e:
                logger.error("event_handler_error",
                           event_type=event_type,
                           agent_id=agent_id,
                           error=str(e))

        # Also check for wildcard subscribers
        wildcard_handlers = self._event_subscriptions.get("*", [])
        for agent_id, handler in wildcard_handlers:
            try:
                await handler(event)
            except Exception as e:
                logger.error("event_handler_error",
                           event_type=event_type,
                           agent_id=agent_id,
                           error=str(e))

        logger.debug("event_broadcast",
                    sender=sender_id,
                    event_type=event_type,
                    subscribers=len(handlers) + len(wildcard_handlers))

        return event

    def subscribe(
        self,
        agent_id: str,
        event_type: str,
        handler: EventHandler
    ) -> None:
        """
        Subscribe to an event type.

        Args:
            agent_id: Subscribing agent
            event_type: Event type to subscribe to (use "*" for all)
            handler: Async function to call when event occurs
        """
        self._event_subscriptions[event_type].append((agent_id, handler))
        logger.debug("event_subscription_added",
                    agent_id=agent_id,
                    event_type=event_type)

    def unsubscribe(
        self,
        agent_id: str,
        event_type: str
    ) -> None:
        """Unsubscribe from an event type."""
        if event_type in self._event_subscriptions:
            self._event_subscriptions[event_type] = [
                (aid, h) for aid, h in self._event_subscriptions[event_type]
                if aid != agent_id
            ]

    async def receive(
        self,
        agent_id: str,
        timeout: Optional[float] = None
    ) -> Optional[Message]:
        """
        Receive the next message for an agent.

        Args:
            agent_id: Agent receiving
            timeout: Optional timeout in seconds

        Returns:
            Next message or None if timeout
        """
        if agent_id not in self._queues:
            return None

        queue = self._queues[agent_id]

        try:
            if timeout:
                message = await asyncio.wait_for(queue.get(), timeout=timeout)
            else:
                message = await queue.get()
            return message
        except asyncio.TimeoutError:
            return None

    def get_pending_count(self, agent_id: str) -> int:
        """Get number of pending messages for an agent."""
        if agent_id not in self._queues:
            return 0
        return self._queues[agent_id].qsize()

    def get_history(
        self,
        agent_id: Optional[str] = None,
        limit: int = 100
    ) -> list[Message]:
        """Get message history, optionally filtered by agent."""
        if agent_id:
            filtered = [
                m for m in self._history
                if m.sender_id == agent_id or m.recipient_id == agent_id
            ]
            return filtered[-limit:]
        return self._history[-limit:]

    def _add_to_history(self, message: Message) -> None:
        """Add message to history with bounded size."""
        self._history.append(message)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

    def get_stats(self) -> dict:
        """Get messaging statistics."""
        return {
            "registered_agents": len(self._queues),
            "pending_requests": len(self._pending_requests),
            "event_types": len(self._event_subscriptions),
            "total_subscriptions": sum(
                len(subs) for subs in self._event_subscriptions.values()
            ),
            "history_size": len(self._history),
        }
