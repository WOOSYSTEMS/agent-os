"""
Capability Manager for Agent OS.

Handles permission checking and capability token management.
Implements capability-based security model.
"""

from datetime import datetime
from typing import Optional
from .models import Capability, CapabilityCheck, Event
import structlog

logger = structlog.get_logger()


class CapabilityManager:
    """
    Manages capabilities (permissions) for agents.

    Each agent has a set of capabilities that define what it can do.
    All tool executions must pass capability checks.
    """

    def __init__(self):
        # agent_id -> list of capabilities
        self._agent_capabilities: dict[str, list[Capability]] = {}
        # Audit log of all checks
        self._audit_log: list[Event] = []

    def grant(self, agent_id: str, capability: Capability) -> None:
        """Grant a capability to an agent."""
        if agent_id not in self._agent_capabilities:
            self._agent_capabilities[agent_id] = []

        self._agent_capabilities[agent_id].append(capability)

        self._log_event("capability.granted", agent_id, {
            "capability": str(capability)
        })

        logger.info("capability_granted",
                   agent_id=agent_id,
                   capability=str(capability))

    def grant_from_string(self, agent_id: str, capability_string: str) -> None:
        """Grant a capability from a string like 'file:/home/*:read'."""
        capability = Capability.parse(capability_string)
        self.grant(agent_id, capability)

    def grant_many(self, agent_id: str, capability_strings: list[str]) -> None:
        """Grant multiple capabilities from strings."""
        for cap_str in capability_strings:
            self.grant_from_string(agent_id, cap_str)

    def revoke(self, agent_id: str, capability: Capability) -> bool:
        """Revoke a specific capability from an agent."""
        if agent_id not in self._agent_capabilities:
            return False

        caps = self._agent_capabilities[agent_id]
        cap_str = str(capability)

        for i, c in enumerate(caps):
            if str(c) == cap_str:
                caps.pop(i)
                self._log_event("capability.revoked", agent_id, {
                    "capability": cap_str
                })
                logger.info("capability_revoked",
                           agent_id=agent_id,
                           capability=cap_str)
                return True

        return False

    def revoke_all(self, agent_id: str) -> None:
        """Revoke all capabilities from an agent."""
        if agent_id in self._agent_capabilities:
            count = len(self._agent_capabilities[agent_id])
            del self._agent_capabilities[agent_id]
            self._log_event("capability.revoked_all", agent_id, {
                "count": count
            })
            logger.info("capabilities_revoked_all",
                       agent_id=agent_id,
                       count=count)

    def check(
        self,
        agent_id: str,
        resource: str,
        path: str,
        action: str
    ) -> CapabilityCheck:
        """
        Check if an agent has capability for an action.

        Args:
            agent_id: The agent requesting access
            resource: Resource type (file, http, shell, etc.)
            path: Specific path or target
            action: Action to perform (read, write, execute, etc.)

        Returns:
            CapabilityCheck with allowed status and reason
        """
        caps = self._agent_capabilities.get(agent_id, [])

        for cap in caps:
            if cap.matches(resource, path, action):
                result = CapabilityCheck(
                    allowed=True,
                    capability=cap,
                    reason=f"Granted by capability: {cap}"
                )
                self._log_event("capability.check.allowed", agent_id, {
                    "resource": resource,
                    "path": path,
                    "action": action,
                    "capability": str(cap)
                })
                return result

        # No matching capability found
        result = CapabilityCheck(
            allowed=False,
            reason=f"No capability grants {resource}:{path}:{action}"
        )
        self._log_event("capability.check.denied", agent_id, {
            "resource": resource,
            "path": path,
            "action": action,
        })
        logger.warning("capability_denied",
                      agent_id=agent_id,
                      resource=resource,
                      path=path,
                      action=action)
        return result

    def list_capabilities(self, agent_id: str) -> list[Capability]:
        """List all capabilities for an agent."""
        return self._agent_capabilities.get(agent_id, []).copy()

    def get_audit_log(
        self,
        agent_id: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 100
    ) -> list[Event]:
        """Get audit log entries, optionally filtered."""
        logs = self._audit_log

        if agent_id:
            logs = [e for e in logs if e.agent_id == agent_id]
        if event_type:
            logs = [e for e in logs if e.type == event_type]

        return logs[-limit:]

    def _log_event(self, event_type: str, agent_id: str, data: dict) -> None:
        """Log an event to the audit log."""
        event = Event(
            type=event_type,
            agent_id=agent_id,
            data=data,
        )
        self._audit_log.append(event)

        # Keep audit log bounded
        if len(self._audit_log) > 10000:
            self._audit_log = self._audit_log[-5000:]


# Default capability sets for common agent types

DEFAULT_CAPABILITIES = {
    "minimal": [
        # Can only read its own memory
    ],
    "basic": [
        "file:*:read",
        "http:*:request",
    ],
    "standard": [
        "file:*:read,write",
        "http:*:request",
        "shell:*:execute",
    ],
    "full": [
        "file:*:*",
        "http:*:*",
        "shell:*:*",
        "agent:*:spawn",
    ],
}


def get_default_capabilities(level: str = "basic") -> list[str]:
    """Get a default capability set by level."""
    return DEFAULT_CAPABILITIES.get(level, DEFAULT_CAPABILITIES["basic"])
