"""
Test Phase 2: Memory and Messaging systems.

Run directly: python3 tests/test_phase2.py
Run with pytest: pytest tests/test_phase2.py
"""

import asyncio
import sys
import os

# Add src to path for direct execution
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

try:
    import pytest
    HAS_PYTEST = True
except ImportError:
    HAS_PYTEST = False

from agent_os.core import (
    MemoryManager, MemoryScope, MemoryEntry,
    MessageBus, Message, Event, MessageType
)
from agent_os.runtime import AgentRuntime
from agent_os.core import AgentConfig


if HAS_PYTEST:
    class TestMemoryManager:
        """Test the Memory Manager."""

        @pytest.fixture
        async def memory(self, tmp_path):
            """Create a memory manager with temp database."""
            db_path = str(tmp_path / "test_memory.db")
            mm = MemoryManager(db_path=db_path)
            await mm.initialize()
            yield mm
            await mm.close()

    async def test_context_memory(self, memory):
        """Test ephemeral context memory."""
        await memory.store("agent1", "task", "test task", MemoryScope.CONTEXT)
        result = await memory.retrieve("agent1", "task", MemoryScope.CONTEXT)
        assert result == "test task"

        # Clear context
        await memory.clear_context("agent1")
        result = await memory.retrieve("agent1", "task", MemoryScope.CONTEXT)
        assert result is None

    async def test_working_memory(self, memory):
        """Test session working memory."""
        await memory.store("agent1", "state", {"step": 1}, MemoryScope.WORKING)
        result = await memory.retrieve("agent1", "state", MemoryScope.WORKING)
        assert result == {"step": 1}

    async def test_shared_memory(self, memory):
        """Test memory sharing between agents."""
        await memory.store("agent1", "data", "shared data", MemoryScope.WORKING)
        await memory.share("agent1", "data", MemoryScope.WORKING)

        # Any agent can access shared memory
        result = await memory.retrieve("agent2", "data", MemoryScope.SHARED)
        assert result == "shared data"

    async def test_long_term_memory(self, memory):
        """Test persistent long-term memory."""
        await memory.store("agent1", "learned", "important fact", MemoryScope.LONG_TERM)
        result = await memory.retrieve("agent1", "learned", MemoryScope.LONG_TERM)
        assert result == "important fact"

    async def test_search(self, memory):
        """Test memory search."""
        await memory.store("agent1", "user_preference_theme", "dark", MemoryScope.WORKING)
        await memory.store("agent1", "user_preference_lang", "en", MemoryScope.WORKING)
        await memory.store("agent1", "other_data", "xyz", MemoryScope.WORKING)

        results = await memory.search("agent1", "user_preference")
        assert len(results) == 2


class TestMessageBus:
    """Test the Message Bus."""

    @pytest.fixture
    def bus(self):
        """Create a message bus."""
        return MessageBus()

    async def test_send_message(self, bus):
        """Test sending a message."""
        bus.register_agent("agent1")
        bus.register_agent("agent2")

        await bus.send("agent1", "agent2", {"action": "hello"})

        # Agent 2 should receive the message
        msg = await bus.receive("agent2", timeout=1.0)
        assert msg is not None
        assert msg.payload == {"action": "hello"}
        assert msg.sender_id == "agent1"

    async def test_request_response(self, bus):
        """Test request/response pattern."""
        bus.register_agent("requester")
        bus.register_agent("responder")

        # Start responder task
        async def responder_task():
            msg = await bus.receive("responder", timeout=5.0)
            if msg:
                await bus.respond(msg, {"answer": 42})

        # Start responder
        asyncio.create_task(responder_task())

        # Send request
        response = await bus.request(
            "requester", "responder",
            {"question": "meaning of life"},
            timeout=5.0
        )

        assert response is not None
        assert response.payload == {"answer": 42}

    async def test_broadcast_event(self, bus):
        """Test event broadcasting."""
        bus.register_agent("publisher")
        bus.register_agent("subscriber1")
        bus.register_agent("subscriber2")

        received = []

        async def handler(event):
            received.append(event)

        bus.subscribe("subscriber1", "data.updated", handler)
        bus.subscribe("subscriber2", "data.updated", handler)

        await bus.broadcast("publisher", "data.updated", {"value": 100})

        # Both subscribers should receive the event
        assert len(received) == 2
        assert all(e.data == {"value": 100} for e in received)

    async def test_wildcard_subscription(self, bus):
        """Test wildcard event subscription."""
        bus.register_agent("publisher")
        bus.register_agent("monitor")

        received = []

        async def handler(event):
            received.append(event)

        # Subscribe to all events
        bus.subscribe("monitor", "*", handler)

        await bus.broadcast("publisher", "event1", {"x": 1})
        await bus.broadcast("publisher", "event2", {"x": 2})

        assert len(received) == 2


class TestRuntimeIntegration:
    """Test memory and messaging integration in runtime."""

    @pytest.fixture
    async def runtime(self, tmp_path):
        """Create a runtime with temp database."""
        db_path = str(tmp_path / "runtime_memory.db")
        rt = AgentRuntime(memory_db_path=db_path)
        await rt.start()
        yield rt
        await rt.stop()

    async def test_runtime_memory(self, runtime):
        """Test memory operations through runtime."""
        await runtime.store_memory("test_agent", "key1", "value1")
        result = await runtime.retrieve_memory("test_agent", "key1")
        assert result == "value1"

    async def test_runtime_stats(self, runtime):
        """Test runtime statistics."""
        stats = runtime.get_stats()
        assert "agents" in stats
        assert "memory" in stats
        assert "messaging" in stats
        assert stats["running"] is True


if __name__ == "__main__":
    # Quick test without pytest
    async def run_tests():
        print("Testing Memory Manager...")
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "test.db")
            memory = MemoryManager(db_path=db_path)
            await memory.initialize()

            # Test context memory
            await memory.store("agent1", "test", "hello", MemoryScope.CONTEXT)
            result = await memory.retrieve("agent1", "test", MemoryScope.CONTEXT)
            assert result == "hello", f"Expected 'hello', got {result}"
            print("  ✓ Context memory works")

            # Test working memory
            await memory.store("agent1", "state", {"x": 1}, MemoryScope.WORKING)
            result = await memory.retrieve("agent1", "state", MemoryScope.WORKING)
            assert result == {"x": 1}
            print("  ✓ Working memory works")

            # Test shared memory
            await memory.share("agent1", "state", MemoryScope.WORKING)
            result = await memory.retrieve("agent2", "state", MemoryScope.SHARED)
            assert result == {"x": 1}
            print("  ✓ Shared memory works")

            # Test long-term memory
            await memory.store("agent1", "fact", "persistent", MemoryScope.LONG_TERM)
            result = await memory.retrieve("agent1", "fact", MemoryScope.LONG_TERM)
            assert result == "persistent"
            print("  ✓ Long-term memory works")

            await memory.close()

        print("\nTesting Message Bus...")
        bus = MessageBus()
        bus.register_agent("agent1")
        bus.register_agent("agent2")

        # Test send/receive
        await bus.send("agent1", "agent2", {"msg": "hello"})
        msg = await bus.receive("agent2", timeout=1.0)
        assert msg is not None
        assert msg.payload == {"msg": "hello"}
        print("  ✓ Send/receive works")

        # Test events
        received = []
        async def handler(event):
            received.append(event)

        bus.subscribe("agent1", "test.event", handler)
        await bus.broadcast("agent2", "test.event", {"data": 123})
        assert len(received) == 1
        assert received[0].data == {"data": 123}
        print("  ✓ Event broadcast works")

        print("\nTesting Runtime Integration...")
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "runtime.db")
            runtime = AgentRuntime(memory_db_path=db_path)
            await runtime.start()

            # Test runtime memory
            await runtime.store_memory("test", "key", "value")
            result = await runtime.retrieve_memory("test", "key")
            assert result == "value"
            print("  ✓ Runtime memory integration works")

            # Test stats
            stats = runtime.get_stats()
            assert "memory" in stats
            assert "messaging" in stats
            print("  ✓ Runtime stats work")

            await runtime.stop()

        print("\n✅ All Phase 2 tests passed!")

    asyncio.run(run_tests())
