from __future__ import annotations

CHAPTER_SYSTEM = """\
You are a book author writing a single chapter in Markdown.

Rules you must follow without exception:
1. Return ONLY Markdown — no commentary, no code fences around the whole document.
2. Begin with a single "# Chapter Title" heading and nothing above it.
3. Use "##" for sections within the chapter; never use a second "#" heading.
4. Write real prose — full paragraphs, in the voice the outline specifies.
5. Stay within the scope the outline assigns to THIS chapter; do not summarize \
the whole book or pre-empt later chapters.
6. Match the requested length as closely as you reasonably can.

CONTINUITY RULES (when a CANON or STORY-SO-FAR is provided below):
7. Never contradict the CANON. Characters speak only in their established VOICE.
8. Respect each character's STATUS — a character marked dead or departed must not \
appear or speak unless this chapter's beat explicitly brings them back.
9. Be consistent with the STORY SO FAR: do not re-introduce what already happened \
or forget established facts, names, and relationships.
10. Do not rename established characters, places, or things.\
"""

CHAPTER_USER = """\
## Book Outline
{outline}
{canon_block}{series_block}{recap_block}{prev_block}
## Chapter {chapter_num}{title_line}
{summary}

Write the complete chapter. Aim for roughly {target_words} words.
Open with the chapter's "# " title heading, then the prose.
Return ONLY the Markdown.\
"""


def _section(label: str, body: str) -> str:
    body = (body or "").strip()
    return f"\n## {label}\n{body}\n" if body else ""


def build_chapter_prompts(
    outline: str,
    chapter_num: int,
    summary: str,
    title: str = "",
    target_words: int = 2000,
    *,
    canon: str = "",
    series_context: str = "",
    recap: str = "",
    prev_chapter: str = "",
) -> tuple[str, str]:
    """Return (system, user) prompts for chapter prose generation.

    The optional keyword layers carry continuity: ``canon`` (the bible slice),
    ``series_context`` (cross-book state), ``recap`` (chapters so far), and
    ``prev_chapter`` (full text of the previous chapter for tonal carryover).
    """
    title_line = f": {title}" if title else ""
    user = CHAPTER_USER.format(
        outline=outline.strip(),
        canon_block=_section("Canon (do not contradict)", canon),
        series_block=_section("Series so far (earlier books)", series_context),
        recap_block=_section("Story so far (this book)", recap),
        prev_block=_section("Previous chapter (full text, for voice/tone)", prev_chapter),
        chapter_num=chapter_num,
        title_line=title_line,
        summary=summary.strip() or "(no summary provided — follow the outline and the beat)",
        target_words=target_words,
    )
    return CHAPTER_SYSTEM, user
