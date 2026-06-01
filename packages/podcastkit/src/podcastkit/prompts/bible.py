from __future__ import annotations

BIBLE_SYSTEM = """\
You are a creative director for scripted audio dramas. Your job is to write \
series bibles that are vivid, producible, and immediately usable by a writing team.

A good series bible is:
- Specific about tone and voice, not vague ("dry corporate comedy", not "funny")
- Concrete about characters — what they want, what they fear, how they speak
- Honest about scope — each episode should be achievable in 40-70 spoken lines

Return only the Markdown document. No preamble, no sign-off.\
"""

BIBLE_USER = """\
Write a series bible for an audio drama with the following concept:

{concept}

The series has {n_episodes} episode(s). Structure the bible as follows:

# [SERIES TITLE]

## Concept
2-3 sentences: premise, genre, tone.

## Characters
One ## section per character. Include:
- **Role** in the story
- **Personality** and speaking style (2-3 sentences)
- **Arc** across the series (what changes for them?)

## Episodes
A numbered list. For each episode:
- **Title**
- One paragraph: what happens, who drives the action, what is at stake

## Production Notes
Tone, pacing, audio style. What makes this series sound distinct?\
"""


def build_bible_prompts(concept: str, n_episodes: int) -> tuple[str, str]:
    """Return (system, user) prompts for series bible generation."""
    return (
        BIBLE_SYSTEM,
        BIBLE_USER.format(concept=concept.strip(), n_episodes=n_episodes),
    )
