"""
WebSocket Manager for Agent OS.

Manages WebSocket connections for real-time updates.
"""

from typing import List, Dict, Any
from fastapi import WebSocket
import structlog
import json

logger = structlog.get_logger()


class ConnectionManager:
    """
    Manages WebSocket connections.

    Features:
    - Connection tracking
    - Broadcast to all clients
    - Client-specific messaging
    - Room/topic subscriptions
    """

    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.subscriptions: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and track a new WebSocket connection."""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("websocket_connected", total=len(self.active_connections))

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

        # Remove from all subscriptions
        for topic in self.subscriptions:
            if websocket in self.subscriptions[topic]:
                self.subscriptions[topic].remove(websocket)

        logger.info("websocket_disconnected", total=len(self.active_connections))

    async def send_personal(self, websocket: WebSocket, message: Dict[str, Any]) -> None:
        """Send a message to a specific client."""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error("websocket_send_error", error=str(e))
            self.disconnect(websocket)

    async def broadcast(self, message: Dict[str, Any]) -> None:
        """Broadcast a message to all connected clients."""
        disconnected = []

        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error("websocket_broadcast_error", error=str(e))
                disconnected.append(connection)

        # Clean up disconnected clients
        for conn in disconnected:
            self.disconnect(conn)

    def subscribe(self, websocket: WebSocket, topic: str) -> None:
        """Subscribe a client to a topic."""
        if topic not in self.subscriptions:
            self.subscriptions[topic] = []

        if websocket not in self.subscriptions[topic]:
            self.subscriptions[topic].append(websocket)
            logger.debug("websocket_subscribed", topic=topic)

    def unsubscribe(self, websocket: WebSocket, topic: str) -> None:
        """Unsubscribe a client from a topic."""
        if topic in self.subscriptions:
            if websocket in self.subscriptions[topic]:
                self.subscriptions[topic].remove(websocket)
                logger.debug("websocket_unsubscribed", topic=topic)

    async def publish(self, topic: str, message: Dict[str, Any]) -> None:
        """Publish a message to all subscribers of a topic."""
        if topic not in self.subscriptions:
            return

        disconnected = []

        for connection in self.subscriptions[topic]:
            try:
                await connection.send_json({"topic": topic, **message})
            except Exception as e:
                logger.error("websocket_publish_error", error=str(e))
                disconnected.append(connection)

        # Clean up disconnected clients
        for conn in disconnected:
            self.disconnect(conn)

    def get_stats(self) -> Dict[str, Any]:
        """Get WebSocket statistics."""
        return {
            "active_connections": len(self.active_connections),
            "topics": len(self.subscriptions),
            "subscriptions_by_topic": {
                topic: len(subs) for topic, subs in self.subscriptions.items()
            },
        }
