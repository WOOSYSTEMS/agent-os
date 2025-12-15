"""
File tools for Agent OS.

Allows agents to read and write files.
"""

import aiofiles
import os
from pathlib import Path
from ..core.models import ToolSchema, ToolParameter


# Read file schema
FILE_READ_SCHEMA = ToolSchema(
    name="file.read",
    description="Read the contents of a file. Returns the file content as text.",
    parameters=[
        ToolParameter(
            name="path",
            type="string",
            description="Path to the file to read",
            required=True
        ),
        ToolParameter(
            name="max_bytes",
            type="integer",
            description="Maximum bytes to read (default 100KB)",
            required=False,
            default=100000
        ),
    ],
    required_capabilities=["file:*:read"]
)


# Write file schema
FILE_WRITE_SCHEMA = ToolSchema(
    name="file.write",
    description="Write content to a file. Creates the file if it doesn't exist.",
    parameters=[
        ToolParameter(
            name="path",
            type="string",
            description="Path to the file to write",
            required=True
        ),
        ToolParameter(
            name="content",
            type="string",
            description="Content to write to the file",
            required=True
        ),
        ToolParameter(
            name="append",
            type="boolean",
            description="Append to file instead of overwriting",
            required=False,
            default=False
        ),
    ],
    required_capabilities=["file:*:write"]
)


# List directory schema
FILE_LIST_SCHEMA = ToolSchema(
    name="file.list",
    description="List files and directories in a path.",
    parameters=[
        ToolParameter(
            name="path",
            type="string",
            description="Directory path to list",
            required=True
        ),
        ToolParameter(
            name="recursive",
            type="boolean",
            description="List recursively",
            required=False,
            default=False
        ),
    ],
    required_capabilities=["file:*:read"]
)


async def file_read(path: str, max_bytes: int = 100000) -> str:
    """Read a file's contents."""
    file_path = Path(path).expanduser().resolve()

    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    if not file_path.is_file():
        raise ValueError(f"Not a file: {path}")

    try:
        async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
            content = await f.read(max_bytes)

        if len(content) >= max_bytes:
            content += "\n...(truncated)"

        return content

    except UnicodeDecodeError:
        # Try reading as binary
        async with aiofiles.open(file_path, "rb") as f:
            content = await f.read(max_bytes)
        return f"(binary file, {len(content)} bytes)"


async def file_write(path: str, content: str, append: bool = False) -> str:
    """Write content to a file."""
    file_path = Path(path).expanduser().resolve()

    # Create parent directories if needed
    file_path.parent.mkdir(parents=True, exist_ok=True)

    mode = "a" if append else "w"

    async with aiofiles.open(file_path, mode, encoding="utf-8") as f:
        await f.write(content)

    action = "Appended to" if append else "Wrote"
    return f"{action} {len(content)} characters to {path}"


async def file_list(path: str, recursive: bool = False) -> str:
    """List files in a directory."""
    dir_path = Path(path).expanduser().resolve()

    if not dir_path.exists():
        raise FileNotFoundError(f"Directory not found: {path}")

    if not dir_path.is_dir():
        raise ValueError(f"Not a directory: {path}")

    entries = []

    if recursive:
        for item in dir_path.rglob("*"):
            rel_path = item.relative_to(dir_path)
            type_char = "d" if item.is_dir() else "f"
            entries.append(f"[{type_char}] {rel_path}")
    else:
        for item in dir_path.iterdir():
            type_char = "d" if item.is_dir() else "f"
            entries.append(f"[{type_char}] {item.name}")

    if not entries:
        return "(empty directory)"

    # Sort and limit
    entries.sort()
    if len(entries) > 1000:
        entries = entries[:1000]
        entries.append("...(truncated)")

    return "\n".join(entries)


# All tools from this module
TOOLS = [
    (FILE_READ_SCHEMA, file_read),
    (FILE_WRITE_SCHEMA, file_write),
    (FILE_LIST_SCHEMA, file_list),
]
