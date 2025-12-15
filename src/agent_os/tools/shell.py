"""
Shell tool for Agent OS.

Allows agents to execute shell commands.
"""

import asyncio
import shlex
from ..core.models import ToolSchema, ToolParameter


# Tool schema
SHELL_EXECUTE_SCHEMA = ToolSchema(
    name="shell.execute",
    description="Execute a shell command and return the output. Use for running programs, scripts, or system commands.",
    parameters=[
        ToolParameter(
            name="command",
            type="string",
            description="The shell command to execute",
            required=True
        ),
        ToolParameter(
            name="timeout",
            type="integer",
            description="Timeout in seconds (default 30)",
            required=False,
            default=30
        ),
        ToolParameter(
            name="working_dir",
            type="string",
            description="Working directory for the command",
            required=False,
            default=None
        ),
    ],
    required_capabilities=["shell:*:execute"]
)


async def shell_execute(
    command: str,
    timeout: int = 30,
    working_dir: str = None
) -> str:
    """
    Execute a shell command.

    Args:
        command: The command to run
        timeout: Max seconds to wait
        working_dir: Directory to run in

    Returns:
        Combined stdout and stderr output
    """
    try:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=working_dir
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            process.kill()
            raise TimeoutError(f"Command timed out after {timeout}s")

        output_parts = []

        if stdout:
            output_parts.append(stdout.decode("utf-8", errors="replace"))
        if stderr:
            output_parts.append(f"[stderr]\n{stderr.decode('utf-8', errors='replace')}")

        output = "\n".join(output_parts) if output_parts else "(no output)"

        # Add exit code info
        if process.returncode != 0:
            output += f"\n[exit code: {process.returncode}]"

        # Truncate very long output
        if len(output) > 50000:
            output = output[:50000] + "\n...(truncated)"

        return output

    except Exception as e:
        raise RuntimeError(f"Shell execution failed: {e}")


# All tools from this module
TOOLS = [
    (SHELL_EXECUTE_SCHEMA, shell_execute),
]
