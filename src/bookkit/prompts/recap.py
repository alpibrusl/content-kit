from __future__ import annotations

RECAP_SYSTEM = """\
You write tight continuity recaps of book chapters for a writers' room.

A good recap is factual and compact: what happened, who was involved, and what
changed. No interpretation, no praise, no spoilers beyond this chapter.\
"""

RECAP_USER = """\
Recap the following chapter in 150–250 words. State only what happens: events,
who is present, decisions made, and any change to a character's situation.

After the prose recap, IF (and only if) this chapter changes a character's
canonical state (death, departure, a new alliance, a revealed secret, a gained or
lost role), append a single fenced ```yaml code block listing them:

```yaml
state_changes:
  - character: "NAME"
    set: {{status: departed}}
  - "Free-text change if it doesn't fit a character."
```

If nothing canonical changed, omit the YAML block entirely.

## Chapter {chapter_num}{title_line}
{chapter_text}\
"""


def build_recap_prompts(chapter_num: int, chapter_text: str, title: str = "") -> tuple[str, str]:
    """Return (system, user) prompts for chapter recap + state-change extraction."""
    title_line = f": {title}" if title else ""
    return (
        RECAP_SYSTEM,
        RECAP_USER.format(
            chapter_num=chapter_num,
            title_line=title_line,
            chapter_text=chapter_text.strip(),
        ),
    )
