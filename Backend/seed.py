"""Seed two JDs so the API has something to answer with on a fresh clone.

The concept ids below are seeded, not resolved — nobody asked M04 — so they
carry `offline_fallback` provenance like any other unconfirmed id. Seed data
that claims a stronger source than it has is how a demo starts lying.

Safe to run again (2026-10-03): each JD's id is derived from its company and
role, an existing row is left alone, and the tables are created first so this
works before the module has ever started. Each run used to add both again.
`Platform_Shell/start.bat seed` runs it with every other module's seed.
"""

import uuid

from backend_M02_JD_Parser.app import engine
from backend_M02_JD_Parser.models import JobDescription
from sqlmodel import Session, SQLModel, select

#: Seeded JDs are named by what they are, so a second run finds the first.
_SEED = uuid.UUID("5eed0000-0000-4000-8000-000000000002")


def seed():
    jds = [
        JobDescription(
            company_name="Google",
            role_title="Software Engineer, DSA",
            raw_text=(
                "We are looking for an engineer proficient in algorithms like Dynamic "
                "Programming and recursion, with solid understanding of Hashing and "
                "system design."
            ),
            required_skills=["Dynamic Programming", "Hashing", "Recursion"],
            resolved_concepts={
                "Dynamic Programming": "concept:dynamic_programming",
                "Recursion": "concept:recursion",
                "Hashing": "concept:hashing",
            },
            concept_source={
                "Dynamic Programming": "offline_fallback",
                "Recursion": "offline_fallback",
                "Hashing": "offline_fallback",
            },
            # In the JD, mapped to nothing: M04 has no system-design concept
            # yet, and EC-2.8 says say so rather than quietly drop it.
            unresolved_skills=["System Design"],
            scanned_against="offline_lexicon",
        ),
        JobDescription(
            company_name="Stripe",
            role_title="Backend Engineer",
            raw_text="Required skills: SQL databases, transactions, ACID properties, and API design.",
            required_skills=["SQL", "Transactions"],
            resolved_concepts={
                "SQL": "concept:sql_basics",
                "Transactions": "concept:transactions_acid",
            },
            concept_source={
                "SQL": "offline_fallback",
                "Transactions": "offline_fallback",
            },
            unresolved_skills=["API Design"],
            scanned_against="offline_lexicon",
        ),
    ]

    for j in jds:
        j.id = uuid.uuid5(_SEED, f"{j.company_name}|{j.role_title}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        # By id, and by name: a database seeded by the old script holds the
        # same JDs under random ids.
        added = [
            j
            for j in jds
            if session.get(JobDescription, j.id) is None
            and session.exec(
                select(JobDescription).where(
                    JobDescription.company_name == j.company_name,
                    JobDescription.role_title == j.role_title,
                )
            ).first()
            is None
        ]
        session.add_all(added)
        session.commit()
    print(f"M02 seed: {len(added)} added, {len(jds) - len(added)} already there.")


if __name__ == "__main__":
    seed()
