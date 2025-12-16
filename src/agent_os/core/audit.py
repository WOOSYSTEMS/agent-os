"""
Audit Logger for Agent OS.

Provides comprehensive security audit logging for:
- Agent actions and tool calls
- Security policy violations
- Resource usage
- Access attempts
"""

import asyncio
import json
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import Optional, Any, Callable, Awaitable
from pathlib import Path
import aiosqlite
import structlog

logger = structlog.get_logger()


class AuditEventType(str, Enum):
    """Types of audit events."""
    # Agent lifecycle
    AGENT_SPAWNED = "agent.spawned"
    AGENT_STARTED = "agent.started"
    AGENT_COMPLETED = "agent.completed"
    AGENT_FAILED = "agent.failed"
    AGENT_TERMINATED = "agent.terminated"

    # Tool execution
    TOOL_CALLED = "tool.called"
    TOOL_COMPLETED = "tool.completed"
    TOOL_FAILED = "tool.failed"
    TOOL_DENIED = "tool.denied"

    # Security events
    CAPABILITY_GRANTED = "security.capability_granted"
    CAPABILITY_REVOKED = "security.capability_revoked"
    CAPABILITY_DENIED = "security.capability_denied"
    POLICY_VIOLATION = "security.policy_violation"

    # Resource events
    RESOURCE_LIMIT_WARNING = "resource.limit_warning"
    RESOURCE_LIMIT_EXCEEDED = "resource.limit_exceeded"

    # Access events
    FILE_ACCESS = "access.file"
    NETWORK_ACCESS = "access.network"
    MEMORY_ACCESS = "access.memory"

    # System events
    RUNTIME_STARTED = "system.runtime_started"
    RUNTIME_STOPPED = "system.runtime_stopped"
    CONFIG_CHANGED = "system.config_changed"


class AuditSeverity(str, Enum):
    """Severity levels for audit events."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class AuditEvent:
    """A single audit event."""
    event_type: AuditEventType
    severity: AuditSeverity
    agent_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    details: dict = field(default_factory=dict)
    source: str = "agent-os"
    session_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "event_type": self.event_type.value,
            "severity": self.severity.value,
            "agent_id": self.agent_id,
            "timestamp": self.timestamp.isoformat(),
            "details": self.details,
            "source": self.source,
            "session_id": self.session_id,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


# Type for audit handlers
AuditHandler = Callable[[AuditEvent], Awaitable[None]]


class AuditLogger:
    """
    Centralized audit logging system.

    Features:
    - Multiple output destinations (file, database, handlers)
    - Event filtering by type and severity
    - Query interface for audit history
    - Real-time event streaming
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        log_file: Optional[str] = None,
        min_severity: AuditSeverity = AuditSeverity.INFO
    ):
        self.db_path = db_path or str(Path.home() / ".agent-os" / "audit.db")
        self.log_file = log_file
        self.min_severity = min_severity

        # Database connection
        self._db: Optional[aiosqlite.Connection] = None
        self._initialized = False

        # In-memory buffer for recent events
        self._buffer: list[AuditEvent] = []
        self._max_buffer = 1000

        # Custom handlers
        self._handlers: list[AuditHandler] = []

        # Statistics
        self._event_counts: dict[str, int] = {}
        self._session_id: Optional[str] = None

        # Severity ordering for filtering
        self._severity_order = {
            AuditSeverity.DEBUG: 0,
            AuditSeverity.INFO: 1,
            AuditSeverity.WARNING: 2,
            AuditSeverity.ERROR: 3,
            AuditSeverity.CRITICAL: 4,
        }

    async def initialize(self, session_id: Optional[str] = None) -> None:
        """Initialize the audit logger."""
        if self._initialized:
            return

        self._session_id = session_id or datetime.now().strftime("%Y%m%d_%H%M%S")

        # Create directory if needed
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        # Connect to SQLite
        self._db = await aiosqlite.connect(self.db_path)

        # Create tables
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                agent_id TEXT,
                timestamp TEXT NOT NULL,
                details TEXT,
                source TEXT,
                session_id TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_agent
            ON audit_events(agent_id)
        """)

        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_type
            ON audit_events(event_type)
        """)

        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_timestamp
            ON audit_events(timestamp)
        """)

        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_session
            ON audit_events(session_id)
        """)

        await self._db.commit()
        self._initialized = True

        logger.info("audit_logger_initialized",
                   db_path=self.db_path,
                   session_id=self._session_id)

    async def close(self) -> None:
        """Close the audit logger."""
        if self._db:
            await self._db.close()
            self._db = None
        self._initialized = False

    def add_handler(self, handler: AuditHandler) -> None:
        """Add a custom event handler."""
        self._handlers.append(handler)

    def remove_handler(self, handler: AuditHandler) -> None:
        """Remove a custom event handler."""
        if handler in self._handlers:
            self._handlers.remove(handler)

    async def log(
        self,
        event_type: AuditEventType,
        severity: AuditSeverity = AuditSeverity.INFO,
        agent_id: Optional[str] = None,
        details: Optional[dict] = None,
        **kwargs
    ) -> AuditEvent:
        """
        Log an audit event.

        Args:
            event_type: Type of event
            severity: Event severity
            agent_id: Associated agent ID
            details: Event details
            **kwargs: Additional details to merge

        Returns:
            The logged AuditEvent
        """
        # Check severity filter
        if self._severity_order[severity] < self._severity_order[self.min_severity]:
            return None

        # Create event
        event_details = details or {}
        event_details.update(kwargs)

        event = AuditEvent(
            event_type=event_type,
            severity=severity,
            agent_id=agent_id,
            details=event_details,
            session_id=self._session_id,
        )

        # Update counts
        type_key = event_type.value
        self._event_counts[type_key] = self._event_counts.get(type_key, 0) + 1

        # Add to buffer
        self._buffer.append(event)
        if len(self._buffer) > self._max_buffer:
            self._buffer = self._buffer[-self._max_buffer:]

        # Persist to database
        if self._db:
            await self._persist_event(event)

        # Write to log file
        if self.log_file:
            await self._write_to_file(event)

        # Call handlers
        for handler in self._handlers:
            try:
                await handler(event)
            except Exception as e:
                logger.error("audit_handler_error", error=str(e))

        # Log to structlog for visibility
        log_method = getattr(logger, severity.value, logger.info)
        log_method("audit_event",
                  event_type=event_type.value,
                  agent_id=agent_id,
                  details=event_details)

        return event

    async def _persist_event(self, event: AuditEvent) -> None:
        """Persist event to database."""
        if not self._db:
            return

        await self._db.execute("""
            INSERT INTO audit_events
            (event_type, severity, agent_id, timestamp, details, source, session_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            event.event_type.value,
            event.severity.value,
            event.agent_id,
            event.timestamp.isoformat(),
            json.dumps(event.details),
            event.source,
            event.session_id,
        ))
        await self._db.commit()

    async def _write_to_file(self, event: AuditEvent) -> None:
        """Write event to log file."""
        if not self.log_file:
            return

        try:
            async with asyncio.Lock():
                with open(self.log_file, "a") as f:
                    f.write(event.to_json() + "\n")
        except Exception as e:
            logger.error("audit_file_write_error", error=str(e))

    # === Convenience logging methods ===

    async def log_agent_spawned(self, agent_id: str, config: dict) -> AuditEvent:
        """Log agent spawn event."""
        return await self.log(
            AuditEventType.AGENT_SPAWNED,
            AuditSeverity.INFO,
            agent_id=agent_id,
            details={"config": config}
        )

    async def log_tool_called(
        self,
        agent_id: str,
        tool_name: str,
        parameters: dict
    ) -> AuditEvent:
        """Log tool call event."""
        return await self.log(
            AuditEventType.TOOL_CALLED,
            AuditSeverity.INFO,
            agent_id=agent_id,
            details={
                "tool": tool_name,
                "parameters": parameters,
            }
        )

    async def log_tool_result(
        self,
        agent_id: str,
        tool_name: str,
        success: bool,
        duration: float
    ) -> AuditEvent:
        """Log tool result event."""
        event_type = AuditEventType.TOOL_COMPLETED if success else AuditEventType.TOOL_FAILED
        severity = AuditSeverity.INFO if success else AuditSeverity.WARNING

        return await self.log(
            event_type,
            severity,
            agent_id=agent_id,
            details={
                "tool": tool_name,
                "success": success,
                "duration_seconds": duration,
            }
        )

    async def log_capability_denied(
        self,
        agent_id: str,
        resource: str,
        action: str,
        reason: str
    ) -> AuditEvent:
        """Log capability denial."""
        return await self.log(
            AuditEventType.CAPABILITY_DENIED,
            AuditSeverity.WARNING,
            agent_id=agent_id,
            details={
                "resource": resource,
                "action": action,
                "reason": reason,
            }
        )

    async def log_policy_violation(
        self,
        agent_id: str,
        violation_type: str,
        details: str
    ) -> AuditEvent:
        """Log security policy violation."""
        return await self.log(
            AuditEventType.POLICY_VIOLATION,
            AuditSeverity.ERROR,
            agent_id=agent_id,
            details={
                "violation_type": violation_type,
                "violation_details": details,
            }
        )

    async def log_file_access(
        self,
        agent_id: str,
        path: str,
        action: str,
        allowed: bool
    ) -> AuditEvent:
        """Log file access attempt."""
        severity = AuditSeverity.INFO if allowed else AuditSeverity.WARNING

        return await self.log(
            AuditEventType.FILE_ACCESS,
            severity,
            agent_id=agent_id,
            details={
                "path": path,
                "action": action,
                "allowed": allowed,
            }
        )

    async def log_network_access(
        self,
        agent_id: str,
        host: str,
        port: int,
        allowed: bool
    ) -> AuditEvent:
        """Log network access attempt."""
        severity = AuditSeverity.INFO if allowed else AuditSeverity.WARNING

        return await self.log(
            AuditEventType.NETWORK_ACCESS,
            severity,
            agent_id=agent_id,
            details={
                "host": host,
                "port": port,
                "allowed": allowed,
            }
        )

    # === Query methods ===

    async def get_events(
        self,
        agent_id: Optional[str] = None,
        event_type: Optional[AuditEventType] = None,
        severity: Optional[AuditSeverity] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        limit: int = 100
    ) -> list[AuditEvent]:
        """
        Query audit events.

        Args:
            agent_id: Filter by agent
            event_type: Filter by event type
            severity: Filter by minimum severity
            since: Filter events after this time
            until: Filter events before this time
            limit: Maximum results

        Returns:
            List of matching AuditEvents
        """
        if not self._db:
            # Return from buffer
            return self._filter_buffer(
                agent_id, event_type, severity, since, until, limit
            )

        # Build query
        query = "SELECT * FROM audit_events WHERE 1=1"
        params = []

        if agent_id:
            query += " AND agent_id = ?"
            params.append(agent_id)

        if event_type:
            query += " AND event_type = ?"
            params.append(event_type.value)

        if severity:
            min_order = self._severity_order[severity]
            severity_list = [
                s.value for s, order in self._severity_order.items()
                if order >= min_order
            ]
            placeholders = ",".join("?" * len(severity_list))
            query += f" AND severity IN ({placeholders})"
            params.extend(severity_list)

        if since:
            query += " AND timestamp >= ?"
            params.append(since.isoformat())

        if until:
            query += " AND timestamp <= ?"
            params.append(until.isoformat())

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        async with self._db.execute(query, params) as cursor:
            rows = await cursor.fetchall()

        events = []
        for row in rows:
            events.append(AuditEvent(
                event_type=AuditEventType(row[1]),
                severity=AuditSeverity(row[2]),
                agent_id=row[3],
                timestamp=datetime.fromisoformat(row[4]),
                details=json.loads(row[5]) if row[5] else {},
                source=row[6],
                session_id=row[7],
            ))

        return events

    def _filter_buffer(
        self,
        agent_id: Optional[str],
        event_type: Optional[AuditEventType],
        severity: Optional[AuditSeverity],
        since: Optional[datetime],
        until: Optional[datetime],
        limit: int
    ) -> list[AuditEvent]:
        """Filter events from in-memory buffer."""
        results = []

        for event in reversed(self._buffer):
            if agent_id and event.agent_id != agent_id:
                continue
            if event_type and event.event_type != event_type:
                continue
            if severity:
                if self._severity_order[event.severity] < self._severity_order[severity]:
                    continue
            if since and event.timestamp < since:
                continue
            if until and event.timestamp > until:
                continue

            results.append(event)
            if len(results) >= limit:
                break

        return results

    async def get_agent_history(
        self,
        agent_id: str,
        limit: int = 50
    ) -> list[AuditEvent]:
        """Get all audit events for an agent."""
        return await self.get_events(agent_id=agent_id, limit=limit)

    async def get_security_events(
        self,
        since: Optional[datetime] = None,
        limit: int = 100
    ) -> list[AuditEvent]:
        """Get security-related events."""
        security_types = [
            AuditEventType.CAPABILITY_DENIED,
            AuditEventType.POLICY_VIOLATION,
            AuditEventType.TOOL_DENIED,
        ]

        events = []
        for event_type in security_types:
            type_events = await self.get_events(
                event_type=event_type,
                since=since,
                limit=limit
            )
            events.extend(type_events)

        # Sort by timestamp
        events.sort(key=lambda e: e.timestamp, reverse=True)
        return events[:limit]

    def get_stats(self) -> dict:
        """Get audit statistics."""
        return {
            "session_id": self._session_id,
            "total_events": sum(self._event_counts.values()),
            "events_by_type": self._event_counts.copy(),
            "buffer_size": len(self._buffer),
            "handlers_count": len(self._handlers),
        }

    def get_recent_events(self, count: int = 10) -> list[AuditEvent]:
        """Get most recent events from buffer."""
        return list(reversed(self._buffer[-count:]))
