"""
Tools for Agent OS.

Built-in tools that agents can use.
"""

from .registry import ToolRegistry
from . import shell, file, http


def register_builtin_tools(registry: ToolRegistry) -> None:
    """Register all built-in tools with a registry."""
    # Shell tools
    for schema, impl in shell.TOOLS:
        registry.register(schema, impl)

    # File tools
    for schema, impl in file.TOOLS:
        registry.register(schema, impl)

    # HTTP tools
    for schema, impl in http.TOOLS:
        registry.register(schema, impl)


# List of all built-in tool names
BUILTIN_TOOLS = [
    "shell.execute",
    "file.read",
    "file.write",
    "file.list",
    "http.request",
    "http.get",
]


__all__ = [
    "ToolRegistry",
    "register_builtin_tools",
    "BUILTIN_TOOLS",
]
