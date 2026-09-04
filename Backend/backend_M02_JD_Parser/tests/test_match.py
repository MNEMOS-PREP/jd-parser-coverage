"""The resume against the posting (FR-2.15).

The sentence this file is about is *"you have 7.2, cutoff is 7.5"*, and the
tests that matter most are the ones where it REFUSES to say it. §3.2.2 makes
eligibility a hard filter, so a wrong comparison does not mis-rank a
requirement — it tells a student they cannot sit a drive they are eligible for.

M01 is faked at the HTTP boundary rather than imported. M02 must work when M01
is a different process on a different port that may or may not be running, and
a test that reached into M01's code would prove something about a deployment
this platform does not have.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
import uuid

import pytest
from backend_M02_JD_Parser import router as router_module
from backend_M02_JD_Parser.app import app
from backend_M02_JD_Parser.match import read_grade
from backend_M02_JD_Parser.router import get_db
from fastapi.testclient import TestClient

ELIGIBILITY_JD = """Software Engineer

Requirements:
- Strong SQL
- Dynamic Programming
- Recursion

Eligibility: minimum 7.5 CGPA, 2026 batch.
"""


def _resume(**overrides) -> dict:
    """A ResumeOut-shaped payload, with only the fields M02 reads."""
    body = {
        "id": str(uuid.uuid4()),
        "is_active": True,
        "confirmed": True,
        "parsed_skills": ["SQL", "Python"],
        "unresolved_skills": [],
        "resolved_concepts": {"SQL": "concept:sql_queries"},
        "red_flags": [],
        "entities": {
            "education": [
                {
                    "institution": "Amrita",
                    "degree": "B.Tech",
                    "grade": "8.1",
                    "dates": {"raw": "2022-2026", "start_year": 2022, "end_year": 2026},
                    "line": "B.Tech, CGPA 8.1",
                    "start": 0,
                    "end": 20,
                }
            ]
        },
    }
    body.update(overrides)
    return body


class _M01Response:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode("utf-8")
        self.status = 200

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture(name="m01")
def m01_fixture(monkeypatch, m04):
    """M01 answering over HTTP, or not.

    Layered on the `m04` fixture because it monkeypatches the same `urlopen`;
    this one delegates anything that is not an M01 URL back to it, so a test
    can have both upstreams in whatever state it needs.
    """

    class Fake:
        def __init__(self):
            self.resumes: list[dict] = []
            self.registry = router_module.dependency_registry()
            self.down()

        def down(self):
            self.registry._cache["M01"] = (time.monotonic(), False, "unreachable (test)")

        def up(self, resumes=None):
            self.registry._cache["M01"] = (time.monotonic(), True, "healthy (200)")
            self.resumes = resumes if resumes is not None else [_resume()]

        def urlopen(self, req, timeout=None):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if "8101" not in url and "/v1/resumes/" not in url:
                return m04.urlopen(req, timeout=timeout)
            if url.endswith("/health"):
                if not self.registry._cache["M01"][1]:
                    raise urllib.error.URLError("connection refused (test)")
                return _M01Response({"status": "ok", "module": "M01"})
            if "/v1/resumes/candidate/" in url:
                return _M01Response(self.resumes)
            raise AssertionError(f"unexpected M01 call: {url}")

    fake = Fake()
    monkeypatch.setattr(urllib.request, "urlopen", fake.urlopen)
    yield fake
    router_module.dependency_registry.cache_clear()


@pytest.fixture(name="matched")
def matched_fixture(session, m01):
    """A client, and a helper that parses a JD and returns the match report."""

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    # The same admin principal `conftest`'s `client` uses; `test_access.py`
    # is where refusals are asserted with real student principals.
    client = TestClient(app, headers={"X-Role": "admin", "X-Candidate-Id": "test-admin"})

    def _match(text=ELIGIBILITY_JD, candidate_id=None):
        candidate_id = candidate_id or uuid.uuid4()
        res = client.post(
            "/v1/jds/parse",
            json={"company_name": "Acme", "role_title": "SWE", "raw_text": text},
        )
        assert res.status_code in (200, 201), res.text
        jd_id = res.json()["id"]
        got = client.get(f"/v1/jds/{jd_id}/match/{candidate_id}")
        assert got.status_code == 200, got.text
        return got.json()

    yield _match
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
#  The sentence FR-2.15 asks for
# ---------------------------------------------------------------------------


def test_the_cutoff_comparison_finally_happens(matched, m01):
    """*"you have 7.2, cutoff is 7.5"* — the sentence M02 could not say.

    The cutoff has been parsed since 2026-08-25 and the comparison was
    impossible, because the left-hand side lives in M01 and M02 did not read
    M01. The banner stated the bar and stopped, which was right at the time.
    """
    m01.up(
        [
            _resume(
                entities={"education": [{"grade": "7.2", "line": "CGPA 7.2", "start": 0, "end": 8}]}
            )
        ]
    )

    report = matched()
    cgpa = next(v for v in report["verdicts"] if v["criterion"] == "cgpa")

    assert cgpa["state"] == "fails"
    assert "7.2" in cgpa["detail"] and "7.5" in cgpa["detail"]
    # And it is the top risk, above every skill gap. §3.2.2: a hard filter.
    assert report["risks"][0]["severity"] == "blocking"


def test_clearing_the_bar_says_so_plainly(matched, m01):
    m01.up()  # 8.1 CGPA against a 7.5 cutoff

    report = matched()
    cgpa = next(v for v in report["verdicts"] if v["criterion"] == "cgpa")

    assert cgpa["state"] == "meets"
    assert not [r for r in report["risks"] if r["severity"] == "blocking"]


# ---------------------------------------------------------------------------
#  The comparisons it REFUSES to make
# ---------------------------------------------------------------------------


def test_a_percentage_is_not_converted_to_a_cgpa(matched, m01):
    """ "82%" is not 8.2, and the factor differs per university.

    Converting would be the single most damaging guess on this screen: it
    decides whether a student believes they can sit a drive at all. So the
    scale mismatch is reported and the student is told to check that one
    themselves.
    """
    m01.up(
        [_resume(entities={"education": [{"grade": "82%", "line": "82%", "start": 0, "end": 3}]})]
    )

    report = matched()
    cgpa = next(v for v in report["verdicts"] if v["criterion"] == "cgpa")

    assert cgpa["state"] == "scale_mismatch"
    assert "82%" in cgpa["detail"]
    # Not blocking — we did not establish a failure, we declined to guess.
    assert all(r["severity"] != "blocking" for r in report["risks"])


def test_no_grade_on_the_resume_is_unknown_and_not_a_failure(matched, m01):
    """A student whose resume omits a CGPA is unassessed, not ineligible.

    The fix is on their resume rather than in their preparation, and calling it
    `fails` would send them to practise for a drive they may well clear.
    """
    m01.up(
        [_resume(entities={"education": [{"grade": None, "line": "B.Tech", "start": 0, "end": 6}]})]
    )

    report = matched()
    cgpa = next(v for v in report["verdicts"] if v["criterion"] == "cgpa")

    assert cgpa["state"] == "unknown"
    assert all(r["severity"] != "blocking" for r in report["risks"])


@pytest.mark.parametrize(
    ("raw", "scale"),
    [
        ("8.1", "cgpa_10"),
        ("9.12", "cgpa_10"),
        ("82%", "percent"),
        ("3.7/4", "gpa_4"),
        ("7.5 / 10", "cgpa_10"),
        ("85/100", "percent"),
        ("3.7", "unknown"),
        (None, "unknown"),
    ],
)
def test_a_grade_is_classified_by_what_the_resume_wrote(raw, scale):
    """Never by the size of the number.

    "9.1" is a 10-point CGPA and "9.1%" is a catastrophe, and the only thing
    separating them is a character a size heuristic would ignore. "3.7" with no
    notation is genuinely ambiguous — a strong 4-point GPA or a failing CGPA —
    so it stays `unknown` rather than being guessed, because the guess decides
    eligibility.
    """
    assert read_grade(raw).scale == scale


# ---------------------------------------------------------------------------
#  When M01 is not there
# ---------------------------------------------------------------------------


def test_an_unreachable_m01_is_not_a_missing_resume(matched, m01):
    """Two states that must never be conflated.

    "You have no resume" when the truth is "we cannot reach the resume service"
    sends a student off to re-upload a file they already uploaded.
    """
    m01.down()

    report = matched()

    assert report["resume_status"] == "m01_unreachable"
    assert report["resume_id"] is None
    # Empty, not falsely reassuring: no verdicts means nothing was checked.
    assert report["verdicts"] == []
    assert report["risks"] == []


def test_no_resume_on_file_says_exactly_that(matched, m01):
    m01.up([])

    report = matched()

    assert report["resume_status"] == "no_resume"
    assert report["verdicts"] == []


def test_a_missing_m01_never_stops_a_jd_being_parsed(matched, m01):
    """Rule 2: a missing dependency narrows scope, never quality.

    The requirements, the weights, the eligibility block and the coverage plan
    all still work. Only the comparison against the resume is gone.
    """
    m01.down()

    report = matched()

    assert report["resume_status"] == "m01_unreachable"
    assert report["jd_id"]


# ---------------------------------------------------------------------------
#  Evidence
# ---------------------------------------------------------------------------


def test_a_requirement_the_resume_never_mentions_is_a_risk(matched, m01):
    """ "Not mentioned" is not "cannot do".

    That distinction is the entire value of this screen — a recruiter screening
    on keywords reads the resume, not the student.
    """
    m01.up([_resume(parsed_skills=["SQL"], resolved_concepts={"SQL": "concept:sql_queries"})])

    report = matched()

    assert "SQL" in report["evidenced"]
    assert "Dynamic Programming" in report["unevidenced"]
    assert any("must-have" in risk["title"] for risk in report["risks"])


def test_an_unconfirmed_resume_is_flagged_low(matched, m01):
    """Everything above is computed from what we extracted, not what they
    verified. If we misread a grade, the whole report inherits it."""
    m01.up([_resume(confirmed=False)])

    report = matched()

    assert any(
        risk["severity"] == "low" and "confirmed" in risk["title"] for risk in report["risks"]
    )


def test_the_active_resume_is_the_one_compared(matched, m01):
    """M01 keeps every version a student uploads and marks one active.

    Matching against a superseded resume reports gaps the student already
    fixed, which is the most demoralising possible way to be wrong.
    """
    stale = _resume(is_active=False, parsed_skills=["COBOL"], resolved_concepts={})
    live = _resume(
        is_active=True, parsed_skills=["SQL"], resolved_concepts={"SQL": "concept:sql_queries"}
    )
    m01.up([stale, live])

    report = matched()

    assert report["resume_id"] == live["id"]
    assert "SQL" in report["evidenced"]


def test_a_choice_the_resume_answers_is_not_a_gap(matched, m01):
    """A posting saying "Python or Java" is met by Python.

    Found by running M01 and M02 against each other with real processes: the
    report told a student with Python that they were missing Java, off a
    posting that offered the choice. §3.2.1's "33% qualified" reading, arriving
    at the resume screen — the same bug the coverage endpoint had, reached by a
    different route, which is why the group is now consulted in both places.
    """
    m01.up([_resume(parsed_skills=["Python"], resolved_concepts={})])

    report = matched("Backend Engineer\n\nRequirements:\n- Strong Python or Java\n- SQL\n")

    assert "Python" in report["evidenced"]
    assert "Java" not in report["unevidenced"], "an answered choice was reported as a gap"
    assert report["met_by_alternative"]["Java"] == "Python"


def test_an_unanswered_choice_is_still_a_gap(matched, m01):
    """The group must not become a way to hide a miss.

    A resume mentioning neither alternative has not met the requirement, and
    exactly one of them carries that so the gap is reported once.
    """
    m01.up([_resume(parsed_skills=["COBOL"], resolved_concepts={})])

    report = matched("Backend Engineer\n\nRequirements:\n- Strong Python or Java\n- SQL\n")

    assert report["met_by_alternative"] == {}
    assert "Python" in report["unevidenced"] and "Java" in report["unevidenced"]


def test_alternatives_do_not_inflate_the_denominator(matched, m01):
    """`must_have_evidence` must not depend on how a company phrased one thing.

    Counting both halves of an answered choice makes a student who meets every
    requirement score below 100% purely because the posting wrote "or".
    """
    m01.up(
        [
            _resume(
                parsed_skills=["Python", "SQL"],
                resolved_concepts={"SQL": "concept:sql_queries"},
            )
        ]
    )

    report = matched("Backend Engineer\n\nRequirements:\n- Strong Python or Java\n- SQL\n")

    assert report["must_have_evidence"] == 1.0
