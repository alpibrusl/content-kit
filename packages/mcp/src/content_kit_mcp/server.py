"""An MCP server that exposes the content-kit CLIs as tools.

A thin adapter: at startup it asks each CLI to describe itself
(``<cli> introspect``) and turns every command into an MCP tool whose schema is
generated from the CLI's own contract. Calling a tool shells out to the CLI with
``--output json`` and returns the structured envelope. There is no second source
of truth — the tools the agent sees are exactly the commands the CLIs expose.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import subprocess

import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from ._catalog import ToolSpec, build_argv, discover_tools

#: The renderers whose CLIs this server adapts. Each must be installed.
CLIS = ("bookkit", "podcastkit")


def _run(spec: ToolSpec, arguments: dict) -> tuple[str, bool]:
    """Invoke a CLI command; return (text, is_error)."""
    argv = build_argv(spec, arguments or {})
    proc = subprocess.run(argv, capture_output=True, text=True)
    out = proc.stdout.strip()
    if spec.json_output and out:
        # pretty-print the JSON envelope for the model; leave raw if not JSON
        with contextlib.suppress(json.JSONDecodeError):
            out = json.dumps(json.loads(out), indent=2, ensure_ascii=False)
    if proc.returncode != 0:
        err = proc.stderr.strip() or out or f"command exited with {proc.returncode}"
        return (f"[exit {proc.returncode}] {err}", True)
    return (out or "(no output)", False)


def build_server() -> Server:
    specs = {s.name: s for s in discover_tools(CLIS)}
    server = Server("content-kit")

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(name=s.name, description=s.description, inputSchema=s.input_schema)
            for s in specs.values()
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
        spec = specs.get(name)
        if spec is None:
            raise ValueError(f"unknown tool: {name!r}")
        # CLIs are blocking; run off the event loop so concurrent calls don't stall.
        text, is_error = await asyncio.to_thread(_run, spec, arguments)
        if is_error:
            raise RuntimeError(text)
        return [types.TextContent(type="text", text=text)]

    return server


async def _amain() -> None:
    server = build_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main() -> None:
    """Console-script entry point: serve over stdio."""
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
