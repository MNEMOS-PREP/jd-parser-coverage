import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


class JobDescription(SQLModel, table=True):
    __tablename__ = "job_descriptions"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    company_name: str
    role_title: str
    raw_text: str

    #: SHA-256 of the NORMALISED (company, role, text). FR-2.12, and §3.2.4:
    #: *"The same JD is pasted by 60 students. Normalise and cache by content
    #: hash; the parse is shared, the gap analysis is per-student."*
    #:
    #: Normalised first, because sixty pastes of one posting differ by
    #: whitespace: a copy out of a PDF, a copy out of a portal and a copy out of
    #: an email are the same document with different line breaks, and hashing
    #: them raw makes the cache miss every time and the module look like it
    #: never had one.
    #:
    #: Company and role are IN the hash, not just the text. Two drives can post
    #: identical text — the same boilerplate JD under two companies — and
    #: returning the first one's label to the second student would put the
    #: wrong company name on their coverage screen.
    content_sha256: str = Field(default="", index=True)
    #: The flat list, kept because several callers read it. `requirements`
    #: below is the one carrying §5's contract; this is the same labels without
    #: the provenance, exactly as M01 keeps `parsed_skills` beside
    #: `skill_mentions`.
    required_skills: list[str] = Field(default_factory=list, sa_column=Column(JSON))

    #: `Requirement` as serialised by extract.py: id, text, SPAN, concept ids,
    #: measurability and where the id came from.
    #:
    #: The span is the point. Every other module holds one contract above the
    #: rest — a fact points at the characters it came from — and M02 produced a
    #: list of strings, so M05 could not cite the JD line a question came from
    #: and a student could not check a requirement we claimed their posting
    #: contained.
    requirements: list[dict] = Field(default_factory=list, sa_column=Column(JSON))

    #: `RequirementGroup`s (FR-2.3): the places the posting offered a CHOICE.
    #: Separate from `requirements` because a group is not a requirement — it
    #: is a statement about several of them, and folding it into the list is
    #: exactly the mistake that made "Java or Python" read as two demands.
    requirement_groups: list[dict] = Field(default_factory=list, sa_column=Column(JSON))

    #: `EligibilityCriteria` (FR-2.4): the CGPA cutoff, backlog rule, batch and
    #: bond, each with the line it was read from.
    #:
    #: These used to be RECOGNISED and thrown away — `_ELIGIBILITY` in
    #: extract.py kept them out of the requirement list, correctly, and nothing
    #: kept them anywhere else. FR-2.15's whole sentence is "you have 7.2,
    #: cutoff is 7.5", and a module that never stored the cutoff cannot say it.
    eligibility: dict = Field(default_factory=dict, sa_column=Column(JSON))

    #: skill_label -> concept_id. Only labels we have an id for; see
    #: `concept_source` for WHERE that id came from, which is not decoration:
    #: an id M04 resolved and an id an offline table guessed look identical
    #: here, and downstream has no way to tell them apart without it.
    resolved_concepts: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON))

    #: skill_label -> "m04" | "offline_fallback"
    concept_source: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON))

    #: Found in the JD, tied to no concept. Kept rather than dropped: a
    #: requirement we cannot map is still a requirement the student has to
    #: meet, and silently losing it is how a coverage plan starts lying.
    unresolved_skills: list[str] = Field(default_factory=list, sa_column=Column(JSON))

    #: "m04" when the scan ran against the real ontology, "offline_lexicon"
    #: when it ran against the five hardcoded concepts below. The difference
    #: is most of the requirements, so it is recorded, not assumed.
    #: §5's `RequirementSet.role_archetype` and `archetype_confidence`.
    #:
    #: `None` when nothing matched well enough, or when the top two archetypes
    #: were too close to separate — both of which are answers, and different
    #: from each other. `archetype_confidence` is recorded either way, because
    #: "we looked and were not sure" is not the same as "we did not look".
    #: How long this parse took, end to end, in milliseconds (FR-2.16).
    #:
    #: Stored on the row rather than logged, so p95 is a query over real
    #: postings instead of a benchmark over invented ones. A benchmark measures
    #: the machine it ran on; §11's budget is a claim about what students wait.
    parse_ms: int = Field(default=0)

    #: Per-stage milliseconds, keyed as §11 names them.
    #:
    #: Broken down because the budget is: normalise 0.1 s, extraction 4 s,
    #: archetype 0.2 s, gap 0.3 s, plan 0.2 s. A single total says a parse was
    #: slow; this says which stage to look at, and the answer is almost always
    #: the model call — which is also the one stage that is optional.
    stage_ms: dict = Field(default_factory=dict, sa_column=Column(JSON))

    #: `lexicon`, `lexicon+model`, or `lexicon (model: <reason>)`.
    #:
    #: Which passes actually ran, recorded per posting rather than inferred
    #: from a config file. Two students comparing thin lists need to be able to
    #: see that one parse had a model and the other did not — §6.2 runs both
    #: and merges, and Rule 2 means either can be absent without an error.
    extracted_by: str = Field(default="lexicon")

    #: How many instruction-shaped spans were neutralised in this posting
    #: (EC-2.13). Almost always zero.
    #:
    #: Recorded rather than hidden, and this is the OPPOSITE of M01's rule. M01
    #: §6.7 is explicit that a student is not told the filter fired, because a
    #: resume's author is the person the filter is aimed at and telling them
    #: turns it into an oracle. A job description's author is not the person
    #: reading this screen: the student pasted a document somebody else wrote,
    #: and "we removed something that was trying to give instructions" is a
    #: fact about the posting they are about to prepare against.
    injections_removed: int = Field(default=0)

    #: The script the posting is written in (EC-2.6): `latin`, `devanagari`,
    #: `tamil`, and so on.
    #:
    #: Stored rather than recomputed, because it is part of what this parse IS
    #: and the parse is cached and shared across sixty students. Recomputing it
    #: on read would also mean re-deciding it, and two answers about one
    #: document is the failure this module avoids everywhere else.
    script: str = Field(default="latin")
    #: How much of the document that script accounts for, as a share of its
    #: LETTERS. 1.0 for an empty document — nothing to detect is not a warning.
    script_share: float = Field(default=1.0)

    role_archetype: str | None = Field(default=None)
    archetype_confidence: float = Field(default=0.0)

    #: The roles this posting might be for, when it is for more than one.
    #:
    #: EC-2.14: *"Two roles in one JD ('SDE or QA') — detect, ask the student
    #: which, default to the first."* Populated only when the archetype match
    #: REFUSED because two were too close; empty in the ordinary case, and
    #: empty is the signal that there was nothing to ask about.
    role_candidates: list[dict] = Field(default_factory=list, sa_column=Column(JSON))

    #: How many requirements came from the archetype rather than the posting
    #: (§5, `inferred_count`). Kept as a number as well as being derivable from
    #: `requirements`, because it is what the UI branches on to say "we filled
    #: some of this in" before it renders a single row.
    inferred_count: int = Field(default=0)

    scanned_against: str = Field(default="offline_lexicon")

    created_at: datetime = Field(default_factory=_utcnow)
