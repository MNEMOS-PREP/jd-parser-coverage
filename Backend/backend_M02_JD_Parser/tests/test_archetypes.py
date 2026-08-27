"""Role archetypes, backfill, and the door that does not need a JD.

§3.2.1 trap 1: *"The 40-word campus JD is the MEDIAN, not the edge case. A
parser tuned on LinkedIn-style JDs will emit three requirements and a useless
plan."*

The tests here are mostly about restraint. A backfill that fires too eagerly
buries what the company actually wrote; a match that fires on a weak signal
produces a plan for a job nobody advertised. Both look like success from the
outside, which is why they need assertions rather than judgement.
"""

from __future__ import annotations

import uuid

import pytest
from backend_M02_JD_Parser.archetypes import ARCHETYPES, backfill_labels
from backend_M02_JD_Parser.archetypes import match as match_archetype
from test_api import _parse_response, _plan


def _parse_as(client, text: str, role: str) -> dict:
    """Parse with an explicit role title.

    `_parsed` defaults the title to "Backend Engineer", which is invisible in
    most tests and decisive here: the archetype match is driven by the title,
    so a test that does not set one is testing the default.
    """
    res = _parse_response(client, text=text, role=role)
    assert res.status_code in (200, 201), res.text
    return res.json()


TINY_JD = """Software Engineer Trainee

Looking for SDE trainees. Good knowledge of DSA and OOPs.
"""

ZONAL_JD = """Zonal Officer Grade II

Requirements:
- Punctuality
"""

FULL_JD = """Backend Engineer

Requirements:
- Strong SQL
- Dynamic Programming
- Recursion
- Hashing
- Transactions
- REST APIs
"""


# ---------------------------------------------------------------------------
#  Matching
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Software Engineer Trainee", "sde_1"),
        ("SDE 1", "sde_1"),
        ("Backend Engineer", "backend_engineer"),
        ("Data Analyst", "data_analyst"),
        ("Data Scientist", "data_scientist"),
        ("Machine Learning Engineer", "ml_engineer"),
        ("QA Engineer", "qa_engineer"),
        ("DevOps Engineer", "devops_engineer"),
        ("Technical Support Engineer", "support_engineer"),
        ("Business Analyst", "business_analyst"),
        ("Human Resources Executive", "hr_recruiter"),
    ],
)
def test_a_title_is_matched_to_its_archetype(title, expected):
    """The title dominates deliberately.

    A posting titled "Data Analyst" is a data analyst whatever its bullets say,
    and the bullets on a campus posting are frequently boilerplate shared across
    every role the company is hiring for that season.
    """
    archetype, confidence = match_archetype(title)

    assert archetype is not None, f"{title!r} matched nothing (confidence {confidence})"
    assert archetype.id == expected


def test_a_longer_title_phrase_beats_a_shorter_one():
    """ "Data Engineer" must not be read as "Engineer".

    Matching on phrases rather than tokens is the entire reason the library is
    written as phrases, and a shorter generic match winning would quietly
    collapse eight archetypes into one.
    """
    archetype, _ = match_archetype("Data Engineer")

    assert archetype is not None and archetype.id == "data_engineer"


def test_an_unrecognisable_title_matches_nothing():
    """Backfilling eight requirements for a job nobody advertised is worse than
    the thin plan it was trying to fix, because it looks complete."""
    archetype, confidence = match_archetype("Zonal Officer Grade II")

    assert archetype is None
    # Reported anyway: "we looked and were not sure" is a different answer from
    # "we did not look", and the screen says so.
    assert confidence >= 0.0


def test_an_ambiguous_title_matches_nothing_rather_than_guessing():
    """§6.3's margin check.

    "Software / Data Engineer" scores two archetypes almost equally. Picking the
    higher by a hair is a coin toss the student cannot see, and it decides which
    eight requirements get invented.
    """
    archetype, _ = match_archetype("Software Engineer / Data Engineer")

    assert archetype is None


# ---------------------------------------------------------------------------
#  Backfill (§6.3)
# ---------------------------------------------------------------------------


def test_a_thin_posting_is_topped_up_to_eight(client, m04):
    """§6.3: *"if the JD yields < 5 measurable requirements, add archetype
    requirements up to 8, each marked `source=archetype`."*"""
    body = _parse_as(client, TINY_JD, "Software Engineer Trainee")

    assert body["role_archetype"] == "sde_1"
    assert body["inferred_count"] > 0
    assert len(body["requirements"]) >= 5
    assert len(body["requirements"]) <= 8 + 4, "backfill overshot its ceiling badly"


def test_every_inferred_requirement_says_it_is_inferred(client, m04):
    """`source="archetype"` and `span=None` travel together.

    That pair is what makes the addition auditable: a requirement with no span
    claiming to come from the JD would be a bug, and a screen can tell them
    apart without asking anybody.
    """
    body = _parse_as(client, TINY_JD, "Software Engineer Trainee")
    inferred = [r for r in body["requirements"] if r["source"] == "archetype"]

    assert inferred, "nothing was backfilled"
    for requirement in inferred:
        assert requirement["span"] is None, f"{requirement['text']} claims a span it cannot have"


def test_an_inferred_requirement_weighs_less_than_a_stated_one(client, m04):
    """§6.4's `source_w = 0.75`.

    The line has been in `_raw_weight` since weights landed and never had
    anything to apply to. It applies now, and it is what stops a backfilled set
    outvoting what the company actually wrote.
    """
    body = _parse_as(client, TINY_JD, "Software Engineer Trainee")
    stated = [r for r in body["requirements"] if r["source"] == "jd"]
    inferred = [r for r in body["requirements"] if r["source"] == "archetype"]

    assert stated and inferred
    # Compared at equal necessity so the multiplier under test is the only
    # difference: everything here is `should` except what the posting stressed.
    assert max(r["weight"] for r in stated) > min(r["weight"] for r in inferred)


def test_a_full_posting_is_not_topped_up(client, m04):
    """A posting with six real requirements does not need help.

    Adding to it would dilute what the company wrote — every stated requirement
    loses weight to an invented one, which is the opposite of the point.
    """
    body = _parse_as(client, FULL_JD, "Backend Engineer")

    assert body["inferred_count"] == 0
    assert all(r["source"] == "jd" for r in body["requirements"])


def test_the_backfill_does_not_duplicate_what_the_posting_said():
    """A JD that says "SQL" must not get a second "SQL" from the archetype."""
    archetype, _ = match_archetype("Backend Engineer")

    assert archetype is not None
    additions = backfill_labels(archetype, ["SQL", "DBMS"])

    assert "SQL" not in additions
    assert "DBMS" not in additions


def test_an_unmatched_posting_is_left_thin_rather_than_filled(client, m04):
    """Rule 2, applied to our own library: no match narrows scope.

    A thin plan is visibly thin. A plan filled from the wrong archetype is
    confident and wrong, and the student has no way to tell.
    """
    body = _parse_as(client, ZONAL_JD, "Zonal Officer Grade II")

    assert body["role_archetype"] is None
    assert body["inferred_count"] == 0


# ---------------------------------------------------------------------------
#  Role-only mode (FR-2.14)
# ---------------------------------------------------------------------------


def test_the_role_picker_lists_every_archetype(client, m04):
    res = client.get("/v1/archetypes")

    assert res.status_code == 200
    body = res.json()
    assert len(body) == len(ARCHETYPES)
    # Every entry shows what a mock for it covers, because "just pick a role"
    # is only trustworthy if the student can see what they are picking.
    assert all(entry["requirements"] for entry in body)
    assert all(entry["default_minutes"] > 0 for entry in body)


@pytest.mark.gate
def test_a_student_with_no_jd_can_still_prepare(client, m04):
    """§2.3: *"Door 3 is mandatory. A student in September with no drive
    scheduled still needs to practise. Requiring a JD to use the product would
    be a self-inflicted wound."*

    It was a self-inflicted wound until 2026-08-27 — with no posting there was
    no way into this module at all.
    """
    res = client.post("/v1/jds/from-role", json={"archetype_id": "sde_1"})

    assert res.status_code == 201, res.text
    body = res.json()

    assert body["role_archetype"] == "sde_1"
    assert len(body["requirements"]) >= 5
    assert all(r["source"] == "archetype" for r in body["requirements"])
    assert all(r["span"] is None for r in body["requirements"])


def test_role_only_stores_no_fabricated_posting(client, m04):
    """`raw_text` is EMPTY, not a plausible JD.

    Writing one and storing it would make the read-back screen quote sentences
    no company ever published, which is the single thing this module must never
    do.
    """
    body = client.post("/v1/jds/from-role", json={"archetype_id": "data_analyst"}).json()

    assert body["raw_text"] == ""
    assert body["eligibility"] == {}, "an invented posting cannot have an eligibility block"


def test_role_only_is_chosen_rather_than_inferred(client, m04):
    """A student saying "I am preparing for an SDE role" is not a match we made
    and were 0.62 sure of."""
    body = client.post("/v1/jds/from-role", json={"archetype_id": "sde_1"}).json()

    assert body["archetype_confidence"] == 1.0


def test_two_students_picking_one_role_share_it(client, m04):
    """Cached on the same terms as a pasted JD, because it IS one set."""
    first = client.post("/v1/jds/from-role", json={"archetype_id": "qa_engineer"})
    second = client.post("/v1/jds/from-role", json={"archetype_id": "qa_engineer"})

    assert first.status_code == 201
    assert second.status_code == 200, "a repeat pick created a second row"
    assert first.json()["id"] == second.json()["id"]


def test_an_unknown_role_says_where_the_list_is(client, m04):
    res = client.post("/v1/jds/from-role", json={"archetype_id": "wizard"})

    assert res.status_code == 404
    assert "/v1/archetypes" in res.json()["detail"]


def test_a_role_only_set_can_be_planned_against(client, m04_mastery):
    """The point of the door. A student who picked a role gets a real plan.

    If this produced a requirement set nothing could allocate over, door 3 would
    be a screen that ends in a dead end — which is what it replaced.
    """
    m04_mastery({"measured": []})
    jd_id = client.post("/v1/jds/from-role", json={"archetype_id": "sde_1"}).json()["id"]

    plan = _plan(client, jd_id, uuid.uuid4(), minutes=60)

    assert plan["allocations"], "a role-only set produced no plan"
    assert plan["allocated_minutes"] <= 60


def test_a_suggestion_the_posting_actually_made_is_not_inferred(client, m04):
    """The archetype found it; the company still said it.

    "Looking for SDE trainees. Good knowledge of DSA and OOPs." has no heading,
    so `_list_lines` never enters list mode and extraction returns nothing at
    all. The archetype then suggests OOPs — which IS in the document, at a real
    offset.

    Calling that requirement "inferred" would understate what the company asked
    for and discount its weight to 0.75 for a demand they made explicitly. So a
    suggested label that locates is `source="jd"`, and `source="archetype"`
    means exactly one thing: nothing in the document said this.
    """
    body = _parse_as(client, TINY_JD, "Software Engineer Trainee")
    by_text = {r["text"]: r for r in body["requirements"]}

    assert by_text["OOPs"]["source"] == "jd", "the posting says OOPs in so many words"
    assert by_text["OOPs"]["span"] is not None

    # And the pairing holds in both directions, which is what makes it auditable.
    for requirement in body["requirements"]:
        if requirement["source"] == "archetype":
            assert requirement["span"] is None
        if requirement["span"] is None:
            assert requirement["source"] == "archetype"


# ---------------------------------------------------------------------------
#  EC-2.14 — two roles in one posting
# ---------------------------------------------------------------------------


def test_an_ambiguous_title_names_the_roles_it_could_not_choose_between(client, m04):
    """*"Detect, ask the student which, default to the first."*

    `match` already refused this case — two archetypes inside `MIN_MARGIN` and
    it returns nothing rather than tossing a coin. That refusal was SILENT: no
    backfill, no explanation, and no way for the student to say which role they
    are actually sitting. Detecting it is the other half of a decision that was
    already being made.
    """
    body = _parse_as(client, FULL_JD, "Software Engineer / Data Engineer")

    assert body["role_archetype"] is None, "still refuses to guess"
    assert len(body["role_candidates"]) >= 2
    ids = [c["id"] for c in body["role_candidates"]]
    assert "sde_1" in ids or "data_engineer" in ids
    # Best first, so "default to the first" is the caller doing nothing.
    scores = [c["confidence"] for c in body["role_candidates"]]
    assert scores == sorted(scores, reverse=True)


def test_an_unambiguous_posting_is_asked_nothing(client, m04):
    """Empty is the signal that there was nothing to ask about.

    A picker that appears on every posting is a picker nobody reads.
    """
    body = _parse_as(client, FULL_JD, "Backend Engineer")

    assert body["role_archetype"] == "backend_engineer"
    assert body["role_candidates"] == []


def test_an_unrecognisable_title_offers_no_menu(client, m04):
    """Nothing scored high enough, which is different from two scoring alike.

    Listing every archetype that trailed by 0.3 would turn a real question into
    a menu of roles the posting is not for.
    """
    body = _parse_as(client, ZONAL_JD, "Zonal Officer Grade II")

    assert body["role_archetype"] is None
    assert body["role_candidates"] == []


# ---------------------------------------------------------------------------
#  EC-2.5 — a non-technical role does not open a coding round
# ---------------------------------------------------------------------------


def test_an_hr_posting_never_opens_a_coding_round(client, m04_mastery):
    """*"Non-technical role (HR, Sales) — technical rounds dropped."*

    Not "scored lower" — dropped. An HR executive's interview does not open a
    twelve-minute coding round because the JD mentioned SQL in passing, and a
    plan that budgets one is describing an interview that will not happen.
    """
    m04_mastery({"measured": []})
    res = _parse_response(
        client,
        text="HR Executive\n\nRequirements:\n- Communication\n- SQL\n- Data Structures\n",
        role="HR Executive",
    )
    jd_id = res.json()["id"]
    assert res.json()["role_archetype"] == "hr_recruiter"

    plan = _plan(client, jd_id, uuid.uuid4(), minutes=60)

    assert plan["allocations"], "nothing allocated"
    assert all(a["round_type"] == "verbal" for a in plan["allocations"])
    assert {r["round_type"] for r in plan["rounds"]} == {"verbal"}


def test_an_engineering_posting_still_gets_its_coding_round(client, m04_mastery):
    """The other side of the same rule, so the drop cannot quietly widen."""
    m04_mastery({"measured": []})
    res = _parse_response(
        client,
        text="Backend Engineer\n\nRequirements:\n- Data Structures\n- Algorithms\n",
        role="Backend Engineer",
    )
    jd_id = res.json()["id"]

    plan = _plan(client, jd_id, uuid.uuid4(), minutes=90)

    assert any(a["round_type"] == "coding" for a in plan["allocations"])
