from __future__ import annotations

SCRIPT_SYSTEM = """\
You are a scriptwriter for audio dramas. You write scripts as JSON arrays.

Rules you must follow without exception:
1. Return ONLY a valid JSON array — no markdown, no explanation, no code fences.
2. Every object must have exactly three fields: "id", "character", "text".
3. "id" format: lowercase 4-char prefix of the character name + "_" + 2-digit counter.
   NARRATOR → "narr", all others → first 4 chars of name lowercased.
   Counter resets per character and increments in order of appearance.
   Examples: narr_01, aria_01, mart_01, yusuf_01, chen_01
4. "character" must be the character's name in ALL CAPS exactly as in the bible.
5. "text" is only what is spoken aloud or narrated. No stage directions.
   Use ellipses (...) for pauses within a line, em-dashes (—) for interruptions.
6. Every NARRATOR line sets a scene, describes action, or marks time passing.
7. If the episode has an AI character, its lines must be polite, measured, and \
slightly unsettling — never outright sinister.\
"""

SCRIPT_USER = """\
## Series Bible
{bible}

## Episode {episode_num}{title_line}
{summary}

Write the complete script for this episode. Aim for {target_lines} lines total.
Distribute them across all characters present in this episode.
Begin with a NARRATOR line that establishes the setting.
End with a NARRATOR line or a final character line that closes the episode.

Return ONLY the JSON array.\
"""

SCRIPT_EXAMPLE = """
Example of correct format (short excerpt):
[
  {"id": "narr_01", "character": "NARRATOR", "text": "A grey Tuesday. The open-plan office."},
  {"id": "host_01", "character": "HOST", "text": "Right. So. Why are we here?"},
  {"id": "aria_01", "character": "ARIA", "text": "Just to confirm... you did ask me to be here."},
  {"id": "narr_02", "character": "NARRATOR", "text": "Nobody answers. Someone refreshes email."}
]
"""


def build_script_prompts(
    bible: str,
    episode_num: int,
    summary: str,
    title: str = "",
    target_lines: int = 60,
) -> tuple[str, str]:
    """Return (system, user) prompts for episode script generation."""
    title_line = f": {title}" if title else ""
    user = (
        SCRIPT_USER.format(
            bible=bible.strip(),
            episode_num=episode_num,
            title_line=title_line,
            summary=summary.strip(),
            target_lines=target_lines,
        )
        + "\n"
        + SCRIPT_EXAMPLE
    )
    return SCRIPT_SYSTEM, user
