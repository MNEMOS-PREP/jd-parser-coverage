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
    resolved_concepts: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON)) # skill_label -> concept_id
    created_at: datetime = Field(default_factory=_utcnow)
