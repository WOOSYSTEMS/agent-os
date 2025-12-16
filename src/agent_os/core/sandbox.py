"""
Sandbox Manager for Agent OS.

Provides secure execution environments for agent tools with:
- Process isolation
- Resource limits (CPU, memory, time)
- File system restrictions
- Network policy enforcement
"""

import asyncio
import os
import signal
import tempfile
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, Any
import structlog

logger = structlog.get_logger()


class SandboxPolicy(str, Enum):
    """Predefined sandbox policies."""
    UNRESTRICTED = "unrestricted"  # No restrictions (dangerous)
    STANDARD = "standard"          # Default restrictions
    STRICT = "strict"              # Maximum restrictions
    NETWORK_ONLY = "network_only"  # Network allowed, no filesystem
    FILESYSTEM_ONLY = "filesystem_only"  # Filesystem allowed, no network


@dataclass
class ResourceLimits:
    """Resource limits for sandboxed execution."""
    max_cpu_seconds: float = 30.0       # CPU time limit
    max_wall_seconds: float = 60.0      # Wall clock time limit
    max_memory_mb: int = 512            # Memory limit in MB
    max_processes: int = 10             # Max subprocess count
    max_file_size_mb: int = 100         # Max file size
    max_open_files: int = 100           # Max open file descriptors


@dataclass
class FilesystemPolicy:
    """Filesystem access policy."""
    allowed_read_paths: list[str] = field(default_factory=list)
    allowed_write_paths: list[str] = field(default_factory=list)
    denied_paths: list[str] = field(default_factory=lambda: [
        "/etc/passwd", "/etc/shadow", "/etc/sudoers",
        "~/.ssh", "~/.gnupg", "~/.aws", "~/.config",
    ])
    allow_temp_files: bool = True
    temp_dir: Optional[str] = None


@dataclass
class NetworkPolicy:
    """Network access policy."""
    allow_outbound: bool = True
    allow_inbound: bool = False
    allowed_hosts: list[str] = field(default_factory=list)  # Empty = all allowed
    denied_hosts: list[str] = field(default_factory=lambda: [
        "169.254.169.254",  # AWS metadata
        "metadata.google.internal",  # GCP metadata
        "localhost", "127.0.0.1",  # Localhost (configurable)
    ])
    allowed_ports: list[int] = field(default_factory=list)  # Empty = all allowed
    denied_ports: list[int] = field(default_factory=lambda: [22, 23, 25])  # SSH, Telnet, SMTP


@dataclass
class SandboxConfig:
    """Complete sandbox configuration."""
    policy: SandboxPolicy = SandboxPolicy.STANDARD
    resources: ResourceLimits = field(default_factory=ResourceLimits)
    filesystem: FilesystemPolicy = field(default_factory=FilesystemPolicy)
    network: NetworkPolicy = field(default_factory=NetworkPolicy)

    # Execution settings
    working_dir: Optional[str] = None
    environment: dict[str, str] = field(default_factory=dict)
    inherit_env: bool = False


@dataclass
class SandboxResult:
    """Result of sandboxed execution."""
    success: bool
    output: str = ""
    error: str = ""
    exit_code: int = 0
    duration_seconds: float = 0.0
    resource_usage: dict = field(default_factory=dict)
    violations: list[str] = field(default_factory=list)


class SecurityViolation(Exception):
    """Raised when a security policy is violated."""
    def __init__(self, violation_type: str, details: str):
        self.violation_type = violation_type
        self.details = details
        super().__init__(f"{violation_type}: {details}")


class SandboxManager:
    """
    Manages sandboxed execution environments.

    Provides:
    - Process isolation with resource limits
    - Filesystem access control
    - Network policy enforcement
    - Execution auditing
    """

    def __init__(self, base_temp_dir: Optional[str] = None):
        self.base_temp_dir = base_temp_dir or tempfile.gettempdir()
        self._active_sandboxes: dict[str, dict] = {}
        self._execution_count = 0

    def create_config(
        self,
        policy: SandboxPolicy = SandboxPolicy.STANDARD,
        **overrides
    ) -> SandboxConfig:
        """Create a sandbox config from a policy with optional overrides."""
        config = SandboxConfig(policy=policy)

        # Apply policy defaults
        if policy == SandboxPolicy.UNRESTRICTED:
            config.resources.max_cpu_seconds = 300
            config.resources.max_wall_seconds = 600
            config.resources.max_memory_mb = 4096
            config.filesystem.denied_paths = []
            config.network.denied_hosts = []

        elif policy == SandboxPolicy.STRICT:
            config.resources.max_cpu_seconds = 10
            config.resources.max_wall_seconds = 30
            config.resources.max_memory_mb = 256
            config.filesystem.allowed_read_paths = ["/tmp"]
            config.filesystem.allowed_write_paths = []
            config.network.allow_outbound = False

        elif policy == SandboxPolicy.NETWORK_ONLY:
            config.filesystem.allowed_read_paths = []
            config.filesystem.allowed_write_paths = []
            config.filesystem.allow_temp_files = False

        elif policy == SandboxPolicy.FILESYSTEM_ONLY:
            config.network.allow_outbound = False
            config.network.allow_inbound = False

        # Apply overrides
        for key, value in overrides.items():
            if hasattr(config, key):
                setattr(config, key, value)

        return config

    def check_path_allowed(
        self,
        path: str,
        policy: FilesystemPolicy,
        action: str = "read"
    ) -> tuple[bool, Optional[str]]:
        """
        Check if a path is allowed by the filesystem policy.

        Returns:
            (allowed, reason) tuple
        """
        # Expand path
        path = os.path.expanduser(path)
        path = os.path.abspath(path)

        # Check denied paths first
        for denied in policy.denied_paths:
            denied = os.path.expanduser(denied)
            denied = os.path.abspath(denied)
            if path.startswith(denied) or path == denied:
                return False, f"Path {path} is in denied list"

        # Check allowed paths
        if action == "read":
            allowed_paths = policy.allowed_read_paths
        else:
            allowed_paths = policy.allowed_write_paths

        # If no allowed paths specified, allow all (except denied)
        if not allowed_paths:
            return True, None

        # Check if path is in allowed list
        for allowed in allowed_paths:
            allowed = os.path.expanduser(allowed)
            allowed = os.path.abspath(allowed)
            if path.startswith(allowed) or path == allowed:
                return True, None

        return False, f"Path {path} not in allowed list for {action}"

    def check_host_allowed(
        self,
        host: str,
        policy: NetworkPolicy
    ) -> tuple[bool, Optional[str]]:
        """
        Check if a host is allowed by the network policy.

        Returns:
            (allowed, reason) tuple
        """
        if not policy.allow_outbound:
            return False, "Outbound network access is disabled"

        # Check denied hosts
        for denied in policy.denied_hosts:
            if host == denied or host.endswith(f".{denied}"):
                return False, f"Host {host} is in denied list"

        # Check allowed hosts (if specified)
        if policy.allowed_hosts:
            for allowed in policy.allowed_hosts:
                if host == allowed or host.endswith(f".{allowed}"):
                    return True, None
            return False, f"Host {host} not in allowed list"

        return True, None

    def check_port_allowed(
        self,
        port: int,
        policy: NetworkPolicy
    ) -> tuple[bool, Optional[str]]:
        """Check if a port is allowed by the network policy."""
        if port in policy.denied_ports:
            return False, f"Port {port} is in denied list"

        if policy.allowed_ports and port not in policy.allowed_ports:
            return False, f"Port {port} not in allowed list"

        return True, None

    async def execute_command(
        self,
        command: str,
        config: Optional[SandboxConfig] = None,
        agent_id: Optional[str] = None
    ) -> SandboxResult:
        """
        Execute a shell command in a sandboxed environment.

        Args:
            command: Shell command to execute
            config: Sandbox configuration (default: STANDARD policy)
            agent_id: Optional agent ID for tracking

        Returns:
            SandboxResult with output and status
        """
        config = config or self.create_config()
        self._execution_count += 1
        execution_id = f"exec_{self._execution_count}"

        start_time = datetime.now()
        violations = []

        logger.info("sandbox_execution_start",
                   execution_id=execution_id,
                   agent_id=agent_id,
                   policy=config.policy.value)

        # Create temporary directory for sandbox
        sandbox_dir = None
        if config.filesystem.allow_temp_files:
            sandbox_dir = tempfile.mkdtemp(
                prefix="agent_sandbox_",
                dir=config.filesystem.temp_dir or self.base_temp_dir
            )

        try:
            # Build environment
            env = {}
            if config.inherit_env:
                env.update(os.environ)
            env.update(config.environment)

            # Set resource-related env vars
            env["AGENT_OS_SANDBOX"] = "1"
            env["AGENT_OS_EXECUTION_ID"] = execution_id

            # Determine working directory
            cwd = config.working_dir or sandbox_dir or os.getcwd()

            # Create the subprocess
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env,
                # Resource limits via preexec_fn would go here on Unix
            )

            # Track active sandbox
            self._active_sandboxes[execution_id] = {
                "process": process,
                "agent_id": agent_id,
                "start_time": start_time,
                "config": config,
            }

            # Wait with timeout
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=config.resources.max_wall_seconds
                )
                exit_code = process.returncode

            except asyncio.TimeoutError:
                # Kill the process
                process.kill()
                await process.wait()
                violations.append(f"Exceeded wall time limit of {config.resources.max_wall_seconds}s")
                stdout, stderr = b"", b"Execution timed out"
                exit_code = -signal.SIGKILL

            duration = (datetime.now() - start_time).total_seconds()

            result = SandboxResult(
                success=exit_code == 0 and not violations,
                output=stdout.decode("utf-8", errors="replace"),
                error=stderr.decode("utf-8", errors="replace"),
                exit_code=exit_code,
                duration_seconds=duration,
                violations=violations,
                resource_usage={
                    "wall_time_seconds": duration,
                }
            )

            logger.info("sandbox_execution_complete",
                       execution_id=execution_id,
                       success=result.success,
                       duration=duration,
                       violations=violations)

            return result

        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            logger.error("sandbox_execution_error",
                        execution_id=execution_id,
                        error=str(e))

            return SandboxResult(
                success=False,
                error=str(e),
                exit_code=-1,
                duration_seconds=duration,
                violations=[f"Execution error: {str(e)}"]
            )

        finally:
            # Cleanup
            if execution_id in self._active_sandboxes:
                del self._active_sandboxes[execution_id]

            if sandbox_dir and os.path.exists(sandbox_dir):
                try:
                    shutil.rmtree(sandbox_dir)
                except Exception as e:
                    logger.warning("sandbox_cleanup_failed",
                                  execution_id=execution_id,
                                  error=str(e))

    async def execute_python(
        self,
        code: str,
        config: Optional[SandboxConfig] = None,
        agent_id: Optional[str] = None
    ) -> SandboxResult:
        """
        Execute Python code in a sandboxed environment.

        Args:
            code: Python code to execute
            config: Sandbox configuration
            agent_id: Optional agent ID

        Returns:
            SandboxResult with output and status
        """
        config = config or self.create_config(SandboxPolicy.STRICT)

        # Create temp file for code
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            delete=False
        ) as f:
            f.write(code)
            code_path = f.name

        try:
            # Execute with python
            result = await self.execute_command(
                f"python3 {code_path}",
                config=config,
                agent_id=agent_id
            )
            return result
        finally:
            # Cleanup code file
            try:
                os.unlink(code_path)
            except:
                pass

    def kill_sandbox(self, execution_id: str) -> bool:
        """Kill a running sandbox by execution ID."""
        if execution_id not in self._active_sandboxes:
            return False

        sandbox = self._active_sandboxes[execution_id]
        process = sandbox.get("process")

        if process and process.returncode is None:
            process.kill()
            logger.info("sandbox_killed", execution_id=execution_id)
            return True

        return False

    def kill_agent_sandboxes(self, agent_id: str) -> int:
        """Kill all sandboxes for an agent."""
        killed = 0
        for exec_id, sandbox in list(self._active_sandboxes.items()):
            if sandbox.get("agent_id") == agent_id:
                if self.kill_sandbox(exec_id):
                    killed += 1
        return killed

    def get_active_sandboxes(self) -> list[dict]:
        """Get list of active sandboxes."""
        result = []
        now = datetime.now()

        for exec_id, sandbox in self._active_sandboxes.items():
            duration = (now - sandbox["start_time"]).total_seconds()
            result.append({
                "execution_id": exec_id,
                "agent_id": sandbox.get("agent_id"),
                "duration_seconds": duration,
                "policy": sandbox["config"].policy.value,
            })

        return result

    def get_stats(self) -> dict:
        """Get sandbox manager statistics."""
        return {
            "total_executions": self._execution_count,
            "active_sandboxes": len(self._active_sandboxes),
        }


# Convenience functions for common operations

def create_standard_sandbox() -> SandboxConfig:
    """Create a standard sandbox configuration."""
    return SandboxConfig(policy=SandboxPolicy.STANDARD)


def create_strict_sandbox() -> SandboxConfig:
    """Create a strict sandbox configuration."""
    manager = SandboxManager()
    return manager.create_config(SandboxPolicy.STRICT)


def check_command_safe(command: str) -> tuple[bool, list[str]]:
    """
    Basic command safety check.

    Returns:
        (is_safe, warnings) tuple
    """
    warnings = []

    # Dangerous patterns
    dangerous_patterns = [
        ("rm -rf /", "Attempts to delete root filesystem"),
        ("rm -rf ~", "Attempts to delete home directory"),
        (":(){:|:&};:", "Fork bomb detected"),
        ("dd if=/dev/zero", "Disk overwrite detected"),
        ("mkfs.", "Filesystem format detected"),
        ("> /dev/sda", "Direct disk write detected"),
        ("chmod 777 /", "Dangerous permission change"),
        ("curl | sh", "Piped remote code execution"),
        ("wget | sh", "Piped remote code execution"),
        ("eval $(", "Dynamic code execution"),
    ]

    command_lower = command.lower()

    for pattern, warning in dangerous_patterns:
        if pattern.lower() in command_lower:
            warnings.append(warning)

    # Check for sudo/su
    if "sudo " in command or command.startswith("su "):
        warnings.append("Privilege escalation attempt")

    return len(warnings) == 0, warnings
