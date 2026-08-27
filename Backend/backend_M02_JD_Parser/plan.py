"""The coverage plan: how many questions each requirement earns (FR-2.8, §6.5).

This is the module's name. §1: *"we produce a coverage plan: an allocation of
interview question budget across requirements. The Mock Interview Engine
consumes that plan directly."* Until now M02 produced a list of requirements and
a gap report, and the allocation — the thing the name refers to — did not exist.

It could not have existed before today. The allocation is driven by `severity`,
severity is driven by `weight`, and `weight` landed this morning. A planner
built on a flat requirement list would have been §3.2.1's trap wearing an
optimiser: equal weights make equal severities make an even split, which is a
template with extra steps.

── Trap 4, which this file exists to avoid ─────────────────────────────────────

§3.2.1: *"'Every SDE mock = 4 DSA + 2 OOP + 2 HR' is not planning, it is a
constant. The entire value is that the plan changes based on THIS student's gaps
against THIS JD."* Two students on one posting must get materially different
plans, and §10's differentiation test asserts exactly that.

── Why the utility is logarithmic ──────────────────────────────────────────────

§6.5 is emphatic: *"without it the optimiser dumps the entire budget on the
single worst gap, producing a mock that is 9 DBMS questions."* Maximising
`Σ severity·q` is linear, and a linear objective under a single constraint puts
everything on the best ratio. `log(1 + q)` makes the second question about a
topic worth less than the first, which is both true and what makes a plan look
like a person wrote it.

── What is deliberately uniform, and why that is not laziness ──────────────────

§6.5 costs a coding question at 12 minutes and a design question at 20 against
a verbal question's 3.5, and §5's `Requirement.measured_by` is what says which
a requirement needs. `measured_by` does not exist — it is one of the three §5
fields still absent — and nothing else in the pipeline carries the signal:
M04's concepts arrive as a name and a list of aliases, with no kind.

So every question here is costed as verbal, and `round_type` says `verbal` for
everything. The alternative was to guess a round type from the label text, which
would put a confident "coding round" on a requirement nobody classified and make
the plan's time estimate wrong in a way no reader could see. The allocation
still differentiates, because severity does the differentiating; what a uniform
cost loses is the *shape* of the session, not its priorities.
"""

from __future__ import annotations

import math

from pydantic import BaseModel, Field

#: §6.5: "roughly one question per 3.5 minutes for verbal, one per 12 minutes
#: for coding, one per 20 for design". Only the first is reachable today; the
#: other two are here because they are the spec's numbers and the day
#: `measured_by` lands they are what it selects between.
MINUTES_PER_QUESTION = {"verbal": 3.5, "coding": 12.0, "design": 20.0}

#: §6.5's constraint, and it is about the student rather than about the maths:
#: "nobody wants 7 DBMS questions".
MAX_QUESTIONS_PER_REQUIREMENT = 4

#: §6.5: "not_measured requirements get severity = r.weight * 0.6 — we don't
#: know, so we should probe". Not zero, which would make an unmeasured topic
#: invisible to the planner, and not full, which would treat absence of
#: evidence as evidence of weakness.
NOT_MEASURED_DISCOUNT = 0.6


class CoverageAllocation(BaseModel):
    """One requirement's share of the interview (§5).

    `rationale` is a sentence, not a code. §5 marks it "shown in the UI", and a
    student looking at four questions on one topic and none on another is owed
    the reason in words they can argue with.
    """

    requirement_id: str
    #: The label, so a caller can render the plan without re-joining it against
    #: the requirement list.
    requirement_text: str
    question_budget: int
    round_type: str = "verbal"
    #: `weight × (1 − mastery)`, discounted when we are guessing. What the
    #: allocation is sorted by, exposed so the sort can be checked.
    priority: float
    rationale: str
    #: Minutes this allocation consumes. Explicit, because the sum of these is
    #: the only honest answer to "how long will this take".
    minutes: float


class CoveragePlan(BaseModel):
    """§5's `CoveragePlan`, minus the fields that need modules M02 has not met.

    `id`, `requirement_set_id` and `rounds` are absent. The first two need a
    persisted plan, which needs the plan to be something a student edits; and
    `rounds` needs `measured_by` to know a coding requirement from a verbal one.
    Absent rather than defaulted, as everywhere else here.
    """

    jd_id: str
    candidate_id: str
    total_minutes: int
    #: What the allocation actually consumes. Lower than `total_minutes`
    #: whenever the remaining time cannot buy another whole question.
    allocated_minutes: float
    allocations: list[CoverageAllocation] = Field(default_factory=list)
    #: §5, and EC-2.11: must-have requirements that did not fit. Stated openly
    #: rather than quietly dropped — a plan that silently omits a must-have is
    #: worse than one that says it needs a longer session.
    uncovered: list[str] = Field(default_factory=list)
    #: Requirements no question can probe, kept out of the optimiser and out of
    #: `uncovered`, because "we could not fit this" and "nothing can test this"
    #: are different problems with different fixes.
    unmeasurable: list[str] = Field(default_factory=list)
    #: Set when the must-haves alone exceed the budget. EC-2.11 requires the
    #: suggestion, not just the omission.
    suggestion: str | None = None
    #: Every requirement is at its four-question cap and minutes are left over.
    #:
    #: At that point the plan genuinely IS the same for every student — there
    #: is nothing left to differentiate WITH — and §3.2.1's trap 4 says a plan
    #: that is the same for everybody is a template. It is not a bug here: a
    #: 90-minute session against a five-requirement posting has more time than
    #: the posting has content. But the student must be told, because a plan
    #: that looks tailored and is not is the exact thing the trap warns about.
    saturated: bool = False
    plan_version: str = "greedy-log-v1"


def severity(weight: float, mastery: float | None, state: str) -> float:
    """§6.5's `r.weight * (1 - mastery) * confidence_discount`.

    A requirement the student is strong on still has a severity above zero when
    the weight is high, which is right: the posting leaning on something is a
    reason to ask about it even when the graph says they are fine, because the
    graph is a posterior and the interview is the evidence.
    """
    if state == "not_measured":
        # We have no mastery to discount by. Probe it — but not as hard as a
        # measured weakness, because this is ignorance, not a known gap.
        return weight * NOT_MEASURED_DISCOUNT
    if mastery is None:
        return weight * NOT_MEASURED_DISCOUNT
    return weight * max(0.0, 1.0 - mastery)


def _marginal_gain(priority: float, questions: int, minutes: float) -> float:
    """Value of one more question on this requirement, per minute it costs.

    `log(1 + q)` is §6.5's diminishing return: the jump from 0 to 1 question is
    worth `log 2`, from 1 to 2 only `log(3/2)`. Dividing by cost is what makes
    the greedy pass a real optimisation rather than a sort — a cheap question on
    a middling gap can beat an expensive one on a bad gap, which is the whole
    reason the constraint is time and not question count.
    """
    delta = math.log(2 + questions) - math.log(1 + questions)
    return (priority * delta) / minutes


def _rationale(necessity: str, state: str, questions: int) -> str:
    gap = {
        "weak": "a measured gap",
        "not_measured": "never measured",
        "adequate": "measured, not strong",
        "strong": "already strong",
    }.get(state, state)

    if necessity == "must" and questions == 1:
        return f"must-have, {gap} — one question is the floor, not the plan"
    if necessity == "must":
        return f"must-have and {gap}"
    if state == "not_measured":
        return f"the posting asks for it and nothing has measured it ({necessity})"
    return f"{necessity}-have, {gap}"


def build_plan(
    *,
    jd_id: str,
    candidate_id: str,
    total_minutes: int,
    requirements: list[dict],
    states: dict[str, str],
    mastery: dict[str, float | None],
) -> CoveragePlan:
    """Allocate `total_minutes` of interview across the requirements.

    Greedy by marginal value per minute, which §6.5 names as the solver. The
    fallback it also names — a small ILP via `pulp` when the must-have floor
    alone exceeds the budget — is not built: in that case there is nothing to
    optimise, because the constraint set is infeasible and the only honest
    outputs are a partial plan and a statement that the session is too short.
    That is what `uncovered` and `suggestion` carry.
    """
    minutes_each = MINUTES_PER_QUESTION["verbal"]

    # `met_by_alternative` is excluded before anything else. The posting offered
    # a choice and the student answered it; spending a question on the
    # alternative they did not take is asking about something the JD does not
    # require, which is the failure FR-2.3 exists to prevent.
    considered = [
        requirement
        for requirement in requirements
        if states.get(requirement["text"]) not in {"unmeasurable", "met_by_alternative"}
        and requirement.get("measurable")
    ]
    unmeasurable = [
        requirement["text"]
        for requirement in requirements
        if not requirement.get("measurable") or states.get(requirement["text"]) == "unmeasurable"
    ]

    priorities: dict[str, float] = {}
    for requirement in considered:
        label = requirement["text"]
        priorities[requirement["id"]] = severity(
            requirement.get("weight", 0.0),
            mastery.get(label),
            states.get(label, "not_measured"),
        )

    questions: dict[str, int] = {requirement["id"]: 0 for requirement in considered}
    remaining = float(total_minutes)
    uncovered: list[str] = []

    # ------------------------------------------------------------------
    #  The floor first: FR-2.9 guarantees ≥1 probe per measurable must-have
    # ------------------------------------------------------------------
    #  Seeded in severity order so that when the budget runs out it is the
    #  least severe must-have that goes uncovered, rather than whichever the
    #  posting happened to write last.
    musts = sorted(
        (r for r in considered if r.get("necessity") == "must"),
        key=lambda r: priorities[r["id"]],
        reverse=True,
    )
    for requirement in musts:
        if remaining >= minutes_each:
            questions[requirement["id"]] = 1
            remaining -= minutes_each
        else:
            uncovered.append(requirement["id"])

    # ------------------------------------------------------------------
    #  Then spend what is left where the next question is worth most
    # ------------------------------------------------------------------
    by_id = {requirement["id"]: requirement for requirement in considered}
    while remaining >= minutes_each:
        best_id = None
        best_gain = 0.0
        for requirement_id, count in questions.items():
            if count >= MAX_QUESTIONS_PER_REQUIREMENT:
                continue
            gain = _marginal_gain(priorities[requirement_id], count, minutes_each)
            if gain > best_gain:
                best_gain, best_id = gain, requirement_id

        # Every requirement is capped out, or every remaining priority is zero.
        # Handing back unspent minutes is the honest end of a greedy pass.
        if best_id is None:
            break

        questions[best_id] += 1
        remaining -= minutes_each

    allocations = [
        CoverageAllocation(
            requirement_id=requirement_id,
            requirement_text=by_id[requirement_id]["text"],
            question_budget=count,
            priority=round(priorities[requirement_id], 4),
            rationale=_rationale(
                by_id[requirement_id].get("necessity", "should"),
                states.get(by_id[requirement_id]["text"], "not_measured"),
                count,
            ),
            minutes=round(count * minutes_each, 2),
        )
        for requirement_id, count in questions.items()
        if count > 0
    ]
    allocations.sort(key=lambda allocation: (-allocation.priority, allocation.requirement_id))

    # Distinguished from "we had time left because the last question did not
    # fit": saturation means every requirement refused more, not that the
    # remainder was too small to spend.
    saturated = (
        bool(allocations)
        and all(
            allocation.question_budget >= MAX_QUESTIONS_PER_REQUIREMENT
            for allocation in allocations
        )
        and len(allocations) == len(considered)
    )

    suggestion = None
    if uncovered:
        needed = math.ceil(len(uncovered) * minutes_each)
        suggestion = (
            f"{len(uncovered)} must-have requirement"
            f"{'' if len(uncovered) == 1 else 's'} did not fit in {total_minutes} minutes. "
            f"About {needed} more minute{'' if needed == 1 else 's'} would cover "
            f"{'it' if len(uncovered) == 1 else 'them'}."
        )
    elif saturated:
        spent = round(sum(a.minutes for a in allocations))
        suggestion = (
            f"This posting only has enough in it for about {spent} minutes. Every requirement "
            f"is already at its four-question cap, so the extra time in a {total_minutes}-minute "
            "session would repeat questions rather than cover more ground."
        )

    return CoveragePlan(
        jd_id=jd_id,
        candidate_id=candidate_id,
        total_minutes=total_minutes,
        allocated_minutes=round(sum(a.minutes for a in allocations), 2),
        allocations=allocations,
        uncovered=uncovered,
        unmeasurable=unmeasurable,
        suggestion=suggestion,
        saturated=saturated,
    )
