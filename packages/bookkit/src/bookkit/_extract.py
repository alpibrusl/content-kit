"""Defensive extraction of structured blocks from free-form LLM output.

Continuity must work on any model, including weaker local ones, so we never rely
on provider features like JSON mode. Instead we parse robustly from plain text.
"""

from __future__ import annotations

import re

# ```yaml ... ```  (preferred) or a bare ``` ... ``` fence as a fallback.
_FENCED_YAML = re.compile(r"```(?:ya?ml)\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)
_FENCED_ANY = re.compile(r"```\s*\n(.*?)```", re.DOTALL)


def split_prose_and_yaml(text: str) -> tuple[str, str | None]:
    """Split model output into (prose, yaml_block).

    Returns the text with the fenced YAML block removed as the prose, plus the YAML
    block's contents (or None if no block was found).
    """
    match = _FENCED_YAML.search(text) or _FENCED_ANY.search(text)
    if not match:
        return text.strip(), None
    yaml_block = match.group(1).strip()
    prose = (text[: match.start()] + text[match.end() :]).strip()
    return prose, yaml_block
