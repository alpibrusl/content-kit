from __future__ import annotations

CONTINUITY_SYSTEM = """\
You are a continuity editor. You are given a story's CANON and the text of one
chapter. Find concrete contradictions between the chapter and the canon — wrong
character status, changed traits or names, broken relationships, timeline errors,
facts that conflict with the world.

Report only real contradictions. Do not invent issues, and do not comment on
quality or style.\
"""

CONTINUITY_USER = """\
## Canon
{canon}

## Chapter {chapter_num}
{chapter_text}

List the contradictions as a single fenced ```yaml code block:

```yaml
findings:
  - kind: "short-label"        # e.g. wrong-status, name-drift, broken-relationship
    detail: "what contradicts the canon"
    severity: warning           # error | warning
```

If there are no contradictions, return an empty list:

```yaml
findings: []
```\
"""


def build_continuity_prompts(canon: str, chapter_num: int, chapter_text: str) -> tuple[str, str]:
    """Return (system, user) prompts for an LLM continuity review of one chapter."""
    return (
        CONTINUITY_SYSTEM,
        CONTINUITY_USER.format(
            canon=canon.strip() or "(no canon provided)",
            chapter_num=chapter_num,
            chapter_text=chapter_text.strip(),
        ),
    )
