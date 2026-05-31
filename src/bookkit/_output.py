"""Output format handling and JSON envelopes — adapted from ACLI spec §2."""

from __future__ import annotations

import json
import sys
import time
from enum import Enum
from typing import Any

VERSION = "0.1.0"


class OutputFormat(str, Enum):
    text = "text"
    json = "json"


def success_envelope(
    command: str,
    data: dict[str, Any],
    *,
    start_time: float | None = None,
    dry_run: bool = False,
    planned_actions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    duration_ms = int((time.time() - start_time) * 1000) if start_time else 0
    envelope: dict[str, Any] = {"ok": True, "command": command}
    if dry_run:
        envelope["dry_run"] = True
        if planned_actions is not None:
            envelope["planned_actions"] = planned_actions
    else:
        envelope["data"] = data
    envelope["meta"] = {"duration_ms": duration_ms, "version": VERSION}
    return envelope


def error_envelope(
    command: str,
    *,
    code: str,
    message: str,
    hint: str | None = None,
    hints: list[str] | None = None,
    start_time: float | None = None,
) -> dict[str, Any]:
    duration_ms = int((time.time() - start_time) * 1000) if start_time else 0
    error: dict[str, Any] = {"code": code, "message": message}
    if hint:
        error["hint"] = hint
    if hints:
        error["hints"] = list(hints)
    return {
        "ok": False,
        "command": command,
        "error": error,
        "meta": {"duration_ms": duration_ms, "version": VERSION},
    }


def emit_progress(step: str, status: str, *, detail: str | None = None) -> None:
    """Emit one NDJSON progress line for long-running commands."""
    line: dict[str, Any] = {"type": "progress", "step": step, "status": status}
    if detail is not None:
        line["detail"] = detail
    sys.stdout.write(json.dumps(line) + "\n")
    sys.stdout.flush()


def emit(data: dict[str, Any], fmt: OutputFormat) -> None:
    """Write the final envelope to stdout in the requested format."""
    if fmt == OutputFormat.json:
        json.dump(data, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        _emit_text(data)


def _emit_text(data: dict[str, Any]) -> None:
    if not data.get("ok"):
        err = data.get("error", {})
        sys.stderr.write(f"Error [{err.get('code', 'UNKNOWN')}]: {err.get('message', '')}\n")
        if hint := err.get("hint"):
            sys.stderr.write(f"  hint: {hint}\n")
        for line in err.get("hints") or []:
            sys.stderr.write(f"  {line}\n")
    else:
        payload = data.get("data") or data.get("planned_actions") or {}
        if isinstance(payload, dict):
            for key, value in payload.items():
                sys.stdout.write(f"{key}: {value}\n")
        elif isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict):
                    parts = "  ".join(f"{k}={v}" for k, v in item.items())
                    sys.stdout.write(f"  {parts}\n")
                else:
                    sys.stdout.write(f"  {item}\n")
