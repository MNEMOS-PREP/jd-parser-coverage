"""A student's saved job descriptions — the memory this module never had (2026-11-17).

── Why job descriptions were forgotten ──────────────────────────────────────────

A parse is shared: FR-2.12 caches it by content hash across every student who
pastes the same posting, because a posting is the company's, not the student's.
That was right, and it had a consequence nobody built around — there was no
row saying THIS student is working on THAT posting. The only memory was the
URL, so leaving the page, or refreshing on another route, lost the job, and
M01's "check against a job" could only say "paste it again".

A workspace is that row: one per (student, posting), holding everything that
is the student's about the job — the name they gave it, the resume they chose,
the tailored copy of each resume they tried (M01 holds the copies; this holds
their ids), the suggestions they turned down, the file name they want, and a
summary of the last analysis for the list. The shared parse is never written.

── Every write is the student's, and only theirs ────────────────────────────────

Routes name the candidate in the path, so the router's guard decides who may
read or write it — one student cannot see, rename or delete another's jobs.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import JSON, Column
from sqlmodel import Field as SQLField
from sqlmodel import Session, SQLModel, select

from backend_M02_JD_Parser.models import JobDescription
from backend_M02_JD_Parser.router import _effective_set, enforce_access, get_db
from backend_M02_JD_Parser.tailoring import TailorIn, TailorReport, analyse, summary


def _utcnow() -> datetime:
    return datetime.now(UTC)


class JdWorkspace(SQLModel, table=True):
    """One student's work on one posting."""

    __tablename__ = "jd_workspaces"

    id: uuid.UUID = SQLField(default_factory=uuid.uuid4, primary_key=True)
    candidate_id: uuid.UUID = SQLField(index=True)
    jd_id: uuid.UUID = SQLField(index=True)
    #: What the student calls it. Defaults to "Company · Role"; renamable.
    title: str = ""
    #: The M01 resume chosen for this job.
    resume_id: str | None = None
    #: M01 resume id -> M01 tailored copy id. One copy per resume per job, so
    #: switching resumes and back finds the edits made the first time.
    tailored: dict = SQLField(default_factory=dict, sa_column=Column(JSON))
    #: Suggestion key -> {"state": "rejected" | "confirmed", "term"?, "at"}.
    decisions: dict = SQLField(default_factory=dict, sa_column=Column(JSON))
    filename: str | None = None
    #: The last analysis, summarised for the list of saved jobs.
    summary: dict = SQLField(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = SQLField(default_factory=_utcnow)
    updated_at: datetime = SQLField(default_factory=_utcnow)
    opened_at: datetime = SQLField(default_factory=_utcnow)


class WorkspaceIn(BaseModel):
    title: str | None = None
    resume_id: str | None = None
    #: {resume_id: tailored_id} entries to record.
    tailored: dict[str, str] | None = None
    filename: str | None = None
    #: Mark it opened now — what orders the list.
    touch: bool = True


class DecisionIn(BaseModel):
    key: str
    #: open undoes a decision.
    state: Literal["rejected", "confirmed", "open"]
    #: For `confirmed`: the term the student said is true of them.
    term: str | None = None


class WorkspaceOut(BaseModel):
    id: uuid.UUID
    candidate_id: uuid.UUID
    jd_id: uuid.UUID
    title: str
    company_name: str
    role_title: str
    requirement_count: int
    resume_id: str | None
    tailored: dict[str, str]
    decisions: dict[str, Any]
    filename: str | None
    summary: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    opened_at: datetime


def _out(row: JdWorkspace, jd: JobDescription | None) -> WorkspaceOut:
    return WorkspaceOut(
        id=row.id,
        candidate_id=row.candidate_id,
        jd_id=row.jd_id,
        title=row.title,
        company_name=(jd.company_name if jd else "") or "",
        role_title=(jd.role_title if jd else "") or "",
        requirement_count=len(jd.requirements or []) if jd else 0,
        resume_id=row.resume_id,
        tailored=dict(row.tailored or {}),
        decisions=dict(row.decisions or {}),
        filename=row.filename,
        summary=dict(row.summary or {}),
        created_at=row.created_at,
        updated_at=row.updated_at,
        opened_at=row.opened_at,
    )


def _find(session: Session, jd_id: uuid.UUID, candidate_id: uuid.UUID) -> JdWorkspace | None:
    return session.exec(
        select(JdWorkspace).where(
            JdWorkspace.jd_id == jd_id, JdWorkspace.candidate_id == candidate_id
        )
    ).first()


def _jd(session: Session, jd_id: uuid.UUID) -> JobDescription:
    jd = session.get(JobDescription, jd_id)
    if jd is None:
        raise HTTPException(status_code=404, detail="Job Description not found")
    return jd


def default_title(jd: JobDescription) -> str:
    parts = [p.strip() for p in (jd.company_name, jd.role_title) if p and p.strip()]
    return " · ".join(parts) or "Untitled job"


router = APIRouter(
    prefix="/v1",
    tags=["M02 Saved job descriptions"],
    dependencies=[Depends(enforce_access)],
)


@router.get("/jds/workspaces/{candidate_id}", response_model=list[WorkspaceOut])
def list_workspaces(candidate_id: uuid.UUID, session: Session = Depends(get_db)):
    """This student's saved jobs, the one they opened last first."""
    rows = session.exec(
        select(JdWorkspace)
        .where(JdWorkspace.candidate_id == candidate_id)
        .order_by(JdWorkspace.opened_at.desc())  # type: ignore[attr-defined]
    ).all()
    out = []
    for row in rows:
        jd = session.get(JobDescription, row.jd_id)
        if jd is not None:
            out.append(_out(row, jd))
    return out


@router.get("/jds/{jd_id}/workspace/{candidate_id}", response_model=WorkspaceOut)
def get_workspace(jd_id: uuid.UUID, candidate_id: uuid.UUID, session: Session = Depends(get_db)):
    row = _find(session, jd_id, candidate_id)
    if row is None:
        raise HTTPException(status_code=404, detail="This job is not saved for you yet.")
    return _out(row, session.get(JobDescription, jd_id))


@router.put("/jds/{jd_id}/workspace/{candidate_id}", response_model=WorkspaceOut)
def save_workspace(
    jd_id: uuid.UUID,
    candidate_id: uuid.UUID,
    payload: WorkspaceIn,
    session: Session = Depends(get_db),
):
    """Save this job for this student, or update what is saved. Idempotent.

    Called the moment a posting is read, so a job is remembered before the
    student does anything else with it.
    """
    jd = _jd(session, jd_id)
    row = _find(session, jd_id, candidate_id)
    now = _utcnow()
    if row is None:
        row = JdWorkspace(candidate_id=candidate_id, jd_id=jd_id, title=default_title(jd))
    if payload.title is not None:
        title = " ".join(payload.title.split())[:120]
        row.title = title or default_title(jd)
    if payload.resume_id is not None:
        row.resume_id = payload.resume_id or None
    if payload.tailored:
        merged = dict(row.tailored or {})
        merged.update({str(k): str(v) for k, v in payload.tailored.items() if k and v})
        row.tailored = merged
    if payload.filename is not None:
        row.filename = payload.filename.strip()[:160] or None
    if payload.touch:
        row.opened_at = now
    row.updated_at = now
    session.add(row)
    session.commit()
    session.refresh(row)
    return _out(row, jd)


@router.delete("/jds/{jd_id}/workspace/{candidate_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workspace(
    jd_id: uuid.UUID, candidate_id: uuid.UUID, session: Session = Depends(get_db)
) -> Response:
    """Forget this job for this student. The shared parse stays for everyone else;
    the tailored copies live in M01 and the screen deletes them there."""
    row = _find(session, jd_id, candidate_id)
    if row is not None:
        session.delete(row)
        session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/jds/{jd_id}/workspace/{candidate_id}/decisions", response_model=WorkspaceOut)
def decide(
    jd_id: uuid.UUID,
    candidate_id: uuid.UUID,
    payload: DecisionIn,
    session: Session = Depends(get_db),
):
    """Turn a suggestion down, say a missing requirement is true of you, or undo either."""
    jd = _jd(session, jd_id)
    row = _find(session, jd_id, candidate_id)
    if row is None:
        row = JdWorkspace(candidate_id=candidate_id, jd_id=jd_id, title=default_title(jd))
    decisions = dict(row.decisions or {})
    if payload.state == "open":
        decisions.pop(payload.key, None)
    else:
        entry: dict[str, Any] = {"state": payload.state, "at": _utcnow().isoformat()}
        if payload.term:
            entry["term"] = " ".join(payload.term.split())[:80]
        decisions[payload.key[:40]] = entry
    row.decisions = decisions
    row.updated_at = _utcnow()
    session.add(row)
    session.commit()
    session.refresh(row)
    return _out(row, jd)


@router.post("/jds/{jd_id}/tailor/{candidate_id}", response_model=TailorReport)
def tailor(
    jd_id: uuid.UUID,
    candidate_id: uuid.UUID,
    payload: TailorIn,
    session: Session = Depends(get_db),
):
    """This posting against one tailored copy of the student's resume.

    The copy's blocks come in the body — the screen already holds them from M01,
    at the revision it is showing, so the analysis is of exactly what the
    student sees. Uses the student's own corrections to the requirement list
    (FR-2.10), and their decisions on earlier suggestions. Remembers a summary
    of the result for the list of saved jobs.
    """
    jd = _jd(session, jd_id)
    requirements, groups, _ = _effective_set(jd, candidate_id, session)
    row = _find(session, jd_id, candidate_id)
    report = analyse(
        jd_id=str(jd_id),
        candidate_id=str(candidate_id),
        raw_jd=jd.raw_text or "",
        requirements=requirements,
        groups=groups,
        payload=payload,
        decisions=dict(row.decisions or {}) if row else {},
    )
    if row is not None:
        row.summary = summary(report)
        session.add(row)
        session.commit()
    return report
