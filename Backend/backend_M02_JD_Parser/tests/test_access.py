"""Who may read whose coverage (Platform_Core `ai_core.identity`).

Every other test file here runs as an admin on purpose — they are about parsing,
resolution and gap reporting, and putting authorisation scaffolding into two
dozen of them means the first person to get it slightly wrong "fixes" it by
weakening the check. This is the file that sends real student principals.

── What was true until now ─────────────────────────────────────────────────────

Nothing. `candidate_id` arrived from the caller and was trusted, so
`GET /v1/jds/{id}/coverage/{candidate_id}` returned any student's gap analysis —
which topics they are weak on, which the ontology has never measured — to
whoever changed the UUID in the URL.

── What stays open, and why that is not an oversight ───────────────────────────

The JD routes. A job description is a public posting a company wrote; it is not
personal data, and FR-2.12 makes that explicit by caching one parse ACROSS
students. Gating it would mean two students preparing for the same drive each
hold a private copy of a public document, and would still protect nothing.

The line is `candidate_id`: the JD is the company's, the gap is the student's.
"""

from __future__ import annotations

import uuid

import pytest
from backend_M02_JD_Parser.app import app
from backend_M02_JD_Parser.router import get_db
from fastapi.testclient import TestClient

JD_TEXT = """Software Engineer, Backend

Requirements:
- Strong Python and SQL
- Experience with Docker and Kubernetes
"""


@pytest.fixture(name="as_student")
def as_student_fixture(session, m04):
    """A client that is one named student and nobody else."""

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db

    def _client(candidate_id: str) -> TestClient:
        return TestClient(app, headers={"X-Role": "student", "X-Candidate-Id": str(candidate_id)})

    yield _client
    app.dependency_overrides.clear()


@pytest.fixture(name="anonymous")
def anonymous_fixture(session, m04):
    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _jd(client) -> str:
    res = client.post(
        "/v1/jds/parse",
        json={"company_name": "Acme", "role_title": "Backend Engineer", "raw_text": JD_TEXT},
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


# ---------------------------------------------------------------------------
#  The attack that worked yesterday
# ---------------------------------------------------------------------------


@pytest.mark.gate
def test_a_student_cannot_read_another_students_coverage(as_student):
    """Changing the UUID in the URL used to return somebody else's gaps.

    A coverage report says which topics a named student is weak on and which
    have never been measured. It is the most sensitive thing this module holds
    and it was the only thing it served without asking who was calling.
    """
    me = str(uuid.uuid4())
    victim = str(uuid.uuid4())
    jd_id = _jd(as_student(me))

    res = as_student(me).get(f"/v1/jds/{jd_id}/coverage/{victim}")

    assert res.status_code == 403
    assert "not your record" in res.json()["detail"]


@pytest.mark.gate
def test_anonymous_gets_nothing_and_is_told_why(as_student, anonymous):
    """Fail closed, and loudly.

    Not an empty coverage report — that is the failure mode that survives
    review, because "no gaps found" looks like good news rather than like a
    refusal.
    """
    me = str(uuid.uuid4())
    jd_id = _jd(as_student(me))

    res = anonymous.get(f"/v1/jds/{jd_id}/coverage/{me}")

    assert res.status_code == 403
    assert "signed in" in res.json()["detail"]


def test_a_student_can_read_their_own_coverage(as_student):
    me = str(uuid.uuid4())
    jd_id = _jd(as_student(me))

    assert as_student(me).get(f"/v1/jds/{jd_id}/coverage/{me}").status_code == 200


# ---------------------------------------------------------------------------
#  What stays open
# ---------------------------------------------------------------------------


def test_a_job_description_is_not_personal_data(anonymous):
    """The JD routes are deliberately ungated.

    A posting is the company's, not the student's, and FR-2.12 caches one parse
    across students on purpose. Gating this would give two students preparing
    for the same drive a private copy each of a public document, and protect
    nothing.
    """
    jd_id = _jd(anonymous)

    assert anonymous.get(f"/v1/jds/{jd_id}").status_code == 200
    assert anonymous.get("/v1/deps").status_code == 200
    assert anonymous.get("/health").status_code == 200


def test_the_mastery_read_from_m04_is_made_as_the_student(m04_mastery):
    """M04 refuses an anonymous caller on every candidate route since
    2026-09-23. Until then it answered anybody, so M02 never said who it was
    asking for — and the day M04 closed, every gap analysis would have lost
    its mastery and reported every topic as unmeasured."""
    from backend_M02_JD_Parser.router import get_candidate_mastery

    fake = m04_mastery({"measured": []})
    candidate = uuid.uuid4()

    assert get_candidate_mastery(candidate) is not None

    (read,) = [r for r in fake.requests if "/mastery" in getattr(r, "full_url", str(r))]
    headers = {k.lower(): v for k, v in read.header_items()}
    assert headers["x-candidate-id"] == str(candidate)
    assert headers["x-role"] == "student"
