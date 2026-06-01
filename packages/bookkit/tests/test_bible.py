from __future__ import annotations

import textwrap
from pathlib import Path

import yaml

from bookkit.bible import BibleConfig, Character, dump_bible, load_bible

SAMPLE = textwrap.dedent(
    """
    title: "The Compliance Engine"
    logline: "An auditor finds the AI rewriting the rules."
    themes: ["control", "bureaucracy"]
    characters:
      - name: "MARA"
        aka: ["the Inspector"]
        role: protagonist
        voice: "Clipped, formal."
        status: alive
        relationships:
          - with: "TOMAS"
            nature: "estranged brother"
      - name: "THE ENGINE"
        role: antagonist
        status: active
    beats:
      - chapter: 1
        summary: "Mara is assigned the audit."
        advances: ["Mara introduced"]
      - chapter: 2
        summary: "Tomas leaves."
        state_changes:
          - character: "TOMAS"
            set: {status: departed}
          - "The Engine edits its own logs."
    """
)


def test_validate_full_bible() -> None:
    bible = BibleConfig.model_validate(yaml.safe_load(SAMPLE))
    assert bible.title == "The Compliance Engine"
    assert len(bible.characters) == 2
    assert len(bible.beats) == 2


def test_relationship_with_alias() -> None:
    bible = BibleConfig.model_validate(yaml.safe_load(SAMPLE))
    mara = bible.character("MARA")
    assert mara is not None
    assert mara.relationships[0].with_ == "TOMAS"


def test_character_lookup_by_alias_caseinsensitive() -> None:
    bible = BibleConfig.model_validate(yaml.safe_load(SAMPLE))
    assert bible.character("the inspector") is bible.character("MARA")
    assert bible.character("nobody") is None


def test_state_changes_coerce_bare_string() -> None:
    bible = BibleConfig.model_validate(yaml.safe_load(SAMPLE))
    beat2 = bible.beat_for(2)
    assert beat2 is not None
    changes = beat2.state_changes
    assert changes[0].set == {"status": "departed"}
    assert changes[1].note == "The Engine edits its own logs."


def test_empty_bible_is_valid() -> None:
    bible = BibleConfig()
    assert bible.characters == []
    assert bible.beats == []


def test_apply_state_changes_updates_beat_and_character() -> None:
    bible = BibleConfig.model_validate(yaml.safe_load(SAMPLE))
    from bookkit.bible import StateChange

    bible.apply_state_changes(3, [StateChange(character="MARA", set={"status": "fugitive"})])
    assert bible.character("MARA").status == "fugitive"  # propagated to live canon
    beat3 = bible.beat_for(3)
    assert beat3 is not None  # beat created on the fly
    assert beat3.state_changes[0].set == {"status": "fugitive"}


def test_dump_roundtrip_preserves_with_alias(tmp_path: Path) -> None:
    bible = BibleConfig(
        title="T",
        characters=[Character(name="MARA", relationships=[{"with": "TOMAS", "nature": "sister"}])],
    )
    text = dump_bible(bible)
    assert "with:" in text  # alias honored on dump, not "with_"
    path = tmp_path / "bible.yaml"
    path.write_text(text, encoding="utf-8")
    reloaded = load_bible(path)
    assert reloaded.character("MARA").relationships[0].with_ == "TOMAS"
