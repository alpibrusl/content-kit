"""Tests for heuristic dialogue attribution (full-cast audiobooks)."""

from __future__ import annotations

from bookkit._dialogue import Matcher, attribute, attribute_paragraph
from bookkit.bible import BibleConfig, Character


def _bible():
    return BibleConfig(
        characters=[
            Character(name="Mara Vance", aka=["Vance"]),
            Character(name="Dieter"),
            Character(name="Vera Quintela", aka=["la arquitecta"]),
        ]
    )


# --- Matcher -----------------------------------------------------------------


def test_matcher_resolves_full_name_alias_and_first_token():
    m = Matcher(_bible())
    assert m.find("then Mara left") == "MARA VANCE"
    assert m.find("Vance nodded") == "MARA VANCE"
    assert m.find("said the arquitecta") is None  # multi-word alias not single-token
    assert m.find("Dieter") == "DIETER"


def test_matcher_ambiguous_token_dropped():
    bible = BibleConfig(characters=[Character(name="Mara Vance"), Character(name="Mara Stone")])
    m = Matcher(bible)
    # "Mara" points at two characters -> not confidently resolvable.
    assert m.find("Mara spoke") is None


def test_matcher_none_bible_matches_nothing():
    assert Matcher(None).find("anybody") is None


def test_attribution_speaker_requires_cue_near_name():
    m = Matcher(_bible())
    assert m.attribution_speaker('"Run," said Mara.') == "MARA VANCE"
    assert m.attribution_speaker("Mara walked across the bridge.") is None  # name, no speech verb


# --- quoted dialogue ---------------------------------------------------------


def test_attribute_quoted_splits_speaker_and_narration():
    m = Matcher(_bible())
    segs = attribute_paragraph('"Run," said Mara. She bolted.', m, "NARRATOR")
    assert segs == [
        ("MARA VANCE", "Run,"),
        ("NARRATOR", "said Mara. She bolted."),
    ]


def test_attribute_quoted_unattributed_falls_back_to_narrator():
    m = Matcher(_bible())
    segs = attribute_paragraph('"Who is there?"', m, "NARRATOR")
    assert segs == [("NARRATOR", "Who is there?")]


# --- dash dialogue (Spanish) -------------------------------------------------


def test_attribute_dash_attributes_and_drops_speech_tag():
    m = Matcher(_bible())
    segs = attribute_paragraph("—Corre —dijo Vera—. Y corrió.", m, "NARRATOR")
    # Speech goes to Vera; the "dijo Vera" tag is dropped; the action is narrated.
    assert ("VERA QUINTELA", "Corre") in segs
    assert (". Y corrió." in [t for _, t in segs]) or ("Y corrió." in [t for _, t in segs])
    assert all("dijo Vera" not in t for _, t in segs)


def test_attribute_dash_unattributed_stays_narrator():
    m = Matcher(_bible())
    segs = attribute_paragraph("—Hola —saludó alguien.", m, "NARRATOR")
    assert all(spk == "NARRATOR" for spk, _ in segs)


# --- whole-chapter attribute -------------------------------------------------


def test_attribute_degrades_to_narrator_without_bible():
    text = '"Hello," said Mara.\n\nPlain narration here.'
    segs = attribute(text, None, "NARRATOR")
    assert all(spk == "NARRATOR" for spk, _ in segs)


def test_attribute_preserves_reading_order():
    text = 'Narration first.\n\n"Then this," said Dieter.'
    segs = attribute(text, _bible(), "NARRATOR")
    assert segs[0] == ("NARRATOR", "Narration first.")
    assert ("DIETER", "Then this,") in segs
