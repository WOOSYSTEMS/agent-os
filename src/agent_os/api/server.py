"""
API Server for Agent OS.

Provides REST API and WebSocket interface for:
- Runtime control
- Agent management
- Real-time monitoring
- Dashboard data
"""

import asyncio
from contextlib import asynccontextmanager
from typing import Optional
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import structlog

from ..runtime import AgentRuntime
from ..core import Event
from .routes import router
from .websocket import ConnectionManager

logger = structlog.get_logger()


def create_app(
    runtime: Optional[AgentRuntime] = None,
    title: str = "Agent OS API",
    version: str = "0.1.0",
) -> FastAPI:
    """
    Create the FastAPI application.

    Args:
        runtime: Optional runtime instance (created if not provided)
        title: API title
        version: API version

    Returns:
        Configured FastAPI app
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Manage runtime lifecycle."""
        # Startup
        if not app.state.runtime._running:
            await app.state.runtime.start()
        logger.info("api_server_started")
        yield
        # Shutdown
        await app.state.runtime.stop()
        logger.info("api_server_stopped")

    app = FastAPI(
        title=title,
        version=version,
        description="REST API for Agent OS - An operating system for AI agents",
        lifespan=lifespan,
    )

    # Store runtime in app state
    app.state.runtime = runtime or AgentRuntime()
    app.state.ws_manager = ConnectionManager()

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routes
    app.include_router(router, prefix="/api/v1")

    # WebSocket endpoint
    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        """WebSocket for real-time updates."""
        await app.state.ws_manager.connect(websocket)
        try:
            while True:
                # Keep connection alive and receive messages
                data = await websocket.receive_text()
                # Echo back for now, can be extended for commands
                await websocket.send_json({"type": "ack", "data": data})
        except WebSocketDisconnect:
            app.state.ws_manager.disconnect(websocket)

    # Register event handler to broadcast to WebSocket clients
    async def broadcast_event(event: Event):
        """Broadcast runtime events to WebSocket clients."""
        await app.state.ws_manager.broadcast({
            "type": "event",
            "event_type": event.type,
            "agent_id": event.agent_id,
            "data": event.data,
            "timestamp": event.timestamp.isoformat(),
        })

    app.state.runtime.on_event(broadcast_event)

    # Root endpoint
    @app.get("/", response_class=HTMLResponse)
    async def root():
        """Root endpoint with links."""
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Agent OS</title>
            <style>
                body { font-family: system-ui, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; }
                h1 { color: #2563eb; }
                a { color: #2563eb; text-decoration: none; }
                a:hover { text-decoration: underline; }
                .card { background: #f1f5f9; padding: 20px; border-radius: 8px; margin: 20px 0; }
                code { background: #e2e8f0; padding: 2px 6px; border-radius: 4px; }
            </style>
        </head>
        <body>
            <h1>Agent OS</h1>
            <p>An operating system for AI agents.</p>

            <div class="card">
                <h3>Quick Links</h3>
                <ul>
                    <li><a href="/api/v1/health">Health Check</a></li>
                    <li><a href="/api/v1/stats">Runtime Stats</a></li>
                    <li><a href="/api/v1/agents">List Agents</a></li>
                    <li><a href="/docs">API Documentation</a></li>
                    <li><a href="/dashboard">Dashboard</a></li>
                </ul>
            </div>

            <div class="card">
                <h3>WebSocket</h3>
                <p>Connect to <code>ws://localhost:8000/ws</code> for real-time updates.</p>
            </div>
        </body>
        </html>
        """

    # Dashboard endpoint
    @app.get("/dashboard", response_class=HTMLResponse)
    async def dashboard():
        """Serve the dashboard."""
        return get_dashboard_html()

    return app


def get_dashboard_html() -> str:
    """Return the dashboard HTML."""
    return '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Agent OS Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/alpinejs@3.x.x/dist/cdn.min.js" defer></script>
    <style>
        [x-cloak] { display: none !important; }
        .pulse { animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: .5; } }
    </style>
</head>
<body class="bg-gray-900 text-white min-h-screen" x-data="dashboard()">
    <!-- Header -->
    <header class="bg-gray-800 border-b border-gray-700 px-6 py-4">
        <div class="flex items-center justify-between">
            <div class="flex items-center space-x-4">
                <h1 class="text-2xl font-bold text-blue-400">Agent OS</h1>
                <span class="text-sm text-gray-400">Dashboard</span>
            </div>
            <div class="flex items-center space-x-4">
                <span class="flex items-center" :class="connected ? 'text-green-400' : 'text-red-400'">
                    <span class="w-2 h-2 rounded-full mr-2" :class="connected ? 'bg-green-400' : 'bg-red-400 pulse'"></span>
                    <span x-text="connected ? 'Connected' : 'Disconnected'"></span>
                </span>
                <button @click="refreshStats()" class="px-3 py-1 bg-blue-600 hover:bg-blue-700 rounded text-sm">
                    Refresh
                </button>
            </div>
        </div>
    </header>

    <main class="p-6">
        <!-- Stats Grid -->
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
            <!-- Agents Card -->
            <div class="bg-gray-800 rounded-lg p-6 border border-gray-700">
                <div class="flex items-center justify-between">
                    <h3 class="text-gray-400 text-sm font-medium">Total Agents</h3>
                    <span class="text-blue-400">
                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"></path>
                        </svg>
                    </span>
                </div>
                <p class="text-3xl font-bold mt-2" x-text="stats.agents?.total || 0"></p>
            </div>

            <!-- Memory Card -->
            <div class="bg-gray-800 rounded-lg p-6 border border-gray-700">
                <div class="flex items-center justify-between">
                    <h3 class="text-gray-400 text-sm font-medium">Memory Entries</h3>
                    <span class="text-purple-400">
                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z"></path>
                        </svg>
                    </span>
                </div>
                <p class="text-3xl font-bold mt-2" x-text="(stats.memory?.working_entries || 0) + (stats.memory?.context_entries || 0)"></p>
            </div>

            <!-- Messages Card -->
            <div class="bg-gray-800 rounded-lg p-6 border border-gray-700">
                <div class="flex items-center justify-between">
                    <h3 class="text-gray-400 text-sm font-medium">Pending Requests</h3>
                    <span class="text-green-400">
                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"></path>
                        </svg>
                    </span>
                </div>
                <p class="text-3xl font-bold mt-2" x-text="stats.messaging?.pending_requests || 0"></p>
            </div>

            <!-- Audit Events Card -->
            <div class="bg-gray-800 rounded-lg p-6 border border-gray-700">
                <div class="flex items-center justify-between">
                    <h3 class="text-gray-400 text-sm font-medium">Audit Events</h3>
                    <span class="text-yellow-400">
                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"></path>
                        </svg>
                    </span>
                </div>
                <p class="text-3xl font-bold mt-2" x-text="stats.audit?.total_events || 0"></p>
            </div>
        </div>

        <!-- Main Content Grid -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <!-- Agents List -->
            <div class="bg-gray-800 rounded-lg border border-gray-700">
                <div class="px-6 py-4 border-b border-gray-700 flex justify-between items-center">
                    <h2 class="text-lg font-semibold">Agents</h2>
                    <button @click="showSpawnModal = true" class="px-3 py-1 bg-green-600 hover:bg-green-700 rounded text-sm">
                        + Spawn Agent
                    </button>
                </div>
                <div class="p-6">
                    <template x-if="agents.length === 0">
                        <p class="text-gray-500 text-center py-8">No agents running</p>
                    </template>
                    <div class="space-y-3">
                        <template x-for="agent in agents" :key="agent.id">
                            <div class="bg-gray-700 rounded-lg p-4">
                                <div class="flex items-center justify-between">
                                    <div>
                                        <span class="font-mono text-sm text-blue-400" x-text="agent.id"></span>
                                        <span class="ml-2 px-2 py-0.5 text-xs rounded"
                                              :class="{
                                                  'bg-green-900 text-green-300': agent.state === 'running',
                                                  'bg-yellow-900 text-yellow-300': agent.state === 'pending',
                                                  'bg-blue-900 text-blue-300': agent.state === 'completed',
                                                  'bg-red-900 text-red-300': agent.state === 'failed',
                                                  'bg-gray-600 text-gray-300': agent.state === 'terminated'
                                              }"
                                              x-text="agent.state"></span>
                                    </div>
                                    <button @click="terminateAgent(agent.id)" class="text-red-400 hover:text-red-300 text-sm">
                                        Terminate
                                    </button>
                                </div>
                                <p class="text-gray-400 text-sm mt-2 truncate" x-text="agent.goal"></p>
                                <div class="flex items-center space-x-4 mt-2 text-xs text-gray-500">
                                    <span>Model: <span x-text="agent.model"></span></span>
                                    <span>Iterations: <span x-text="agent.iterations"></span></span>
                                </div>
                            </div>
                        </template>
                    </div>
                </div>
            </div>

            <!-- Events Log -->
            <div class="bg-gray-800 rounded-lg border border-gray-700">
                <div class="px-6 py-4 border-b border-gray-700 flex justify-between items-center">
                    <h2 class="text-lg font-semibold">Live Events</h2>
                    <button @click="events = []" class="text-gray-400 hover:text-white text-sm">Clear</button>
                </div>
                <div class="p-4 h-96 overflow-y-auto font-mono text-sm">
                    <template x-if="events.length === 0">
                        <p class="text-gray-500 text-center py-8">Waiting for events...</p>
                    </template>
                    <template x-for="(event, index) in events" :key="index">
                        <div class="py-2 border-b border-gray-700 last:border-0">
                            <div class="flex items-center space-x-2">
                                <span class="text-gray-500 text-xs" x-text="formatTime(event.timestamp)"></span>
                                <span class="px-1.5 py-0.5 text-xs rounded"
                                      :class="{
                                          'bg-blue-900 text-blue-300': event.event_type.includes('agent'),
                                          'bg-green-900 text-green-300': event.event_type.includes('tool'),
                                          'bg-yellow-900 text-yellow-300': event.event_type.includes('runtime'),
                                          'bg-purple-900 text-purple-300': event.event_type.includes('security')
                                      }"
                                      x-text="event.event_type"></span>
                            </div>
                            <p class="text-gray-400 text-xs mt-1" x-text="JSON.stringify(event.data)"></p>
                        </div>
                    </template>
                </div>
            </div>
        </div>
    </main>

    <!-- Spawn Agent Modal -->
    <div x-show="showSpawnModal" x-cloak class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
        <div class="bg-gray-800 rounded-lg p-6 w-full max-w-md border border-gray-700" @click.away="showSpawnModal = false">
            <h3 class="text-xl font-semibold mb-4">Spawn New Agent</h3>
            <form @submit.prevent="spawnAgent()">
                <div class="mb-4">
                    <label class="block text-sm text-gray-400 mb-2">Goal</label>
                    <textarea x-model="newAgent.goal" rows="3" class="w-full bg-gray-700 rounded px-3 py-2 text-white" placeholder="Describe what the agent should accomplish..."></textarea>
                </div>
                <div class="mb-4">
                    <label class="block text-sm text-gray-400 mb-2">Model</label>
                    <select x-model="newAgent.model" class="w-full bg-gray-700 rounded px-3 py-2 text-white">
                        <option value="claude-sonnet-4-20250514">Claude Sonnet 4</option>
                        <option value="claude-3-5-sonnet-20241022">Claude 3.5 Sonnet</option>
                        <option value="claude-3-haiku-20240307">Claude 3 Haiku</option>
                    </select>
                </div>
                <div class="flex justify-end space-x-3">
                    <button type="button" @click="showSpawnModal = false" class="px-4 py-2 text-gray-400 hover:text-white">Cancel</button>
                    <button type="submit" class="px-4 py-2 bg-green-600 hover:bg-green-700 rounded">Spawn</button>
                </div>
            </form>
        </div>
    </div>

    <script>
        function dashboard() {
            return {
                connected: false,
                stats: {},
                agents: [],
                events: [],
                showSpawnModal: false,
                newAgent: {
                    goal: '',
                    model: 'claude-sonnet-4-20250514'
                },
                ws: null,

                init() {
                    this.connectWebSocket();
                    this.refreshStats();
                    this.refreshAgents();
                    // Auto-refresh every 5 seconds
                    setInterval(() => {
                        this.refreshStats();
                        this.refreshAgents();
                    }, 5000);
                },

                connectWebSocket() {
                    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                    this.ws = new WebSocket(`${protocol}//${window.location.host}/ws`);

                    this.ws.onopen = () => {
                        this.connected = true;
                        console.log('WebSocket connected');
                    };

                    this.ws.onclose = () => {
                        this.connected = false;
                        console.log('WebSocket disconnected');
                        // Reconnect after 3 seconds
                        setTimeout(() => this.connectWebSocket(), 3000);
                    };

                    this.ws.onmessage = (event) => {
                        const data = JSON.parse(event.data);
                        if (data.type === 'event') {
                            this.events.unshift(data);
                            // Keep only last 50 events
                            if (this.events.length > 50) {
                                this.events = this.events.slice(0, 50);
                            }
                            // Refresh agents on agent events
                            if (data.event_type.startsWith('agent.')) {
                                this.refreshAgents();
                            }
                        }
                    };
                },

                async refreshStats() {
                    try {
                        const response = await fetch('/api/v1/stats');
                        this.stats = await response.json();
                    } catch (e) {
                        console.error('Failed to fetch stats:', e);
                    }
                },

                async refreshAgents() {
                    try {
                        const response = await fetch('/api/v1/agents');
                        this.agents = await response.json();
                    } catch (e) {
                        console.error('Failed to fetch agents:', e);
                    }
                },

                async spawnAgent() {
                    try {
                        const response = await fetch('/api/v1/agents', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(this.newAgent)
                        });
                        if (response.ok) {
                            this.showSpawnModal = false;
                            this.newAgent.goal = '';
                            this.refreshAgents();
                        }
                    } catch (e) {
                        console.error('Failed to spawn agent:', e);
                    }
                },

                async terminateAgent(agentId) {
                    try {
                        await fetch(`/api/v1/agents/${agentId}/terminate`, { method: 'POST' });
                        this.refreshAgents();
                    } catch (e) {
                        console.error('Failed to terminate agent:', e);
                    }
                },

                formatTime(timestamp) {
                    return new Date(timestamp).toLocaleTimeString();
                }
            };
        }
    </script>
</body>
</html>'''


class APIServer:
    """
    API Server wrapper for easy management.

    Example:
        server = APIServer()
        await server.start()
        # ... server runs ...
        await server.stop()
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8000,
        runtime: Optional[AgentRuntime] = None,
    ):
        self.host = host
        self.port = port
        self.runtime = runtime or AgentRuntime()
        self.app = create_app(runtime=self.runtime)
        self._server = None
        self._task = None

    async def start(self) -> None:
        """Start the API server."""
        config = uvicorn.Config(
            self.app,
            host=self.host,
            port=self.port,
            log_level="info",
        )
        self._server = uvicorn.Server(config)
        self._task = asyncio.create_task(self._server.serve())
        logger.info("api_server_starting", host=self.host, port=self.port)

    async def stop(self) -> None:
        """Stop the API server."""
        if self._server:
            self._server.should_exit = True
            if self._task:
                await self._task
        logger.info("api_server_stopped")

    def run(self) -> None:
        """Run the server (blocking)."""
        uvicorn.run(self.app, host=self.host, port=self.port)
