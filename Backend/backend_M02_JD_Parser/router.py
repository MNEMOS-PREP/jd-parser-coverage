"""M02 — JD Parser & Coverage Planner.

Two things this module must never do, both of them Rule 2 (a missing input
narrows the SCOPE of what we show, never the quality, and never silently):

1. **Report an unmeasured gap as a zero.** With M04 down we know nothing about
   the candidate, and "nothing" is `null` plus a named reason — not
   `coverage_score: 0.0`, which reads as "you are qualified for none of this".
2. **Pass off a guess as a resolution.** The offline tables below let the
   module work with M04 down; every value they produce is labelled as theirs.
"""

import json
import re
import urllib.request
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any

from ai_core.dependencies import DependencyRegistry, DependencyStatus
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session

from backend_M02_JD_Parser.models import JobDescription

router = APIRouter(prefix="/v1", tags=["M02 JD Parser & Coverage Planner"])

_MANIFEST = Path(__file__).resolve().parents[2] / "module.json"

# Gap thresholds. Spec §6.5 — the same numbers M15 renders against, so a
# student is not told "weak" here and "adequate" two screens later.
WEAK_BELOW = 0.45
ADEQUATE_BELOW = 0.70

#: A requirement M04 has never measured is not a requirement the student has
#: failed. Spec §6.5: not_measured carries severity weight × 0.6 — we do not
#: know, so we should probe — rather than the 1.0 that "missing" implied.
NOT_MEASURED_SEVERITY = 0.6


def get_db():
    from backend_M02_JD_Parser.app import engine

    with Session(engine) as session:
        yield session


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
def parse_jd(payload: JdParseIn, session: Session = Depends(get_db)):
    concepts = get_m04_concepts()
    scanned_against = "m04" if concepts else "offline_lexicon"
    if not concepts:
        concepts = FALLBACK_CONCEPTS

    found_skills = set()
    text_lower = payload.raw_text.lower()
    for c in concepts:
        names_to_check = [c["name"].lower()] + [a.lower() for a in c.get("aliases", [])]
        for name in names_to_check:
            if re.search(rf"\b{re.escape(name)}\b", text_lower):
                found_skills.add(c["name"])
                break

    resolved = resolve_labels(sorted(found_skills))

    concepts_by_label: dict[str, str] = {}
    concept_source: dict[str, str] = {}
    unresolved: list[str] = []
    for label in sorted(found_skills):
        concept_id = resolved.get(label)
        if concept_id:
            concepts_by_label[label] = str(concept_id)
            concept_source[label] = "m04"
            continue
        guess = FALLBACK_RESOLUTIONS.get(label.lower())
        if guess:
            # Usable, and marked. M04 has not confirmed this id exists.
            concepts_by_label[label] = guess
            concept_source[label] = "offline_fallback"
        else:
            unresolved.append(label)

    jd = JobDescription(
        company_name=payload.company_name,
        role_title=payload.role_title,
        raw_text=payload.raw_text,
        required_skills=sorted(found_skills),
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
