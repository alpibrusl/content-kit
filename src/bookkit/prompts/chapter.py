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
6. Match the requested length as closely as you reasonably can.\
"""

CHAPTER_USER = """\
## Book Outline
{outline}

## Chapter {chapter_num}{title_line}
{summary}

Write the complete chapter. Aim for roughly {target_words} words.
Open with the chapter's "# " title heading, then the prose.
Return ONLY the Markdown.\
"""


def build_chapter_prompts(
    outline: str,
    chapter_num: int,
    summary: str,
    title: str = "",
    target_words: int = 2000,
) -> tuple[str, str]:
    """Return (system, user) prompts for chapter prose generation."""
    title_line = f": {title}" if title else ""
    user = CHAPTER_USER.format(
        outline=outline.strip(),
        chapter_num=chapter_num,
        title_line=title_line,
        summary=summary.strip() or "(no summary provided — follow the outline)",
        target_words=target_words,
    )
    return CHAPTER_SYSTEM, user
