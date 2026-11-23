"""sentinel-mcp CLI: serve (stdio/http) and conformance self-test."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from sentinel_mcp.server import build_server, server_generation
from sentinel_mcp.transport import run_stdio, run_streamable_http

app = typer.Typer(
    help="Registry-ready MCP server with verification, policy, WORM audit, and graph memory.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def serve(
    transport: str = typer.Option("stdio", "--transport", "-t", help="stdio or http."),
    port: int = typer.Option(8000, "--port", min=1, max=65535),
    ledger: Path = typer.Option(  # noqa: B008
        None, "--ledger", help="WORM ledger JSONL path (default: in-memory)."
    ),
) -> None:
    """Start the MCP server (blocks until the client disconnects)."""
    from sentinel_mcp import SentinelServices  # noqa: PLC0415

    services = SentinelServices(ledger_path=ledger)
    server = build_server(services=services)
    console.print(
        f"[green]sentinel-mcp[/green] generation={server_generation()} transport={transport}"
    )
    if transport == "stdio":
        run_stdio(server)
    elif transport in ("http", "streamable-http"):
        run_streamable_http(server, port=port)
    else:
        console.print(f"[red]Unknown transport:[/red] {transport} (valid: stdio, http)")
        raise typer.Exit(code=2)


@app.command()
def conformance() -> None:
    """Run the built-in conformance self-test (exit 1 on any failure)."""
    from sentinel_mcp.conformance import run_conformance as _run  # noqa: PLC0415

    raise typer.Exit(code=_run())


def main() -> None:
    """Console-script entrypoint."""
    app()


if __name__ == "__main__":
    main()
