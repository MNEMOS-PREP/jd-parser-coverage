"""The resume against the posting: eligibility, evidence, and risk (FR-2.15).

Everything else in this module compares a job description to the SKILL GRAPH —
what M04 has measured about a student across every session they have ever done.
This file compares it to the RESUME, which is a different and more immediate
question. The graph says what a student can do. The resume says what a company
will read about them next week, and the two disagree constantly.

── The sentence FR-2.15 asks for ───────────────────────────────────────────────

*"you have 7.2, cutoff is 7.5"*

M02 has held the cutoff since 2026-08-25 and could not say that sentence,
because the left-hand side lives in M01 (`entities.education.grade`) and M02 did
not read M01. The eligibility banner stated the bar and stopped — correctly,
because asserting that a student falls short on a number this module does not
hold is the worst thing here to be wrong about.

── Comparing grades is where this gets dangerous ───────────────────────────────

M01 stores the grade VERBATIM, in whatever notation the resume used: "8.1",
"82%", "3.7", "9.1/10". §3.2.2 makes eligibility a hard filter, which means a
wrong comparison does not mis-rank a requirement — it tells a student they
cannot sit a drive they are eligible for, or that they can sit one they cannot.

So the comparison is refused far more often than it is made:

  · a percentage against a CGPA cutoff is NOT converted. "82%" is not 8.2, and
    the conversion factor differs per university. `scale_mismatch`.
  · a 4-point GPA against a 10-point cutoff is NOT converted. `scale_mismatch`.
  · no grade on the resume at all is `unknown`, not `fails`.

`unknown` is a real verdict here and it is displayed as one. A student whose
resume does not state a CGPA is not ineligible; they are unassessed, and the
fix is on their resume rather than in their preparation.

── Risk is ranked by what actually stops you ───────────────────────────────────

A hard eligibility failure outranks every skill gap on the page, because no
amount of interview preparation gets you into a drive whose CGPA bar you miss.
That ordering is the whole point of separating eligibility from requirements in
the first place (§3.2.2), and a risk list that buried "you miss the cutoff"
under six skill gaps would have thrown the separation away at the last step.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from backend_M02_JD_Parser.extract import EligibilityCriteria

#: "8.1", "9.12", "82%", "3.7/4", "7.5 / 10". Whatever the resume wrote.
_GRADE_VALUE = re.compile(r"(?P<value>\d{1,3}(?:\.\d{1,3})?)\s*(?P<pct>%)?\s*(?:/\s*(?P<of>\d+))?")


class GradeReading(BaseModel):
    """What M01's verbatim grade string turned out to mean, if anything."""

    #: Exactly what the resume said. Always shown beside any verdict, because a
    #: student disputing our reading needs to see what we read.
    raw: str | None = None
    value: float | None = None
    #: `cgpa_10`, `gpa_4`, `percent`, or `unknown`. Named rather than inferred
    #: at the comparison site, so the refusal to convert is one decision in one
    #: place instead of an `if` somebody later "simplifies".
    scale: str = "unknown"


class Verdict(BaseModel):
    """One eligibility criterion, checked.

    `state` is `meets`, `fails`, `unknown` or `scale_mismatch`. Four, not two:
    collapsing the last two into `fails` is what turns "we could not read your
    grade" into "you are not eligible", which is a different sentence with
    different consequences for somebody deciding whether to prepare.
    """

    criterion: str
    state: str
    #: The sentence FR-2.15 asks for, already written. One place decides how a
    #: cutoff is phrased, so a student never sees two spellings of it.
    detail: str
    #: What the posting demands, verbatim from the parse.
    required: str | None = None
    #: What the resume says, verbatim from M01.
    yours: str | None = None


class Risk(BaseModel):
    """Something that will cost this student the role, ranked by how much.

    `severity` is `blocking`, `high`, `medium` or `low`. `blocking` is reserved
    for eligibility: a skill gap is something to prepare for and a CGPA cutoff
    is something to be turned away by, and a list that ranked them together
    would tell a student to study for a drive they cannot sit.
    """

    severity: str
    title: str
    detail: str
    #: Requirement labels this risk is about, so a screen can point at rows.
    requirements: list[str] = Field(default_factory=list)


class MatchReport(BaseModel):
    """What this resume looks like against this posting."""

    jd_id: str
    candidate_id: str
    #: `None` when M01 is unreachable or holds no resume for this candidate.
    #: Every other field is then empty and `resume_status` says which, because
    #: an empty report and a missing upstream must not look the same.
    resume_id: str | None = None
    #: `ok`, `no_resume`, or `m01_unreachable`.
    resume_status: str
    verdicts: list[Verdict] = Field(default_factory=list)
    #: Requirement labels the resume shows evidence for, and those it does not.
    evidenced: list[str] = Field(default_factory=list)
    unevidenced: list[str] = Field(default_factory=list)
    #: label -> the alternative that met the same requirement. A posting saying
    #: "Python or Java" is met by Python, and listing Java as missing is
    #: §3.2.1's "33% qualified" reading arriving at the resume screen.
    met_by_alternative: dict[str, str] = Field(default_factory=dict)
    #: Fraction of MUST-have requirements the resume evidences. `None` when the
    #: posting states no must-haves — not 0.0, which would read as total
    #: failure rather than as a question nobody asked.
    must_have_evidence: float | None = None
    risks: list[Risk] = Field(default_factory=list)


def read_grade(raw: str | None) -> GradeReading:
    """M01's verbatim grade string, classified — never converted.

    The scale is decided from what the resume WROTE, not from the size of the
    number. "9.1" is a 10-point CGPA and "9.1%" is a catastrophe, and the only
    thing separating them is a character that a size heuristic would ignore.
    """
    if not raw:
        return GradeReading()

    match = _GRADE_VALUE.search(raw)
    if not match:
        return GradeReading(raw=raw)

    value = float(match.group("value"))
    out_of = match.group("of")

    if match.group("pct"):
        scale = "percent"
    elif out_of == "100":
        scale = "percent"
    elif out_of == "4":
        scale = "gpa_4"
    elif out_of == "10":
        scale = "cgpa_10"
    elif value > 10:
        # No notation, and too large for any 10-point scale. Almost certainly a
        # percentage written bare — but "almost certainly" is not enough to
        # compare against a cutoff, so it is named and then refused.
        scale = "percent"
    elif value <= 4.0:
        # Genuinely ambiguous: 3.7 is a strong 4-point GPA and a failing CGPA.
        # `unknown` rather than a guess, because the guess decides eligibility.
        scale = "unknown"
    else:
        scale = "cgpa_10"

    return GradeReading(raw=raw, value=value, scale=scale)


def _cgpa_verdict(criteria: EligibilityCriteria, grade: GradeReading) -> Verdict:
    required = f"{criteria.min_cgpa} CGPA"

    if grade.value is None:
        return Verdict(
            criterion="cgpa",
            state="unknown",
            required=required,
            yours=grade.raw,
            detail=(
                "This drive needs "
                f"{criteria.min_cgpa} CGPA. Your resume does not state a grade we could read, "
                "so we cannot tell you whether you clear it — that is a gap in the resume, not "
                "a verdict on you."
            ),
        )

    if grade.scale != "cgpa_10":
        named = {
            "percent": "a percentage",
            "gpa_4": "a 4-point GPA",
            "unknown": "a grade on a scale we could not identify",
        }[grade.scale]
        return Verdict(
            criterion="cgpa",
            state="scale_mismatch",
            required=required,
            yours=grade.raw,
            detail=(
                f"This drive needs {criteria.min_cgpa} CGPA and your resume says "
                f"{grade.raw!r}, which is {named}. We will not convert between scales — the "
                "factor differs per university, and getting it wrong tells you the opposite of "
                "the truth about a drive you may or may not be able to sit. Check this one "
                "against the posting yourself."
            ),
        )

    meets = grade.value >= criteria.min_cgpa
    return Verdict(
        criterion="cgpa",
        state="meets" if meets else "fails",
        required=required,
        yours=grade.raw,
        detail=(
            f"You have {grade.value}, the cutoff is {criteria.min_cgpa}."
            + (
                ""
                if meets
                else " This is a hard filter — it is checked before anyone reads the rest."
            )
        ),
    )


#: What a degree line calls a branch, mapped to the code a posting uses.
#:
#: Deliberately small and exact. A resume says "B.Tech Computer Science and
#: Engineering" and a posting says "CSE", and those are the same branch; a
#: resume saying "B.Tech Electronics" against a posting saying "EEE" is a
#: judgement call, and this table declines to make it — an unmatched degree
#: produces `unknown`, not `fails`.
_DEGREE_TO_BRANCH = {
    "computer science": "CSE",
    "computer science and engineering": "CSE",
    "cse": "CSE",
    "information technology": "IT",
    "information science": "ISE",
    "electronics and communication": "ECE",
    "ece": "ECE",
    "electrical and electronics": "EEE",
    "eee": "EEE",
    "mechanical": "MECH",
    "civil": "CIVIL",
    "artificial intelligence": "AIML",
    "ai and ml": "AIML",
    "artificial intelligence and data science": "AIDS",
    "data science": "AIDS",
}


def _branch_of(degree: str | None) -> str | None:
    """The branch code a degree line names, or `None`.

    Longest match wins: "computer science and engineering" must beat "computer
    science", or every CSE degree with the full spelling reads as the short one
    — harmless here, and not harmless the day the two diverge.
    """
    if not degree:
        return None
    lowered = " ".join(degree.lower().split())
    for name in sorted(_DEGREE_TO_BRANCH, key=len, reverse=True):
        if name in lowered:
            return _DEGREE_TO_BRANCH[name]
    return None


def _branch_verdict(criteria: EligibilityCriteria, branches: list[str]) -> Verdict | None:
    """Whether the student's branch is on the posting's list.

    `unknown` whenever we could not read a branch off the resume, which is
    common: a degree line reading "B.Tech, 2026" names no branch at all. Telling
    a student they are ineligible because their resume was terse would be the
    same mistake as converting a grade scale.
    """
    if not criteria.allowed_branches:
        return None

    allowed = ", ".join(criteria.allowed_branches)
    if not branches:
        return Verdict(
            criterion="branch",
            state="unknown",
            required=allowed,
            detail=(
                f"This drive is open to {allowed}. We could not read a branch off your resume, "
                "so we cannot check it — that is a gap in the resume, not a verdict on you."
            ),
        )

    overlap = sorted(set(branches) & set(criteria.allowed_branches))
    return Verdict(
        criterion="branch",
        state="meets" if overlap else "fails",
        required=allowed,
        yours=", ".join(sorted(branches)),
        detail=(
            f"This drive is open to {allowed} and your resume reads as {', '.join(sorted(branches))}."
            + (
                ""
                if overlap
                else " This is a hard filter — it is checked before anyone reads the rest."
            )
        ),
    )


def _batch_verdict(criteria: EligibilityCriteria, years: list[int]) -> Verdict | None:
    if not criteria.year_of_passing:
        return None

    wanted = ", ".join(str(year) for year in criteria.year_of_passing)
    if not years:
        return Verdict(
            criterion="year_of_passing",
            state="unknown",
            required=f"{wanted} batch",
            detail=(
                f"This drive is for the {wanted} batch. We could not find a graduation year on "
                "your resume, so we cannot check it."
            ),
        )

    overlap = sorted(set(years) & set(criteria.year_of_passing))
    return Verdict(
        criterion="year_of_passing",
        state="meets" if overlap else "fails",
        required=f"{wanted} batch",
        yours=", ".join(str(year) for year in sorted(years)),
        detail=(
            f"This drive is for the {wanted} batch and your resume reads as "
            f"{', '.join(str(y) for y in sorted(years))}."
        ),
    )


def build_match(
    *,
    jd_id: str,
    candidate_id: str,
    resume: dict | None,
    resume_status: str,
    eligibility: dict,
    requirements: list[dict],
    groups: list[dict] | None = None,
) -> MatchReport:
    """The resume against the posting.

    `resume` is M01's `ResumeOut` as a dict, or None. Nothing here reaches for
    a field that might not be there without a default: M01 is an OPTIONAL
    upstream, and a match report that raises when a resume is half-parsed is
    worse than one that reports what it could check.
    """
    if resume is None:
        return MatchReport(
            jd_id=jd_id,
            candidate_id=candidate_id,
            resume_status=resume_status,
        )

    groups = groups or []
    labels_by_id = {r["id"]: r["text"] for r in requirements}
    criteria = EligibilityCriteria(**eligibility) if eligibility else EligibilityCriteria()
    entities = resume.get("entities") or {}
    education = entities.get("education") or []

    # The best-stated grade wins rather than the first: a resume listing school
    # marks above a degree CGPA would otherwise be judged on the school marks.
    readings = [read_grade(entry.get("grade")) for entry in education]
    grade = next(
        (reading for reading in readings if reading.scale == "cgpa_10"),
        next((reading for reading in readings if reading.value is not None), GradeReading()),
    )

    verdicts: list[Verdict] = []
    if criteria.min_cgpa is not None:
        verdicts.append(_cgpa_verdict(criteria, grade))

    years = [
        entry["dates"]["end_year"]
        for entry in education
        if isinstance(entry.get("dates"), dict) and entry["dates"].get("end_year")
    ]
    batch = _batch_verdict(criteria, years)
    if batch:
        verdicts.append(batch)

    branches = [
        code for entry in education if (code := _branch_of(entry.get("degree"))) is not None
    ]
    branch = _branch_verdict(criteria, branches)
    if branch:
        verdicts.append(branch)

    # ------------------------------------------------------------------
    #  Evidence: does the resume actually SAY the thing the posting wants?
    # ------------------------------------------------------------------
    #  Matched on concept id where both sides resolved, and on the normalised
    #  label otherwise. Concept ids are the reliable half — "React.js" on a
    #  resume and "React" in a posting are one concept and two strings — and
    #  the label fallback is what keeps unresolved requirements checkable at
    #  all, which is most of them while the ontology holds 120 concepts.
    resume_concepts = {str(value) for value in (resume.get("resolved_concepts") or {}).values()}
    resume_labels = {
        _key(label)
        for label in [
            *(resume.get("parsed_skills") or []),
            *(resume.get("unresolved_skills") or []),
        ]
    }

    hits = {
        requirement["text"]: (
            bool(
                {str(concept) for concept in (requirement.get("concept_ids") or [])}
                & resume_concepts
            )
            or _key(requirement["text"]) in resume_labels
        )
        for requirement in requirements
    }

    # A choice the posting offered is met by ONE of its answers (FR-2.3).
    #
    # Without this the report tells a student with Python that they are missing
    # Java, off a posting that said "Python or Java" — §3.2.1's "33% qualified"
    # reading, reappearing in the one place it does the most damage. It is the
    # same bug the coverage endpoint had, and it was found the same way: by
    # running the two modules against each other and reading the output.
    met_by_alternative: dict[str, str] = {}
    for group in groups:
        members = [
            label
            for label in (labels_by_id.get(rid) for rid in group.get("requirement_ids", []))
            if label
        ]
        satisfied = next((label for label in members if hits.get(label)), None)
        if not satisfied:
            continue
        for label in members:
            if label != satisfied:
                met_by_alternative[label] = satisfied

    evidenced: list[str] = []
    unevidenced: list[str] = []
    for requirement in requirements:
        label = requirement["text"]
        if label in met_by_alternative:
            continue
        (evidenced if hits[label] else unevidenced).append(label)

    # Alternatives the posting already accepted are out of the denominator too.
    # Counting them makes the fraction depend on how many ways a company happened
    # to phrase one requirement.
    musts = [
        r
        for r in requirements
        if r.get("necessity") == "must" and r["text"] not in met_by_alternative
    ]
    must_have_evidence = (
        sum(1 for r in musts if r["text"] in evidenced) / len(musts) if musts else None
    )

    return MatchReport(
        jd_id=jd_id,
        candidate_id=candidate_id,
        resume_id=str(resume.get("id")) if resume.get("id") else None,
        resume_status=resume_status,
        verdicts=verdicts,
        evidenced=evidenced,
        unevidenced=unevidenced,
        met_by_alternative=met_by_alternative,
        must_have_evidence=(
            round(must_have_evidence, 3) if must_have_evidence is not None else None
        ),
        risks=_risks(verdicts, requirements, unevidenced, resume, must_have_evidence),
    )


def _key(label: str) -> str:
    return " ".join(label.lower().split())


#: Ordering for the risk list. `blocking` is eligibility and nothing else.
_SEVERITY_ORDER = {"blocking": 0, "high": 1, "medium": 2, "low": 3}


def _risks(
    verdicts: list[Verdict],
    requirements: list[dict],
    unevidenced: list[str],
    resume: dict,
    must_have_evidence: float | None,
) -> list[Risk]:
    """Ranked by what actually stops the student, hardest first."""
    risks: list[Risk] = []

    for verdict in verdicts:
        if verdict.state == "fails":
            risks.append(
                Risk(
                    severity="blocking",
                    title=f"You do not meet the {verdict.criterion.replace('_', ' ')} bar",
                    detail=verdict.detail,
                )
            )
        elif verdict.state in {"unknown", "scale_mismatch"}:
            risks.append(
                Risk(
                    severity="medium",
                    title=f"We could not check the {verdict.criterion.replace('_', ' ')} bar",
                    detail=verdict.detail,
                )
            )

    unevidenced_musts = [
        r["text"] for r in requirements if r.get("necessity") == "must" and r["text"] in unevidenced
    ]
    if unevidenced_musts:
        risks.append(
            Risk(
                severity="high",
                title=(
                    f"{len(unevidenced_musts)} must-have requirement"
                    f"{'' if len(unevidenced_musts) == 1 else 's'} "
                    "with nothing on your resume"
                ),
                detail=(
                    "The posting states these and your resume does not mention them. A recruiter "
                    "screening on keywords will not see them, whatever you can actually do."
                ),
                requirements=unevidenced_musts,
            )
        )

    if must_have_evidence is not None and must_have_evidence < 0.5:
        risks.append(
            Risk(
                severity="high",
                title="Your resume evidences under half of what this role asks for",
                detail=(
                    f"{round(must_have_evidence * 100)}% of the must-have requirements appear on "
                    "your resume. That is a resume problem before it is a preparation problem."
                ),
            )
        )

    flags = resume.get("red_flags") or []
    if flags:
        risks.append(
            Risk(
                severity="medium",
                title=f"{len(flags)} thing{'' if len(flags) == 1 else 's'} on your resume "
                "an interviewer will ask about",
                detail=(
                    "Gaps, overlaps or unverifiable claims that M01 flagged. They are not "
                    "disqualifying; they are the questions you should have an answer ready for."
                ),
            )
        )

    if not resume.get("confirmed", False):
        risks.append(
            Risk(
                severity="low",
                title="You have not confirmed this resume's read-back",
                detail=(
                    "Everything above is computed from what we extracted, not from what you "
                    "verified. If we misread a skill or a grade, this whole report inherits it."
                ),
            )
        )

    risks.sort(key=lambda risk: _SEVERITY_ORDER.get(risk.severity, 9))
    return risks
