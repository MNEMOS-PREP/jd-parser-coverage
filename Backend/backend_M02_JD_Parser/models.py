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
    scanned_against: str = Field(default="offline_lexicon")

    created_at: datetime = Field(default_factory=_utcnow)
