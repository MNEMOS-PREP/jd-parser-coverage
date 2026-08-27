"""The student's corrections to a shared parse (FR-2.10).

Extraction scores F1 0.857 on the golden corpus, which sounds fine until it is
read the other way round: roughly one row in seven is wrong, and until now a
student looking at a requirement the posting never made had no way to say so.
§3.2 lists it as the counter to the whole "parse produces obvious nonsense"
risk — *"read-back screen is editable"* — and it was the one part of that
counter never built.

── Why an overlay and not an update ────────────────────────────────────────────

FR-2.12 caches one parse across every student who pastes the same posting, and
§3.2.4 is explicit about why: *"The same JD is pasted by 60 students. The parse
is shared, the gap analysis is per-student."*

So `JobDescription` is not one student's document. A `PATCH` that mutated
`jd.requirements` would let any student silently rewrite what fifty-nine others
see — delete a requirement they personally do not have, and everyone else's
coverage plan quietly stops testing it. That is not a permissions bug to be
fixed with a check; it is the wrong shape.

Edits are therefore rows of their own, keyed by `(candidate_id, jd_id)`, and
the shared parse is never written to. Two students on one drive can disagree
about what the posting says and both be served correctly.

── What an edit can say ────────────────────────────────────────────────────────

Three actions, and they are the three things a student can actually know better
than the parser:

    remove       "this is not in the posting" — a misread, a fragment, or
                 something the archetype supplied that does not apply.
    add          "you missed this" — the label plus, if it is really there,
                 the span it can be found at.
    necessity    "this is a must, not a nice-to-have" — the posting's wording
                 was ambiguous and the student read the room better.

Nothing here lets a student edit a SPAN or a concept id. A span is a citation
into the document and a concept id belongs to M04; letting either be typed
would turn provenance into an opinion.

── Everything downstream re-derives ────────────────────────────────────────────

An edit changes the label list, and the label list is re-run through `locate` —
so necessity, weights, disjunction grouping and classification are all
recomputed rather than patched. Removing a requirement redistributes its weight
across the rest, which is what §6.4's normalisation means and what a
hand-adjusted list would get wrong on the first edit.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlmodel import Field, SQLModel

#: What a student is allowed to say about a requirement.
REMOVE = "remove"
ADD = "add"
NECESSITY = "necessity"
ACTIONS = frozenset({REMOVE, ADD, NECESSITY})


def _utcnow() -> datetime:
    return datetime.now(UTC)


class RequirementEdit(SQLModel, table=True):
    """One correction, belonging to one student, against one shared parse.

    Append-only. An edit is not updated in place and not deleted when
    superseded — the newest row for a `(candidate_id, jd_id, target)` wins, and
    the older ones stay.

    That costs almost nothing and buys the question every read-back screen
    eventually has to answer: *why does my list differ from the parse?* A log of
    what somebody changed answers it; a mutated row does not.
    """

    __tablename__ = "requirement_edits"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    candidate_id: uuid.UUID = Field(index=True)
    jd_id: uuid.UUID = Field(index=True)

    #: `remove` | `add` | `necessity`.
    action: str

    #: For `remove` and `necessity`, the requirement's LABEL rather than its id.
    #:
    #: Ids are positional — `R-3` is the third requirement in document order —
    #: so they move when the set changes. An edit keyed by id would silently
    #: retarget the moment another edit shifted the numbering, which is exactly
    #: when a student is making several.
    target: str

    #: For `necessity`: the new value. Unused by the other two.
    value: str = ""

    created_at: datetime = Field(default_factory=_utcnow)


def _key(label: str) -> str:
    return " ".join(label.lower().split())


def effective(
    labels: list[str],
    edits: list[RequirementEdit],
) -> tuple[list[str], dict[str, str], dict[str, str]]:
    """The label list this student should see, and their necessity overrides.

    Returns `(labels, necessity_overrides, sources)`.

    Applied in order, so a student who removes something and then adds it back
    ends with it present. Later edits win, which is the only rule that matches
    what somebody clicking twice expects.

    A label the student ADDED is marked `source="user"` — §5 has carried that
    value in its enum since the spec was written and nothing had ever produced
    it. It matters downstream for the same reason `archetype` does: §6.4
    discounts anything that is not `jd` to 0.75, so a student's addition
    counts, and counts slightly less than what the company actually wrote.
    """
    present = list(labels)
    overrides: dict[str, str] = {}
    sources: dict[str, str] = {}

    for edit in sorted(edits, key=lambda e: e.created_at):
        key = _key(edit.target)

        if edit.action == REMOVE:
            present = [label for label in present if _key(label) != key]
            overrides.pop(key, None)
            sources.pop(key, None)

        elif edit.action == ADD:
            if not any(_key(label) == key for label in present):
                present.append(edit.target)
            sources[key] = "user"

        elif edit.action == NECESSITY and edit.value:
            overrides[key] = edit.value

    return present, overrides, sources
