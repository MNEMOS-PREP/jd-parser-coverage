"""Saved jobs and resume tailoring (`workspace.py`, `tailoring.py`, 2026-11-17).

What is pinned is what would make a student stop trusting the screen:

- A job they read is still there tomorrow, theirs alone, renamable, deletable.
- Evidence is graded honestly: shown in work, only listed, said in other
  words, or absent — and a keyword typed into a tailored line that the
  uploaded resume never had is flagged, not counted.
- A suggestion never adds a fact. A missing requirement is a question.
- Every suggestion says what, why, which line of the posting, and what it
  improves — quoting the two documents, not generic advice.
"""

from __future__ import annotations

import uuid

import pytest
from backend_M02_JD_Parser.app import app
from backend_M02_JD_Parser.router import get_db
from backend_M02_JD_Parser.tailoring import (
    TailorBlock,
    TailorIn,
    TailorResume,
    analyse,
    find,
    forms,
    implied_choices,
)
from fastapi.testclient import TestClient

JD = """Requirements:
- Strong programming skills in Python and SQL.
- Experience building REST APIs with FastAPI or Flask.
- Familiarity with Docker and Kubernetes.
- Experience with PostgreSQL.
Nice to have:
- Exposure to MLOps tools such as MLflow.
"""


def _req(
    rid: str, text: str, necessity: str = "must", weight: float = 0.1, kind: str = "hard_skill"
):
    start = JD.index(text)
    return {
        "id": rid,
        "text": text,
        "necessity": necessity,
        "weight": weight,
        "kind": kind,
        "span": {"start": start, "end": start + len(text), "text": text},
        "concept_ids": [],
        "source": "jd",
    }


REQUIREMENTS = [
    _req("R-1", "Python"),
    _req("R-2", "SQL"),
    _req("R-3", "FastAPI"),
    _req("R-4", "Flask"),
    _req("R-5", "Docker", kind="tool"),
    _req("R-6", "Kubernetes", kind="tool"),
    _req("R-7", "PostgreSQL"),
    _req("R-8", "MLOps tools such as MLflow", necessity="could", weight=0.02),
]


def _block(bid, kind, section, text, group=None, **extra):
    return TailorBlock(
        id=bid,
        kind=kind,
        section=section,
        group=group,
        text=text,
        original=extra.pop("original", text),
        **extra,
    )


def _blocks():
    return [
        _block("b01", "name", "contact", "PRIYA SHARMA"),
        _block("b02", "heading", "skills", "SKILLS"),
        _block("b03", "text", "skills", "Languages: Python, Java, SQL"),
        _block("b04", "text", "skills", "Tools: Git, MLflow"),
        _block("b05", "heading", "projects", "PROJECTS"),
        _block("b06", "entry", "projects", "Notes Search", group="b06"),
        _block(
            "b07", "bullet", "projects", "Indexed 10,000 notes for full-text search.", group="b06"
        ),
        _block("b08", "entry", "projects", "Ride Match", group="b08"),
        _block(
            "b09",
            "bullet",
            "projects",
            "Built the matching service with FastAPI and Postgres, shipped in Docker containers.",
            group="b08",
        ),
    ]


def _analyse(blocks=None, *, decisions=None, pages=None, resume=None, requirements=None):
    return analyse(
        jd_id="jd",
        candidate_id="c",
        raw_jd=JD,
        requirements=requirements or REQUIREMENTS,
        groups=[],
        payload=TailorIn(
            resume=resume
            or TailorResume(resolved_concepts={}, canonical_skills={"Postgres": "PostgreSQL"}),
            blocks=blocks or _blocks(),
            pages=pages,
        ),
        decisions=decisions,
    )


def _row(report, text):
    return next(r for r in report.requirements if r.text == text)


def _suggestion(report, kind, requirement=None):
    return next(
        s
        for s in report.suggestions
        if s.kind == kind and (requirement is None or s.requirement == requirement)
    )


# ---------------------------------------------------------------------------
#  Reading a label the way a resume would write it
# ---------------------------------------------------------------------------


def test_a_label_is_read_for_the_skill_inside_it():
    assert "MLflow" in forms("MLOps tools such as MLflow")
    assert "GCP" in forms("GCP experience")
    assert "RAG" in forms("RAG pipelines")
    assert "vector" not in forms("vector databases")
    assert "React" in forms("React / Angular")


def test_whole_words_plurals_and_signs():
    assert find("LLMs", "a multi-LLM inference engine")
    assert find("C++", "Wrote it in C++ and Rust") and not find("C++", "C, Java")
    assert not find("Go", "Go-getter who likes to go further")
    assert find("Machine Learning", "machine-learning pipeline")


def test_a_plain_or_in_the_posting_is_a_choice():
    groups = implied_choices(JD, REQUIREMENTS)
    assert {"requirement_ids": ["R-3", "R-4"]} in [
        {"requirement_ids": g["requirement_ids"]} for g in groups
    ]
    # "Docker and Kubernetes" is two demands, not a choice.
    assert not any(set(g["requirement_ids"]) == {"R-5", "R-6"} for g in groups)


# ---------------------------------------------------------------------------
#  Grading evidence
# ---------------------------------------------------------------------------


def test_evidence_is_graded_shown_listed_other_words_or_absent():
    report = _analyse()
    assert _row(report, "FastAPI").status == "direct"
    assert _row(report, "Docker").status == "direct"
    assert _row(report, "Python").status == "partial"  # only listed
    assert _row(report, "PostgreSQL").status == "partial"  # "Postgres": same thing, other words
    assert _row(report, "PostgreSQL").hits[0].how == "same_concept"
    assert _row(report, "Kubernetes").status == "missing"
    # FastAPI answered the posting's "FastAPI or Flask".
    assert (
        _row(report, "Flask").status == "alternative" and _row(report, "Flask").met_by == "FastAPI"
    )
    assert _row(report, "MLOps tools such as MLflow").term == "MLflow"


def test_the_posting_line_and_heading_come_with_each_requirement():
    row = _row(_analyse(), "Kubernetes")
    assert row.jd_line == "- Familiarity with Docker and Kubernetes."
    assert row.jd_heading == "Requirements"


def test_an_unquoted_requirement_is_listed_but_not_scored():
    extra = {**_req("R-9", "Python"), "id": "R-9", "text": "Cloud Architecture", "span": None}
    with_it = _analyse(requirements=[*REQUIREMENTS, extra])
    without = _analyse()
    assert _row(with_it, "Cloud Architecture").inferred
    assert with_it.coverage.score == without.coverage.score
    assert not any(s.requirement == "Cloud Architecture" for s in with_it.suggestions)


def test_a_keyword_typed_into_a_line_is_flagged_not_counted():
    before = _analyse()
    blocks = _blocks()
    blocks[6] = _block(
        "b07",
        "bullet",
        "projects",
        "Indexed 10,000 notes for full-text search on Kubernetes.",
        group="b06",
        original="Indexed 10,000 notes for full-text search.",
    )
    after = _analyse(blocks)
    assert _row(after, "Kubernetes").status == "unsupported"
    assert after.coverage.score == before.coverage.score
    flag = next(f for f in after.flags if f.block_id == "b07")
    assert flag.terms == ["Kubernetes"] and "not anywhere in the resume" in flag.message
    keyword = next(k for k in after.keywords if k.term == "Kubernetes")
    assert keyword.state == "inserted"

    # Said to be true by the student: it counts, and the flag says so.
    confirmed = _analyse(blocks, decisions={"k": {"state": "confirmed", "term": "Kubernetes"}})
    assert _row(confirmed, "Kubernetes").status == "direct"
    assert next(f for f in confirmed.flags if f.block_id == "b07").terms == []


def test_showing_a_listed_skill_in_work_moves_the_score_and_keeps_the_baseline():
    blocks = _blocks()
    blocks[6] = _block(
        "b07",
        "bullet",
        "projects",
        "Indexed 10,000 notes with a Python service for full-text search.",
        group="b06",
        original="Indexed 10,000 notes for full-text search.",
    )
    report = _analyse(blocks)
    assert _row(report, "Python").status == "direct"
    # Python was on the uploaded resume (skills), so this is evidence, not invention.
    assert not report.flags
    assert report.coverage.score > report.coverage.baseline


# ---------------------------------------------------------------------------
#  Suggestions
# ---------------------------------------------------------------------------


def test_a_skill_shown_in_work_is_offered_for_the_skills_line_it_keeps_company_with():
    blocks = _blocks()
    blocks[3] = _block("b04", "text", "skills", "Tools: Git, FastAPI, MLflow")
    report = _analyse(blocks)
    add = _suggestion(report, "add_skill", "Docker")
    assert add.block_id == "b04" and add.after == "Tools: Git, FastAPI, MLflow, Docker"
    assert "Ride Match" in add.reason.why and "shipped in Docker" in add.reason.why
    assert add.reason.type == "keyword"


def test_the_postings_spelling_replaces_the_resumes_without_changing_the_claim():
    use = _suggestion(_analyse(), "use_jd_term", "PostgreSQL")
    assert use.block_id == "b09"
    assert use.after == (
        "Built the matching service with FastAPI and PostgreSQL, shipped in Docker containers."
    )
    assert "Postgres" in use.reason.why


def test_a_missing_requirement_is_a_question_never_an_insertion():
    missing = _suggestion(_analyse(), "missing", "Kubernetes")
    assert missing.action == "confirm" and missing.needs_confirmation
    assert missing.after is None
    assert "We won't add it for you" in missing.reason.why
    assert "Familiarity with Docker and Kubernetes" in missing.reason.addresses
    assert missing.reason.type == "missing_requirement"
    assert missing.impact == "high"


def test_a_listed_skill_asks_where_it_was_used():
    surface = _suggestion(_analyse(), "surface", "Python")
    assert surface.action == "confirm" and surface.candidates
    assert set(surface.candidates) <= {"b07", "b09"}


def test_a_rejected_suggestion_stays_rejected():
    first = _analyse()
    key = _suggestion(first, "missing", "Kubernetes").key
    again = _analyse(decisions={key: {"state": "rejected"}})
    assert _suggestion(again, "missing", "Kubernetes").state == "rejected"
    assert again.suggestions[-1].state == "rejected"  # dismissed ones sort last


def test_the_most_relevant_project_is_offered_first_place():
    blocks = _blocks()
    blocks.append(
        _block("b10", "bullet", "projects", "Wrote the SQL schema and the Python ETL.", group="b08")
    )
    move = _suggestion(_analyse(blocks), "reorder")
    assert move.block_id == "b08" and move.move_before == "b06"
    assert move.reason.type == "structure"


def test_trimming_is_offered_only_past_one_page():
    assert not any(s.kind == "trim" for s in _analyse(pages=1).suggestions)
    trim = _suggestion(_analyse(pages=2), "trim")
    assert trim.block_id == "b07" and trim.action == "hide"


# ---------------------------------------------------------------------------
#  Saved jobs over HTTP
# ---------------------------------------------------------------------------


@pytest.fixture(name="student")
def student_fixture(session, m04):
    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    candidate = str(uuid.uuid4())
    yield candidate, TestClient(app, headers={"X-Role": "student", "X-Candidate-Id": candidate})
    app.dependency_overrides.clear()


def _parse(client) -> dict:
    res = client.post(
        "/v1/jds/parse",
        json={"company_name": "Acme", "role_title": "Backend Intern", "raw_text": JD},
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_a_job_is_saved_renamed_listed_and_forgotten(student):
    candidate, client = student
    jd = _parse(client)
    url = f"/v1/jds/{jd['id']}/workspace/{candidate}"

    saved = client.put(url, json={}).json()
    assert saved["title"] == "Acme · Backend Intern"
    again = client.put(url, json={}).json()
    assert again["id"] == saved["id"]  # one row per student per posting

    renamed = client.put(url, json={"title": "  Acme — dream job ", "resume_id": "r1"}).json()
    assert renamed["title"] == "Acme — dream job" and renamed["resume_id"] == "r1"
    client.put(url, json={"tailored": {"r1": "t1"}, "filename": "Priya_Acme_resume"})
    client.put(url, json={"tailored": {"r2": "t2"}})
    kept = client.get(url).json()
    assert kept["tailored"] == {"r1": "t1", "r2": "t2"}
    assert kept["filename"] == "Priya_Acme_resume"

    listed = client.get(f"/v1/jds/workspaces/{candidate}").json()
    assert [w["jd_id"] for w in listed] == [jd["id"]]

    assert client.delete(url).status_code == 204
    assert client.get(url).status_code == 404
    assert client.get(f"/v1/jds/{jd['id']}").status_code == 200  # the shared parse stays


def test_another_student_cannot_see_or_touch_your_jobs(student, session):
    candidate, client = student
    jd = _parse(client)
    client.put(f"/v1/jds/{jd['id']}/workspace/{candidate}", json={})
    stranger = TestClient(app, headers={"X-Role": "student", "X-Candidate-Id": str(uuid.uuid4())})
    assert stranger.get(f"/v1/jds/workspaces/{candidate}").status_code == 403
    assert stranger.delete(f"/v1/jds/{jd['id']}/workspace/{candidate}").status_code == 403


def test_the_analysis_remembers_a_summary_and_honours_decisions(student):
    candidate, client = student
    jd = _parse(client)
    client.put(f"/v1/jds/{jd['id']}/workspace/{candidate}", json={})
    body = {
        "resume": {"id": "r1", "resolved_concepts": {}, "canonical_skills": {}},
        "tailored_id": "t1",
        "revision": 3,
        "blocks": [b.model_dump() for b in _blocks()],
    }
    report = client.post(f"/v1/jds/{jd['id']}/tailor/{candidate}", json=body).json()
    assert report["revision"] == 3 and report["coverage"]["requirements"] > 0
    open_before = sum(1 for s in report["suggestions"] if s["state"] == "open")

    key = report["suggestions"][0]["key"]
    client.post(
        f"/v1/jds/{jd['id']}/workspace/{candidate}/decisions",
        json={"key": key, "state": "rejected"},
    )
    again = client.post(f"/v1/jds/{jd['id']}/tailor/{candidate}", json=body).json()
    assert next(s for s in again["suggestions"] if s["key"] == key)["state"] == "rejected"

    saved = client.get(f"/v1/jds/workspaces/{candidate}").json()[0]
    assert saved["summary"]["open"] == open_before - 1
    assert saved["summary"]["resume_id"] == "r1"

    undone = client.post(
        f"/v1/jds/{jd['id']}/workspace/{candidate}/decisions", json={"key": key, "state": "open"}
    ).json()
    assert key not in undone["decisions"]
