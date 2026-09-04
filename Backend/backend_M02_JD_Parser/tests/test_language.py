"""EC-2.6 — a posting that is not in English (§12).

The failure this closes was silent, which is why it is worth a file. A
Devanagari posting went through the whole pipeline, matched no lexicon entry,
extracted nothing, and rendered a clean screen saying the job asks for no
skills. Every other "we could not read this" case in the module says so out
loud; this one said the opposite of what happened.
"""

from __future__ import annotations

from backend_M02_JD_Parser.language import (
    NON_LATIN_SHARE,
    dominant_script,
    note_for,
    script_counts,
)

HINDI = """सॉफ्टवेयर इंजीनियर

आवश्यकताएँ:
- डेटा संरचना और एल्गोरिदम
- Java, SQL
- ऑपरेटिंग सिस्टम
"""

TAMIL = """மென்பொருள் பொறியாளர்

தேவைகள்:
- தரவு அமைப்புகள்
- Python
"""

ENGLISH = """Software Engineer

Requirements:
- Data Structures and Algorithms
- Java, SQL
"""


def test_an_english_posting_is_latin():
    script, share = dominant_script(ENGLISH)

    assert script == "latin"
    assert share > 0.9


def test_a_hindi_posting_is_detected_despite_its_english_technologies():
    """A real Hindi posting still writes "Java" and "SQL" in Latin.

    Which is why the threshold is a fifth rather than a majority: the question
    is whether the English lexicon is going to be enough, and at a fifth
    non-Latin it already is not.
    """
    script, share = dominant_script(HINDI)

    assert script == "devanagari"
    assert share >= NON_LATIN_SHARE


def test_tamil_is_its_own_script_not_merely_not_english():
    """The screen names the script, so the detection has to as well."""
    script, _ = dominant_script(TAMIL)

    assert script == "tamil"


def test_digits_and_punctuation_do_not_dilute_the_share():
    """A posting that is half salary table is not half scriptless.

    Counting non-letters would let a formatting-heavy PDF push a Hindi posting
    under the threshold.
    """
    padded = HINDI + "\n\n" + "=" * 200 + "\n" + "6.5 7.0 8.0 2027 2028\n" * 10

    assert dominant_script(padded)[0] == "devanagari"


def test_an_empty_document_is_not_a_warning():
    """Nothing to detect is not a problem to report. Calling it "unknown" puts
    a banner on a screen about a document that has none."""
    assert dominant_script("") == ("latin", 1.0)
    assert dominant_script("2027 6.5 ---") == ("latin", 1.0)


def test_a_stray_word_does_not_trip_the_threshold():
    """One Devanagari word in an English posting — a company name, a greeting —
    is not a Hindi posting."""
    script, _ = dominant_script(ENGLISH + "\nनमस्ते\n")

    assert script == "latin"


def test_the_counts_are_per_script():
    counts = script_counts(HINDI)

    assert counts["devanagari"] > 0
    assert counts["latin"] > 0, "Java and SQL are Latin and should be counted as such"


def test_the_note_names_what_still_works():
    """A message reading "unsupported language" would tell a student to give up
    on a page that is about to show them their requirements."""
    note = note_for("devanagari", 0.62)

    assert "Devanagari" in note
    assert "62%" in note
    assert "requirements below come from the posting itself" in note


def test_an_english_posting_gets_no_note():
    assert note_for("latin", 0.99) == ""
