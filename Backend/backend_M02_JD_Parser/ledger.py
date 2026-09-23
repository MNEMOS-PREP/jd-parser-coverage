"""The coverage ledger — what makes coverage a guarantee (FR-2.11, §6.6).

§6.6, and it is the strongest claim in the specification:

    *"When M5 selects a question, it writes `coverage_ledger(session,
    requirement_id, turn_id, state='asked')`. When M13 scores that turn, the
    row moves to `scored` with the score. The planner reads the ledger at each
    round boundary and re-prioritises remaining budget toward the least-covered
    high-weight requirements. **This is the mechanism that makes coverage a
    guarantee rather than an intention.**"*

Until now M02 produced a plan and nothing read it back. A plan nobody checks is
an intention: it says four questions should be asked about DBMS, and if the
session asks none, no part of this platform notices.

── Why M02 owns the table when M05 and M13 do the writing ──────────────────────

Because M02 is the module that made the promise. The plan is its output, the
requirement ids are its ids, and the weights the re-prioritisation reads are
its weights. A ledger living in M05 would be M05 keeping score of somebody
else's commitment in somebody else's vocabulary.

Which means this table has to exist BEFORE either writer does. The endpoints
here are the contract M05 and M13 are written against, not a client of theirs.

── Identity: forwarded, not asserted ───────────────────────────────────────────

`ai_core.identity` has four roles and the list is closed on purpose — *"a role
added in one module is a role the other eighteen do not know how to refuse."*
There is no `service` role and this file does not invent one.

A ledger write is session-scoped, a session belongs to a candidate, and M05
writing `asked` is acting on that candidate's behalf. So these endpoints are
candidate-scoped like every other personal route here, `enforce_access` gates
them without being asked to, and M05 forwards the student's identity exactly as
M02 forwards it to M01. One pattern, already proven in this repository, and no
second way to authenticate.

── Append-only ─────────────────────────────────────────────────────────────────

§6.6 says a row "moves to scored". It does not move here: a second row is
appended and the newest state for a `(session, requirement, turn)` wins.

An interview is evidence, and evidence that can be overwritten is evidence
somebody can quietly revise. "Asked at 14:02, answered at 14:04, scored 0.3 at
14:09" is the sequence a dispute needs (§12 EC-2.13's cousin, and M13's whole
disputes queue assumes it). A mutated row keeps only the verdict.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlmodel import Field, SQLModel

#: §5's five states, in the order a turn passes through them.
PLANNED = "planned"
ASKED = "asked"
ANSWERED = "answered"
SCORED = "scored"
SKIPPED = "skipped"

STATES = (PLANNED, ASKED, ANSWERED, SCORED, SKIPPED)

#: How far through a turn each state is. Used to decide which of two rows for
#: one turn is the current one — an `answered` arriving after a `scored` is a
#: late duplicate, not a regression.
_PROGRESS = {PLANNED: 0, ASKED: 1, ANSWERED: 2, SKIPPED: 3, SCORED: 4}


def _utcnow() -> datetime:
    return datetime.now(UTC)


class CoverageLedger(SQLModel, table=True):
    """One event in one turn's life (§5's `coverage_ledger`).

    §5 gives the primary key as `(session_id, requirement_id, turn_id)`. Here
    the row has its own id and that triple is merely indexed, because the table
    is append-only: the same turn legitimately produces `asked` then `answered`
    then `scored`, and a composite key would force each to overwrite the last.
    """

    __tablename__ = "coverage_ledger"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    session_id: uuid.UUID = Field(index=True)
    candidate_id: uuid.UUID = Field(index=True)
    #: Which posting this session is preparing for. Not in §5's sketch, and
    #: needed: the requirement ids are M02's and they are only unique WITHIN a
    #: parse, so a ledger without it cannot tell R-3 of one JD from R-3 of
    #: another when a student prepares for two drives.
    jd_id: uuid.UUID = Field(index=True)

    requirement_id: str
    turn_id: uuid.UUID | None = None

    #: `planned` | `asked` | `answered` | `scored` | `skipped`.
    state: str
    #: Only meaningful for `scored`. `None` everywhere else, never 0.0 — the
    #: same distinction the rest of this module keeps between "no score" and
    #: "a score of zero".
    score: float | None = None

    updated_at: datetime = Field(default_factory=_utcnow)


class CoverageTurnScore(SQLModel, table=True):
    """A turn's score as M13 sends it — addressed by TURN, not by requirement.

    M13 knows which turn it scored and nothing about M02's requirement ids, and
    should not: M06 already told M02 which requirements a question was about
    when it wrote the turn's `asked` row. So the score is kept here against the
    turn, and M02 does the mapping — appending one `scored` ledger row per
    requirement the turn touched.

    **Order-independent on purpose.** M06's ledger rows and M13's scores leave
    two different modules' outboxes on two different schedules, so a score can
    arrive before the `asked` row it belongs to. It is kept rather than refused,
    and applied when the row lands (`router.apply_turn_score`). Either arrival
    order produces the same ledger, which is what removes the need for the two
    outboxes to coordinate at all.

    Append-only, like the ledger: a re-score is a new row, and the newest wins.
    """

    __tablename__ = "coverage_turn_score"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    session_id: uuid.UUID = Field(index=True)
    candidate_id: uuid.UUID = Field(index=True)
    turn_id: uuid.UUID = Field(index=True)
    #: 0..1. M13 normalises, because one ledger spans rubrics of different
    #: scales; the category and its scale are kept beside it.
    score: float
    raw_category: int | None = None
    n_categories: int | None = None
    rubric_version: str | None = None
    #: M13's evaluation. A resend of the same evaluation is a no-op.
    evaluation_id: uuid.UUID | None = Field(default=None, index=True)
    scored_at: datetime | None = None
    recorded_at: datetime = Field(default_factory=_utcnow)


def owed_scored_rows(
    turn_rows: list[CoverageLedger], score: CoverageTurnScore
) -> list[tuple[uuid.UUID, str]]:
    """`(jd_id, requirement_id)` pairs this turn still owes a `scored` row.

    One per requirement the turn touched. A requirement whose newest `scored`
    row already carries this score owes nothing — so applying the same score
    twice, from a resend or from both arrival orders, appends nothing twice.
    """
    touched: dict[tuple[uuid.UUID, str], list[CoverageLedger]] = {}
    for row in turn_rows:
        if row.state in (ASKED, ANSWERED, SCORED):
            touched.setdefault((row.jd_id, row.requirement_id), []).append(row)
    owed = []
    for key, rows in touched.items():
        scored = sorted((r for r in rows if r.state == SCORED), key=lambda r: r.updated_at)
        if scored and scored[-1].score == score.score:
            continue
        owed.append(key)
    return owed


def current(rows: list[CoverageLedger]) -> dict[tuple[str, str], CoverageLedger]:
    """The latest state of each turn, keyed by `(requirement_id, turn_id)`.

    Furthest-through wins rather than newest-written. An `answered` event that
    arrives after a `scored` one is a late duplicate — M13 and M05 are separate
    services and their clocks are not ordered — and letting it win would move a
    scored turn backwards.
    """
    best: dict[tuple[str, str], CoverageLedger] = {}
    for row in rows:
        key = (row.requirement_id, str(row.turn_id or ""))
        seen = best.get(key)
        if seen is None or _PROGRESS.get(row.state, 0) >= _PROGRESS.get(seen.state, 0):
            best[key] = row
    return best


def covered_counts(rows: list[CoverageLedger]) -> dict[str, int]:
    """Questions actually PUT to the student, per requirement.

    `asked` and beyond. A `planned` row is the plan restating itself and a
    `skipped` one is the opposite of coverage, so neither counts — which is the
    whole point of reading the ledger instead of the plan.
    """
    counts: dict[str, int] = {}
    for row in current(rows).values():
        if row.state in {ASKED, ANSWERED, SCORED}:
            counts[row.requirement_id] = counts.get(row.requirement_id, 0) + 1
    return counts


def scores_by_requirement(rows: list[CoverageLedger]) -> dict[str, list[float]]:
    """Every score recorded against each requirement, in arrival order."""
    out: dict[str, list[float]] = {}
    for row in sorted(current(rows).values(), key=lambda r: r.updated_at):
        if row.state == SCORED and row.score is not None:
            out.setdefault(row.requirement_id, []).append(row.score)
    return out
