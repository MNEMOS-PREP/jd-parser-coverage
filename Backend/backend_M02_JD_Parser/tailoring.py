"""A resume against a posting, line by line — and what to change (2026-11-17).

`match.py` answers "does the resume mention what the posting asks for" as two
lists. Tailoring needs the same question answered per LINE, because the student
is about to edit lines: which line evidences which requirement, in which words,
how strongly, and which requirements no line evidences at all.

── Evidence has three strengths, and they are not the same ──────────────────────

    direct   the requirement is NAMED in a line of work — a bullet, a role, a
             project, a certification. A recruiter reads it as something done.
    partial  named only in the skills list or the summary (claimed, not shown),
             or written in other words that mean the same thing ("Postgres"
             for "PostgreSQL") — true, and invisible to an exact keyword screen.
    missing  nowhere.

A fourth state exists only in a tailored copy: **unsupported** — the words are
in a line the student edited or added, and nowhere in the resume they uploaded.
It does not count as evidence. It is flagged, so a keyword typed in to please a
posting is never mistaken for experience.

── Suggestions never add a fact ─────────────────────────────────────────────────

Each one is grounded in a line the resume already has, or asks the student
first. "Add Docker to your skills" is offered only when a bullet already says
Docker. A requirement nothing evidences is offered as a QUESTION — "do you have
this?" — never inserted. And every suggestion carries its reason: what changes,
why, which line of the posting it answers, what it improves, and what kind of
change it is. The reasons are assembled from the actual match, not written by
a model, so they can be checked against the two documents.

── The number ───────────────────────────────────────────────────────────────────

`coverage.score` is the posting's requirement weights, counted 1 for direct
evidence, ½ for partial and 0 otherwise. It is a count that opens to its list —
every requirement and the line that evidences it — not a verdict on the student.
`baseline` is the same count over the resume as uploaded, so a student can see
what their edits did, and that an unsupported keyword did not move it.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from backend_M02_JD_Parser.extract import _governing_heading, _line_bounds

Level = Literal["direct", "partial"]
Status = Literal["direct", "partial", "missing", "alternative", "unsupported"]

#: Sections whose lines are things DONE. A requirement named here is shown.
_WORK = frozenset(
    {
        "experience",
        "projects",
        "achievements",
        "publications",
        "certifications",
        "education",
        "extras",
        "unknown",
    }
)
#: Sections that CLAIM rather than show.
_CLAIMED = frozenset({"skills", "summary"})

_SECTION_LABEL = {
    "experience": "Experience",
    "projects": "Projects",
    "skills": "Skills",
    "summary": "Summary",
    "education": "Education",
    "certifications": "Certifications",
    "achievements": "Achievements",
    "publications": "Publications",
    "extras": "Other",
    "unknown": "Other",
    "contact": "Header",
}

_NECESSITY = {"must": 1.0, "should": 0.7, "could": 0.4}
_NECESSITY_WORD = {"must": "must-have", "should": "expected", "could": "nice-to-have"}

#: Kinds of requirement a keyword can stand for, and so a skills line can hold.
_KEYWORD_KINDS = frozenset({"hard_skill", "tool", "domain"})

_WEAK_OPENER = re.compile(
    r"^\s*(?:worked\s+on|helped(?:\s+(?:with|to))?|was\s+involved\s+in|participated\s+in|"
    r"assisted\s+(?:with|in)|responsible\s+for|part\s+of|involved\s+in|tasked\s+with)\b",
    re.IGNORECASE,
)

_STOP = frozenset(
    "a an and are as at be by for from has have in into is it of on or our that the their "
    "this to we will with you your must should can able experience knowledge good strong "
    "work working skills skill understanding using use plus bonus etc".split()
)


# ---------------------------------------------------------------------------
#  Shapes
# ---------------------------------------------------------------------------


class TailorBlock(BaseModel):
    """M01's tailored block, as much of it as this needs."""

    id: str
    kind: str = "text"
    section: str = "unknown"
    group: str | None = None
    text: str = ""
    original: str = ""
    hidden: bool = False
    added: bool = False
    masked: bool = False


class TailorResume(BaseModel):
    """The resume's own skill reading, from M01 — for "said in other words"."""

    id: str | None = None
    resolved_concepts: dict[str, str] = Field(default_factory=dict)
    canonical_skills: dict[str, str] = Field(default_factory=dict)


class TailorIn(BaseModel):
    resume: TailorResume = Field(default_factory=TailorResume)
    tailored_id: str | None = None
    revision: int = 0
    blocks: list[TailorBlock]
    #: How many pages the copy prints to now, from M01's layout. Optional.
    pages: int | None = None


class TailorHit(BaseModel):
    block_id: str
    section: str
    level: Level
    #: named | listed | summary | same_concept
    how: str
    term: str
    start: int
    end: int
    #: In the resume as uploaded (`natural`) or only in an edited/added line.
    natural: bool = True


class TailorRequirement(BaseModel):
    id: str
    text: str
    necessity: str = "should"
    weight: float = 0.0
    kind: str = "hard_skill"
    status: Status
    met_by: str | None = None
    #: Where the posting says it: the exact words, the line, the heading over it.
    quote: str | None = None
    jd_line: str | None = None
    jd_heading: str | None = None
    span: dict[str, Any] | None = None
    inferred: bool = False
    hits: list[TailorHit] = Field(default_factory=list)
    #: The short form a screen shows: the words the resume used, or the skill
    #: inside a long label ("MLflow" from "MLOps tools such as MLflow").
    term: str = ""
    #: The alternatives, when the posting offered a choice ("AWS or GCP").
    choice: list[str] = Field(default_factory=list)


class TailorKeyword(BaseModel):
    term: str
    requirement_id: str
    #: natural: in the resume as uploaded. inserted: only in an edited or added
    #: line. missing: nowhere.
    state: Literal["natural", "inserted", "missing"]
    blocks: list[str] = Field(default_factory=list)


class TailorFlag(BaseModel):
    """An edited or added line that says something the uploaded resume never did."""

    block_id: str
    terms: list[str]
    message: str
    confirmed: list[str] = Field(default_factory=list)


class TailorReason(BaseModel):
    what: str
    why: str
    addresses: str
    improves: str
    type: Literal["keyword", "phrasing", "missing_requirement", "structure"]
    type_label: str


class TailorSuggestion(BaseModel):
    key: str
    kind: str
    category: Literal["skills", "experience", "projects", "keywords", "structure"]
    priority: float
    impact: Literal["high", "medium", "low"]
    title: str
    requirement_id: str | None = None
    requirement: str | None = None
    jd_line: str | None = None
    #: replace · insert · move · hide · confirm · draft
    action: str
    block_id: str | None = None
    before: str | None = None
    after: str | None = None
    insert_after: str | None = None
    move_before: str | None = None
    #: Lines the student could show this in, for a `confirm`.
    candidates: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    needs_confirmation: bool = False
    reason: TailorReason
    state: Literal["open", "rejected", "confirmed"] = "open"


class TailorCoverage(BaseModel):
    score: float | None
    baseline: float | None
    requirements: int
    direct: int
    partial: int
    missing: int
    unsupported: int
    musts: int
    musts_direct: int
    musts_covered: int


class TailorSection(BaseModel):
    section: str
    label: str
    direct: list[str]
    partial: list[str]


class TailorReport(BaseModel):
    jd_id: str
    candidate_id: str
    resume_id: str | None
    tailored_id: str | None
    revision: int
    coverage: TailorCoverage
    sections: list[TailorSection]
    requirements: list[TailorRequirement]
    keywords: list[TailorKeyword]
    flags: list[TailorFlag]
    suggestions: list[TailorSuggestion]


# ---------------------------------------------------------------------------
#  Finding a requirement in a line
# ---------------------------------------------------------------------------

_CHOICE = re.compile(r"\s+/\s+")


#: "MLOps tools such as MLflow": the example is the thing a resume will name.
_EXAMPLE = re.compile(r"\s+(?:such\s+as|e\.g\.?|like|including|i\.e\.?)\s+", re.IGNORECASE)
#: Words a posting wraps round a skill that a resume never repeats:
#: "GCP experience", "Kubernetes knowledge", "Excel skills".
_WRAPPER = re.compile(
    r"\s+(?:experience|knowledge|skills?|familiarity|exposure|proficiency|expertise|"
    r"fundamentals|basics|concepts)$",
    re.IGNORECASE,
)


_GENERIC_TAIL = re.compile(
    r"\s+(?:pipelines?|systems?|frameworks?|tools?|platforms?|services?|applications?|apps?|"
    r"models?|stack|librar(?:y|ies)|databases?|development|programming)$",
    re.IGNORECASE,
)


def core(label: str) -> str:
    """The shortest honest name for a label: "MLflow" for "MLOps tools such as MLflow"."""
    parts = _EXAMPLE.split(label)
    if len(parts) > 1:
        return parts[-1].strip(" .,;")
    return _WRAPPER.sub("", label).strip() or label


def forms(label: str) -> list[str]:
    """Every way a resume could say this label, read off the label itself.

    The label; each side of a spaced-slash choice ("React / Angular"); the
    example in "tools such as MLflow"; and the skill without the posting's
    wrapper word ("GCP experience" -> "GCP").
    """
    out = [label]
    sides = [side.strip() for side in _CHOICE.split(label) if side.strip()]
    if len(sides) > 1:
        out.extend(sides)
    for piece in list(out):
        parts = _EXAMPLE.split(piece)
        if len(parts) > 1:
            out.extend(p.strip(" .,;") for p in re.split(r",|\s+or\s+|\s+and\s+", parts[-1]))
        bare = _WRAPPER.sub("", piece).strip()
        if bare and bare != piece:
            out.append(bare)
        # "RAG pipelines", "Spring Boot applications": the name without the
        # generic noun - only when what is left is a name, never "vector".
        named = _GENERIC_TAIL.sub("", piece).strip()
        if named and named != piece and any(ch.isupper() for ch in named):
            out.append(named)
    seen: list[str] = []
    for form in out:
        if form and form not in seen:
            seen.append(form)
    return seen


def implied_choices(raw: str, requirements: list[dict]) -> list[dict]:
    """ "FastAPI or Flask" on one line of the posting, as a choice (FR-2.3).

    The parser groups the choices it recognises; this adds the plain ones it
    missed — two requirements on the same line with only "or" or "/" between
    them — read from the posting's own words, never assumed.
    """
    placed = []
    for requirement in requirements:
        span = requirement.get("span") or {}
        try:
            placed.append((int(span["start"]), int(span["end"]), str(requirement["id"])))
        except (KeyError, TypeError, ValueError):
            continue
    placed.sort()
    groups: list[dict] = []
    for (_s1, e1, a), (s2, _e2, b) in zip(placed, placed[1:], strict=False):
        between = raw[e1:s2] if 0 <= e1 <= s2 <= len(raw) else ""
        if "\n" not in between and re.fullmatch(r"\s*(?:,?\s*or|/)\s*", between, re.IGNORECASE):
            groups.append({"id": f"I-{a}-{b}", "requirement_ids": [a, b]})
    return groups


def pattern(form: str) -> re.Pattern[str] | None:
    """A whole-word pattern for `form`, as `match._in_text` decides what counts.

    Two letters are too few to find safely ("go" is prose) unless written as an
    acronym or with a sign ("C++", "C#"), and those are matched case-sensitively.
    A trailing plural is optional on both sides: "LLMs" finds "LLM".
    """
    form = " ".join(form.split())
    if not form:
        return None
    letters = re.sub(r"[^A-Za-z0-9]", "", form)
    signed = bool(re.search(r"[+#]", form))
    flags = re.IGNORECASE
    if len(letters) < 3:
        if not (signed or (form.isalpha() and form.isupper())):
            return None
        flags = 0
    base = form
    if len(base) > 3 and base.endswith("s") and not base.endswith("ss") and base[-2].isalpha():
        base = base[:-1]
    words = [w for w in re.split(r"[\s\-]+", base) if w]
    needle = r"[\s\-]+".join(re.escape(w) for w in words)
    plural = "s?" if base[-1:].isalpha() else ""
    return re.compile(rf"(?<![A-Za-z0-9]){needle}{plural}(?![A-Za-z0-9+#])", flags)


def find(form: str, text: str) -> list[tuple[int, int]]:
    compiled = pattern(form)
    if compiled is None or not text:
        return []
    return [(m.start(), m.end()) for m in compiled.finditer(text)]


def _norm(label: str) -> str:
    return re.sub(r"[^a-z0-9+#]", "", label.lower())


# ---------------------------------------------------------------------------
#  Small text helpers for the reasons
# ---------------------------------------------------------------------------


def _clip(text: str, limit: int = 90) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip(" ,;") + "…"


def _around(text: str, start: int, end: int, width: int = 48) -> str:
    """The words around a match, quoted: "…replaced an overfitting baseline…"."""
    left = max(0, start - width)
    right = min(len(text), end + width)
    while left > 0 and text[left - 1] != " ":
        left -= 1
    while right < len(text) and text[right] != " ":
        right += 1
    piece = text[left:right].strip()
    return f"{'…' if left > 0 else ''}{piece}{'…' if right < len(text) else ''}"


def _key(*parts: object) -> str:
    raw = "|".join(" ".join(str(p).lower().split()) for p in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9+#.]+", text.lower()) if w not in _STOP and len(w) > 2}


# ---------------------------------------------------------------------------
#  The analysis
# ---------------------------------------------------------------------------


def _jd_place(raw: str, span: dict | None) -> tuple[str | None, str | None, str | None]:
    """(quote, the line it is on, the heading above it) — or Nones."""
    if not span or not raw:
        return None, None, None
    try:
        start, end = int(span["start"]), int(span["end"])
    except (KeyError, TypeError, ValueError):
        return None, None, None
    if not (0 <= start < end <= len(raw)):
        return None, None, None
    line_start, line_end = _line_bounds(raw, start)
    line = " ".join(raw[line_start:line_end].split())
    heading = _governing_heading(raw, line_start).rstrip(":").strip() or None
    return raw[start:end], _clip(line, 300), heading


def _visible(blocks: list[TailorBlock]) -> list[TailorBlock]:
    return [
        b
        for b in blocks
        if not b.hidden and b.kind not in {"name", "contact", "heading"} and b.text.strip()
    ]


def _hits_for(
    requirement: dict,
    blocks: list[TailorBlock],
    *,
    alias_labels: list[str],
    use_original: bool,
    original_text: str,
) -> list[TailorHit]:
    hits: list[TailorHit] = []
    labels = forms(requirement["text"])
    for block in blocks:
        text = block.original if use_original else block.text
        if not text:
            continue
        found = False
        for form in labels:
            for start, end in find(form, text):
                found = True
                in_original = use_original or bool(find(form, original_text))
                hits.append(
                    TailorHit(
                        block_id=block.id,
                        section=block.section,
                        level="direct" if block.section in _WORK else "partial",
                        how="named"
                        if block.section in _WORK
                        else ("summary" if block.section == "summary" else "listed"),
                        term=text[start:end],
                        start=start,
                        end=end,
                        natural=in_original,
                    )
                )
                break
            if found:
                break
        if found:
            continue
        for alias in alias_labels:
            spans = find(alias, text)
            if spans:
                start, end = spans[0]
                hits.append(
                    TailorHit(
                        block_id=block.id,
                        section=block.section,
                        level="partial",
                        how="same_concept",
                        term=text[start:end],
                        start=start,
                        end=end,
                        natural=use_original or bool(find(alias, original_text)),
                    )
                )
                break
    return hits


def _aliases(requirement: dict, resume: TailorResume) -> list[str]:
    """The resume's own words for this requirement, when it says it differently.

    From what the resume's reading already resolved — M04's concept ids, and
    M01's alias table — never from a list kept here.
    """
    wanted = {str(c) for c in requirement.get("concept_ids") or []}
    target = {_norm(form) for form in forms(requirement["text"])}
    out: list[str] = []
    for label, concept in (resume.resolved_concepts or {}).items():
        if str(concept) in wanted and _norm(label) not in target:
            out.append(label)
    for surface, canonical in (resume.canonical_skills or {}).items():
        if _norm(canonical) in target and _norm(surface) not in target:
            out.append(surface)
    return sorted(set(out), key=len, reverse=True)


def _status(hits: list[TailorHit]) -> Status:
    if any(h.level == "direct" and h.how == "named" for h in hits):
        return "direct"
    if hits:
        return "partial"
    return "missing"


def _score(rows: list[TailorRequirement], status: dict[str, Status]) -> float | None:
    counted = [r for r in rows if status[r.id] != "alternative" and not r.inferred]
    if not counted:
        return None
    weights = [max(r.weight, 0.0) for r in counted]
    if sum(weights) <= 0:
        weights = [1.0] * len(counted)
    value = {"direct": 1.0, "partial": 0.5}
    total = sum(w * value.get(status[r.id], 0.0) for r, w in zip(counted, weights, strict=True))
    return round(total / sum(weights), 3)


def _salient_new(text: str, original_corpus: str) -> list[str]:
    """Names, tools and numbers in `text` that the uploaded resume never says."""
    corpus = original_corpus.lower()
    out: list[str] = []
    for index, match in enumerate(re.finditer(r"[A-Za-z0-9][A-Za-z0-9+#.\-/%]*", text)):
        word = match.group(0).rstrip(".-/")
        if not word or word.lower() in _STOP:
            continue
        has_digit = any(ch.isdigit() for ch in word)
        capital = word[:1].isupper() and index > 0
        inner = any(ch.isupper() for ch in word[1:])
        if not (has_digit or capital or inner):
            continue
        if re.search(rf"(?<![A-Za-z0-9]){re.escape(word.lower())}", corpus):
            continue
        if word not in out:
            out.append(word)
    return out


def analyse(
    *,
    jd_id: str,
    candidate_id: str,
    raw_jd: str,
    requirements: list[dict],
    groups: list[dict],
    payload: TailorIn,
    decisions: dict[str, dict] | None = None,
) -> TailorReport:
    decisions = decisions or {}
    blocks = payload.blocks
    visible = _visible(blocks)
    originals = [
        b for b in blocks if not b.added and b.original and b.kind not in {"name", "contact"}
    ]
    original_corpus = "\n".join(b.original for b in originals)
    by_id = {b.id: b for b in blocks}
    confirmed_terms = {
        str(d.get("term", "")).lower()
        for d in decisions.values()
        if d.get("state") == "confirmed" and d.get("term")
    }

    # Per requirement: evidence now, and evidence in the resume as uploaded.
    rows: list[TailorRequirement] = []
    status_now: dict[str, Status] = {}
    status_then: dict[str, Status] = {}
    for requirement in requirements:
        aliases = _aliases(requirement, payload.resume)
        hits = _hits_for(
            requirement,
            visible,
            alias_labels=aliases,
            use_original=False,
            original_text=original_corpus,
        )
        # Words that are only in an edited or added line, and nowhere in the
        # uploaded resume, are not evidence unless the student said they are true.
        supported = [
            h
            for h in hits
            if h.natural
            or h.term.lower() in confirmed_terms
            or requirement["text"].lower() in confirmed_terms
        ]
        then = _hits_for(
            requirement,
            originals,
            alias_labels=aliases,
            use_original=True,
            original_text=original_corpus,
        )
        quote, line, heading = _jd_place(raw_jd, requirement.get("span"))
        status: Status = _status(supported)
        if status == "missing" and hits:
            status = "unsupported"
        rows.append(
            TailorRequirement(
                id=str(requirement["id"]),
                text=requirement["text"],
                necessity=requirement.get("necessity") or "should",
                weight=float(requirement.get("weight") or 0.0),
                kind=requirement.get("kind") or "hard_skill",
                status=status,
                quote=quote,
                jd_line=line,
                jd_heading=heading,
                span=requirement.get("span"),
                # Not quoted from the posting: the role's archetype, or a model's
                # reading with no words to point at.
                inferred=requirement.get("source") == "archetype" or not requirement.get("span"),
                hits=hits,
                term=next((h.term for h in hits if h.how != "same_concept"), None)
                or core(requirement["text"]),
            )
        )
        status_now[str(requirement["id"])] = status
        status_then[str(requirement["id"])] = _status(then)

    labels_by_id = {r.id: r for r in rows}
    # Unquoted requirements stay listed but do not score or prompt changes —
    # unless nothing is quoted (a role picked without a posting).
    if all(r.inferred for r in rows):
        for r in rows:
            r.inferred = False

    # A choice the posting offered is met by any one of its answers (FR-2.3).
    for group in [*(groups or []), *implied_choices(raw_jd, requirements)]:
        members = [labels_by_id[i] for i in group.get("requirement_ids", []) if i in labels_by_id]
        for member in members:
            member.choice = member.choice or [m.term for m in members]
        for statuses in (status_now, status_then):
            best = next((m for m in members if statuses[m.id] == "direct"), None) or next(
                (m for m in members if statuses[m.id] == "partial"), None
            )
            if best is None:
                continue
            for member in members:
                if member.id != best.id and statuses[member.id] in {"missing", "unsupported"}:
                    statuses[member.id] = "alternative"
                    if statuses is status_now:
                        member.status = "alternative"
                        member.met_by = best.text

    coverage = _coverage(rows, status_now, status_then)
    sections = _sections(rows, blocks)
    keywords = _keywords(rows)
    flags = _flags(blocks, original_corpus, confirmed_terms)
    suggestions = _suggest(
        rows=rows,
        blocks=blocks,
        visible=visible,
        by_id=by_id,
        status=status_now,
        payload=payload,
        decisions=decisions,
        coverage=coverage,
    )
    return TailorReport(
        jd_id=jd_id,
        candidate_id=candidate_id,
        resume_id=payload.resume.id,
        tailored_id=payload.tailored_id,
        revision=payload.revision,
        coverage=coverage,
        sections=sections,
        requirements=rows,
        keywords=keywords,
        flags=flags,
        suggestions=suggestions,
    )


def _coverage(
    rows: list[TailorRequirement], now: dict[str, Status], then: dict[str, Status]
) -> TailorCoverage:
    counted = [r for r in rows if now[r.id] != "alternative" and not r.inferred]
    musts = [r for r in counted if r.necessity == "must"]
    return TailorCoverage(
        score=_score(rows, now),
        baseline=_score(rows, then),
        requirements=len(counted),
        direct=sum(1 for r in counted if now[r.id] == "direct"),
        partial=sum(1 for r in counted if now[r.id] == "partial"),
        missing=sum(1 for r in counted if now[r.id] == "missing"),
        unsupported=sum(1 for r in counted if now[r.id] == "unsupported"),
        musts=len(musts),
        musts_direct=sum(1 for r in musts if now[r.id] == "direct"),
        musts_covered=sum(1 for r in musts if now[r.id] in {"direct", "partial"}),
    )


def _sections(rows: list[TailorRequirement], blocks: list[TailorBlock]) -> list[TailorSection]:
    order: list[str] = []
    for block in blocks:
        if block.section not in order and block.section != "contact":
            order.append(block.section)
    out: list[TailorSection] = []
    for section in order:
        direct = [
            r.id
            for r in rows
            if r.status != "alternative"
            and not r.inferred
            and any(h.section == section and h.level == "direct" for h in r.hits)
        ]
        partial = [
            r.id
            for r in rows
            if r.status != "alternative"
            and not r.inferred
            and r.id not in direct
            and any(h.section == section for h in r.hits)
        ]
        out.append(
            TailorSection(
                section=section,
                label=_SECTION_LABEL.get(section, section.title()),
                direct=direct,
                partial=partial,
            )
        )
    return out


def _keywords(rows: list[TailorRequirement]) -> list[TailorKeyword]:
    out: list[TailorKeyword] = []
    for row in rows:
        if row.kind not in _KEYWORD_KINDS or row.status == "alternative" or row.inferred:
            continue
        named = [h for h in row.hits if h.how != "same_concept"]
        if not named:
            state = "missing"
        elif any(h.natural for h in named):
            state = "natural"
        else:
            state = "inserted"
        out.append(
            TailorKeyword(
                term=row.text,
                requirement_id=row.id,
                state=state,
                blocks=sorted({h.block_id for h in named}),
            )
        )
    return out


def _flags(blocks: list[TailorBlock], corpus: str, confirmed: set[str]) -> list[TailorFlag]:
    out: list[TailorFlag] = []
    for block in blocks:
        if block.hidden or block.masked or block.kind in {"name", "contact", "heading"}:
            continue
        if not block.added and block.text == block.original:
            continue
        terms = _salient_new(block.text, corpus)
        if not terms:
            continue
        unconfirmed = [t for t in terms if t.lower() not in confirmed]
        if not unconfirmed:
            out.append(
                TailorFlag(
                    block_id=block.id,
                    terms=[],
                    confirmed=terms,
                    message=f"You added {', '.join(terms)} and said it is true. Be ready to explain it.",
                )
            )
            continue
        listed = ", ".join(f"“{t}”" for t in unconfirmed[:4])
        out.append(
            TailorFlag(
                block_id=block.id,
                terms=unconfirmed,
                confirmed=[t for t in terms if t not in unconfirmed],
                message=(
                    f"{listed} {'is' if len(unconfirmed) == 1 else 'are'} not anywhere in the resume "
                    "you uploaded. Keep it only if it is true and you can defend it in an interview — "
                    "it does not count towards this job's match until you confirm it."
                ),
            )
        )
    return out


# ---------------------------------------------------------------------------
#  Suggestions
# ---------------------------------------------------------------------------


def _impact(priority: float) -> Literal["high", "medium", "low"]:
    if priority >= 0.6:
        return "high"
    if priority >= 0.3:
        return "medium"
    return "low"


def _addresses(row: TailorRequirement) -> str:
    where = f" under “{row.jd_heading}”" if row.jd_heading else ""
    necessity = _NECESSITY_WORD.get(row.necessity, row.necessity)
    if row.inferred or not row.jd_line:
        return f"“{row.text}” ({necessity}) — inferred from the role, not quoted from the posting."
    return f"“{row.text}”, a {necessity} requirement{where}: “{row.jd_line}”"


def _entry_title(block: TailorBlock, by_id: dict[str, TailorBlock]) -> str:
    entry = by_id.get(block.group or "")
    if entry is not None and entry.id != block.id:
        return _clip(entry.text.split("|")[0], 60)
    return _SECTION_LABEL.get(block.section, "your resume")


def _suggest(
    *,
    rows: list[TailorRequirement],
    blocks: list[TailorBlock],
    visible: list[TailorBlock],
    by_id: dict[str, TailorBlock],
    status: dict[str, Status],
    payload: TailorIn,
    decisions: dict[str, dict],
    coverage: TailorCoverage,
) -> list[TailorSuggestion]:
    max_weight = max((r.weight for r in rows), default=0.0) or 1.0
    out: list[TailorSuggestion] = []
    buried: dict[str, list[tuple[TailorRequirement, TailorHit]]] = {}
    asked_choices: set[tuple[str, ...]] = set()

    def base(row: TailorRequirement, factor: float) -> float:
        weight = (row.weight / max_weight) if row.weight > 0 else 0.5
        return round(min(1.0, weight * _NECESSITY.get(row.necessity, 0.7) * factor + 0.05), 3)

    skills_lines = [
        b
        for b in visible
        if b.section == "skills" and b.kind in {"text", "bullet"} and not b.masked
    ]
    work_bullets = [
        b for b in visible if b.section in _WORK and b.kind == "bullet" and not b.masked
    ]
    musts_line = (
        f"{coverage.musts_direct} of {coverage.musts} must-haves are shown in your work"
        if coverage.musts
        else None
    )

    for row in rows:
        if row.status == "alternative" or row.kind == "qualification" or row.inferred:
            continue
        named = [h for h in row.hits if h.how != "same_concept"]
        direct = [h for h in named if h.level == "direct" and h.natural]
        listed = [h for h in named if h.how == "listed"]
        alias = [h for h in row.hits if h.how == "same_concept"]

        # A. Shown in work, absent from the skills list → name it there.
        if (
            row.kind in _KEYWORD_KINDS
            and direct
            and not listed
            and skills_lines
            and not any(h.section == "skills" for h in row.hits)
        ):
            source = by_id[direct[0].block_id]
            target = _best_skills_line(skills_lines, source.text)
            after = target.text.rstrip(" ,.;") + f", {row.term}"
            out.append(
                TailorSuggestion(
                    key=_key("add_skill", row.text, target.id),
                    kind="add_skill",
                    category="skills",
                    priority=base(row, 0.6),
                    impact=_impact(base(row, 0.6)),
                    title=f"Add {row.term} to your skills",
                    requirement_id=row.id,
                    requirement=row.text,
                    jd_line=row.jd_line,
                    action="replace",
                    block_id=target.id,
                    before=target.text,
                    after=after,
                    evidence=[source.id],
                    reason=TailorReason(
                        what=f"Append “{row.term}” to “{_clip(target.text, 70)}”.",
                        why=(
                            f"Your {_entry_title(source, by_id)} line already says "
                            f"“{_around(source.text, direct[0].start, direct[0].end)}”, but your "
                            "skills list — the part a recruiter or an ATS keyword filter reads "
                            f"first — does not name {row.term}."
                        ),
                        addresses=_addresses(row),
                        improves=(
                            f"{row.term} is already evidenced; this makes the keyword match exact "
                            "where screening looks first. Nothing new is claimed."
                        ),
                        type="keyword",
                        type_label="TailorKeyword optimisation",
                    ),
                )
            )

        # B. Said in other words → use the posting's word.
        if alias and not named:
            hit = next((h for h in alias if h.section in _WORK), alias[0])
            block = by_id[hit.block_id]
            after = block.text[: hit.start] + row.text + block.text[hit.end :]
            out.append(
                TailorSuggestion(
                    key=_key("use_jd_term", row.text, block.id, hit.term),
                    kind="use_jd_term",
                    category="keywords",
                    priority=base(row, 0.85),
                    impact=_impact(base(row, 0.85)),
                    title=f"Write “{row.text}” the way the posting does",
                    requirement_id=row.id,
                    requirement=row.text,
                    jd_line=row.jd_line,
                    action="replace",
                    block_id=block.id,
                    before=block.text,
                    after=after,
                    evidence=[block.id],
                    reason=TailorReason(
                        what=f"Replace “{hit.term}” with “{row.text}” in this line.",
                        why=(
                            f"The posting writes “{row.text}”; your resume writes “{hit.term}”. "
                            "They are the same thing (your resume's own reading maps both to one "
                            "skill), but a keyword screen matches the posting's spelling, not the "
                            "meaning."
                        ),
                        addresses=_addresses(row),
                        improves=(
                            f"Moves {row.text} from partial (same thing, other words) to an exact "
                            "match, without changing what the line claims."
                        ),
                        type="keyword",
                        type_label="TailorKeyword optimisation",
                    ),
                )
            )

        # C. Listed but never shown in work → ask where it was used.
        if row.kind in _KEYWORD_KINDS and listed and not direct and work_bullets:
            candidates = _related_bullets(work_bullets, row, limit=3)
            out.append(
                TailorSuggestion(
                    key=_key("surface", row.text),
                    kind="surface",
                    category="experience"
                    if any(by_id[c].section == "experience" for c in candidates[:1])
                    else "projects",
                    priority=base(row, 0.75),
                    impact=_impact(base(row, 0.75)),
                    title=f"Show where you used {row.term}",
                    requirement_id=row.id,
                    requirement=row.text,
                    jd_line=row.jd_line,
                    action="confirm",
                    candidates=candidates,
                    evidence=[listed[0].block_id],
                    needs_confirmation=True,
                    reason=TailorReason(
                        what=(
                            f"Name {row.term} in the project or role where you used it — only if "
                            "you did. Pick the line and we'll draft it from your own words."
                        ),
                        why=(
                            f"{row.term} is in your skills list, but no bullet says what you did "
                            "with it. A listed skill is a claim; a bullet is evidence, and it is "
                            "the first thing an interviewer will ask about."
                        ),
                        addresses=_addresses(row),
                        improves=(
                            f"Moves {row.term} from listed to shown in work."
                            + (f" {musts_line}." if row.necessity == "must" and musts_line else "")
                        ),
                        type="missing_requirement",
                        type_label="Missing evidence",
                    ),
                )
            )

        # D. Shown, but buried or weakly worded: collected per line, below.
        if direct and row.necessity in {"must", "should"}:
            hit = direct[0]
            if by_id[hit.block_id].kind == "bullet":
                buried.setdefault(hit.block_id, []).append((row, hit))

        # E. Nowhere → ask; never insert.
        # A choice the posting offered ("AWS or GCP") with neither on the resume
        # is ONE gap, asked about once.
        if row.status in {"missing", "unsupported"} and not (
            row.choice and tuple(row.choice) in asked_choices
        ):
            if row.choice:
                asked_choices.add(tuple(row.choice))
            soft = row.kind == "soft_skill"
            candidates = _related_bullets(work_bullets, row, limit=3)
            named_as = " or ".join(row.choice) if row.choice else row.term
            out.append(
                TailorSuggestion(
                    key=_key("missing", row.text),
                    kind="missing",
                    category="keywords",
                    priority=base(row, 1.0),
                    impact=_impact(base(row, 1.0)),
                    title=f"{named_as}: not on your resume",
                    requirement_id=row.id,
                    requirement=row.text,
                    jd_line=row.jd_line,
                    action="confirm",
                    candidates=candidates,
                    needs_confirmation=True,
                    insert_after=(skills_lines[-1].id if skills_lines and not soft else None),
                    reason=TailorReason(
                        what=(
                            f"Only if it is true: show {row.text} in a line about something you did"
                            + ("" if soft else ", or add it to your skills")
                            + ". If it isn't, leave it out and prepare to talk about the gap."
                        ),
                        why=(
                            f"The posting asks for {row.text} and no line of your resume mentions "
                            "it. We won't add it for you — a resume you didn't write is one you "
                            "can't defend."
                        ),
                        addresses=_addresses(row),
                        improves=(
                            f"Turns a {_NECESSITY_WORD.get(row.necessity, row.necessity)} gap into "
                            "evidence — if you have it."
                            + (f" {musts_line}." if row.necessity == "must" and musts_line else "")
                        ),
                        type="missing_requirement",
                        type_label="Missing requirement",
                    ),
                )
            )

    out.extend(_reword(buried, by_id, base))
    out.extend(_reorder(rows, blocks, by_id, status))
    out.extend(_trim(rows, visible, by_id, payload.pages))

    for suggestion in out:
        decided = decisions.get(suggestion.key) or {}
        if decided.get("state") in {"rejected", "confirmed"}:
            suggestion.state = decided["state"]  # type: ignore[assignment]
    out.sort(key=lambda s: (s.state != "open", -s.priority, s.title))
    return out


def _reword(
    buried: dict[str, list[tuple[TailorRequirement, TailorHit]]],
    by_id: dict[str, TailorBlock],
    base: Any,
) -> list[TailorSuggestion]:
    """One suggestion per line whose evidence a skim would miss.

    Per LINE, not per requirement: a bullet ending "...using React, FastAPI,
    PostgreSQL and Docker" is one rewrite that brings all four forward.
    """
    out: list[TailorSuggestion] = []
    for block_id, found in buried.items():
        block = by_id[block_id]
        weak = _WEAK_OPENER.match(block.text)
        total = len(block.text.split())
        late = [
            (row, hit)
            for row, hit in found
            if total >= 18 and len(block.text[: hit.start].split()) / max(total, 1) > 0.6
        ]
        if not weak and not late:
            continue
        chosen = sorted(late or found, key=lambda pair: -pair[0].weight)
        rows = [row for row, _ in chosen]
        terms = ", ".join(row.term for row in rows[:4])
        lead = rows[0]
        if weak:
            why = (
                f"It opens with “{weak.group(0).strip()}”, which says you were near the "
                "work, not what you did — and the posting’s words come after it."
            )
        else:
            first = min(len(block.text[: hit.start].split()) for _, hit in chosen)
            why = (
                f"{terms} first appear{'s' if len(rows) == 1 else ''} at word {first + 1} of "
                f"{total}. A recruiter skimming reads the first half of a line."
            )
        priority = max(base(row, 0.6) for row in rows)
        out.append(
            TailorSuggestion(
                key=_key("reword", block.id, block.text),
                kind="reword",
                category="experience" if block.section == "experience" else "projects",
                priority=priority,
                impact=_impact(priority),
                title=f"Lead with {terms}"
                if len(terms) < 48
                else "Lead with what this posting asks for",
                requirement_id=lead.id,
                requirement=", ".join(row.text for row in rows[:4]),
                jd_line=lead.jd_line,
                action="draft",
                block_id=block.id,
                before=block.text,
                evidence=[block.id],
                reason=TailorReason(
                    what=(
                        f"Reword this line so {terms} and what you did with "
                        f"{'it' if len(rows) == 1 else 'them'} come first. Same facts, same numbers."
                    ),
                    why=why,
                    addresses=_addresses(lead)
                    + (f" — and {len(rows) - 1} more in this line." if len(rows) > 1 else ""),
                    improves=(
                        "Makes evidence you already have visible in the first few words. The "
                        "requirements are met either way; this makes the line read that way."
                    ),
                    type="phrasing",
                    type_label="Stronger phrasing",
                ),
            )
        )
    return out


def _best_skills_line(lines: list[TailorBlock], evidence_text: str) -> TailorBlock:
    """The skills line whose items keep company with the evidence.

    A bullet naming Docker beside React and FastAPI belongs with the line that
    already lists React and FastAPI — read from the resume, not from a table
    of which tool is which.
    """
    evidence = evidence_text.lower()

    def overlap(line: TailorBlock) -> int:
        items = re.split(r"[,:;|]", line.text)
        return sum(1 for item in items[1:] if item.strip() and item.strip().lower() in evidence)

    return max(lines, key=lambda line: (overlap(line), -lines.index(line)))


def _related_bullets(bullets: list[TailorBlock], row: TailorRequirement, limit: int) -> list[str]:
    """Lines most likely to be where a requirement was used, by shared words.

    The words of the posting's own line around the requirement, against each
    bullet. A guess offered as a choice — the student picks, or picks none.
    """
    context = _words(f"{row.text} {row.jd_line or ''}")
    scored = sorted(
        bullets,
        key=lambda b: (len(context & _words(b.text)), -bullets.index(b)),
        reverse=True,
    )
    return [b.id for b in scored[:limit]]


def _reorder(
    rows: list[TailorRequirement],
    blocks: list[TailorBlock],
    by_id: dict[str, TailorBlock],
    status: dict[str, Status],
) -> list[TailorSuggestion]:
    """The most relevant project first. Experience stays in date order."""
    entries = [b for b in blocks if b.kind == "entry" and b.section == "projects" and not b.hidden]
    if len(entries) < 2:
        return []
    relevance: dict[str, tuple[float, list[str]]] = {}
    for entry in entries:
        members = {b.id for b in blocks if b.group == entry.id}
        names = [
            r.text
            for r in rows
            if status.get(r.id) == "direct"
            and any(h.block_id in members and h.level == "direct" for h in r.hits)
        ]
        weight = sum(max(r.weight, 0.05) for r in rows if r.text in names)
        relevance[entry.id] = (weight, names)
    first = entries[0]
    best = max(entries, key=lambda e: relevance[e.id][0])
    best_weight, best_names = relevance[best.id]
    first_weight, first_names = relevance[first.id]
    if best.id == first.id or best_weight <= first_weight * 1.25 or len(best_names) < 2:
        return []
    priority = round(min(0.75, 0.3 + 0.08 * (len(best_names) - len(first_names))), 3)
    return [
        TailorSuggestion(
            key=_key("reorder", best.id, first.id),
            kind="reorder",
            category="projects",
            priority=priority,
            impact=_impact(priority),
            title=f"Put {_clip(best.text.split('|')[0], 40)} first",
            action="move",
            block_id=best.id,
            move_before=first.id,
            evidence=[best.id],
            reason=TailorReason(
                what=(
                    f"Move “{_clip(best.text.split('|')[0], 60)}” (with its bullets) above "
                    f"“{_clip(first.text.split('|')[0], 60)}”."
                ),
                why=(
                    f"It shows {len(best_names)} of this posting's requirements "
                    f"({', '.join(best_names[:4])}{'…' if len(best_names) > 4 else ''}); the project "
                    f"currently first shows {len(first_names) or 'none'}"
                    f"{' (' + ', '.join(first_names[:3]) + ')' if first_names else ''}. "
                    "A recruiter skimming reads the first project, and sometimes only that."
                ),
                addresses=f"{len(best_names)} requirements of this posting, at once.",
                improves="Order only — nothing is reworded, and your experience stays in date order.",
                type="structure",
                type_label="Structural improvement",
            ),
        )
    ]


def _trim(
    rows: list[TailorRequirement],
    visible: list[TailorBlock],
    by_id: dict[str, TailorBlock],
    pages: int | None,
) -> list[TailorSuggestion]:
    """When the copy runs past a page: the bullets this job does not need."""
    if not pages or pages <= 1:
        return []
    used = {h.block_id for r in rows for h in r.hits}
    spare = [
        b
        for b in visible
        if b.kind == "bullet"
        and b.section in {"projects", "achievements", "extras"}
        and b.id not in used
    ]
    out: list[TailorSuggestion] = []
    for block in spare[-3:]:
        out.append(
            TailorSuggestion(
                key=_key("trim", block.id, block.text),
                kind="trim",
                category="structure",
                priority=0.35,
                impact="medium",
                title="Hide a line this job doesn't need",
                action="hide",
                block_id=block.id,
                before=block.text,
                evidence=[block.id],
                reason=TailorReason(
                    what="Hide this line from this version (it stays in your resume, and can be shown again).",
                    why=(
                        f"This version prints on {pages} pages, and this line in "
                        f"{_entry_title(block, by_id)} evidences none of this posting's requirements."
                    ),
                    addresses="Length: most campus screens expect one page.",
                    improves="Shorter, with every remaining line about this job.",
                    type="structure",
                    type_label="Structural improvement",
                ),
            )
        )
    return out


def summary(report: TailorReport) -> dict[str, Any]:
    """What a saved job keeps of its last analysis, for the list of saved jobs."""
    return {
        "score": report.coverage.score,
        "baseline": report.coverage.baseline,
        "musts": report.coverage.musts,
        "musts_direct": report.coverage.musts_direct,
        "open": sum(1 for s in report.suggestions if s.state == "open"),
        "flags": len([f for f in report.flags if f.terms]),
        "revision": report.revision,
        "resume_id": report.resume_id,
    }
