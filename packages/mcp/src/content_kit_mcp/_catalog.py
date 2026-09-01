"""Turn a content-kit CLI's ``introspect`` catalog into MCP tool definitions.

This module is deliberately free of any MCP-SDK dependency: it is the pure
mapping from a CLI's self-description (``<cli> introspect`` → a JSON catalog of
commands, arguments, and typed options) to (a) an MCP input schema and (b) the
argv needed to invoke the command. The server layer wires these into the SDK.

Keeping it pure keeps the adapter honest: the MCP surface is *generated* from
the CLIs' own contract, so it can never drift from what the tools actually
accept — add a command or option to a CLI and it appears here for free.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Any

#: Option carried by most commands for output *format*; the server always
#: forces JSON on those, so it is never exposed as a tool parameter. A command
#: may reuse the same name for an output *path* (``bookkit write outline
#: --output outline.md``) — that one is a real parameter and must not be
#: confused with the format flag, so the two are told apart by type, not name.
_OUTPUT_OPTION = "--output"


def _is_format_option(opt: dict[str, Any]) -> bool:
    """True for the ``--output text|json`` format switch, not for a path."""
    if opt.get("name") != _OUTPUT_OPTION:
        return False
    type_str = opt.get("type", "")
    return type_str.startswith("enum[") and "json" in type_str[len("enum[") : -1].split("|")


@dataclass(frozen=True)
class ToolSpec:
    """One MCP tool, generated from one CLI subcommand."""

    name: str  # e.g. "bookkit_write_outline"
    description: str
    input_schema: dict[str, Any]
    cli: str  # e.g. "bookkit"
    command: dict[str, Any]  # the raw introspect entry, for build_argv
    json_output: bool  # whether the command supports --output json


def tool_name(cli: str, command_name: str) -> str:
    """``("bookkit", "write outline")`` -> ``"bookkit_write_outline"``."""
    sanitized = command_name.replace("-", "_").replace(" ", "_")
    return f"{cli}_{sanitized}"


def _param_key(option_name: str) -> str:
    """``"--book-dir"`` -> ``"book_dir"``; ``"--recap/--no-recap"`` -> ``"recap"``."""
    positive = option_name.split("/", 1)[0]
    return positive.lstrip("-").replace("-", "_")


def _schema_for_type(type_str: str) -> dict[str, Any]:
    """Map an introspect option type to a JSON-schema fragment."""
    if type_str == "bool":
        return {"type": "boolean"}
    if type_str == "integer":
        return {"type": "integer"}
    if type_str.startswith("enum[") and type_str.endswith("]"):
        choices = [c for c in type_str[len("enum[") : -1].split("|") if c]
        return {"type": "string", "enum": choices}
    # "path", "string", and anything unknown collapse to a plain string.
    return {"type": "string"}


def build_input_schema(command: dict[str, Any]) -> dict[str, Any]:
    """JSON-schema (object) for a command's positional args + options."""
    properties: dict[str, Any] = {}
    required: list[str] = []

    for arg in command.get("arguments", []):
        key = arg["name"].replace("-", "_")
        prop: dict[str, Any] = {"type": "string"}
        if arg.get("description"):
            prop["description"] = arg["description"]
        properties[key] = prop
        if arg.get("required"):
            required.append(key)

    for opt in command.get("options", []):
        if _is_format_option(opt):
            continue  # the server forces JSON; not a user-facing knob
        key = _param_key(opt["name"])
        prop = _schema_for_type(opt.get("type", "string"))
        bits = []
        if opt.get("description"):
            bits.append(opt["description"])
        if opt.get("default") not in (None, ""):
            bits.append(f"(default: {opt['default']})")
        if bits:
            prop["description"] = " ".join(bits)
        properties[key] = prop

    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    schema["additionalProperties"] = False
    return schema


def _has_output_option(command: dict[str, Any]) -> bool:
    return any(_is_format_option(opt) for opt in command.get("options", []))


def build_argv(spec: ToolSpec, arguments: dict[str, Any]) -> list[str]:
    """Construct the argv to invoke ``spec``'s command with ``arguments``."""
    argv: list[str] = [spec.cli, *spec.command["name"].split()]

    # Positional arguments, in declaration order.
    for arg in spec.command.get("arguments", []):
        key = arg["name"].replace("-", "_")
        if key in arguments and arguments[key] is not None:
            argv.append(str(arguments[key]))
        elif arg.get("required"):
            raise ValueError(f"missing required argument: {key!r}")

    # Options. Only emit those the caller actually set, so the CLI's own
    # defaults stand otherwise.
    for opt in spec.command.get("options", []):
        name = opt["name"]
        if _is_format_option(opt):
            continue
        key = _param_key(name)
        if key not in arguments or arguments[key] is None:
            continue
        value = arguments[key]
        if opt.get("type") == "bool":
            if "/" in name:  # paired flag, e.g. --recap/--no-recap
                positive, negative = name.split("/", 1)
                argv.append(positive if value else negative)
            elif value:  # simple flag, e.g. --cast
                argv.append(name)
        else:
            argv.extend([name, str(value)])

    if spec.json_output:
        argv.extend([_OUTPUT_OPTION, "json"])
    return argv


def tools_from_catalog(cli: str, catalog: dict[str, Any]) -> list[ToolSpec]:
    """Build ToolSpecs from a parsed ``<cli> introspect`` envelope."""
    commands = catalog.get("data", {}).get("commands", [])
    specs: list[ToolSpec] = []
    for command in commands:
        # The introspect command itself is plumbing, not a user action.
        if command["name"] == "introspect":
            continue
        description = command.get("description", "").strip()
        for example in command.get("examples", []):
            if example.get("invocation"):
                description += f"\n\nExample: {example['invocation']}"
                break
        specs.append(
            ToolSpec(
                name=tool_name(cli, command["name"]),
                description=description,
                input_schema=build_input_schema(command),
                cli=cli,
                command=command,
                json_output=_has_output_option(command),
            )
        )
    return specs


def load_catalog(cli: str) -> dict[str, Any]:
    """Run ``<cli> introspect`` and return the parsed JSON envelope."""
    proc = subprocess.run([cli, "introspect"], capture_output=True, text=True, check=True)
    return json.loads(proc.stdout)


def discover_tools(clis: tuple[str, ...]) -> list[ToolSpec]:
    """Discover every tool across ``clis``; a CLI that is missing is skipped."""
    specs: list[ToolSpec] = []
    for cli in clis:
        try:
            catalog = load_catalog(cli)
        except (FileNotFoundError, subprocess.CalledProcessError, json.JSONDecodeError):
            continue
        specs.extend(tools_from_catalog(cli, catalog))
    return specs
