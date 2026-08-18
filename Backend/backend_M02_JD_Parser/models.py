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
    required_skills: list[str] = Field(default_factory=list, sa_column=Column(JSON))

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
