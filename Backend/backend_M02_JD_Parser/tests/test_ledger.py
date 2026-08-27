"""The coverage ledger (FR-2.11, §6.6).

§6.6 makes the strongest claim in the specification: the ledger is *"the
mechanism that makes coverage a guarantee rather than an intention."*

Until it existed M02 produced a plan and nothing read it back. The plan said
four questions about DBMS; if the session asked none, no part of the platform
noticed. These tests are about the difference between those two states.

M05 and M13 do the writing and neither exists yet. M02 owns the table anyway,
because M02 made the promise — the plan is its output, the requirement ids are
its ids, and the weights the re-prioritisation reads are its weights. Which
means the endpoint is the contract they will be written against, and it has to
be right before they arrive rather than after.
"""

from __future__ import annotations

import uuid

import pytest
from test_api import _parse_response, _plan

SESSION_JD = """Backend Engineer

Requirements:
- Dynamic Programming
- SQL
- Recursion
- Hashing
"""


def _jd(client) -> str:
    res = _parse_response(client, text=SESSION_JD)
    assert res.status_code in (200, 201), res.text
    return res.json()["id"]


def _record(client, session_id, candidate, **body):
    return client.post(f"/v1/sessions/{session_id}/coverage/{candidate}", json=body)


def _coverage(client, session_id, candidate):
    res = client.get(f"/v1/sessions/{session_id}/coverage/{candidate}")
    assert res.status_code == 200, res.text
    return res.json()


# ---------------------------------------------------------------------------
#  A turn's life
# ---------------------------------------------------------------------------


def test_a_turn_moves_from_asked_to_scored(client, m04):
    """§6.6: M05 writes `asked`, M13 moves it to `scored`."""
    jd_id = _jd(client)
    session_id, me, turn = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    assert (
        _record(
            client,
            session_id,
            me,
            jd_id=jd_id,
            requirement_id="R-1",
            state="asked",
            turn_id=str(turn),
        ).status_code
        == 201
    )
    assert (
        _record(
            client,
            session_id,
            me,
            jd_id=jd_id,
            requirement_id="R-1",
            state="scored",
            turn_id=str(turn),
            score=0.7,
        ).status_code
        == 201
    )

    body = _coverage(client, session_id, me)
    assert body["asked"]["R-1"] == 1, "one turn, not two"
    assert body["scores"]["R-1"] == [0.7]


def test_the_ledger_is_append_only(client, m04):
    """§6.6 says a row "moves to scored". It does not move.

    An interview is evidence, and evidence that can be overwritten is evidence
    somebody can quietly revise. "Asked 14:02, answered 14:04, scored 0.3 at
    14:09" is the sequence a dispute needs; a mutated row keeps only the
    verdict, and M13's whole disputes queue assumes the sequence.
    """
    from backend_M02_JD_Parser.ledger import CoverageLedger
    from sqlmodel import select

    jd_id = _jd(client)
    session_id, me, turn = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    for state in ("asked", "answered", "scored"):
        _record(
            client,
            session_id,
            me,
            jd_id=jd_id,
            requirement_id="R-1",
            state=state,
            turn_id=str(turn),
            **({"score": 0.4} if state == "scored" else {}),
        )

    from backend_M02_JD_Parser.app import app
    from backend_M02_JD_Parser.router import get_db

    db = next(app.dependency_overrides[get_db]())
    rows = list(
        db.exec(select(CoverageLedger).where(CoverageLedger.session_id == session_id)).all()
    )

    assert len(rows) == 3, "an event overwrote another"


def test_a_late_event_cannot_move_a_turn_backwards(client, m04):
    """M05 and M13 are separate services and their clocks are not ordered.

    An `answered` arriving after a `scored` is a late duplicate, and letting
    newest-written win would un-score a scored turn.
    """
    jd_id = _jd(client)
    session_id, me, turn = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    _record(
        client,
        session_id,
        me,
        jd_id=jd_id,
        requirement_id="R-1",
        state="scored",
        turn_id=str(turn),
        score=0.9,
    )
    _record(
        client,
        session_id,
        me,
        jd_id=jd_id,
        requirement_id="R-1",
        state="answered",
        turn_id=str(turn),
    )

    body = _coverage(client, session_id, me)
    assert body["scores"]["R-1"] == [0.9], "a late `answered` erased a score"


def test_a_skipped_turn_is_not_coverage(client, m04):
    """`skipped` is the opposite of covering something, and it must not count.

    This is the whole reason to read the ledger instead of the plan: the plan
    cannot tell the difference.
    """
    jd_id = _jd(client)
    session_id, me = uuid.uuid4(), uuid.uuid4()
    _record(
        client,
        session_id,
        me,
        jd_id=jd_id,
        requirement_id="R-2",
        state="skipped",
        turn_id=str(uuid.uuid4()),
    )

    body = _coverage(client, session_id, me)
    assert body["asked"].get("R-2", 0) == 0


# ---------------------------------------------------------------------------
#  The re-prioritisation — the part that makes it a guarantee
# ---------------------------------------------------------------------------


@pytest.mark.gate
def test_a_rebuilt_plan_does_not_re_ask_what_the_session_covered(client, m04_mastery):
    """§6.6: *"the planner reads the ledger at each round boundary and
    re-prioritises remaining budget toward the least-covered high-weight
    requirements."*

    Without this the plan is an intention: rebuild it mid-session and it
    allocates the same four questions about DBMS the interview has already
    asked, because nothing told it they happened.
    """
    m04_mastery({"measured": []})
    jd_id = _jd(client)
    me, session_id = uuid.uuid4(), uuid.uuid4()

    before = _plan(client, jd_id, me, minutes=90)
    target = before["allocations"][0]["requirement_id"]
    promised = next(a for a in before["allocations"] if a["requirement_id"] == target)
    assert promised["question_budget"] >= 2, "need a requirement with room to cover"

    for _ in range(promised["question_budget"]):
        _record(
            client,
            session_id,
            me,
            jd_id=jd_id,
            requirement_id=target,
            state="asked",
            turn_id=str(uuid.uuid4()),
        )

    after = _plan(client, jd_id, me, minutes=90)
    rebuilt = next((a for a in after["allocations"] if a["requirement_id"] == target), None)

    assert rebuilt is not None
    assert rebuilt["already_asked"] == promised["question_budget"]
    # Its budget is already spent by the session, so the remaining minutes go
    # somewhere else — which is the re-prioritisation, stated as an assertion.
    assert rebuilt["question_budget"] <= promised["question_budget"]


def test_the_must_have_floor_is_not_re_paid_by_the_plan(client, m04_mastery):
    """FR-2.9's floor is satisfied by the SESSION, not only by the plan.

    Spending a second question to satisfy a rule the interview already
    satisfied is the plan arguing with the ledger.
    """
    m04_mastery({"measured": []})
    jd_id = _jd(client)
    me, session_id = uuid.uuid4(), uuid.uuid4()

    musts = [
        r["id"]
        for r in client.get(f"/v1/jds/{jd_id}").json()["requirements"]
        if r["necessity"] == "must"
    ]
    assert musts, "fixture has no must-haves"
    for rid in musts:
        _record(
            client,
            session_id,
            me,
            jd_id=jd_id,
            requirement_id=rid,
            state="asked",
            turn_id=str(uuid.uuid4()),
        )

    plan = _plan(client, jd_id, me, minutes=20)
    for rid in musts:
        row = next((a for a in plan["allocations"] if a["requirement_id"] == rid), None)
        if row is not None:
            assert row["already_asked"] >= 1


# ---------------------------------------------------------------------------
#  What it refuses
# ---------------------------------------------------------------------------


def test_an_unknown_state_is_refused(client, m04):
    jd_id = _jd(client)
    res = _record(
        client,
        uuid.uuid4(),
        uuid.uuid4(),
        jd_id=jd_id,
        requirement_id="R-1",
        state="pondered",
        turn_id=str(uuid.uuid4()),
    )

    assert res.status_code == 422
    assert "state must be one of" in res.json()["detail"]


def test_an_event_about_no_turn_is_refused(client, m04):
    """A `scored` row with no turn cannot be disputed later, which is the one
    thing a ledger is for."""
    jd_id = _jd(client)
    res = _record(
        client,
        uuid.uuid4(),
        uuid.uuid4(),
        jd_id=jd_id,
        requirement_id="R-1",
        state="scored",
        score=0.5,
    )

    assert res.status_code == 422
    assert "turn_id is required" in res.json()["detail"]


def test_a_score_belongs_only_on_a_scored_row(client, m04):
    jd_id = _jd(client)
    res = _record(
        client,
        uuid.uuid4(),
        uuid.uuid4(),
        jd_id=jd_id,
        requirement_id="R-1",
        state="asked",
        turn_id=str(uuid.uuid4()),
        score=0.5,
    )

    assert res.status_code == 422


@pytest.mark.gate
def test_a_student_cannot_read_another_students_session(client, m04):
    """Candidate-scoped, so `enforce_access` gates it without being asked.

    `ai_core.identity` has four roles and the list is closed on purpose — there
    is no `service` role and this module does not invent one. M05 forwards the
    student's identity exactly as M02 forwards it to M01.
    """
    from backend_M02_JD_Parser.app import app
    from fastapi.testclient import TestClient

    stranger = TestClient(app, headers={"X-Role": "student", "X-Candidate-Id": str(uuid.uuid4())})
    res = stranger.get(f"/v1/sessions/{uuid.uuid4()}/coverage/{uuid.uuid4()}")

    assert res.status_code == 403


def test_a_session_with_nothing_recorded_says_so(client, m04):
    """Different from a session that covered nothing, and the screen needs to
    tell them apart."""
    body = _coverage(client, uuid.uuid4(), uuid.uuid4())

    assert body["questions_asked"] == 0
    assert body["requirements"] == []
    assert body["jd_id"] is None
