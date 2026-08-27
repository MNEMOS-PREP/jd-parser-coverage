"""The regression gate for extraction (§10, AC-2.3, AC-2.4).

**These are not acceptance numbers.** `golden.MEASURES_REAL_WORLD` is False and
says why: eleven of the twelve documents are synthetic, written by the same hand
as the parser, so an F1 here is an optimistic estimate of an F1 on postings
nobody wrote for it.

What this IS is the thing the module has never had. Every extraction change
until 2026-08-27 was verified by reading output on one or two examples. That
method found four real bugs in a day and would have caught none of them a second
time — the floors below are what stop the fifth fix undoing the first.

The floors are set at what the parser scores TODAY, deliberately below the
spec's targets. A floor above the current score is a failing build nobody can
fix; a floor at the current score is a ratchet. Raising it is the work.
"""

from __future__ import annotations

import pytest
from backend_M02_JD_Parser import golden
from backend_M02_JD_Parser.archetypes import match as match_archetype
from backend_M02_JD_Parser.extract import (
    disjunction_parts,
    drop_redundant,
    extract_surface_forms,
)
from backend_M02_JD_Parser.normalise import normalise

#: Where extraction stands as of 2026-08-27, rounded down.
#:
#: 0.55 -> 0.72 -> 0.82 in one day. The corpus was committed at 0.581, named
#: four bugs within the hour, and successive fixes took it to 0.857 — past
#: §13's 0.85 target. The floor moves with the measurement because that is what
#: makes it a ratchet rather than a number somebody set once.
#:
#: Passing the target does NOT mean AC-2.3 is met. The target is a claim about
#: real postings and eleven of these twelve documents are synthetic; see
#: `golden.MEASURES_REAL_WORLD`. What is true is that the parser scores 0.857 on
#: the shapes the spec names.
#:
#: Below §13's 0.85, and that gap is the point of writing it here: the target is
#: a claim about real postings and this is a measurement on a synthetic set, so
#: the honest thing is two numbers rather than one number and a hope.
F1_FLOOR = 0.82
PRECISION_FLOOR = 0.84

#: AC-2.4's target is 0.95 and the set is small enough that one wrong answer
#: moves it three points. Held at the measured value.
DISJUNCTION_FLOOR = 0.90


def _extracted(case: golden.GoldenJd) -> set[str]:
    """What the parser reads out of this posting, as it reaches the student.

    `drop_redundant` is part of that and the first version of this scorer left
    it out — which made the number wrong in a specific and misleading way.

    `_split_conjunctions` keeps the WHOLE phrase and its parts on purpose,
    because only the resolver can tell "Transactions and ACID" (one concept)
    from "SQL and data structures" (two). `drop_redundant` then removes the
    compound once its parts are carrying the meaning. Scoring the stage in
    between counted "Docker and Kubernetes" as an invented requirement
    alongside Docker and Kubernetes — a fabrication the student never sees,
    reported on seven of twelve documents.

    Resolution itself is still excluded: that is AC-2.5, and M04 owns it. What
    is measured here is what a reader of the JD screen would see with the
    ontology down, which is the honest floor.
    """
    labels = extract_surface_forms(normalise(case.text))
    # Nothing resolves, so `drop_redundant` falls back to its structural rule:
    # a phrase whose every conjunction part is present in its own right is
    # noise. That is exactly the case being corrected for.
    return golden.keys(drop_redundant(labels, []))


# ---------------------------------------------------------------------------
#  AC-2.3 — requirement extraction
# ---------------------------------------------------------------------------


@pytest.mark.gate
def test_extraction_does_not_regress():
    """The ratchet. A change that reads fewer real requirements fails here."""
    score = golden.Score()
    for case in golden.load_jds():
        score.add(_extracted(case), golden.keys(case.requirements))

    assert score.f1 >= F1_FLOOR, f"extraction F1 fell below the floor — {score}"


@pytest.mark.gate
def test_extraction_does_not_start_inventing():
    """Precision separately, because the two failures are not equally bad.

    A missed requirement shows up as a thin list the student can see. An
    invented one becomes an interview question about something the company
    never asked for, and nothing on any screen marks it as our mistake.
    """
    score = golden.Score()
    for case in golden.load_jds():
        score.add(_extracted(case), golden.keys(case.requirements))

    assert score.precision >= PRECISION_FLOOR, f"extraction started inventing — {score}"


def test_the_numbers_are_reported_even_when_they_pass(capsys):
    """A gate that only speaks when it fails is a number nobody watches."""
    score = golden.Score()
    per_case: list[tuple[str, float]] = []
    for case in golden.load_jds():
        one = golden.Score()
        one.add(_extracted(case), golden.keys(case.requirements))
        score.add(_extracted(case), golden.keys(case.requirements))
        per_case.append((case.id, one.f1))

    with capsys.disabled():
        print(f"\n  AC-2.3 overall: {score}")
        print(
            f"  target {golden.AC_2_3_TARGET}, floor {F1_FLOOR}, "
            f"measures_real_world={golden.MEASURES_REAL_WORLD}"
        )
        for case_id, f1 in sorted(per_case, key=lambda pair: pair[1]):
            print(f"    {f1:.3f}  {case_id}")

    assert score.expected > 0


def test_the_corpus_is_honest_about_what_it_is():
    """The flag is a claim about the CORPUS, not about the code.

    A synthetic golden set quietly relabelled as acceptance evidence is how a
    project ends up believing it met a bar it never tested. Flipping this is a
    deliberate act that goes with replacing the documents.
    """
    assert golden.MEASURES_REAL_WORLD is False
    assert len(golden.load_jds()) >= 12, "the corpus shrank"


# ---------------------------------------------------------------------------
#  AC-2.4 — disjunctions
# ---------------------------------------------------------------------------


@pytest.mark.gate
def test_disjunction_detection_does_not_regress():
    """Scored as accuracy over 30 strings, positives and negatives together.

    The negatives are the half that matters: splitting "CI/CD" fabricates a
    skill, and this module's whole rule is that fabricating is worse than
    missing.
    """
    cases = golden.load_disjunctions()
    # Every part is treated as resolvable, which is what `disjunction_parts`
    # consults for the slash form. That isolates the SPLIT decision from the
    # ontology's coverage — otherwise this measures M04's alias table.
    resolved = {part: "concept:x" for case in cases for part in case.parts}

    wrong: list[str] = []
    for case in cases:
        got = tuple(disjunction_parts(case.text, resolved))
        if golden.keys(got) != golden.keys(case.parts):
            wrong.append(f"{case.text!r}: expected {list(case.parts)}, got {list(got)}")

    accuracy = 1 - len(wrong) / len(cases)
    assert accuracy >= DISJUNCTION_FLOOR, "disjunction accuracy fell:\n  " + "\n  ".join(wrong)


def test_a_single_name_containing_a_slash_is_never_split():
    """The negatives, asserted on their own so a regression names itself.

    "CI/CD" and "TCP/IP" are single names far more often than "React/Angular"
    is two, and a wrong split is a fabricated skill.
    """
    negatives = [case for case in golden.load_disjunctions() if not case.parts]
    assert negatives, "the corpus lost its negative cases"

    for case in negatives:
        assert disjunction_parts(case.text, {}) == [], f"{case.text!r} was split"


# ---------------------------------------------------------------------------
#  The archetype match, on the same corpus
# ---------------------------------------------------------------------------


def test_every_golden_role_title_is_recognisable_or_honestly_not():
    """Not an accuracy floor — a check that the match never guesses.

    A wrong archetype backfills eight requirements for a job nobody advertised,
    which is worse than the thin plan it was fixing because it looks complete.
    So the assertion is about the REFUSAL: whatever it returns, it is either a
    real archetype or None, never a low-confidence pick.
    """
    for case in golden.load_jds():
        archetype, confidence = match_archetype(case.role, case.text)
        if archetype is not None:
            assert confidence >= 0.30, f"{case.role!r} matched at {confidence}"
