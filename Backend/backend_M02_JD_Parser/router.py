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
import logging
import math
import re
import time
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from ai_core.concepts import normalise_alias
from ai_core.dependencies import DependencyRegistry, DependencyStatus
from ai_core.identity import Principal, may_see, principal_from_headers
from ai_core.mastery import SE_PRIOR
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
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from backend_M02_JD_Parser.archetypes import ARCHETYPES, BY_ID, backfill_labels, candidates
from backend_M02_JD_Parser.archetypes import match as match_archetype
from backend_M02_JD_Parser.company import (
    CompanyBrief,
    build_brief,
    m15_get,
    same_archetype,
)
from backend_M02_JD_Parser.documents import UnreadableDocument, to_text
from backend_M02_JD_Parser.edits import ACTIONS, NECESSITY, RequirementEdit, effective
from backend_M02_JD_Parser.language import dominant_script
from backend_M02_JD_Parser.ledger import (
    ANSWERED,
    ASKED,
    PLANNED,
    SCORED,
    STATES,
    CoverageLedger,
    CoverageTurnScore,
    covered_counts,
    owed_scored_rows,
    scores_by_requirement,
)
from backend_M02_JD_Parser.match import MatchReport, build_match
from backend_M02_JD_Parser.models import JobDescription
from backend_M02_JD_Parser.normalise import for_requirements, normalise, too_thin
from backend_M02_JD_Parser.plan import CoveragePlan, build_plan
from backend_M02_JD_Parser.propose import merge, propose
from backend_M02_JD_Parser.safety import neutralise, normalise_homoglyphs, scan

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


log = logging.getLogger("uvicorn.error")

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

#: §6.5: *"state = not_measured if confidence < 0.25"*.
#:
#: Below this we have a number from M04 and no business acting on it. Reporting
#: a mastery the estimator itself is unsure of is worse than reporting nothing,
#: because a bar reads as a finding and "we asked you one question about this
#: eighteen months ago" does not.
MIN_CONFIDENCE = 0.25


def confidence_from(se_effective: float | None) -> float | None:
    """§6.5's `confidence = 1 - mean(standard_error)`, on the platform's scale.

    Normalised by `SE_PRIOR` rather than by a literal, because that constant
    already exists and means exactly the right thing: *"you cannot know less
    than you knew before you had any data."* An SE at the prior is confidence 0;
    an SE of 0 is confidence 1.

    Writing 1.5 here instead would be a second definition of a number that has
    one, and the day M04 retunes its prior this module would disagree with it
    silently.

    `None` when the upstream did not state an SE at all, and that is NOT the
    same as zero. Zero means "M04 measured this and is completely unsure";
    `None` means nobody said. Collapsing the two would take a real `mastery_p`
    from an upstream that publishes no uncertainty and throw it away — Rule 2
    says a missing field narrows scope, it does not destroy quality.
    """
    if se_effective is None:
        return None
    return max(0.0, min(1.0, 1.0 - (se_effective / SE_PRIOR)))


#: A job description is a page or two. Anything past this is the wrong file,
#: and reading it into memory before finding that out is how an upload endpoint
#: becomes a way to exhaust the server.
MAX_UPLOAD_BYTES = 5 * 1024 * 1024

#: §11's budget, in milliseconds, keyed as the stages are timed.
#:
#: `model` is §11's "extraction (mid tier)" 4 s. It is the only stage that is
#: optional and the only one that leaves this machine, which is why it is worth
#: seeing on its own: a slow parse is almost always a slow model call, and a
#: deployment with no key never pays it.
STAGE_BUDGET_MS = {
    "total": 8_000,
    "normalise": 100,
    "extract": 500,
    "model": 4_000,
    "resolve": 500,
}


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


def _m04_get(path: str, candidate_id: uuid.UUID | str | None = None) -> Any | None:
    """GET from M04, or None.

    Probes first: `is_available` is cached, the call is not, and asking a dead
    port three times per request costs a socket timeout each time.

    A candidate-scoped read forwards that student, exactly as M02 does when it
    calls M01. M04 refuses an anonymous caller on every candidate route since
    2026-09-23; before that it answered anybody, which is why this worked
    without saying who was asking.
    """
    deps = dependency_registry()
    dep = deps.get("M04")
    if dep is None or not dep.base_url or not deps.is_available("M04"):
        return None
    headers = {"User-Agent": USER_AGENT}
    if candidate_id is not None:
        headers.update({"X-Role": "student", "X-Candidate-Id": str(candidate_id)})
    request = urllib.request.Request(f"{dep.base_url.rstrip('/')}{path}", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=2.0) as response:
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
    return _m04_get(f"/v1/candidates/{candidate_id}/mastery", candidate_id)


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


#: The five concepts whose M04 ids are known and verified.
#:
#: Hand-written on purpose, and the only part of the offline path that is. An
#: id here is a claim that M04's ontology contains this exact string, and it is
#: checked against M04 at `test_the_offline_ids_are_ids_m04_actually_has`.
_VERIFIED_CONCEPTS: list[dict[str, Any]] = [
    {"name": "Dynamic Programming", "aliases": ["DP", "dynamic programming"]},
    {"name": "Recursion", "aliases": ["recursion"]},
    {"name": "Hashing", "aliases": ["hashing", "hash map", "hashmap"]},
    {"name": "SQL", "aliases": ["sql", "sql_queries"]},
    {"name": "Transactions", "aliases": ["transactions", "transactions_acid"]},
]

#: label -> M04 concept id, for the five above and nothing else.
#:
#: Deliberately NOT derived, while the vocabulary below is. An id invented from
#: an archetype label — `concept:kubernetes` — would look exactly like a real
#: one and match nothing in M04, so every mastery lookup against it returns
#: nothing and "no score" becomes indistinguishable from "not measured yet".
#: Five honest ids beat a hundred and ninety plausible ones.
FALLBACK_RESOLUTIONS = {
    "dynamic programming": "concept:dynamic_programming",
    "recursion": "concept:recursion",
    "hashing": "concept:hashing",
    # `concept:sql_queries`, not `concept:sql_basics`. M04 has never had the
    # second, and M02 had been handing it out since the offline table was
    # written — caught the first time the ids were checked against M04's
    # ontology rather than against this file.
    #
    # The damage was not limited to a degraded parse. FR-2.12 caches the parse
    # by content hash and SHARES it across every student on the drive, so one
    # posting parsed while M04 happened to be down stored a dead id in
    # `resolved_concepts` for all sixty of them — and a dead id fails silently
    # in the worst direction: the mastery lookup succeeds, returns no rows, and
    # reads as "never measured" rather than as "this id is wrong".
    "sql": "concept:sql_queries",
    "transactions": "concept:transactions_acid",
}


@lru_cache(maxsize=1)
def _fallback_concepts() -> list[dict[str, Any]]:
    """What the module can recognise with M04 unreachable.

    Five entries was the honest answer and a nearly useless one: a posting
    scanned offline saw DP, recursion, hashing, SQL and transactions, and was
    blind to every other thing a company has ever asked for.

    The 24 archetypes already carry the canonical requirement set for each
    role — about 190 labels, reviewed, and trusted enough that §6.3 ADDS
    requirements from them. Reusing that vocabulary here costs nothing to
    maintain and cannot drift, because there is one copy of it.

    None of the derived entries carries a concept id. They widen what the
    module can SEE; grounding still needs M04, which is the `testable` versus
    `grounded` split FR-2.5 already draws.
    """
    from backend_M02_JD_Parser.archetypes import ARCHETYPES

    concepts = list(_VERIFIED_CONCEPTS)
    seen = {normalise_alias(c["name"]) for c in concepts}

    for archetype in ARCHETYPES:
        for requirement in archetype.requirements:
            key = normalise_alias(requirement)
            if key and key not in seen:
                seen.add(key)
                concepts.append({"name": requirement, "aliases": [requirement.lower()]})
    return concepts


#: Enough ontology to be useful with M04 down, and never mistaken for the
#: ontology — responses record which one was used.
FALLBACK_CONCEPTS: list[dict[str, Any]] = _fallback_concepts()


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
    # ------------------------------------------------------------------
    #  Stage 1 (§6.1) — get the job out of the document it arrived in
    # ------------------------------------------------------------------
    #  Before this ran, Cognizant's 2027 brochure produced "All rights
    #  reserved" as its HIGHEST-weighted requirement: the copyright footer
    #  appears once per page, and §6.4 counts repetition as emphasis, so the
    #  parser concluded the most important thing the job asks for is a legal
    #  notice. It did exactly what it was told.
    #
    #  Hashed AFTER normalising, so the same posting forwarded twice with
    #  different mail furniture is one cache entry rather than two.
    started = time.perf_counter()
    stage_ms: dict[str, int] = {}

    def _mark(name: str, since: float) -> float:
        stage_ms[name] = int((time.perf_counter() - since) * 1000)
        return time.perf_counter()

    text = normalise(payload.raw_text)
    if too_thin(payload.raw_text, text):
        # EC-2.4. Not an error — the upload worked, there is just no job in it.
        raise HTTPException(
            status_code=422,
            detail=(
                "There is not much job description in that once the signatures, footers and "
                "disclaimers are removed. Paste just the role and requirements section."
            ),
        )

    # ------------------------------------------------------------------
    #  EC-2.13 — the posting is untrusted text
    # ------------------------------------------------------------------
    #  Before anything reads it, and long before §6.2 sends it to a model. A
    #  resume is uploaded by the person it is about and the attack is
    #  self-interested; a JD is pasted by a student who did not write it,
    #  parsed ONCE, and shared across sixty students (FR-2.12). One poisoned
    #  posting reaches everybody preparing for that drive.
    #
    #  Homoglyphs are folded first because they are how the patterns get
    #  dodged, and both operations preserve length exactly — every span this
    #  module stores is an offset into this string.
    text = normalise_homoglyphs(text)
    findings = scan(text)
    if findings:
        text = neutralise(text, findings)
        log.warning(
            "M02 neutralised %d instruction-shaped span(s) in a job description: %s",
            len(findings),
            ", ".join(sorted({f.kind for f in findings})),
        )

    # EC-2.6, decided before anything tries to read the text. A Devanagari
    # posting used to go through the whole pipeline, match no lexicon entry and
    # produce a clean screen saying the job asks for no skills.
    script, share = dominant_script(text)

    mark = _mark("normalise", started)

    digest = content_digest(payload.company_name, payload.role_title, text)
    cached = session.exec(
        select(JobDescription).where(JobDescription.content_sha256 == digest)
    ).first()
    if cached is not None:
        # A cache hit is the §11 "cached JD ≤ 1 s" path, and it is worth timing
        # separately: it is the number sixty students out of sixty-one get.
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
    # The label list comes from the document WITHOUT its administrative block;
    # every span is still located against `text`, which is what gets stored.
    # See `normalise.for_requirements` — eligibility deliberately reads the
    # fuller version, because an arrears rule inside a registration section is
    # still an arrears rule.
    role_block = for_requirements(text)
    surface_forms = extract_surface_forms(role_block)
    mark = _mark("extract", mark)

    # ------------------------------------------------------------------
    #  §6.2 — the model reads what no regex can, and the document checks it
    # ------------------------------------------------------------------
    #  Not a replacement for the lexicon: a union with it. The two fail in
    #  opposite directions, which is the whole reason to run both —
    #
    #      the lexicon   misses prose, never invents
    #      the model     reads prose, would invent if allowed to
    #
    #  Every proposal must verbatim-resolve in this document or it is dropped
    #  (see `propose.py`), so the model can only point AT the posting. On the
    #  golden corpus the union moves recall 0.826 -> 0.957, and the one case
    #  the lexicon cannot do at all — a requirements paragraph with no heading,
    #  no bullet and no delimiter pattern — goes 0.000 -> 1.000.
    #
    #  Runs once per unique posting, because the parse is cached by content
    #  hash (FR-2.12). Sixty students on one drive pay for one call.
    proposed, model_reason = propose(role_block)
    mark = _mark("model", mark)
    extracted_by = "lexicon"
    if proposed:
        surface_forms = merge(surface_forms, proposed)
        extracted_by = "lexicon+model"
    elif model_reason:
        # Named, not silent. "Why is this posting's list thin?" should be
        # answerable from the row rather than from the logs.
        extracted_by = f"lexicon (model: {model_reason})"

    # Concepts named in prose rather than enumerated. Ambiguous one-word
    # aliases are excluded there — that is what closes the "solid" hole.
    prose_hits = scan_prose(role_block, concepts)

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

    # ------------------------------------------------------------------
    #  FR-2.6 — the 40-word campus JD is the MEDIAN, not the edge case
    # ------------------------------------------------------------------
    #  §3.2.1 trap 1. "Looking for SDE trainees. Good knowledge of DSA and
    #  OOPs." yields two requirements, and a coverage plan over two
    #  requirements is not a mock interview — it is two questions and a shrug.
    #
    #  §6.3's rule: under five, top up to eight from the archetype, and mark
    #  every addition. `source="archetype"` with `span=None` is the pair that
    #  makes it auditable — a requirement with no span claiming to come from the
    #  JD would be a bug, and a screen can tell them apart without asking.
    archetype, confidence = match_archetype(payload.role_title, text)
    inferred: list[str] = []
    if archetype is not None:
        inferred = backfill_labels(archetype, required)
        # Resolved like any other label, so a backfilled requirement is
        # measurable on the same terms as a stated one.
        if inferred:
            for label in inferred:
                guess = resolve_labels([label]).get(label) or FALLBACK_RESOLUTIONS.get(
                    normalise_alias(label)
                )
                if guess:
                    concepts_by_label[label] = str(guess)
                    concept_source[label] = (
                        "m04" if scanned_against == "m04" else "offline_fallback"
                    )
            required = [*required, *inferred]

    # Located against the ORIGINAL text, and folded: "Java or Python" becomes
    # one group over two alternatives rather than three requirements.
    requirement_set = locate(
        text,
        required,
        resolved=concepts_by_label,
        sources=concept_source,
        disjunctions=disjunctions,
        inferred=inferred,
    )

    stage_ms["archetype"] = stage_ms.get("archetype", 0)
    mark = _mark("resolve", mark)

    jd = JobDescription(
        company_name=payload.company_name,
        role_title=payload.role_title,
        raw_text=text,
        content_sha256=digest,
        required_skills=required,
        # Located against the ORIGINAL text, so an offset here indexes exactly
        # what the student pasted.
        # A hard filter, never an interview topic (§3.2.2) — so it is stored
        # beside the requirements rather than among them.
        eligibility=extract_eligibility(text).model_dump(mode="json"),
        requirements=[
            requirement.model_dump(mode="json") for requirement in requirement_set.requirements
        ],
        requirement_groups=[group.model_dump(mode="json") for group in requirement_set.groups],
        resolved_concepts=concepts_by_label,
        concept_source=concept_source,
        unresolved_skills=unresolved,
        scanned_against=scanned_against,
        role_archetype=archetype.id if archetype else None,
        # EC-2.14. `match` refused because two archetypes were too close, which
        # is right and was silent. Naming them lets the screen ask.
        role_candidates=[
            {"id": a.id, "name": a.name, "confidence": c}
            for a, c in (candidates(payload.role_title, text) if archetype is None else [])
        ],
        archetype_confidence=confidence,
        # Counted from the RESULT, not from what was suggested: a suggested
        # label that turned out to be in the document is stated, not inferred.
        injections_removed=len(findings),
        # EC-2.6. Detected on the NORMALISED text, not the raw bytes: a PDF's
        # header and font names are Latin and would dilute the share of a
        # posting that is entirely Devanagari.
        script=script,
        script_share=share,
        extracted_by=extracted_by,
        parse_ms=int((time.perf_counter() - started) * 1000),
        stage_ms=stage_ms,
        inferred_count=sum(1 for r in requirement_set.requirements if r.source == "archetype"),
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

    confidence_by_label: dict[str, float] = {}

    for label, concept_id in jd.resolved_concepts.items():
        row = measured_map.get(concept_id)
        mastery_p = row.get("mastery_p") if row else None

        # `se_effective`, not `se`. The first is what was persisted when the
        # evidence arrived; the second is that widened by how long ago it
        # arrived. M04's own comment says `se_effective` "is what every display
        # rule uses", and a coverage plan is a display rule with a budget
        # attached — a concept measured confidently eighteen months ago should
        # be probed again, and `se` alone would call it settled.
        se_effective = None
        if row is not None:
            se_effective = row.get("se_effective", row.get("se"))
        confidence = confidence_from(se_effective)
        if confidence is not None:
            confidence_by_label[label] = round(confidence, 3)
        mastery_by_label[label] = mastery_p

        # §6.5: *"not_measured if confidence < 0.25"*. A number the estimator
        # is unsure of is worse than no number, because a bar reads as a
        # finding and "we asked you one question about this a year ago" does
        # not. This is the case the module could not previously see: M04
        # answered, it had a `mastery_p`, and it should still not have been
        # scored.
        if mastery_p is not None and confidence is not None and confidence < MIN_CONFIDENCE:
            not_measured.append(label)
            states[label] = "not_measured"
            gap_severity[label] = NOT_MEASURED_SEVERITY
            continue

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
            # §6.5: `severity = weight * (1 - mastery) * confidence_discount`.
            # The weight is applied by the planner; this is the rest of it. A
            # weakness we are only half sure of is half a weakness.
            gap_severity[label] = round((1.0 - mastery_p) * (confidence or 1.0), 4)
        else:
            covered.append(label)
            states[label] = "adequate" if mastery_p < ADEQUATE_BELOW else "strong"
            gap_severity[label] = round(max(0.0, 1.0 - mastery_p) * (confidence or 1.0), 4)

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
        # §6.5's confidence, per requirement. Exposed rather than folded
        # away, because a student told a topic is 'not measured' when M04
        # plainly has a number for it is owed the reason.
        "confidence": confidence_by_label,
        "gap_severity": gap_severity,
        # Two numbers, because one of them was doing both jobs badly.
        #
        # GROUNDED is what M04's concept graph can drive adaptively. TESTABLE
        # is what a question can be put in front of the student for at all,
        # including requirements M05 must generate from. On a modern posting
        # the first is small and the second is nearly everything, and reporting
        # only the first said "72 of 73 untestable" about a JD where 72 are
        # perfectly askable.
        "grounded_count": sum(1 for r in (jd.requirements or []) if r.get("grounded")),
        "testable_count": sum(1 for r in (jd.requirements or []) if r.get("testable")),
        "requirement_total": len(jd.requirements or []),
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


def _evidence_for(jd: JobDescription, candidate_id: str) -> dict[str, float]:
    """M15's per-requirement nudge, or nothing at all (FR-2.13).

    Nothing at all is the ordinary case and it costs one cached probe: M15 down,
    M15 does not know the company, or it knows the company and holds too few
    reported questions for the distribution to mean anything. All three are
    "plan from the posting alone", which is what M02 did before M15 existed and
    is a complete answer.
    """
    brief = build_brief(
        dependency_registry(),
        company_name=jd.company_name or "",
        role_title=jd.role_title or "",
        archetype=jd.role_archetype,
        eligibility=jd.eligibility or {},
        requirements=jd.requirements or [],
        candidate_id=candidate_id,
    )
    return brief.evidence_boost if brief else {}


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
        # EC-2.5. An HR interview does not open a coding round because the JD
        # mentioned SQL in passing.
        archetype=jd.role_archetype,
        # FR-2.13. What this company is actually reported to ask about, as a
        # bounded nudge to §6.4's weights. Built from the same function the
        # brief route serves, so the plan and the panel beside it can never
        # disagree about which drive this posting is.
        evidence=_evidence_for(jd, str(candidate_id)),
        # §6.6. A plan rebuilt mid-session must not re-ask what the session has
        # already covered, and the only thing that knows is the ledger.
        already_asked=covered_counts(
            list(
                session.exec(
                    select(CoverageLedger)
                    .where(CoverageLedger.jd_id == jd_id)
                    .where(CoverageLedger.candidate_id == candidate_id)
                ).all()
            )
        ),
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


@router.get("/jds/{jd_id}/company", response_model=CompanyBrief | None)
def get_jd_company(
    jd_id: uuid.UUID,
    candidate_id: uuid.UUID | None = None,
    session: Session = Depends(get_db),
):
    """What M15 knows about the company this posting is for (FR-2.13).

    A JD says what a company WANTS. M15 holds what it ASKED — the questions
    students reported after sitting the drive, the package that was actually
    offered, the bond the posting never mentioned. Only the second kind of fact
    is unavailable anywhere else, which is the whole argument for the call.

    ── Why `null` is a real answer ────────────────────────────────────────────

    `null` covers two cases and the screen distinguishes them by asking `/deps`,
    which it already renders: M15 is down, or M15 does not know this company.
    The first is an outage and the second is ordinary — most postings are for
    companies nobody on this campus has reported yet — and neither is an error,
    so neither raises.

    A brief that comes back with `report_count: 0` is the third case and it is
    the interesting one: M15 knows the company and has no reports. That is a
    page that invites a submission rather than one that apologises.

    ── `candidate_id` is optional here, and gated when present ────────────────

    Optional because the brief is public information: every student on the
    campus sees the same reported questions. Passing it asks M15 to order those
    questions against this student's gaps, which is personal, so the parameter
    goes through `enforce_access` exactly like the routes that require it.
    """
    jd = session.get(JobDescription, jd_id)
    if not jd:
        raise HTTPException(status_code=404, detail="Job Description not found")

    return build_brief(
        dependency_registry(),
        company_name=jd.company_name or "",
        role_title=jd.role_title or "",
        archetype=jd.role_archetype,
        eligibility=jd.eligibility or {},
        requirements=jd.requirements or [],
        candidate_id=str(candidate_id) if candidate_id else None,
    )


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


class ArchetypeOut(BaseModel):
    """One entry in §2.3's door-3 role picker."""

    id: str
    name: str
    #: What a mock for this role would cover. Shown before the student commits,
    #: because "just pick a role" is only trustworthy if they can see what they
    #: are picking — otherwise it is a button that produces an interview about
    #: something unspecified.
    requirements: list[str]
    default_minutes: int


@router.get("/archetypes", response_model=list[ArchetypeOut], tags=["meta"])
def list_archetypes():
    """§7's `GET /v1/archetypes` — the role picker list (FR-2.14).

    Ordered as the library is written, which is roughly by how many campus
    drives hire for each. Not alphabetical: a student scanning this wants the
    common cases first, and "Associate Product Manager" leading the list because
    of its initial would be a worse screen.
    """
    return [
        ArchetypeOut(
            id=archetype.id,
            name=archetype.name,
            requirements=list(archetype.requirements),
            default_minutes=archetype.default_minutes,
        )
        for archetype in ARCHETYPES
    ]


class RoleOnlyIn(BaseModel):
    """§2.3 door 3: "just pick a role"."""

    archetype_id: str
    #: Optional. A student who knows the company can name it and still skip the
    #: posting — that is a real case in September, when the calendar is out and
    #: the JDs are not.
    company_name: str = "Any company"


class CompanyOption(BaseModel):
    """One company the student can pick, as M15 spells it (§2.3 door 1)."""

    id: str
    name: str
    #: Every other spelling M15 resolves to this company. Shown, because a
    #: student searching "CTS" needs to recognise "Cognizant" in the result.
    aliases: list[str] = Field(default_factory=list)
    #: How many drive reports M15 holds. The list screen's real advantage is
    #: showing how much is known BEFORE the student commits to a company.
    report_count: int = 0


class DriveOption(BaseModel):
    """One drive chip: a specific interview this company runs."""

    id: str
    name: str
    company_id: str
    #: M15's archetype string, resolved to M02's id where the two agree. `None`
    #: when M15 names a role M02 has no archetype for — the chip still works,
    #: it just cannot pre-fill a requirement set.
    archetype_id: str | None = None
    typical_package_lpa: float | None = None
    bond_months: int | None = None
    typical_locations: list[str] = Field(default_factory=list)


@router.get("/companies", response_model=list[CompanyOption], tags=["meta"])
def list_companies(q: str = ""):
    """The companies a student can pick from (§2.3 door 1).

    A proxy onto M15 rather than a table of M02's own. §3.2's fifth hard part
    is that "TCS", "Tata Consultancy Services" and "TCS Digital" are one
    company and several drives, and that the alias table matters more than it
    sounds — so there is exactly one of it, in the module that owns it.

    Empty rather than an error when M15 is down. The screen needs to render
    either way, `/deps` already says which module is missing, and an exception
    here would take the whole input screen down over an optional door.
    """
    rows = m15_get(dependency_registry(), f"/v1/companies?q={urllib.parse.quote(q.strip())}")
    if not isinstance(rows, list):
        return []
    return [
        CompanyOption(
            id=str(row.get("id")),
            name=str(row.get("canonical_name") or ""),
            aliases=[str(a) for a in row.get("aliases") or []],
            report_count=int(row.get("report_count") or 0),
        )
        for row in rows
        if row.get("id")
    ]


@router.get("/companies/{company_id}/drives", response_model=list[DriveOption], tags=["meta"])
def list_drives(company_id: str):
    """The drives this company runs — §2.3's "highest-value element".

    Each carries the figures the posting would have stated, so a student who
    picks a chip already knows the package and the bond before any JD exists.

    `archetype_id` is resolved through `same_archetype`, which reads M15's
    spelling against M02's archetype titles. The two vocabularies are not the
    same and were never going to be: M15 writes `sde`, M02's id is `sde_1`.
    """
    rows = m15_get(dependency_registry(), f"/v1/companies/{company_id}/variants")
    if not isinstance(rows, list):
        return []

    out: list[DriveOption] = []
    for row in rows:
        if not row.get("id"):
            continue
        m15_archetype = str(row.get("role_archetype") or "")
        matched = next(
            (a.id for a in ARCHETYPES if same_archetype(m15_archetype, a.id)),
            None,
        )
        out.append(
            DriveOption(
                id=str(row["id"]),
                name=str(row.get("name") or ""),
                company_id=str(company_id),
                archetype_id=matched,
                typical_package_lpa=row.get("typical_package_lpa"),
                bond_months=row.get("bond_months"),
                typical_locations=[str(x) for x in row.get("typical_locations") or []],
            )
        )
    return out


class DriveIn(BaseModel):
    """§2.3 door 1: a company and the drive being sat."""

    company_id: str
    drive_id: str


@router.post("/jds/from-drive", response_model=JobDescription, status_code=status.HTTP_201_CREATED)
def parse_from_drive(
    payload: DriveIn,
    response: Response,
    session: Session = Depends(get_db),
):
    """A requirement set for a named drive at a named company (§2.3 door 1).

    Door 3 already turns an archetype into a requirement set. This is the same
    machinery with two things door 3 cannot know: WHICH company, and which of
    that company's interviews.

    Both matter to everything downstream. The company name is what FR-2.13
    resolves to fetch the drive's reported topics and its package and bond; the
    drive is which of three TCS interviews the student is actually sitting. A
    plan built from "SDE at any company" and one built from "TCS Digital" are
    different plans, and until now only the first could be asked for.

    `raw_text` stays EMPTY, exactly as in door 3 and for the same reason: there
    is no posting, and storing a plausible one would make the read-back screen
    quote sentences no company published.
    """
    drives = list_drives(payload.company_id)
    drive = next((d for d in drives if d.id == payload.drive_id), None)
    if drive is None:
        # Covers both "no such drive" and "M15 is down", and says which,
        # because only one of them is something the student can act on.
        deps = dependency_registry()
        if not deps.is_available("M15"):
            raise HTTPException(
                status_code=503,
                detail=(
                    "Company drives need M15 Company Guider, which is not running. "
                    "You can still paste the posting, upload it, or pick a role."
                ),
            )
        raise HTTPException(status_code=404, detail="No such drive for this company.")

    companies = list_companies(q="")
    company = next((c for c in companies if c.id == payload.company_id), None)
    company_name = company.name if company else "Any company"

    archetype = BY_ID.get(drive.archetype_id or "")
    if archetype is None:
        raise HTTPException(
            status_code=422,
            detail=(
                f"We know the {drive.name} drive but not the role it hires for, so we "
                "cannot build a requirement set for it. Pick a role instead, or paste "
                "the posting."
            ),
        )

    # Keyed on the DRIVE, not the archetype. Two students sitting TCS Digital
    # share one requirement set; a student sitting TCS Ninja does not share
    # theirs, because it is a different interview.
    digest = content_digest(company_name, drive.name, f"drive:{drive.id}")
    cached = session.exec(
        select(JobDescription).where(JobDescription.content_sha256 == digest)
    ).first()
    if cached is not None:
        response.status_code = status.HTTP_200_OK
        return cached

    concepts = get_m04_concepts()
    scanned_against = "m04" if concepts else "offline_lexicon"

    labels = list(archetype.requirements)
    resolved = resolve_labels(labels)
    concepts_by_label: dict[str, str] = {}
    concept_source: dict[str, str] = {}
    unresolved: list[str] = []
    for label in labels:
        concept_id = resolved.get(label) or FALLBACK_RESOLUTIONS.get(normalise_alias(label))
        if concept_id:
            concepts_by_label[label] = str(concept_id)
            concept_source[label] = "m04" if resolved.get(label) else "offline_fallback"
        else:
            unresolved.append(label)

    requirement_set = locate(
        "",
        labels,
        resolved=concepts_by_label,
        sources=concept_source,
        inferred=labels,
    )

    # What M15 knows about the drive, stored as eligibility. These are the only
    # figures on this record that came from anywhere real — there is no posting
    # to read them off, and reported figures are better than none.
    eligibility: dict[str, Any] = {}
    if drive.typical_package_lpa is not None:
        eligibility["package_lpa_total"] = drive.typical_package_lpa
    if drive.bond_months is not None:
        eligibility["bond_months"] = drive.bond_months
    if drive.typical_locations:
        eligibility["location"] = drive.typical_locations

    jd = JobDescription(
        company_name=company_name,
        role_title=drive.name,
        raw_text="",
        content_sha256=digest,
        required_skills=labels,
        eligibility=eligibility,
        requirements=[r.model_dump(mode="json") for r in requirement_set.requirements],
        requirement_groups=[g.model_dump(mode="json") for g in requirement_set.groups],
        resolved_concepts=concepts_by_label,
        concept_source=concept_source,
        unresolved_skills=unresolved,
        scanned_against=scanned_against,
        extracted_by="drive",
        role_archetype=archetype.id,
        # Chosen by the student, not inferred by us.
        archetype_confidence=1.0,
        inferred_count=len(labels),
    )
    session.add(jd)
    session.commit()
    session.refresh(jd)
    return jd


@router.post("/jds/from-role", response_model=JobDescription, status_code=status.HTTP_201_CREATED)
def parse_from_role(
    payload: RoleOnlyIn,
    response: Response,
    session: Session = Depends(get_db),
):
    """A requirement set with no job description at all (FR-2.14).

    §2.3: *"Door 3 ('just pick a role') is mandatory. A student in September
    with no drive scheduled still needs to practise. Requiring a JD to use the
    product would be a self-inflicted wound."* It was a self-inflicted wound
    until now — with no posting there was no way into this module.

    Every requirement here carries `source="archetype"` and `span=None`, which
    is not a degraded version of a parse: it is an accurate description of where
    these came from. There is no document, so there is nothing to point at, and
    §6.4 discounts them to 0.75 exactly as it does a backfill.

    `raw_text` is EMPTY rather than a synthesised posting. Writing a plausible
    JD and storing it would make the read-back screen quote sentences no company
    ever published, which is the one thing this module must never do.
    """
    archetype = BY_ID.get(payload.archetype_id)
    if archetype is None:
        raise HTTPException(
            status_code=404,
            detail=f"No such role. Ask /v1/archetypes for the {len(ARCHETYPES)} we know.",
        )

    # Cached like a pasted JD, on the same terms: two students picking "SDE"
    # share one requirement set, because it IS one requirement set.
    digest = content_digest(payload.company_name, archetype.name, f"archetype:{archetype.id}")
    cached = session.exec(
        select(JobDescription).where(JobDescription.content_sha256 == digest)
    ).first()
    if cached is not None:
        response.status_code = status.HTTP_200_OK
        return cached

    concepts = get_m04_concepts()
    scanned_against = "m04" if concepts else "offline_lexicon"

    labels = list(archetype.requirements)
    resolved = resolve_labels(labels)
    concepts_by_label: dict[str, str] = {}
    concept_source: dict[str, str] = {}
    unresolved: list[str] = []
    for label in labels:
        concept_id = resolved.get(label) or FALLBACK_RESOLUTIONS.get(normalise_alias(label))
        if concept_id:
            concepts_by_label[label] = str(concept_id)
            concept_source[label] = "m04" if resolved.get(label) else "offline_fallback"
        else:
            unresolved.append(label)

    # Located against the empty string, which finds nothing — correctly. Every
    # requirement comes back with `span=None` and `source="archetype"`.
    requirement_set = locate(
        "",
        labels,
        resolved=concepts_by_label,
        sources=concept_source,
        inferred=labels,
    )

    jd = JobDescription(
        company_name=payload.company_name,
        role_title=archetype.name,
        raw_text="",
        content_sha256=digest,
        required_skills=labels,
        eligibility={},
        requirements=[r.model_dump(mode="json") for r in requirement_set.requirements],
        requirement_groups=[g.model_dump(mode="json") for g in requirement_set.groups],
        resolved_concepts=concepts_by_label,
        concept_source=concept_source,
        unresolved_skills=unresolved,
        scanned_against=scanned_against,
        extracted_by="archetype",
        role_archetype=archetype.id,
        # Chosen, not inferred. A student saying "I am preparing for an SDE
        # role" is not a match we made and were 0.62 sure of.
        archetype_confidence=1.0,
        inferred_count=len(labels),
    )
    session.add(jd)
    session.commit()
    session.refresh(jd)
    return jd


# ---------------------------------------------------------------------------
#  FR-2.10 — the student corrects a parse they do not own
# ---------------------------------------------------------------------------


class RequirementEditIn(BaseModel):
    """One correction. `value` is only read for `necessity`."""

    action: str
    target: str
    value: str = ""


def _effective_set(jd: JobDescription, candidate_id: uuid.UUID, session: Session):
    """This candidate's view of a shared parse, with their edits applied.

    Re-runs `locate` rather than patching the stored rows, so necessity,
    §6.4's weights, the disjunction grouping and the classification are all
    RE-DERIVED. Removing a requirement redistributes its weight across the
    rest, which is what normalisation means and what a hand-adjusted list gets
    wrong on the very first edit.
    """
    edits = list(
        session.exec(
            select(RequirementEdit)
            .where(RequirementEdit.jd_id == jd.id)
            .where(RequirementEdit.candidate_id == candidate_id)
        ).all()
    )
    stored = jd.requirements or []
    if not edits:
        return stored, jd.requirement_groups or [], 0

    labels, overrides, extra_sources = effective([r["text"] for r in stored], edits)

    # Provenance carried across from the original parse, so an edited set still
    # says which ids came from M04 and which the offline table guessed.
    concept_source = dict(jd.concept_source or {})
    concept_source.update(extra_sources)

    inferred = [r["text"] for r in stored if r.get("source") == "archetype"]
    result = locate(
        jd.raw_text,
        labels,
        resolved=jd.resolved_concepts or {},
        sources=concept_source,
        disjunctions=find_disjunctions(labels, jd.resolved_concepts or {}),
        inferred=[label for label in inferred if label in labels],
        necessity_overrides=overrides,
    )
    requirements = [r.model_dump(mode="json") for r in result.requirements]

    # A label the student ADDED is theirs, and §6.4 discounts anything that is
    # not `jd` to 0.75 — so their addition counts, and counts slightly less
    # than what the company actually wrote.
    added = {" ".join(k.lower().split()) for k, v in extra_sources.items() if v == "user"}
    for requirement in requirements:
        if " ".join(requirement["text"].lower().split()) in added:
            requirement["source"] = "user"

    groups = [g.model_dump(mode="json") for g in result.groups]
    return requirements, groups, len(edits)


@router.get("/jds/{jd_id}/requirements/{candidate_id}")
def get_effective_requirements(
    jd_id: uuid.UUID,
    candidate_id: uuid.UUID,
    session: Session = Depends(get_db),
):
    """This student's view of the posting (FR-2.10).

    Candidate-scoped, and that is the whole design. `GET /jds/{id}` returns the
    SHARED parse — one row, cached by content hash across every student who
    pasted the same posting (FR-2.12) — and it stays shared. This returns the
    same parse with one student's corrections laid over it.

    Two students on one drive can disagree about what the posting says, and
    both are served correctly, because neither ever writes to the other's copy.
    """
    jd = session.get(JobDescription, jd_id)
    if not jd:
        raise HTTPException(status_code=404, detail="Job Description not found")

    requirements, groups, edit_count = _effective_set(jd, candidate_id, session)
    return {
        "jd_id": str(jd_id),
        "candidate_id": str(candidate_id),
        "requirements": requirements,
        "requirement_groups": groups,
        "edit_count": edit_count,
    }


@router.post("/jds/{jd_id}/requirements/{candidate_id}", status_code=status.HTTP_201_CREATED)
def edit_requirements(
    jd_id: uuid.UUID,
    candidate_id: uuid.UUID,
    payload: RequirementEditIn,
    session: Session = Depends(get_db),
):
    """Record one correction. The shared parse is never written to.

    A `PATCH` on the requirement itself is what §7 sketches, and it would be
    the wrong verb here: there is nothing of this student's to patch. The
    posting belongs to the company and the parse is shared sixty ways. What is
    being created is a correction that belongs to them.
    """
    if payload.action not in ACTIONS:
        raise HTTPException(
            status_code=422,
            detail=f"action must be one of {', '.join(sorted(ACTIONS))}",
        )
    if payload.action == NECESSITY and payload.value not in {"must", "should", "could"}:
        raise HTTPException(
            status_code=422,
            detail="necessity must be must, should or could",
        )
    if not payload.target.strip():
        raise HTTPException(status_code=422, detail="target is required")

    jd = session.get(JobDescription, jd_id)
    if not jd:
        raise HTTPException(status_code=404, detail="Job Description not found")

    edit = RequirementEdit(
        candidate_id=candidate_id,
        jd_id=jd_id,
        action=payload.action,
        target=payload.target.strip(),
        value=payload.value.strip(),
    )
    session.add(edit)
    session.commit()

    requirements, groups, edit_count = _effective_set(jd, candidate_id, session)
    return {
        "jd_id": str(jd_id),
        "candidate_id": str(candidate_id),
        "requirements": requirements,
        "requirement_groups": groups,
        "edit_count": edit_count,
    }


@router.delete("/jds/{jd_id}/requirements/{candidate_id}")
def reset_requirement_edits(
    jd_id: uuid.UUID,
    candidate_id: uuid.UUID,
    session: Session = Depends(get_db),
):
    """Throw away this student's corrections and go back to the parse.

    A real button, because the alternative is a student who made three edits
    and cannot remember which — and an edited list nobody trusts is worse than
    an unedited one they can argue with.
    """
    rows = list(
        session.exec(
            select(RequirementEdit)
            .where(RequirementEdit.jd_id == jd_id)
            .where(RequirementEdit.candidate_id == candidate_id)
        ).all()
    )
    for row in rows:
        session.delete(row)
    session.commit()

    jd = session.get(JobDescription, jd_id)
    if not jd:
        raise HTTPException(status_code=404, detail="Job Description not found")

    requirements, groups, edit_count = _effective_set(jd, candidate_id, session)
    return {
        "jd_id": str(jd_id),
        "candidate_id": str(candidate_id),
        "requirements": requirements,
        "requirement_groups": groups,
        "edit_count": edit_count,
        "removed": len(rows),
    }


class StagePerf(BaseModel):
    """p95 for one stage, against the budget §11 sets for it."""

    stage: str
    p95_ms: int
    budget_ms: int
    within_budget: bool
    samples: int


class DoorUsage(BaseModel):
    """How one of §2.3's three doors is actually being used (AC-2.7)."""

    door: str
    #: What a student would call it, because this renders on an ops screen that
    #: a placement officer reads and "extracted_by=lexicon" is not a door.
    label: str
    count: int
    share: float


@router.get("/doors", response_model=list[DoorUsage], tags=["meta"])
def door_usage(session: Session = Depends(get_db)):
    """Which door students come through (AC-2.7).

    §13 asks for the drive-chip versus manual-paste ratio, and until the chips
    existed there was nothing to measure. This is that ratio, over the postings
    this instance holds.

    It is the number that says whether door 1 earned its place. §2.3 claims
    pre-loading the drives means "most students never type anything at all"; if
    the chips ship and the paste share does not move, the claim was wrong and
    the placement-cell calendar behind it is not worth building either.

    Derived from `extracted_by` rather than from a counter of its own. A second
    record of the same event is a second thing to keep correct, and the first
    time the two disagreed nobody could say which was right.

    Empty until something is parsed — the honest answer to "what is your ratio"
    before there is one, and different from a set of zeroes.
    """
    rows = list(session.exec(select(JobDescription)).all())
    if not rows:
        return []

    #: `extracted_by` value -> the door it belongs to. Pasting and uploading
    #: are ONE door: §2.3 counts "bring me the posting" as a single way in, and
    #: a student who forwards the mail as an attachment made the same choice as
    #: one who copied its body.
    doors = {
        "drive": ("drive_chip", "Picked a campus drive"),
        "archetype": ("role_only", "Just picked a role"),
    }

    counts: dict[str, int] = {}
    labels: dict[str, str] = {}
    for row in rows:
        door, label = doors.get(row.extracted_by or "", ("posting", "Pasted or uploaded a posting"))
        counts[door] = counts.get(door, 0) + 1
        labels[door] = label

    total = len(rows)
    return sorted(
        (
            DoorUsage(door=door, label=labels[door], count=count, share=round(count / total, 3))
            for door, count in counts.items()
        ),
        key=lambda usage: usage.count,
        reverse=True,
    )


@router.get("/performance", response_model=list[StagePerf], tags=["meta"])
def performance(session: Session = Depends(get_db)):
    """p95 per stage, over the postings this instance has actually parsed
    (FR-2.16, AC-2.5).

    §11 budgets a cold parse at 8 s and names a figure per stage. None of it
    was ever timed, so the number was UNKNOWN — which is worse than missed. A
    missed budget is a bug report; an unknown one is a blank space where
    everybody assumes it is fine.

    Measured over stored rows rather than a benchmark script, for the same
    reason `golden.py` scores real documents: a benchmark measures the machine
    it ran on, and §11's budget is a claim about what a student waits for.

    Returns an empty list until something has been parsed. That is the honest
    answer to "what is your p95" before there is one, and it is different from
    a zero.
    """
    rows = list(session.exec(select(JobDescription)).all())
    if not rows:
        return []

    def _p95(values: list[int]) -> int:
        if not values:
            return 0
        ordered = sorted(values)
        # Nearest-rank, which needs no interpolation and is right for the small
        # samples this will have long before it has large ones.
        index = max(0, math.ceil(0.95 * len(ordered)) - 1)
        return ordered[index]

    # A row is TIMED if it carries a stage breakdown, not if its total is
    # non-zero. Filtering on `parse_ms` treats a sub-millisecond parse as
    # unmeasured — which is backwards, and made this endpoint's own test fail
    # one run in three depending on how fast the machine was that minute.
    timed = [r for r in rows if r.stage_ms]
    if not timed:
        return []

    totals = [r.parse_ms for r in timed]
    total_p95 = _p95(totals)
    out = [
        StagePerf(
            stage="total",
            p95_ms=total_p95,
            budget_ms=STAGE_BUDGET_MS["total"],
            within_budget=total_p95 <= STAGE_BUDGET_MS["total"],
            samples=len(timed),
        )
    ]
    for stage, budget in STAGE_BUDGET_MS.items():
        if stage == "total":
            continue
        values = [r.stage_ms[stage] for r in timed if stage in r.stage_ms]
        if not values:
            continue
        p95 = _p95(values)
        out.append(
            StagePerf(
                stage=stage,
                p95_ms=p95,
                budget_ms=budget,
                within_budget=p95 <= budget,
                samples=len(values),
            )
        )
    return out


# ---------------------------------------------------------------------------
#  FR-2.11 / §6.6 — the live coverage ledger
# ---------------------------------------------------------------------------


class LedgerEventIn(BaseModel):
    """One turn's progress, written by M05 or M13.

    `turn_id` is optional only for `planned`. Every other state is about a
    question that exists, and a `scored` row with no turn cannot be disputed
    later — which is the one thing a ledger is for.
    """

    jd_id: uuid.UUID
    requirement_id: str
    state: str
    turn_id: uuid.UUID | None = None
    score: float | None = None


@router.post(
    "/sessions/{session_id}/coverage/{candidate_id}",
    status_code=status.HTTP_201_CREATED,
)
def record_coverage(
    session_id: uuid.UUID,
    candidate_id: uuid.UUID,
    payload: LedgerEventIn,
    session: Session = Depends(get_db),
):
    """Record that a requirement was asked about, answered, scored or skipped.

    §6.6: *"When M5 selects a question, it writes `coverage_ledger(...,
    state='asked')`. When M13 scores that turn, the row moves to `scored`."*

    M02 owns this table although M05 and M13 do the writing, because M02 made
    the promise: the plan is its output, the requirement ids are its ids, and
    the weights the re-prioritisation reads are its weights. Which means the
    endpoint has to exist BEFORE either writer does — this is the contract they
    are written against, not a client of theirs.

    Candidate-scoped, so `enforce_access` gates it without being asked to and
    no new authentication mechanism appears. `ai_core.identity` has four roles
    and the list is closed on purpose; M05 forwards the student's identity
    exactly as M02 forwards it to M01.
    """
    if payload.state not in STATES:
        raise HTTPException(
            status_code=422,
            detail=f"state must be one of {', '.join(STATES)}",
        )
    if payload.state != PLANNED and payload.turn_id is None:
        raise HTTPException(
            status_code=422,
            detail=f"turn_id is required for state {payload.state!r} — a row about a question "
            "that does not exist cannot be disputed later, which is what a ledger is for",
        )
    if payload.score is not None and payload.state != SCORED:
        raise HTTPException(
            status_code=422,
            detail="score belongs only on a `scored` row",
        )

    if not session.get(JobDescription, payload.jd_id):
        raise HTTPException(status_code=404, detail="Job Description not found")

    # Appended, never updated. An interview is evidence, and evidence that can
    # be overwritten is evidence somebody can quietly revise — "asked 14:02,
    # answered 14:04, scored 0.3 at 14:09" is the sequence a dispute needs.
    event = CoverageLedger(
        session_id=session_id,
        candidate_id=candidate_id,
        jd_id=payload.jd_id,
        requirement_id=payload.requirement_id,
        turn_id=payload.turn_id,
        state=payload.state,
        score=payload.score,
    )
    session.add(event)
    session.commit()
    session.refresh(event)

    # A score may have arrived first — M13's outbox and M06's drain on their
    # own schedules. Applied now, so arrival order cannot change the ledger.
    if event.turn_id is not None and event.state in (ASKED, ANSWERED):
        apply_turn_score(session, session_id, candidate_id, event.turn_id)

    return {"id": str(event.id), "state": event.state, "recorded_at": event.updated_at}


class TurnScoreIn(BaseModel):
    """What M13 sends when it has scored a turn (`emit.coverage_update`)."""

    score: float = Field(ge=0.0, le=1.0)
    raw_category: int | None = None
    n_categories: int | None = None
    rubric_version: str | None = None
    evaluation_id: uuid.UUID | None = None
    scored_at: datetime | None = None


def apply_turn_score(
    session: Session, session_id: uuid.UUID, candidate_id: uuid.UUID, turn_id: uuid.UUID
) -> int:
    """Append the `scored` rows this turn's newest score is owed. Returns how many."""
    score = session.exec(
        select(CoverageTurnScore)
        .where(CoverageTurnScore.session_id == session_id)
        .where(CoverageTurnScore.candidate_id == candidate_id)
        .where(CoverageTurnScore.turn_id == turn_id)
        .order_by(CoverageTurnScore.recorded_at.desc())
    ).first()
    if score is None:
        return 0
    turn_rows = list(
        session.exec(
            select(CoverageLedger)
            .where(CoverageLedger.session_id == session_id)
            .where(CoverageLedger.candidate_id == candidate_id)
            .where(CoverageLedger.turn_id == turn_id)
        ).all()
    )
    owed = owed_scored_rows(turn_rows, score)
    for jd_id, requirement_id in owed:
        session.add(
            CoverageLedger(
                session_id=session_id,
                candidate_id=candidate_id,
                jd_id=jd_id,
                requirement_id=requirement_id,
                turn_id=turn_id,
                state=SCORED,
                score=score.score,
            )
        )
    if owed:
        session.commit()
    return len(owed)


@router.post(
    "/sessions/{session_id}/coverage/{candidate_id}/turns/{turn_id}/score",
    status_code=status.HTTP_201_CREATED,
)
def record_turn_score(
    session_id: uuid.UUID,
    candidate_id: uuid.UUID,
    turn_id: uuid.UUID,
    payload: TurnScoreIn,
    response: Response,
    session: Session = Depends(get_db),
):
    """M13 scored this turn: move every requirement it touched to `scored`.

    §6.6's second half — *"When M13 scores that turn, the row moves to
    `scored` with the score"* — which until now had no route M13 could call.
    `POST /coverage/{candidate}` takes a requirement id, and M13 does not know
    one: it knows the turn. M02 owns the mapping, so M02 does it.

    **202 when nothing is known about the turn yet.** The score is kept and
    applied when M06's `asked` row lands. It is not a 404 because it is not a
    mistake: two modules' queues drain in whatever order they drain in, and a
    404 here would make M13 retry into a hold for a row that was merely early.
    """
    duplicate = (
        payload.evaluation_id is not None
        and session.exec(
            select(CoverageTurnScore)
            .where(CoverageTurnScore.turn_id == turn_id)
            .where(CoverageTurnScore.evaluation_id == payload.evaluation_id)
        ).first()
        is not None
    )
    if not duplicate:
        session.add(
            CoverageTurnScore(
                session_id=session_id,
                candidate_id=candidate_id,
                turn_id=turn_id,
                score=payload.score,
                raw_category=payload.raw_category,
                n_categories=payload.n_categories,
                rubric_version=payload.rubric_version,
                evaluation_id=payload.evaluation_id,
                scored_at=payload.scored_at,
            )
        )
        session.commit()

    applied = apply_turn_score(session, session_id, candidate_id, turn_id)
    known = session.exec(
        select(CoverageLedger)
        .where(CoverageLedger.session_id == session_id)
        .where(CoverageLedger.turn_id == turn_id)
    ).first()
    if known is None:
        response.status_code = status.HTTP_202_ACCEPTED
    return {
        "turn_id": str(turn_id),
        "applied": applied,
        "parked": known is None,
        "duplicate": duplicate,
    }


@router.get("/sessions/{session_id}/coverage/{candidate_id}")
def session_coverage(
    session_id: uuid.UUID,
    candidate_id: uuid.UUID,
    session: Session = Depends(get_db),
):
    """What this session has actually covered, against what it promised.

    Live during the interview and the post-session report afterwards — the same
    view, because they are the same question asked at different times, and
    building two would let them disagree.

    §6.6 calls the ledger *"the mechanism that makes coverage a guarantee
    rather than an intention"*, and this is where the guarantee becomes
    checkable: `promised` comes from the plan, `asked` comes from the ledger,
    and `uncovered` is the difference nobody could see before.
    """
    rows = list(
        session.exec(
            select(CoverageLedger)
            .where(CoverageLedger.session_id == session_id)
            .where(CoverageLedger.candidate_id == candidate_id)
        ).all()
    )
    if not rows:
        return {
            "session_id": str(session_id),
            "candidate_id": str(candidate_id),
            "jd_id": None,
            "asked": {},
            "scores": {},
            "requirements": [],
            "questions_asked": 0,
        }

    jd_id = rows[0].jd_id
    jd = session.get(JobDescription, jd_id)
    asked = covered_counts(rows)
    scores = scores_by_requirement(rows)

    by_id = {r["id"]: r for r in (jd.requirements if jd else []) or []}
    requirements = [
        {
            "requirement_id": rid,
            "text": by_id.get(rid, {}).get("text", rid),
            "necessity": by_id.get(rid, {}).get("necessity"),
            "weight": by_id.get(rid, {}).get("weight"),
            "asked": asked.get(rid, 0),
            "scores": scores.get(rid, []),
        }
        for rid in sorted(set(asked) | set(scores))
    ]
    return {
        "session_id": str(session_id),
        "candidate_id": str(candidate_id),
        "jd_id": str(jd_id),
        "asked": asked,
        "scores": scores,
        "requirements": requirements,
        "questions_asked": sum(asked.values()),
    }
