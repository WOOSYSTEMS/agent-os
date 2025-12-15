"""
HTTP tools for Agent OS.

Allows agents to make HTTP requests.
"""

import httpx
from ..core.models import ToolSchema, ToolParameter


# HTTP request schema
HTTP_REQUEST_SCHEMA = ToolSchema(
    name="http.request",
    description="Make an HTTP request to a URL. Supports GET, POST, PUT, DELETE methods.",
    parameters=[
        ToolParameter(
            name="url",
            type="string",
            description="The URL to request",
            required=True
        ),
        ToolParameter(
            name="method",
            type="string",
            description="HTTP method (GET, POST, PUT, DELETE)",
            required=False,
            default="GET"
        ),
        ToolParameter(
            name="headers",
            type="object",
            description="HTTP headers as key-value pairs",
            required=False,
            default=None
        ),
        ToolParameter(
            name="body",
            type="string",
            description="Request body (for POST/PUT)",
            required=False,
            default=None
        ),
        ToolParameter(
            name="timeout",
            type="integer",
            description="Timeout in seconds",
            required=False,
            default=30
        ),
    ],
    required_capabilities=["http:*:request"]
)


async def http_request(
    url: str,
    method: str = "GET",
    headers: dict = None,
    body: str = None,
    timeout: int = 30
) -> str:
    """
    Make an HTTP request.

    Returns response status, headers, and body.
    """
    method = method.upper()
    if method not in ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"]:
        raise ValueError(f"Unsupported HTTP method: {method}")

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.request(
            method=method,
            url=url,
            headers=headers,
            content=body
        )

        # Build result
        result_parts = [
            f"Status: {response.status_code} {response.reason_phrase}",
            "",
            "Headers:",
        ]

        for key, value in response.headers.items():
            result_parts.append(f"  {key}: {value}")

        result_parts.append("")
        result_parts.append("Body:")

        # Get response body
        try:
            body_text = response.text
            if len(body_text) > 50000:
                body_text = body_text[:50000] + "\n...(truncated)"
            result_parts.append(body_text)
        except Exception:
            result_parts.append(f"(binary response, {len(response.content)} bytes)")

        return "\n".join(result_parts)


# Convenience tool for GET requests
HTTP_GET_SCHEMA = ToolSchema(
    name="http.get",
    description="Make a GET request to a URL. Simpler version of http.request for basic fetches.",
    parameters=[
        ToolParameter(
            name="url",
            type="string",
            description="The URL to fetch",
            required=True
        ),
    ],
    required_capabilities=["http:*:request"]
)


async def http_get(url: str) -> str:
    """Simple GET request."""
    return await http_request(url, method="GET")


# All tools from this module
TOOLS = [
    (HTTP_REQUEST_SCHEMA, http_request),
    (HTTP_GET_SCHEMA, http_get),
]
