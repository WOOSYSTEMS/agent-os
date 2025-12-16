"""
Memory Manager for Agent OS.

Provides unified memory across different scopes:
- Context: Current conversation/task (ephemeral)
- Working: Current session state
- Long-term: Persistent across sessions (SQLite)
- Shared: Accessible by multiple agents
"""

import json
import asyncio
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pathlib import Path
import aiosqlite
import structlog

logger = structlog.get_logger()


class MemoryScope(str, Enum):
    """Memory scope levels."""
    CONTEXT = "context"    # Ephemeral, current task only
    WORKING = "working"    # Session state, cleared on restart
    LONG_TERM = "long_term"  # Persistent, survives restarts
    SHARED = "shared"      # Accessible by multiple agents


class MemoryEntry:
    """A single memory entry."""

    def __init__(
        self,
        key: str,
        value: Any,
        scope: MemoryScope,
        agent_id: str,
        metadata: Optional[dict] = None,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None
    ):
        self.key = key
        self.value = value
        self.scope = scope
        self.agent_id = agent_id
        self.metadata = metadata or {}
        self.created_at = created_at or datetime.now()
        self.updated_at = updated_at or datetime.now()

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "value": self.value,
            "scope": self.scope.value,
            "agent_id": self.agent_id,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class MemoryManager:
    """
    Unified memory manager for all agents.

    Provides:
    - Key-value storage with scoping
    - Persistence via SQLite for long-term memory
    - Memory sharing between agents
    - Search and retrieval
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or str(Path.home() / ".agent-os" / "memory.db")

        # In-memory stores for ephemeral data
        self._context: dict[str, dict[str, MemoryEntry]] = {}  # agent_id -> key -> entry
        self._working: dict[str, dict[str, MemoryEntry]] = {}
        self._shared: dict[str, MemoryEntry] = {}  # key -> entry (no agent_id scoping)

        # SQLite connection for long-term storage
        self._db: Optional[aiosqlite.Connection] = None
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the memory manager and database."""
        if self._initialized:
            return

        # Create directory if needed
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        # Connect to SQLite
        self._db = await aiosqlite.connect(self.db_path)

        # Create tables
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                scope TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                metadata TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(key, scope, agent_id)
            )
        """)

        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_memories_agent
            ON memories(agent_id, scope)
        """)

        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_memories_key
            ON memories(key)
        """)

        await self._db.commit()
        self._initialized = True
        logger.info("memory_manager_initialized", db_path=self.db_path)

    async def close(self) -> None:
        """Close the database connection."""
        if self._db:
            await self._db.close()
            self._db = None
        self._initialized = False

    async def store(
        self,
        agent_id: str,
        key: str,
        value: Any,
        scope: MemoryScope = MemoryScope.WORKING,
        metadata: Optional[dict] = None
    ) -> None:
        """
        Store a value in memory.

        Args:
            agent_id: The agent storing the value
            key: Key to store under
            value: Value to store (will be JSON serialized for persistence)
            scope: Memory scope
            metadata: Optional metadata
        """
        entry = MemoryEntry(
            key=key,
            value=value,
            scope=scope,
            agent_id=agent_id,
            metadata=metadata
        )

        if scope == MemoryScope.CONTEXT:
            if agent_id not in self._context:
                self._context[agent_id] = {}
            self._context[agent_id][key] = entry

        elif scope == MemoryScope.WORKING:
            if agent_id not in self._working:
                self._working[agent_id] = {}
            self._working[agent_id][key] = entry

        elif scope == MemoryScope.SHARED:
            self._shared[key] = entry

        elif scope == MemoryScope.LONG_TERM:
            await self._store_persistent(entry)

        logger.debug("memory_stored",
                    agent_id=agent_id,
                    key=key,
                    scope=scope.value)

    async def _store_persistent(self, entry: MemoryEntry) -> None:
        """Store entry in SQLite."""
        if not self._db:
            await self.initialize()

        value_json = json.dumps(entry.value)
        metadata_json = json.dumps(entry.metadata)

        await self._db.execute("""
            INSERT OR REPLACE INTO memories
            (key, value, scope, agent_id, metadata, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            entry.key,
            value_json,
            entry.scope.value,
            entry.agent_id,
            metadata_json,
            entry.created_at.isoformat(),
            datetime.now().isoformat()
        ))
        await self._db.commit()

    async def retrieve(
        self,
        agent_id: str,
        key: str,
        scope: MemoryScope = MemoryScope.WORKING
    ) -> Optional[Any]:
        """
        Retrieve a value from memory.

        Args:
            agent_id: The agent retrieving
            key: Key to look up
            scope: Memory scope to search

        Returns:
            The value if found, None otherwise
        """
        entry = await self._get_entry(agent_id, key, scope)
        return entry.value if entry else None

    async def _get_entry(
        self,
        agent_id: str,
        key: str,
        scope: MemoryScope
    ) -> Optional[MemoryEntry]:
        """Get the full memory entry."""
        if scope == MemoryScope.CONTEXT:
            return self._context.get(agent_id, {}).get(key)

        elif scope == MemoryScope.WORKING:
            return self._working.get(agent_id, {}).get(key)

        elif scope == MemoryScope.SHARED:
            return self._shared.get(key)

        elif scope == MemoryScope.LONG_TERM:
            return await self._retrieve_persistent(agent_id, key)

        return None

    async def _retrieve_persistent(
        self,
        agent_id: str,
        key: str
    ) -> Optional[MemoryEntry]:
        """Retrieve from SQLite."""
        if not self._db:
            await self.initialize()

        async with self._db.execute("""
            SELECT key, value, scope, agent_id, metadata, created_at, updated_at
            FROM memories
            WHERE key = ? AND agent_id = ? AND scope = ?
        """, (key, agent_id, MemoryScope.LONG_TERM.value)) as cursor:
            row = await cursor.fetchone()

        if not row:
            return None

        return MemoryEntry(
            key=row[0],
            value=json.loads(row[1]),
            scope=MemoryScope(row[2]),
            agent_id=row[3],
            metadata=json.loads(row[4]) if row[4] else {},
            created_at=datetime.fromisoformat(row[5]),
            updated_at=datetime.fromisoformat(row[6])
        )

    async def delete(
        self,
        agent_id: str,
        key: str,
        scope: MemoryScope = MemoryScope.WORKING
    ) -> bool:
        """Delete a memory entry."""
        if scope == MemoryScope.CONTEXT:
            if agent_id in self._context and key in self._context[agent_id]:
                del self._context[agent_id][key]
                return True

        elif scope == MemoryScope.WORKING:
            if agent_id in self._working and key in self._working[agent_id]:
                del self._working[agent_id][key]
                return True

        elif scope == MemoryScope.SHARED:
            if key in self._shared:
                del self._shared[key]
                return True

        elif scope == MemoryScope.LONG_TERM:
            if not self._db:
                await self.initialize()
            cursor = await self._db.execute("""
                DELETE FROM memories
                WHERE key = ? AND agent_id = ? AND scope = ?
            """, (key, agent_id, scope.value))
            await self._db.commit()
            return cursor.rowcount > 0

        return False

    async def list_keys(
        self,
        agent_id: str,
        scope: MemoryScope = MemoryScope.WORKING
    ) -> list[str]:
        """List all keys for an agent in a scope."""
        if scope == MemoryScope.CONTEXT:
            return list(self._context.get(agent_id, {}).keys())

        elif scope == MemoryScope.WORKING:
            return list(self._working.get(agent_id, {}).keys())

        elif scope == MemoryScope.SHARED:
            return list(self._shared.keys())

        elif scope == MemoryScope.LONG_TERM:
            if not self._db:
                await self.initialize()
            async with self._db.execute("""
                SELECT key FROM memories
                WHERE agent_id = ? AND scope = ?
            """, (agent_id, scope.value)) as cursor:
                rows = await cursor.fetchall()
            return [row[0] for row in rows]

        return []

    async def search(
        self,
        agent_id: str,
        query: str,
        scope: Optional[MemoryScope] = None,
        limit: int = 10
    ) -> list[MemoryEntry]:
        """
        Search memories by key pattern.

        Args:
            agent_id: Agent to search for
            query: Key pattern (supports % wildcard)
            scope: Optional scope filter
            limit: Max results

        Returns:
            List of matching entries
        """
        results = []

        # Search in-memory stores
        if scope in (None, MemoryScope.CONTEXT):
            for key, entry in self._context.get(agent_id, {}).items():
                if query in key:
                    results.append(entry)

        if scope in (None, MemoryScope.WORKING):
            for key, entry in self._working.get(agent_id, {}).items():
                if query in key:
                    results.append(entry)

        if scope in (None, MemoryScope.SHARED):
            for key, entry in self._shared.items():
                if query in key:
                    results.append(entry)

        # Search persistent store
        if scope in (None, MemoryScope.LONG_TERM):
            if not self._db:
                await self.initialize()

            like_query = f"%{query}%"
            async with self._db.execute("""
                SELECT key, value, scope, agent_id, metadata, created_at, updated_at
                FROM memories
                WHERE agent_id = ? AND key LIKE ?
                LIMIT ?
            """, (agent_id, like_query, limit)) as cursor:
                rows = await cursor.fetchall()

            for row in rows:
                results.append(MemoryEntry(
                    key=row[0],
                    value=json.loads(row[1]),
                    scope=MemoryScope(row[2]),
                    agent_id=row[3],
                    metadata=json.loads(row[4]) if row[4] else {},
                    created_at=datetime.fromisoformat(row[5]),
                    updated_at=datetime.fromisoformat(row[6])
                ))

        return results[:limit]

    async def clear_agent(self, agent_id: str) -> None:
        """Clear all memory for an agent (except long-term)."""
        if agent_id in self._context:
            del self._context[agent_id]
        if agent_id in self._working:
            del self._working[agent_id]
        logger.info("agent_memory_cleared", agent_id=agent_id)

    async def clear_context(self, agent_id: str) -> None:
        """Clear only context memory for an agent."""
        if agent_id in self._context:
            del self._context[agent_id]

    async def share(
        self,
        from_agent: str,
        key: str,
        from_scope: MemoryScope = MemoryScope.WORKING
    ) -> bool:
        """
        Share a memory entry to the shared scope.

        Args:
            from_agent: Agent sharing the memory
            key: Key to share
            from_scope: Source scope

        Returns:
            True if shared successfully
        """
        entry = await self._get_entry(from_agent, key, from_scope)
        if not entry:
            return False

        # Copy to shared scope
        shared_entry = MemoryEntry(
            key=key,
            value=entry.value,
            scope=MemoryScope.SHARED,
            agent_id=from_agent,  # Track who shared it
            metadata={
                **entry.metadata,
                "shared_by": from_agent,
                "shared_at": datetime.now().isoformat()
            }
        )
        self._shared[key] = shared_entry

        logger.info("memory_shared",
                   agent_id=from_agent,
                   key=key)
        return True

    def get_stats(self) -> dict:
        """Get memory statistics."""
        context_count = sum(len(v) for v in self._context.values())
        working_count = sum(len(v) for v in self._working.values())
        shared_count = len(self._shared)

        return {
            "context_entries": context_count,
            "working_entries": working_count,
            "shared_entries": shared_count,
            "agents_with_context": len(self._context),
            "agents_with_working": len(self._working),
        }
