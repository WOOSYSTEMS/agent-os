"""
Test Phase 4: Dashboard & API systems.

Run directly: python3 tests/test_phase4.py
Run with pytest: pytest tests/test_phase4.py
"""

import asyncio
import sys
import os
import tempfile

# Add src to path for direct execution
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from agent_os.api import create_app, APIServer
from agent_os.api.websocket import ConnectionManager
from agent_os.runtime import AgentRuntime


class TestConnectionManager:
    """Test the WebSocket Connection Manager."""

    def test_stats(self):
        """Test connection stats."""
        manager = ConnectionManager()
        stats = manager.get_stats()

        assert stats["active_connections"] == 0
        assert stats["topics"] == 0


class TestAPICreation:
    """Test API app creation."""

    async def test_create_app(self, tmp_path):
        """Test creating the FastAPI app."""
        memory_db = str(tmp_path / "memory.db")
        audit_db = str(tmp_path / "audit.db")

        runtime = AgentRuntime(
            memory_db_path=memory_db,
            audit_db_path=audit_db,
        )

        app = create_app(runtime=runtime)

        assert app is not None
        assert app.state.runtime is runtime
        assert app.state.ws_manager is not None

    async def test_api_server_creation(self, tmp_path):
        """Test creating the API server."""
        memory_db = str(tmp_path / "memory.db")
        audit_db = str(tmp_path / "audit.db")

        runtime = AgentRuntime(
            memory_db_path=memory_db,
            audit_db_path=audit_db,
        )

        server = APIServer(host="127.0.0.1", port=8765, runtime=runtime)

        assert server.host == "127.0.0.1"
        assert server.port == 8765
        assert server.runtime is runtime


if __name__ == "__main__":
    async def run_tests():
        print("Testing WebSocket Connection Manager...")

        manager = ConnectionManager()
        stats = manager.get_stats()
        assert stats["active_connections"] == 0
        print("  ✓ Connection manager works")

        print("\nTesting API Creation...")

        with tempfile.TemporaryDirectory() as tmp:
            memory_db = os.path.join(tmp, "memory.db")
            audit_db = os.path.join(tmp, "audit.db")

            runtime = AgentRuntime(
                memory_db_path=memory_db,
                audit_db_path=audit_db,
            )

            # Test app creation
            app = create_app(runtime=runtime)
            assert app is not None
            assert app.state.runtime is runtime
            print("  ✓ App creation works")

            # Test server creation
            server = APIServer(host="127.0.0.1", port=8765, runtime=runtime)
            assert server.host == "127.0.0.1"
            assert server.port == 8765
            print("  ✓ Server creation works")

        print("\nTesting API Endpoints (using TestClient)...")

        try:
            from fastapi.testclient import TestClient

            with tempfile.TemporaryDirectory() as tmp:
                memory_db = os.path.join(tmp, "memory.db")
                audit_db = os.path.join(tmp, "audit.db")

                runtime = AgentRuntime(
                    memory_db_path=memory_db,
                    audit_db_path=audit_db,
                )
                await runtime.start()

                app = create_app(runtime=runtime)

                with TestClient(app) as client:
                    # Test health endpoint
                    response = client.get("/api/v1/health")
                    assert response.status_code == 200
                    data = response.json()
                    assert data["status"] == "healthy"
                    print("  ✓ Health endpoint works")

                    # Test stats endpoint
                    response = client.get("/api/v1/stats")
                    assert response.status_code == 200
                    data = response.json()
                    assert "agents" in data
                    assert "memory" in data
                    print("  ✓ Stats endpoint works")

                    # Test agents list
                    response = client.get("/api/v1/agents")
                    assert response.status_code == 200
                    assert isinstance(response.json(), list)
                    print("  ✓ Agents list endpoint works")

                    # Test tools list
                    response = client.get("/api/v1/tools")
                    assert response.status_code == 200
                    tools = response.json()
                    assert len(tools) > 0
                    print("  ✓ Tools list endpoint works")

                    # Test info endpoint
                    response = client.get("/api/v1/info")
                    assert response.status_code == 200
                    data = response.json()
                    assert data["name"] == "Agent OS"
                    print("  ✓ Info endpoint works")

                    # Test root page
                    response = client.get("/")
                    assert response.status_code == 200
                    assert "Agent OS" in response.text
                    print("  ✓ Root page works")

                    # Test dashboard page
                    response = client.get("/dashboard")
                    assert response.status_code == 200
                    assert "Agent OS Dashboard" in response.text
                    print("  ✓ Dashboard page works")

                await runtime.stop()

        except ImportError:
            print("  ⚠ Skipping endpoint tests (httpx not installed)")

        print("\n✅ All Phase 4 tests passed!")

    asyncio.run(run_tests())
