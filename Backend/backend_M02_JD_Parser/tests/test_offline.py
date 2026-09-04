"""The degraded path, and how wide it is honest about being.

Rule 2: *"a missing dependency narrows the SCOPE of a feature, never its
quality, and never silently."* M04 down is the case that rule was written for,
and for a long time M02 obeyed the letter of it and not the spirit: the module
said clearly that it was offline, and then recognised five concepts.

Two separate promises are tested here, and keeping them separate is the point.

  · What the module can SEE offline should be as wide as its own vocabulary
    already reaches — the archetype requirement sets, which it already trusts
    enough to add requirements from.
  · What the module can GROUND offline is only the ids it can prove M04 has.
    An invented `concept:kubernetes` looks exactly like a real id and matches
    nothing, so every mastery lookup returns nothing and "no score" becomes
    indistinguishable from "not measured yet".
"""

from __future__ import annotations

import pathlib

import pytest
from ai_core.concepts import normalise_alias
from backend_M02_JD_Parser.router import (
    _VERIFIED_CONCEPTS,
    FALLBACK_CONCEPTS,
    FALLBACK_RESOLUTIONS,
)

#: M04's ontology, if the sibling repository is checked out beside this one.
#: Not a dependency — the suite runs offline with no network and no siblings —
#: but when it IS there, the strongest available check is the real file.
_M04_ONTOLOGY = (
    pathlib.Path(__file__).resolve().parents[3].parent
    / "Memory"
    / "packages"
    / "knowledge"
    / "ontology"
    / "concepts.yaml"
)


def test_the_offline_vocabulary_is_wider_than_the_ids():
    """Five concepts was honest and nearly useless.

    A posting scanned with M04 down saw DP, recursion, hashing, SQL and
    transactions, and was blind to everything else a company has ever asked
    for. The archetypes already carry the canonical requirement set for 24
    roles, reviewed and maintained, and reusing them costs nothing because
    there is one copy.
    """
    assert len(FALLBACK_CONCEPTS) > 50, "the archetype vocabulary did not load"
    names = {normalise_alias(c["name"]) for c in FALLBACK_CONCEPTS}
    assert "dbms" in names
    assert "operating systems" in names


def test_nothing_derived_claims_a_concept_id():
    """The vocabulary widened; the grounding did not.

    This is the assertion that keeps the two promises apart. Every id M02 hands
    out offline has to be one it can prove M04 holds, and there are five of
    those.
    """
    assert len(FALLBACK_RESOLUTIONS) == len(_VERIFIED_CONCEPTS) == 5

    verified = {normalise_alias(c["name"]) for c in _VERIFIED_CONCEPTS}
    for label in FALLBACK_RESOLUTIONS:
        assert normalise_alias(label) in verified, (
            f"{label!r} resolves to a concept id but is not one of the verified five"
        )


def test_every_verified_concept_resolves():
    """A concept in the verified list with no id is a gap in the pair."""
    for concept in _VERIFIED_CONCEPTS:
        assert normalise_alias(concept["name"]) in {
            normalise_alias(k) for k in FALLBACK_RESOLUTIONS
        }


@pytest.mark.gate
@pytest.mark.skipif(not _M04_ONTOLOGY.exists(), reason="M04 not checked out beside M02")
def test_the_offline_ids_are_ids_m04_actually_has():
    """The claim these five ids make, checked against the file that decides it.

    An id here asserts that M04's ontology contains this exact string. If it
    does not, M02 hands a downstream module an id that resolves to nothing, and
    the failure is silent in the worst way: the mastery lookup succeeds and
    returns no rows, which reads as "this student has never been measured on
    it" rather than as "this id is wrong".

    Skipped rather than mocked when M04 is not on disk. A mock of the ontology
    would assert that M02 agrees with M02.
    """
    text = _M04_ONTOLOGY.read_text(encoding="utf-8")

    missing = [
        concept_id
        for concept_id in FALLBACK_RESOLUTIONS.values()
        if f"id: {concept_id}" not in text
    ]

    assert not missing, (
        "offline ids that M04's ontology does not contain:\n  "
        + "\n  ".join(missing)
        + "\nThese resolve to nothing downstream and fail silently."
    )
