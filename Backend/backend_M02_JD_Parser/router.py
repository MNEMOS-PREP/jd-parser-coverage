"""M02 — JD Parser & Coverage Planner.

Two things this module must never do, both of them Rule 2 (a missing input
narrows the SCOPE of what we show, never the quality, and never silently):

1. **Report an unmeasured gap as a zero.** With M04 down we know nothing about
   the candidate, and "nothing" is `null` plus a named reason — not
   `coverage_score: 0.0`, which reads as "you are qualified for none of this".
2. **Pass off a guess as a resolution.** The offline tables below let the
   module work with M04 down; every value they produce is labelled as theirs.
"""

import hashlib
import json
import re
import urllib.request
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any

from ai_core.concepts import normalise_alias
from ai_core.dependencies import DependencyRegistry, DependencyStatus
from ai_core.identity import Principal, may_see, principal_from_headers
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlmodel import Session, select

from backend_M02_JD_Parser.models import JobDescription

from .extract import drop_redundant, extract_surface_forms, scan_prose


def get_db():
    from backend_M02_JD_Parser.app import engine

    with Session(engine) as session:
        yield session


def enforce_access(request: Request) -> Principal | None:
    """Who is asking, and may they have what this route is about?

    Declared once, on the ROUTER, so it runs on every endpoint in this module
    including the ones nobody has written yet. `ai_core.identity` makes the
    check one call precisely because a per-route check is the one somebody
    omits on the sixteenth endpoint, and the sixteenth endpoint is the one that
    leaks. A router-level dependency cannot be omitted by forgetting.

    ── What is candidate-scoped here, and what is not ──────────────────────────

    Only `candidate_id`. A JOB DESCRIPTION is not personal data — it is a public
    posting a company wrote, and two students preparing for the same drive
    should share one parse rather than each holding a private copy of a public
    document (FR-2.12 makes that explicit by caching across students). So
    `/jds/parse` and `/jds/{id}` stay open.

    `/jds/{id}/coverage/{candidate_id}` is the opposite: it is a gap analysis of
    one named student against that posting, and it answered for anybody who
    guessed a UUID.
    """
    principal = principal_from_headers(dict(request.headers))

    candidate_id = request.path_params.get("candidate_id")
    if candidate_id is None:
        return principal

    decision = may_see(principal, str(candidate_id))
    if not decision:
        # 403 with the reason, not 404. Pretending the record does not exist
        # would be a lie to the student it is about.
        raise HTTPException(status_code=403, detail=decision.reason)

    return principal


router = APIRouter(
    prefix="/v1",
    tags=["M02 JD Parser & Coverage Planner"],
    dependencies=[Depends(enforce_access)],
)

_MANIFEST = Path(__file__).resolve().parents[2] / "module.json"

# Gap thresholds. Spec §6.5 — the same numbers M15 renders against, so a
# student is not told "weak" here and "adequate" two screens later.
WEAK_BELOW = 0.45
ADEQUATE_BELOW = 0.70

#: A requirement M04 has never measured is not a requirement the student has
#: failed. Spec §6.5: not_measured carries severity weight × 0.6 — we do not
#: know, so we should probe — rather than the 1.0 that "missing" implied.
NOT_MEASURED_SEVERITY = 0.6


@lru_cache(maxsize=1)
def dependency_registry() -> DependencyRegistry:
    """Built once, not per call.

    The registry caches probe results for ~30s. Rebuilding it inside every
    helper threw that cache away and re-probed M04 three times per request, so
    the cache existed but never hit.
    """
    if not _MANIFEST.exists():
        return DependencyRegistry()
    return DependencyRegistry.from_manifest(_MANIFEST)


def _m04_get(path: str) -> Any | None:
    """GET from M04, or None.

    Probes first: `is_available` is cached, the call is not, and asking a dead
    port three times per request costs a socket timeout each time.
    """
    deps = dependency_registry()
    dep = deps.get("M04")
    if dep is None or not dep.base_url or not deps.is_available("M04"):
        return None
    try:
        with urllib.request.urlopen(f"{dep.base_url.rstrip('/')}{path}", timeout=2.0) as response:
            return json.loads(response.read())
    except Exception:
        return None


def get_m04_concepts() -> list[dict[str, Any]]:
    data = _m04_get("/v1/concepts")
    return data.get("concepts", []) if isinstance(data, dict) else []


def resolve_labels(labels: list[str]) -> dict[str, str | None]:
    """label -> concept_id as M04 resolves it. `None` means M04 could not."""
    if not labels:
        return {}
    deps = dependency_registry()
    dep = deps.get("M04")
    if dep is None or not dep.base_url or not deps.is_available("M04"):
        return {label: None for label in labels}
    url = f"{dep.base_url.rstrip('/')}/v1/concepts/resolve"
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps({"labels": labels}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=2.0) as response:
            return json.loads(response.read()).get("resolved", {})
    except Exception:
        return {label: None for label in labels}


def get_candidate_mastery(candidate_id: uuid.UUID) -> dict | None:
    """M04 mastery rows, or `None` when M04 did not answer.

    `None` and `{}` are different facts and the caller has to be able to tell
    them apart: `{}` is "M04 is up and has measured nothing for this student",
    `None` is "we did not ask anyone". Collapsing both to `{}` is what turned
    an outage into a coverage score of zero.
    """
    return _m04_get(f"/v1/candidates/{candidate_id}/mastery")



#: Whitespace is the only thing normalised away.
#:
#: Not casefold: a JD is prose, and lowering it would make two genuinely
#: different postings collide about as often as it helps. Sixty pastes of one
#: drive differ by line breaks and indentation — a copy out of a PDF, out of a
#: portal, out of an email — and that is the whole difference the cache has to
#: see through.
_WHITESPACE = re.compile(r"\s+")


def content_digest(company: str, role: str, text: str) -> str:
    """The cache key for one job description (FR-2.12)."""
    parts = [_WHITESPACE.sub(" ", value or "").strip() for value in (company, role, text)]
    return hashlib.sha256("␟".join(parts).encode("utf-8")).hexdigest()


class JdParseIn(BaseModel):
    company_name: str
    role_title: str
    raw_text: str


#: Enough ontology to be useful with M04 down, and small enough that nobody
#: mistakes it for the ontology. Responses record which one was used.
FALLBACK_CONCEPTS: list[dict[str, Any]] = [
    {"name": "Dynamic Programming", "aliases": ["DP", "dynamic programming"]},
    {"name": "Recursion", "aliases": ["recursion"]},
    {"name": "Hashing", "aliases": ["hashing", "hash map", "hashmap"]},
    {"name": "SQL", "aliases": ["sql", "sql_basics"]},
    {"name": "Transactions", "aliases": ["transactions", "transactions_acid"]},
]

FALLBACK_RESOLUTIONS = {
    "dynamic programming": "concept:dynamic_programming",
    "recursion": "concept:recursion",
    "hashing": "concept:hashing",
    "sql": "concept:sql_basics",
    "transactions": "concept:transactions_acid",
}


@router.get("/deps", response_model=list[DependencyStatus], tags=["meta"])
def dependency_health() -> list[DependencyStatus]:
    """Which upstream modules are up, and what breaks when they are not.

    Answers "why is my coverage score null?" in one request instead of a
    console dig.
    """
    return dependency_registry().statuses(force=True)


@router.post("/jds/parse", response_model=JobDescription, status_code=status.HTTP_201_CREATED)
def parse_jd(
    payload: JdParseIn,
    response: Response,
    session: Session = Depends(get_db),
):
    # ------------------------------------------------------------------
    #  FR-2.12 — the same JD, pasted by sixty students, is parsed once.
    #
    #  Looked up GLOBALLY rather than per candidate, and that is the whole
    #  point of the requirement: §3.2.4 is explicit that "the parse is shared,
    #  the gap analysis is per-student". M01's equivalent dedup is scoped to
    #  one candidate because a resume belongs to one person; a posting belongs
    #  to a company and sixty people are preparing for it.
    #
    #  A hit answers 200 rather than 201: nothing was created. The row it
    #  returns is the row the first student's paste made, so a coverage request
    #  against it is the same request either way.
    # ------------------------------------------------------------------
    digest = content_digest(payload.company_name, payload.role_title, payload.raw_text)
    cached = session.exec(
        select(JobDescription).where(JobDescription.content_sha256 == digest)
    ).first()
    if cached is not None:
        response.status_code = status.HTTP_200_OK
        return cached

    concepts = get_m04_concepts()
    scanned_against = "m04" if concepts else "offline_lexicon"
    if not concepts:
        concepts = FALLBACK_CONCEPTS

    # ------------------------------------------------------------------
    #  Read the job description, THEN resolve. The previous version walked
    #  the ontology and matched it against the text, which had two failure
    #  modes here and the second is the dangerous one:
    #
    #    · a JD listing Python, SQL, data structures, algorithms, Docker,
    #      Kubernetes, Java and Go yielded one requirement — SQL Queries;
    #    · "a solid communicator with a solid track record in retail sales,
    #      no engineering required" yielded SOLID Principles, because "solid"
    #      is an alias. A requirement invented from an adjective does not stay
    #      cosmetic: downstream it selects interview questions.
    #
    #  See extract.py.
    # ------------------------------------------------------------------
    surface_forms = extract_surface_forms(payload.raw_text)

    # Concepts named in prose rather than enumerated. Ambiguous one-word
    # aliases are excluded there — that is what closes the "solid" hole.
    prose_hits = scan_prose(payload.raw_text, concepts)

    labels: list[str] = []
    seen: set[str] = set()
    for label in [*surface_forms, *sorted(prose_hits)]:
        key = normalise_alias(label)
        if key and key not in seen:
            seen.add(key)
            labels.append(label)

    resolved = resolve_labels(labels)

    concepts_by_label: dict[str, str] = {}
    concept_source: dict[str, str] = {}
    unresolved: list[str] = []
    for label in labels:
        concept_id = resolved.get(label)
        if concept_id:
            concepts_by_label[label] = str(concept_id)
            concept_source[label] = "m04"
            continue
        guess = FALLBACK_RESOLUTIONS.get(normalise_alias(label))
        if guess:
            # Usable, and marked. M04 has not confirmed this id exists.
            concepts_by_label[label] = guess
            concept_source[label] = "offline_fallback"
        else:
            unresolved.append(label)

    unresolved = drop_redundant(unresolved, list(concepts_by_label))
    # Everything the JD asks for, mapped or not, in the order it asks. An
    # unmapped requirement is still a requirement — coverage reports it as
    # `unmeasurable` rather than dropping it, which is the only honest answer
    # to "does this candidate meet the bar" when we cannot test the bar.
    required = [label for label in labels if label in concepts_by_label or label in unresolved]

    jd = JobDescription(
        company_name=payload.company_name,
        role_title=payload.role_title,
        raw_text=payload.raw_text,
        content_sha256=digest,
        required_skills=required,
        resolved_concepts=concepts_by_label,
        concept_source=concept_source,
        unresolved_skills=unresolved,
        scanned_against=scanned_against,
    )
    session.add(jd)
    session.commit()
    session.refresh(jd)
    return jd


@router.get("/jds/{jd_id}", response_model=JobDescription)
def get_jd(jd_id: uuid.UUID, session: Session = Depends(get_db)):
    jd = session.get(JobDescription, jd_id)
    if not jd:
        raise HTTPException(status_code=404, detail="Job Description not found")
    return jd


@router.get("/jds/{jd_id}/coverage/{candidate_id}")
def get_jd_coverage(jd_id: uuid.UUID, candidate_id: uuid.UUID, session: Session = Depends(get_db)):
    """Per-requirement gap for one candidate against one JD.

    `coverage_score` is `null` whenever there is nothing to average — M04 down,
    or up and holding no measurement for any of these concepts. It is a
    fraction of the requirements we could actually check, never a fraction of
    all of them, so an unmeasured requirement can never depress it.
    """
    jd = session.get(JobDescription, jd_id)
    if not jd:
        raise HTTPException(status_code=404, detail="Job Description not found")

    deps = dependency_registry()
    degraded = [d.model_dump() for d in deps.degraded()]

    covered: list[str] = []
    weak: list[str] = []
    not_measured: list[str] = []
    gap_severity: dict[str, float] = {}
    states: dict[str, str] = {}
    mastery_by_label: dict[str, float | None] = {}

    # Requirements we could not map to a concept are reported, never scored.
    # Spec EC-2.8: state it as "we cannot test this here".
    unmeasurable = list(jd.unresolved_skills)
    for label in unmeasurable:
        states[label] = "unmeasurable"

    mastery = get_candidate_mastery(candidate_id)
    m04_answered = mastery is not None
    measured_map = {
        row["concept_id"]: row for row in (mastery or {}).get("measured", []) if "concept_id" in row
    }

    for label, concept_id in jd.resolved_concepts.items():
        row = measured_map.get(concept_id)
        mastery_p = row.get("mastery_p") if row else None
        mastery_by_label[label] = mastery_p

        if not m04_answered or mastery_p is None:
            # Either we never asked, or M04 declined to claim a number. Both
            # are "not measured" — a reason to probe this topic, not evidence
            # against the student.
            not_measured.append(label)
            states[label] = "not_measured"
            gap_severity[label] = NOT_MEASURED_SEVERITY
        elif mastery_p < WEAK_BELOW:
            weak.append(label)
            states[label] = "weak"
            gap_severity[label] = 1.0 - mastery_p
        else:
            covered.append(label)
            states[label] = "adequate" if mastery_p < ADEQUATE_BELOW else "strong"
            gap_severity[label] = max(0.0, 1.0 - mastery_p)

    measured_count = len(covered) + len(weak)
    coverage_score = (len(covered) / measured_count) if measured_count else None

    return {
        "jd_id": str(jd_id),
        "candidate_id": str(candidate_id),
        "coverage_score": coverage_score,
        "measured_against": "M04" if m04_answered else None,
        "measured_count": measured_count,
        "requirement_count": len(jd.resolved_concepts) + len(unmeasurable),
        "covered": covered,
        "weak": weak,
        "not_measured": not_measured,
        "unmeasurable": unmeasurable,
        "states": states,
        "mastery": mastery_by_label,
        "gap_severity": gap_severity,
        # The ids themselves, so a caller can show WHICH concept a
        # requirement was matched to alongside where that id came from.
        "resolved_concepts": jd.resolved_concepts,
        "concept_source": jd.concept_source,
        "scanned_against": jd.scanned_against,
        "degraded": degraded,
    }
