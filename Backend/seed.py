"""Seed two JDs so the API has something to answer with on a fresh clone.

The concept ids below are seeded, not resolved — nobody asked M04 — so they
carry `offline_fallback` provenance like any other unconfirmed id. Seed data
that claims a stronger source than it has is how a demo starts lying.
"""

from backend_M02_JD_Parser.app import engine
from backend_M02_JD_Parser.models import JobDescription
from sqlmodel import Session


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

    with Session(engine) as session:
        for j in jds:
            session.add(j)
        session.commit()
    print("M02 Seed completed successfully.")


if __name__ == "__main__":
    seed()
