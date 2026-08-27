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
from ai_core.models import USER_AGENT
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from pydantic import BaseModel
from sqlmodel import Session, select

from backend_M02_JD_Parser.documents import UnreadableDocument, to_text
from backend_M02_JD_Parser.match import MatchReport, build_match
from backend_M02_JD_Parser.models import JobDescription
from backend_M02_JD_Parser.plan import CoveragePlan, build_plan

from .extract import (
    drop_redundant,
    extract_eligibility,
    extract_surface_forms,
    find_disjunctions,
    locate,
    scan_prose,
    slash_parts,
)


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

#: A job description is a page or two. Anything past this is the wrong file,
#: and reading it into memory before finding that out is how an upload endpoint
#: becomes a way to exhaust the server.
MAX_UPLOAD_BYTES = 5 * 1024 * 1024


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

    # ------------------------------------------------------------------
    #  Is "Java/Python/C++" three alternatives, or is it "CI/CD"?
    # ------------------------------------------------------------------
    #  `_DELIMITERS` refuses to split on `/` on purpose, because "CI/CD" and
    #  "TCP/IP" are single names far more often than "React/Angular" is two and
    #  a wrong split fabricates a skill. That leaves the real disjunctions
    #  unsplit, which §3.2.1 says makes a Python-only student look 33%
    #  qualified — so the question gets ASKED rather than guessed at from
    #  punctuation: probe the parts, and split only where at least two of them
    #  are things the ontology has heard of.
    #
    #  One extra resolve call, and only when the posting contains a slash. With
    #  M04 down the offline table answers and fewer compounds split: scope
    #  narrows, nothing is invented.
    compounds = {label: parts for label in labels if (parts := slash_parts(label))}
    if compounds:
        probe = sorted({part for parts in compounds.values() for part in parts})
        probed = resolve_labels(probe)
        for compound, parts in compounds.items():
            known = [
                part
                for part in parts
                if probed.get(part) or FALLBACK_RESOLUTIONS.get(normalise_alias(part))
            ]
            if len(known) < 2:
                continue
            # Inserted right after the compound so they read in document order.
            at = labels.index(compound) + 1
            for offset, part in enumerate(parts):
                if normalise_alias(part) not in {normalise_alias(x) for x in labels}:
                    labels.insert(at + offset, part)

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

    # Recorded BEFORE `drop_redundant`, which is about to delete
    # "Docker or Kubernetes" for being subsumed by its parts. It is right to
    # delete it — it resolves to nothing — but the choice it states has to
    # survive it, or two alternatives read as two separate demands.
    disjunctions = find_disjunctions(labels, concepts_by_label)

    unresolved = drop_redundant(unresolved, list(concepts_by_label))
    # Everything the JD asks for, mapped or not, in the order it asks. An
    # unmapped requirement is still a requirement — coverage reports it as
    # `unmeasurable` rather than dropping it, which is the only honest answer
    # to "does this candidate meet the bar" when we cannot test the bar.
    required = [label for label in labels if label in concepts_by_label or label in unresolved]

    # Located against the ORIGINAL text, and folded: "Java or Python" becomes
    # one group over two alternatives rather than three requirements.
    requirement_set = locate(
        payload.raw_text,
        required,
        resolved=concepts_by_label,
        sources=concept_source,
        disjunctions=disjunctions,
    )

    jd = JobDescription(
        company_name=payload.company_name,
        role_title=payload.role_title,
        raw_text=payload.raw_text,
        content_sha256=digest,
        required_skills=required,
        # Located against the ORIGINAL text, so an offset here indexes exactly
        # what the student pasted.
        # A hard filter, never an interview topic (§3.2.2) — so it is stored
        # beside the requirements rather than among them.
        eligibility=extract_eligibility(payload.raw_text).model_dump(mode="json"),
        requirements=[
            requirement.model_dump(mode="json") for requirement in requirement_set.requirements
        ],
        requirement_groups=[group.model_dump(mode="json") for group in requirement_set.groups],
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

    # ------------------------------------------------------------------
    #  A choice is met by ONE of its answers (FR-2.3, FR-2.7)
    # ------------------------------------------------------------------
    #  Everything above treats each label as its own demand, which is right for
    #  almost all of them and wrong for exactly the case §3.2.1 is about. A
    #  posting that says "Java or Python" is satisfied by Python, and a student
    #  strong in Python was being marked weak on Java and having their score
    #  lowered for it — the "33% qualified" reading, arriving at the one number
    #  the student actually reads.
    #
    #  The best-placed alternative represents the group. The others are not
    #  gaps and are not silence either: `met_by_alternative` says the posting
    #  asked and this student answered it another way, which is a different
    #  fact from "not measured" and has to look different.
    label_by_requirement = {
        requirement["id"]: requirement["text"] for requirement in (jd.requirements or [])
    }
    buckets = (covered, weak, not_measured, unmeasurable)

    def _standing(label: str) -> tuple[int, float]:
        """How well this alternative is doing. Higher is better."""
        rank = {
            "strong": 4,
            "adequate": 3,
            "weak": 2,
            "not_measured": 1,
            "unmeasurable": 0,
        }.get(states.get(label, "unmeasurable"), 0)
        return rank, mastery_by_label.get(label) or 0.0

    met_by_alternative: dict[str, str] = {}
    for group in jd.requirement_groups or []:
        members = [
            label_by_requirement.get(requirement_id)
            for requirement_id in group.get("requirement_ids", [])
        ]
        members = [label for label in members if label and label in states]
        if len(members) < 2:
            continue

        best = max(members, key=_standing)
        for label in members:
            if label == best:
                continue
            states[label] = "met_by_alternative"
            met_by_alternative[label] = best
            gap_severity.pop(label, None)
            for bucket in buckets:
                if label in bucket:
                    bucket.remove(label)

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
        # label -> the alternative that met the same requirement. A student
        # asking "why is nothing being said about Java?" gets an answer.
        "met_by_alternative": met_by_alternative,
        # The ids themselves, so a caller can show WHICH concept a
        # requirement was matched to alongside where that id came from.
        "resolved_concepts": jd.resolved_concepts,
        "concept_source": jd.concept_source,
        "scanned_against": jd.scanned_against,
        "degraded": degraded,
    }


class PlanIn(BaseModel):
    """§9: `POST /v1/jds/{id}/plan {minutes, modalities, focus_overrides}`.

    `modalities` and `focus_overrides` are not accepted, because neither has
    anything to act on. Modality selection needs `Requirement.measured_by` to
    know a coding requirement from a verbal one, and focus overrides need
    FR-2.10's editable requirements. Accepting them and ignoring them would be
    worse than refusing them: a caller would believe the plan honoured a focus
    it never saw.
    """

    #: How long the student has. §2.3: "students budget in evenings, not in
    #: features", so this is the one input that always exists.
    minutes: int = 45


@router.post("/jds/{jd_id}/plan/{candidate_id}", response_model=CoveragePlan)
def post_jd_plan(
    jd_id: uuid.UUID,
    candidate_id: uuid.UUID,
    payload: PlanIn,
    session: Session = Depends(get_db),
):
    """The allocation of interview question budget across requirements (FR-2.8).

    `candidate_id` is in the PATH rather than the body because `enforce_access`
    keys on that path parameter, and a plan is a gap analysis with a schedule
    attached — the same personal data the coverage route is gated for. In the
    body it would have been unauthenticated by omission.

    The gap is read by calling the coverage endpoint's own function rather than
    recomputing it. Two implementations of "is this student weak on this" would
    diverge, and the first sign would be a plan that allocates four questions to
    something the coverage screen shows as strong.
    """
    if payload.minutes < 1:
        raise HTTPException(status_code=422, detail="minutes must be at least 1")

    jd = session.get(JobDescription, jd_id)
    if not jd:
        raise HTTPException(status_code=404, detail="Job Description not found")

    coverage = get_jd_coverage(jd_id, candidate_id, session)

    return build_plan(
        jd_id=str(jd_id),
        candidate_id=str(candidate_id),
        total_minutes=payload.minutes,
        requirements=jd.requirements or [],
        states=coverage["states"],
        mastery=coverage["mastery"],
    )


def _m01_get(path: str, *, candidate_id: str) -> Any | None:
    """GET from M01, or None.

    Identity is FORWARDED, not asserted. M01 gates every resume route on
    `X-Candidate-Id` and it is right to — a resume is the most personal thing
    this platform holds. M02 has already checked, at `enforce_access`, that the
    caller may see this candidate; passing the header on is how that decision
    travels rather than being made twice with two chances to differ.

    A service token would be worse here even though it is the usual answer:
    it would let M02 read any resume, and the only thing standing between that
    and a leak would be M02 never having a bug.
    """
    deps = dependency_registry()
    dep = deps.get("M01")
    if dep is None or not dep.base_url or not deps.is_available("M01"):
        return None
    request = urllib.request.Request(
        f"{dep.base_url.rstrip('/')}{path}",
        headers={
            "X-Role": "student",
            "X-Candidate-Id": candidate_id,
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=2.0) as response:
            return json.loads(response.read())
    except Exception:
        return None


def get_candidate_resume(candidate_id: uuid.UUID) -> tuple[dict | None, str]:
    """This candidate's active resume from M01, and why there is not one.

    Returns `(resume, status)` where status is `ok`, `no_resume` or
    `m01_unreachable`. Three states rather than a bare `None`, because "we
    cannot reach M01" and "you have not uploaded a resume" lead a student to
    completely different actions and the second is the only one they can fix.
    """
    deps = dependency_registry()
    dep = deps.get("M01")
    if dep is None or not dep.base_url or not deps.is_available("M01"):
        return None, "m01_unreachable"

    rows = _m01_get(f"/v1/resumes/candidate/{candidate_id}", candidate_id=str(candidate_id))
    if rows is None:
        return None, "m01_unreachable"
    if not rows:
        return None, "no_resume"

    # The active one, or the newest. M01 keeps every version a student uploads
    # and marks one active; matching against a superseded resume would report
    # gaps the student already fixed.
    active = [row for row in rows if row.get("is_active")]
    chosen = (active or rows)[0]
    return chosen, "ok"


@router.get("/jds/{jd_id}/match/{candidate_id}", response_model=MatchReport)
def get_jd_match(
    jd_id: uuid.UUID,
    candidate_id: uuid.UUID,
    session: Session = Depends(get_db),
):
    """This student's resume against this posting (FR-2.15).

    Distinct from `/coverage`, and the distinction is the point. Coverage asks
    the Skill Graph what the student CAN DO, accumulated over every session
    they have ever run. This asks the resume what a recruiter will READ about
    them next week. The two disagree constantly, and a student needs both:
    one tells them what to practise, the other what to rewrite.

    M01 is optional. When it is down or holds no resume, the report says which
    and carries nothing else — never an empty verdict list that reads as "you
    passed every check".
    """
    jd = session.get(JobDescription, jd_id)
    if not jd:
        raise HTTPException(status_code=404, detail="Job Description not found")

    resume, status = get_candidate_resume(candidate_id)

    return build_match(
        jd_id=str(jd_id),
        candidate_id=str(candidate_id),
        resume=resume,
        resume_status=status,
        eligibility=jd.eligibility or {},
        requirements=jd.requirements or [],
        groups=jd.requirement_groups or [],
    )


@router.post("/jds/upload", response_model=JobDescription, status_code=status.HTTP_201_CREATED)
async def upload_jd(
    response: Response,
    company_name: str = Form(...),
    role_title: str = Form(...),
    file: UploadFile = File(...),
    session: Session = Depends(get_db),
):
    """A job description as a PDF, .docx or .txt (FR-2.1).

    §1 calls the input *"usually a badly formatted blob from a placement-portal
    email"*, and until now the only way in was `raw_text` — which assumes the
    student can select the text. A placement-cell mail arrives as an attachment
    at least as often as it arrives as a body.

    Converts to text and then calls `parse_jd`, rather than reimplementing the
    pipeline for uploads. Two entry points with two pipelines is how one of them
    quietly stops getting the extraction fixes: this route has no parsing logic
    of its own, so a JD pasted and the same JD uploaded produce byte-identical
    rows — and the content hash proves it, because the second one comes back
    200 from the cache rather than 201.
    """
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,  # CONTENT_TOO_LARGE; the named constant was renamed under us
            detail=(
                f"That file is {len(data) // 1_000_000} MB. A job description is a page or two — "
                "if it is bigger than that, it is probably the wrong file."
            ),
        )

    try:
        text = to_text(data, file.filename)
    except UnreadableDocument as error:
        # 422 with the sentence the document layer wrote, because the fix
        # differs per cause and only that layer knows which cause it was.
        raise HTTPException(
            status_code=422,
            detail=str(error),  # UNPROCESSABLE_CONTENT
        ) from error

    return parse_jd(
        JdParseIn(company_name=company_name, role_title=role_title, raw_text=text),
        response,
        session,
    )
