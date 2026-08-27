"""The student corrects a parse they do not own (FR-2.10).

Extraction scores F1 0.857, which reads better than it lives: roughly one row in
seven is wrong, and a student looking at a requirement the posting never made
had no way to say so. §3.2 lists the editable read-back as the counter to the
whole "parse produces obvious nonsense" risk, and it was the part never built.

The test that matters most here is not that an edit works. It is that an edit
CANNOT reach anybody else. FR-2.12 caches one parse across every student who
pastes the same posting, so `JobDescription` is not one student's document, and
a `PATCH` that wrote to it would let any student silently rewrite what
fifty-nine others see.
"""

from __future__ import annotations

import uuid

import pytest
from test_api import _parse_response

EDIT_JD = """Backend Engineer

Requirements:
- Strong Python and SQL
- Experience with Docker
- Familiarity with Git

Nice to have:
- Exposure to Kafka
"""


def _jd(client) -> str:
    res = _parse_response(client, text=EDIT_JD)
    assert res.status_code in (200, 201), res.text
    return res.json()["id"]


def _effective(client, jd_id, candidate):
    res = client.get(f"/v1/jds/{jd_id}/requirements/{candidate}")
    assert res.status_code == 200, res.text
    return res.json()


def _edit(client, jd_id, candidate, **body):
    res = client.post(f"/v1/jds/{jd_id}/requirements/{candidate}", json=body)
    assert res.status_code == 201, res.text
    return res.json()


def _texts(body) -> list[str]:
    return [r["text"] for r in body["requirements"]]


# ---------------------------------------------------------------------------
#  The three things a student knows better than the parser
# ---------------------------------------------------------------------------


def test_a_requirement_the_posting_never_made_can_be_removed(client, m04):
    jd_id = _jd(client)
    me = uuid.uuid4()
    assert "Docker" in _texts(_effective(client, jd_id, me))

    body = _edit(client, jd_id, me, action="remove", target="Docker")

    assert "Docker" not in _texts(body)
    assert body["edit_count"] == 1


def test_a_requirement_the_parser_missed_can_be_added(client, m04):
    jd_id = _jd(client)
    me = uuid.uuid4()

    body = _edit(client, jd_id, me, action="add", target="Terraform")

    assert "Terraform" in _texts(body)


def test_an_added_requirement_is_marked_as_the_students_own(client, m04):
    """§5's `source` enum has carried `user` since the spec was written and
    nothing had ever produced it.

    It matters for the same reason `archetype` does: §6.4 discounts anything
    that is not `jd` to 0.75, so a student's addition counts, and counts
    slightly less than what the company actually wrote.
    """
    jd_id = _jd(client)
    me = uuid.uuid4()

    body = _edit(client, jd_id, me, action="add", target="Terraform")
    added = next(r for r in body["requirements"] if r["text"] == "Terraform")

    assert added["source"] == "user"


def test_necessity_can_be_corrected(client, m04):
    """The posting's wording was ambiguous and the student read the room."""
    jd_id = _jd(client)
    me = uuid.uuid4()
    before = next(r for r in _effective(client, jd_id, me)["requirements"] if r["text"] == "Kafka")
    assert before["necessity"] == "could"

    body = _edit(client, jd_id, me, action="necessity", target="Kafka", value="must")
    after = next(r for r in body["requirements"] if r["text"] == "Kafka")

    assert after["necessity"] == "must"


# ---------------------------------------------------------------------------
#  The shared parse is never written to
# ---------------------------------------------------------------------------


@pytest.mark.gate
def test_one_students_edit_cannot_reach_another(client, m04):
    """§3.2.4: *"the parse is shared, the gap analysis is per-student."*

    A `PATCH` that mutated `jd.requirements` would let any student delete a
    requirement they personally do not have, and everyone else's coverage plan
    would quietly stop testing it. That is not a permissions bug to fix with a
    check — it is the wrong shape, and this is the assertion that keeps it out.
    """
    jd_id = _jd(client)
    me, them = uuid.uuid4(), uuid.uuid4()

    _edit(client, jd_id, me, action="remove", target="Docker")

    assert "Docker" not in _texts(_effective(client, jd_id, me))
    assert "Docker" in _texts(_effective(client, jd_id, them)), "an edit leaked across students"


@pytest.mark.gate
def test_the_stored_parse_is_untouched(client, m04):
    """The other half of the same rule, asserted against the shared row itself."""
    jd_id = _jd(client)
    me = uuid.uuid4()
    _edit(client, jd_id, me, action="remove", target="Docker")
    _edit(client, jd_id, me, action="add", target="Terraform")

    shared = client.get(f"/v1/jds/{jd_id}").json()
    texts = [r["text"] for r in shared["requirements"]]

    assert "Docker" in texts
    assert "Terraform" not in texts


# ---------------------------------------------------------------------------
#  Everything downstream re-derives
# ---------------------------------------------------------------------------


def test_removing_a_requirement_redistributes_its_weight(client, m04):
    """§6.4 normalises across the set, so a removal is not a subtraction.

    Patching the stored list instead would leave the weights summing to less
    than one, and every "% of the ask" on the screen would be quietly wrong.
    """
    jd_id = _jd(client)
    me = uuid.uuid4()
    before = _effective(client, jd_id, me)
    assert sum(r["weight"] for r in before["requirements"]) == pytest.approx(1.0, abs=0.01)

    after = _edit(client, jd_id, me, action="remove", target="Docker")

    assert sum(r["weight"] for r in after["requirements"]) == pytest.approx(1.0, abs=0.01)
    assert len(after["requirements"]) == len(before["requirements"]) - 1


def test_a_corrected_necessity_changes_the_weight(client, m04):
    """Necessity is a multiplier in §6.4, not a label beside one.

    Applied during `locate` rather than to the finished list, so the whole set
    renormalises around the correction.
    """
    jd_id = _jd(client)
    me = uuid.uuid4()
    before = next(r for r in _effective(client, jd_id, me)["requirements"] if r["text"] == "Kafka")

    body = _edit(client, jd_id, me, action="necessity", target="Kafka", value="must")
    after = next(r for r in body["requirements"] if r["text"] == "Kafka")

    assert after["weight"] > before["weight"]
    assert sum(r["weight"] for r in body["requirements"]) == pytest.approx(1.0, abs=0.01)


def test_edits_apply_in_order_so_clicking_twice_does_what_it_looks_like(client, m04):
    jd_id = _jd(client)
    me = uuid.uuid4()

    _edit(client, jd_id, me, action="remove", target="Docker")
    body = _edit(client, jd_id, me, action="add", target="Docker")

    assert "Docker" in _texts(body)


def test_the_corrections_can_be_thrown_away(client, m04):
    """A real button, because a student who made three edits and cannot
    remember which is left with a list they do not trust."""
    jd_id = _jd(client)
    me = uuid.uuid4()
    _edit(client, jd_id, me, action="remove", target="Docker")
    _edit(client, jd_id, me, action="add", target="Terraform")

    res = client.delete(f"/v1/jds/{jd_id}/requirements/{me}")

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["removed"] == 2
    assert body["edit_count"] == 0
    assert "Docker" in _texts(body)
    assert "Terraform" not in _texts(body)


# ---------------------------------------------------------------------------
#  What an edit is not allowed to say
# ---------------------------------------------------------------------------


def test_an_unknown_action_is_refused(client, m04):
    jd_id = _jd(client)
    res = client.post(
        f"/v1/jds/{jd_id}/requirements/{uuid.uuid4()}",
        json={"action": "rewrite", "target": "Docker"},
    )

    assert res.status_code == 422
    assert "action must be one of" in res.json()["detail"]


def test_a_necessity_outside_the_three_is_refused(client, m04):
    jd_id = _jd(client)
    res = client.post(
        f"/v1/jds/{jd_id}/requirements/{uuid.uuid4()}",
        json={"action": "necessity", "target": "Docker", "value": "critical"},
    )

    assert res.status_code == 422


@pytest.mark.gate
def test_a_student_cannot_edit_another_students_view(client, m04, session):
    """Candidate-scoped, so `enforce_access` gates it without being asked to.

    The router-level dependency is what makes this true for endpoints nobody
    has written yet — a per-route check is the one somebody omits on the
    sixteenth endpoint, and the sixteenth endpoint is the one that leaks.
    """
    from backend_M02_JD_Parser.app import app
    from fastapi.testclient import TestClient

    jd_id = _jd(client)
    stranger = TestClient(app, headers={"X-Role": "student", "X-Candidate-Id": str(uuid.uuid4())})

    res = stranger.post(
        f"/v1/jds/{jd_id}/requirements/{uuid.uuid4()}",
        json={"action": "remove", "target": "Docker"},
    )

    assert res.status_code == 403
