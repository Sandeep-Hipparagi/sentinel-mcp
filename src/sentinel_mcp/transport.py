"""Transport launchers (stdio and streamable-http) for both MCP SDK generations."""

from __future__ import annotations

from typing import Any


def run_stdio(server: Any) -> None:
    """Serve over stdio (blocks until the client disconnects)."""
    generation = type(server).__module__
    if "fastmcp" in generation:
        server.run(transport="stdio")
        return
    import anyio  # noqa: PLC0415

    anyio.run(server.run_stdio_async)


def run_streamable_http(server: Any, host: str = "127.0.0.1", port: int = 8000) -> None:
    """Serve over streamable HTTP (blocks until stopped)."""
    generation = type(server).__module__
    if "fastmcp" in generation:
        server.settings.host = host
        server.settings.port = port
        server.run(transport="streamable-http")
        return
    import anyio  # noqa: PLC0415

    anyio.run(server.run_streamable_http_async)
