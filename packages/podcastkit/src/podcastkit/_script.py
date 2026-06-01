"""Utilities for parsing, normalizing, and validating script.json content."""

from __future__ import annotations

import json
import re


def extract_json(text: str) -> list[dict]:
    """Extract a JSON array from an LLM response.

    Handles raw JSON, markdown code fences, and arrays embedded in prose.
    Raises ValueError if no valid array is found.
    """
    text = text.strip()

    # Direct parse
    if text.startswith("["):
        return json.loads(text)

    # Strip markdown code fences
    m = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    if m:
        return json.loads(m.group(1))

    # Find the outermost array anywhere in the response
    m = re.search(r"\[.*\]", text, re.DOTALL)
    if m:
        return json.loads(m.group(0))

    raise ValueError(
        "No JSON array found in LLM response. "
        "The model may have returned prose instead of JSON — try again."
    )


def _char_prefix(character: str) -> str:
    """Derive a 4-char ID prefix from a character name."""
    name = character.upper().strip()
    if name == "NARRATOR":
        return "narr"
    return name[:4].lower()


def normalize_script(entries: list[dict]) -> list[dict]:
    """Normalize IDs and character names in a script entry list.

    - Sets character to ALL CAPS
    - Rebuilds IDs as <prefix>_<nn> in order of appearance per character
    - Validates required fields are present
    """
    counters: dict[str, int] = {}
    result = []
    for i, raw in enumerate(entries):
        if not isinstance(raw, dict):
            raise ValueError(f"Entry {i} is not an object: {raw!r}")
        for field in ("character", "text"):
            if field not in raw:
                raise ValueError(f"Entry {i} missing required field '{field}'")

        character = str(raw["character"]).upper().strip()
        text = str(raw["text"]).strip()
        prefix = _char_prefix(character)
        counters[prefix] = counters.get(prefix, 0) + 1
        result.append(
            {
                "id": f"{prefix}_{counters[prefix]:02d}",
                "character": character,
                "text": text,
            }
        )
    return result


def derive_timeline(script: list[dict], ai_characters: set[str] | None = None) -> list[dict]:
    """Build a timeline list from a normalized script.

    AI/robot characters get pre_silence=1.2 (comedy beat rule).
    All others get 0.5, except the very first line which gets 0.5 too.
    """
    ai_chars = ai_characters or set()
    timeline = []
    for entry in script:
        char = entry["character"]
        pre = 1.2 if char in ai_chars else 0.5
        timeline.append({"id": entry["id"], "pre_silence": pre})
    return timeline


def derive_voices_stub(script: list[dict]) -> dict:
    """Return a voices dict stub with placeholder voice_ids for all characters."""
    seen: dict[str, dict] = {}
    for entry in script:
        char = entry["character"]
        if char not in seen:
            seen[char] = {
                "backend": "kokoro",
                "voice_id": "REPLACE_ME",
            }
    return seen
