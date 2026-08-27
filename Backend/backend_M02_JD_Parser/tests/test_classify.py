"""What kind of requirement is this, and what could test it (FR-2.2, §3.2.1).

Most of this file is §3.2.1's trap 3, which is a three-way distinction the
platform gets wrong in both directions if it collapses it: invent a score for
"go-getter attitude", or throw away "communication", which M12 and M17 really do
measure.

The rest is about `measured_by` reaching the plan, because that is the field's
whole reason to exist. A classification nothing prices is decoration.
"""

from __future__ import annotations

import uuid

import pytest
from backend_M02_JD_Parser.classify import kind_of, measured_by, seniority_of
from backend_M02_JD_Parser.plan import MINUTES_PER_QUESTION, round_for
from test_api import _parsed, _plan  # the helpers, not a second copy of them

# ---------------------------------------------------------------------------
#  Trap 3: three tiers, not one
# ---------------------------------------------------------------------------


def test_communication_maps_to_something_that_measures_it():
    """§3.2.1: *"'Communication' maps to real measured constructs (M12/M17)."*"""
    assert measured_by("excellent written and verbal communication") == ["communication"]


def test_a_team_player_maps_to_a_behavioural_probe():
    """§3.2.1: *"'Team player' maps to behavioural probes (M6 HR round)."*"""
    assert measured_by("Must be a team player") == ["behavioural"]


def test_an_attitude_maps_to_nothing_and_says_so():
    """§3.2.1: *"'Go-getter attitude' maps to nothing — mark it `unmeasurable`
    and say so rather than faking a score."*

    An empty list is the answer, not a gap in the lexicon. Nothing in this
    platform produces evidence about somebody's attitude, and a score beside it
    would be invented.
    """
    assert measured_by("A go-getter attitude") == []
    assert measured_by("Self-starter with passion") == []
    # Still a requirement, and still a soft skill. Both facts at once.
    assert kind_of("A go-getter attitude", measured=[]) == "soft_skill"


def test_an_adjective_does_not_make_a_real_requirement_unmeasurable():
    """ "Passionate about distributed systems" is a design requirement.

    The unmeasurable check runs against the LABEL only, not the surrounding
    line — otherwise one enthusiastic adjective anywhere in a bullet would
    silence every requirement on it.
    """
    assert measured_by("distributed systems", context="Passionate about distributed systems") == [
        "design"
    ]


# ---------------------------------------------------------------------------
#  measured_by, and the price it sets
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("DSA", "coding"),
        ("Dynamic Programming", "coding"),
        ("problem solving", "coding"),
        ("System design", "design"),
        ("scalability", "design"),
        ("microservices", "design"),
        ("Docker", "technical"),
        ("Python", "technical"),
        ("aptitude", "aptitude"),
        ("logical reasoning", "aptitude"),
    ],
)
def test_a_requirement_is_measured_by_what_would_actually_test_it(label, expected):
    assert expected in measured_by(label)


def test_an_unclassified_requirement_defaults_to_the_cheapest_round():
    """A wrong default that OVERPRICES fits fewer questions than it should.

    A wrong default that underprices promises a 45-minute mock that takes two
    hours. Between an under-full session and a broken promise, the first is
    recoverable — so the default is verbal.
    """
    assert measured_by("Kubernetes") == ["technical"]
    assert round_for(measured_by("Kubernetes")) == "verbal"


def test_a_requirement_measured_several_ways_is_priced_at_the_dearest():
    """ "DSA and system design" needs the design slot.

    Pricing it as coding fits a twelve-minute question into a slot that needs
    twenty, and the session runs over by the difference every time — silently,
    because nothing downstream re-checks the arithmetic.
    """
    modes = measured_by("DSA and system design")

    assert "coding" in modes and "design" in modes
    assert round_for(modes) == "design"
    assert MINUTES_PER_QUESTION[round_for(modes)] == 20.0


def test_the_context_line_carries_the_signal_the_label_lost():
    """A bare "communication" is one word; the line around it is where the
    signal usually is."""
    assert measured_by("communication") == ["communication"]
    assert "design" in measured_by(
        "scalability", context="- Understanding of system design and scalability"
    )


# ---------------------------------------------------------------------------
#  kind
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("Docker", "tool"),
        ("Jenkins", "tool"),
        ("fintech", "domain"),
        ("B.Tech", "qualification"),
        ("Python", "hard_skill"),
        ("team player", "soft_skill"),
    ],
)
def test_kind_reads_what_sort_of_thing_the_requirement_is(label, expected):
    assert kind_of(label, measured=measured_by(label)) == expected


def test_a_two_letter_degree_needs_its_dots():
    """`b.?e` matched the word "be".

    So "Must be a team player" classified as a QUALIFICATION — wrong, and the
    kind of wrong that looks deliberate on screen rather than like a regex
    accident.
    """
    label = "Must be a team player"

    assert kind_of(label, measured=measured_by(label)) == "soft_skill"


# ---------------------------------------------------------------------------
#  seniority_signal
# ---------------------------------------------------------------------------


def test_seniority_is_read_from_the_plural_a_posting_actually_writes():
    """A posting says "we are hiring FRESHERS", never "we are hiring fresher".

    The lexicon is anchored on both sides, so the singular form matched nothing
    at all in the sentence postings write.
    """
    assert seniority_of("We are hiring freshers for the 2026 batch.") == "fresher"
    assert seniority_of("Summer interns wanted") == "intern"
    assert seniority_of("Senior Backend Engineer") == "senior"


def test_silence_about_seniority_is_none_and_not_fresher():
    """This platform's users are overwhelmingly freshers.

    Defaulting to `fresher` would make the field always agree with the audience
    and therefore never inform anything — a field that cannot be wrong cannot
    be useful.
    """
    assert seniority_of("Backend Engineer\n\nRequirements:\n- Python\n") is None


def test_seniority_is_one_reading_for_the_whole_posting(client, m04):
    """A posting says it once, at the top, and every requirement inherits it.

    Scanning per requirement would find it on one row and leave the rest
    silent, which reads as disagreement rather than as one statement.
    """
    body = _parsed(
        client,
        "Backend Engineer\n\nWe are hiring freshers.\n\nRequirements:\n- Python\n- SQL\n",
    )

    signals = {r["seniority_signal"] for r in body["requirements"]}
    assert signals == {"fresher"}


# ---------------------------------------------------------------------------
#  It reaches the plan, which is the point
# ---------------------------------------------------------------------------


def test_a_coding_requirement_costs_a_coding_question(client, m04_mastery):
    """§6.5 prices coding at twelve minutes. Until `measured_by` existed this
    file priced everything at three and a half, which oversold a 45-minute
    session against four coding requirements by a factor of three."""
    m04_mastery({"measured": []})
    res = client.post(
        "/v1/jds/parse",
        json={
            "company_name": "Acme",
            "role_title": "SWE",
            "raw_text": "SWE\n\nRequirements:\n- Dynamic Programming\n- Recursion\n",
        },
    )
    jd_id = res.json()["id"]

    plan = _plan(client, jd_id, uuid.uuid4(), minutes=45)

    assert all(a["round_type"] == "coding" for a in plan["allocations"])
    assert all(a["minutes"] == a["question_budget"] * 12.0 for a in plan["allocations"])
    assert plan["allocated_minutes"] <= 45


def test_a_requirement_nothing_can_measure_gets_no_questions(client, m04_mastery):
    """Trap 3 reaching the allocator.

    Spending interview minutes on "go-getter attitude" produces nothing to
    score. It stays in the report as `unmeasurable` — the posting asked for it
    and hiding that would hide what the company said — and out of the budget.
    """
    m04_mastery({"measured": []})
    res = client.post(
        "/v1/jds/parse",
        json={
            "company_name": "Acme",
            "role_title": "SWE",
            "raw_text": "SWE\n\nRequirements:\n- Dynamic Programming\n- A go-getter attitude\n",
        },
    )
    jd_id = res.json()["id"]

    plan = _plan(client, jd_id, uuid.uuid4(), minutes=45)
    allocated = {a["requirement_text"] for a in plan["allocations"]}

    # "go-getter attitude", not "A go-getter attitude": the leading article is
    # peeled now, which is what makes the label the thing rather than a phrase
    # about the thing.
    assert "go-getter attitude" not in allocated
    assert "go-getter attitude" in plan["unmeasurable"]
