"""What this company actually does at a drive (FR-2.13, §3.2 hard part 5).

FR-2.13: *"Enrich with company drive data from M15 when available."*

A job description says what a company WANTS. M15 holds what it ASKED — the
questions students reported after sitting the drive, the package that was
actually offered, the bond nobody mentioned in the posting. Those are different
facts and the second kind is the one a student cannot get anywhere else.

── The three enrichments, and why each is worth a network call ─────────────────

**1. The company is one company.** §3.2's fifth non-obvious hard part: *"'TCS',
'Tata Consultancy Services', 'TCS Digital', 'TCS NQT' are one company and four
different drives. The alias + drive-variant table matters more than it
sounds."* M02 reads a company name out of a PDF; M15 owns the alias table. M02
asking is the only version of this that does not end with M02 keeping a second
alias table that drifts from the first.

**2. The drive is a specific drive.** A `DriveVariant` carries a typical
package, a bond and the locations it hires into. M02 extracts exactly those
three from the posting when the posting states them — and most postings state
one of the three. Where the JD is silent M15 can answer, and where the two
disagree the student is looking at the single most useful sentence on the page:
*"the posting says 4.5 LPA; students who sat this drive reported 3.6 fixed."*

**3. The questions are evidence about weight.** §6.4 weights a requirement by
how the JD writes it — position, repetition, emphasis, which section. Every one
of those terms is a proxy for "how much does this company care", and M15 has
the direct measurement: the topics that keep appearing in reported questions.

── Why this is not a topic→requirement lookup table ────────────────────────────

The obvious implementation is a dictionary mapping M15's topic strings to M02's
requirement labels, and it is wrong for the reason a fixed list is always
wrong: it is one company's vocabulary behind from the day it is written, and
the topics come from student submissions, so they are open-ended by
construction.

`normalise_alias` is imported from `ai_core.concepts` — the same function M02's
own de-duplication uses and the same one M04 resolves concepts with. Two
modules spelling a topic differently is a problem the platform already solved
once; solving it again here would be a second answer to it.

── Rule 2 ─────────────────────────────────────────────────────────────────────

M15 absent removes the brief and nothing else. The plan is still a plan, the
weights are still §6.4's weights, and the screen says which module is not
running rather than showing a gap. `evidence_boost` is empty rather than 1.0
everywhere, so a caller can tell "no adjustment" from "M15 said nothing about
this requirement".
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any

from ai_core.concepts import normalise_alias
from pydantic import BaseModel, Field

#: How far a requirement's weight may move on M15's evidence, either way.
#:
#: §6.4's weights are a product of five terms that each top out near 1.5, and
#: this is deliberately the smallest of them. The reported questions are a
#: sample of what a handful of students remembered after an interview, and a
#: term that could double a weight would let nine submissions overrule what the
#: company wrote down. It nudges the ordering; it does not decide it.
MAX_EVIDENCE_BOOST = 1.25
MIN_EVIDENCE_BOOST = 0.85

#: Below this much corroborated evidence, the topic distribution is not a
#: distribution.
#:
#: Four students remembering four different questions says nothing about which
#: topic the drive favours, and treating it as a signal is how a sample of four
#: becomes a plan. Measured in corroboration-weighted claims rather than in
#: rows: two students agreeing on one topic is worth more than two students
#: naming two, and the count cannot tell those apart.
MIN_EVIDENCE_WEIGHT = 8.0


class DriveFact(BaseModel):
    """One thing M15 knows about this drive that the posting did not say.

    `stated` is what the JD said, `observed` is what M15 holds, and both are
    carried even when they agree — a student who reads "the posting says 18
    months and so do the reports" has learned something, and it is not the same
    thing as silence.
    """

    field: str
    stated: str | None = None
    observed: str | None = None
    #: `absent` (JD silent), `agrees`, or `differs`. Three states because they
    #: read completely differently to somebody deciding whether to apply.
    relation: str


class CompanyBrief(BaseModel):
    """M15's answer about the company this posting is for (FR-2.13).

    `None` from the assembler entirely when M15 is unreachable or does not know
    the company — an empty brief and an absent one are different, and only the
    first means "we asked and this company has no reports yet".
    """

    company_id: str
    company_name: str
    #: Every spelling M15 resolves to this company. Shown, because the posting
    #: said one of them and the student may only know another.
    aliases: list[str] = Field(default_factory=list)
    report_count: int = 0

    drive_variant_id: str | None = None
    drive_variant_name: str | None = None
    #: Why this variant and not another, in words. "TCS NQT" and "TCS Digital"
    #: are the same company and a different interview, and picking one silently
    #: is picking one wrong half the time.
    variant_reason: str = ""

    #: What the reports say that the posting did not (§3.2 hard part 5).
    facts: list[DriveFact] = Field(default_factory=list)

    #: Topic -> share of this drive's evidence, for the topics M15 holds.
    #: Not every requirement appears; absence is "no report mentions it", never
    #: "this company does not ask about it".
    observed_topics: dict[str, float] = Field(default_factory=dict)
    #: How much corroborated evidence produced those shares. Weighted claims,
    #: not a row count: two students agreeing on one topic is worth more than
    #: two students naming two, and a count cannot tell those apart.
    evidence_weight: float = 0.0

    #: Whether the topics describe this DRIVE or the whole COMPANY.
    #:
    #: `drive` when M15 had variant-scoped evidence, `company` when it only had
    #: company-wide reports, `none` when it had neither. Carried rather than
    #: hidden because they are different claims: "TCS Digital asks about DBMS"
    #: and "TCS asks about DBMS" are one sentence apart and TCS runs three
    #: different interviews.
    topics_scope: str = "none"

    #: requirement id -> multiplier, present only where M15 had evidence.
    #: Empty when `evidence_weight` is below the floor, so a caller can tell
    #: "no adjustment" from "M15 said nothing about this one".
    evidence_boost: dict[str, float] = Field(default_factory=dict)

    #: M15's own word for how much it knows: `none`, `thin`, `partial`, `good`.
    #: Passed through rather than re-derived, because M15 owns that judgement
    #: and a second opinion computed here would eventually disagree with the
    #: company page the student can open in the next tab.
    data_sufficiency: str = "none"


# ---------------------------------------------------------------------------
#  Picking the drive
# ---------------------------------------------------------------------------


def _tokens(text: str) -> set[str]:
    return {t for t in normalise_alias(text).split() if len(t) > 1}


def same_archetype(m15_value: str, m02_id: str | None) -> bool:
    """Do M15's role_archetype and M02's archetype id mean the same role?

    They are not the same string and were never going to be. M15's seeded
    variants say `sde`; M02's archetype ids are `sde_1`, `backend_engineer`,
    `qa_engineer`. Two modules, two vocabularies, and comparing them directly
    is an integration that silently never matches — which is exactly what the
    first version of this did, and no unit test noticed because the test wrote
    both sides.

    Resolved through M02's OWN archetype aliases rather than a translation
    table. Every archetype here already carries the spellings a posting might
    use — `sde_1` lists "sde", "software engineer", "programmer analyst" —
    because that is how a role title is matched in the first place (§6.3). M15
    writing "sde" is M15 writing one of those spellings, and a lookup table
    mapping the two id sets would be a third vocabulary to keep in step with
    the other two.
    """
    if not m15_value or not m02_id:
        return False

    from backend_M02_JD_Parser.archetypes import BY_ID

    if normalise_alias(m15_value) == normalise_alias(m02_id):
        return True

    archetype = BY_ID.get(m02_id)
    if archetype is None:
        return False

    needle = normalise_alias(m15_value)
    if normalise_alias(archetype.name) == needle:
        return True
    return any(normalise_alias(alias) == needle for alias in archetype.titles)


def pick_variant(
    variants: list[dict[str, Any]], *, role_title: str, archetype: str | None
) -> tuple[dict[str, Any] | None, str]:
    """Which of this company's drives this posting is describing.

    Scored on two things M02 already has and did not have to invent: the role
    archetype it inferred (§6.3), and the words in the posting's own title.

    The archetype is worth more than the title overlap because it survives
    rewording — "SDE-1" and "Software Development Engineer" produce the same
    archetype and share no tokens. The title still counts, because a company
    runs several drives for one archetype and the name is what separates them:
    "TCS NQT" and "TCS Digital" are both `software_engineer`.

    Returns the variant and the reason, and the reason is never empty. A single
    variant is still a choice — it is "this company runs one drive we know of",
    which is different from "we matched your posting to it".
    """
    if not variants:
        return None, ""

    title_tokens = _tokens(role_title)
    scored: list[tuple[float, str, dict[str, Any]]] = []
    for variant in variants:
        name = str(variant.get("name") or "")
        overlap = title_tokens & _tokens(name)
        archetype_hit = same_archetype(str(variant.get("role_archetype") or ""), archetype)
        score = (1.0 if archetype_hit else 0.0) + 0.35 * len(overlap)
        if archetype_hit and overlap:
            reason = f"{name} — same role archetype, and the posting's title says {' '.join(sorted(overlap))}"
        elif archetype_hit:
            reason = f"{name} — the only drive here for a {archetype.replace('_', ' ')} role"
        elif overlap:
            reason = f"{name} — the posting's title says {' '.join(sorted(overlap))}"
        else:
            reason = ""
        scored.append((score, reason, variant))

    scored.sort(key=lambda row: row[0], reverse=True)
    best_score, best_reason, best = scored[0]

    if best_score == 0.0:
        if len(variants) == 1:
            name = str(best.get("name") or "this drive")
            return best, f"{name} — the only drive this company has reports for"
        # Several drives and nothing distinguishes them. Guessing here is the
        # §6.3 coin toss one layer down, and the cost is worse: the student
        # prepares for the wrong interview.
        return None, (
            f"{len(variants)} different drives at this company and the posting does not "
            "say which — the figures below are the company's, not this drive's"
        )

    runner_up = scored[1][0] if len(scored) > 1 else 0.0
    if best_score - runner_up < 0.3:
        return None, (
            f"the posting matches {scored[0][2].get('name')} and {scored[1][2].get('name')} "
            "equally — pick one on the company page to see its figures"
        )

    return best, best_reason


# ---------------------------------------------------------------------------
#  Cross-checking the posting against the reports
# ---------------------------------------------------------------------------


def _lpa(value: Any) -> str | None:
    return None if value is None else f"{float(value):.1f} LPA"


def _months(value: Any) -> str | None:
    return None if value is None else f"{int(value)} months"


def cross_check(eligibility: dict[str, Any], variant: dict[str, Any] | None) -> list[DriveFact]:
    """Where the posting and the reports agree, differ, or the posting is silent.

    The package comparison uses the posting's TOTAL against M15's typical,
    because that is the number a posting advertises and the number a student
    compares. M02 keeps `package_lpa_fixed` separately for exactly the reason
    this comparison is worth showing — a 6.5 LPA offer with 2 LPA variable is a
    4.5 LPA salary — and a student who sees "reported: 4.2" beside "posting:
    6.5" has just learned what the variable part means without being lectured.
    """
    if not variant:
        return []

    facts: list[DriveFact] = []
    comparisons = [
        (
            "package",
            _lpa(eligibility.get("package_lpa_total")),
            _lpa(variant.get("typical_package_lpa")),
        ),
        ("bond", _months(eligibility.get("bond_months")), _months(variant.get("bond_months"))),
        (
            "locations",
            ", ".join(eligibility.get("location") or []) or None,
            ", ".join(variant.get("typical_locations") or []) or None,
        ),
    ]

    for field, stated, observed in comparisons:
        if observed is None:
            continue
        if stated is None:
            facts.append(DriveFact(field=field, observed=observed, relation="absent"))
        elif stated.lower() == observed.lower():
            facts.append(
                DriveFact(field=field, stated=stated, observed=observed, relation="agrees")
            )
        else:
            facts.append(
                DriveFact(field=field, stated=stated, observed=observed, relation="differs")
            )
    return facts


# ---------------------------------------------------------------------------
#  Evidence about weight
# ---------------------------------------------------------------------------


#: Blocks whose claims say what this drive covers.
#:
#: `questions_tech` is the reported questions and `technical` is the per-round
#: topic breakdown. Both are about what gets ASKED. `questions_hr` is not here:
#: "why this company" is a real question and it is not a requirement the
#: posting can be weighted against, and `process` describes the shape of the
#: day rather than its content.
TOPIC_BLOCKS = ("questions_tech", "technical")

#: Claims M15 has recorded a contradiction for, or rejected outright. A
#: contested claim is not weak evidence — it is evidence somebody who sat the
#: same drive says is wrong, and averaging the two is how a page ends up
#: asserting something no student agrees with.
UNTRUSTED_STATES = frozenset({"contested", "rejected"})


def _claim_topics(claim: dict[str, Any]) -> list[str]:
    """Every topic a claim names.

    `topics` (a list) before `topic` (a string), because the list is the real
    field: one coding question is about arrays AND strings, and the singular
    form cannot say so. Reading only `topic` is what made the first version of
    this see two topics on a page that names fourteen.
    """
    structured = claim.get("structured")
    if not isinstance(structured, dict):
        return []
    raw = structured.get("topics")
    if isinstance(raw, list) and raw:
        return [str(t) for t in raw]
    single = structured.get("topic")
    return [str(single)] if single else []


def topic_shares(page: dict[str, Any]) -> tuple[dict[str, float], float]:
    """Topic -> share of this drive's evidence, and how much evidence that was.

    Weighted by `corroboration_count`, not counted. M15 has already decided how
    much a report is worth — two students independently reporting the same
    thing is what promotes a claim to `confirmed` — and counting rows would
    treat one person's memory as equal to four people agreeing.

    Stale claims still count, at their weight. `is_stale` means the hiring
    process may have moved on, which is a reason to trust the FIGURES less; a
    topic this company asked about last year is still the best guess anybody
    has about the topic it will ask about next year.
    """
    blocks = page.get("fact_blocks")
    if not isinstance(blocks, dict):
        return {}, 0.0

    weights: dict[str, float] = {}
    for name in TOPIC_BLOCKS:
        block = blocks.get(name)
        if not isinstance(block, dict):
            continue
        for claim in block.get("claims") or []:
            if str(claim.get("verification_state") or "") in UNTRUSTED_STATES:
                continue
            # A claim nobody has corroborated is still one student who was
            # there, so the floor is 1 rather than 0.
            weight = max(1, int(claim.get("corroboration_count") or 0))
            for topic in _claim_topics(claim):
                key = normalise_alias(topic)
                if key:
                    weights[key] = weights.get(key, 0.0) + weight

    total = sum(weights.values())
    if not total:
        return {}, 0.0
    return {topic: weight / total for topic, weight in weights.items()}, total


def _by_words(key: str, shares: dict[str, float]) -> float | None:
    """The best share for a topic that shares its WORDS with this requirement.

    M15's "dynamic programming" against a requirement labelled "dynamic
    programming and recursion", and a requirement labelled "sql" against a
    topic "sql joins". Containment either way, because either side can be the
    more specific one.

    On tokens rather than on characters. The character version needed a length
    floor to stop `"c"` matching inside `"recursion"`, and the floor then threw
    away `oop`, `sql`, `aws` and `git` — three-character words that are most of
    what a fresher posting is made of, and `oop` was M15's joint-top topic for
    the drive that found this.

    A word boundary is what separates the two cases, which is the lesson this
    module has already learned twice: `"sql" in "nosql"` in `drop_redundant`,
    and `\\bNET\\b` matching inside `.NET` in the span check. `c` is not a word
    in "recursion"; `oop` is a word in "object oriented programming oop".

    The BEST match, not the first: "dbms" and "dbms normalisation" can both be
    subsets of one requirement, and iteration order should not decide which.
    """
    words = set(key.split())
    if not words:
        return None

    best: float | None = None
    for topic, value in shares.items():
        topic_words = set(topic.split())
        if not topic_words:
            continue
        if topic_words <= words or words <= topic_words:
            if best is None or value > best:
                best = value
    return best


def evidence_boost(
    requirements: list[dict[str, Any]], shares: dict[str, float], *, seen: float
) -> dict[str, float]:
    """Per-requirement multiplier from what this company is reported to ask.

    §6.4 weights a requirement by position, repetition, emphasis and section —
    four proxies for "how much does this company care about it". M15 has the
    direct measurement, and this is it expressed on the same scale so the
    planner can multiply it in beside the rest.

    Matched on `normalise_alias`, from `ai_core.concepts`: the same function
    M02's own de-duplication uses and M04 resolves concepts with. A lookup table
    from M15's topics to M02's labels would be the hardcoded version, and it
    would be wrong within a week — the topics come from student submissions and
    are open-ended by construction.

    A share is turned into a multiplier against the FLAT share, not against the
    largest one. `1/n` is what every topic would get if the drive asked about
    all of them equally, so a topic at twice the flat share is a topic this
    drive asks about twice as often as an even spread — a statement about this
    company. Normalising by the maximum instead would make the top topic 1.25
    in every company, including one whose questions are perfectly evenly
    spread, which is a statement about arithmetic.
    """
    if seen < MIN_EVIDENCE_WEIGHT or not shares:
        return {}

    flat = 1.0 / len(shares)
    boost: dict[str, float] = {}
    for requirement in requirements:
        label = str(requirement.get("label") or requirement.get("text") or "")
        key = normalise_alias(label)
        if not key:
            continue
        share = shares.get(key)
        if share is None:
            share = _by_words(key, shares)
        if share is None:
            continue
        scale = share / flat
        boost[str(requirement["id"])] = round(
            max(MIN_EVIDENCE_BOOST, min(MAX_EVIDENCE_BOOST, scale)), 3
        )
    return boost


# ---------------------------------------------------------------------------
#  The client
# ---------------------------------------------------------------------------


def m15_get(deps: Any, path: str, *, timeout: float = 2.0) -> Any | None:
    """GET from M15, or None.

    Probes first, like `_m04_get`: `is_available` is cached and the call is
    not, and asking a dead port costs a socket timeout every time.

    No identity header. M15's company routes are public by design — reported
    questions and drive figures are what every student on the campus sees — and
    sending a candidate id to a route that does not gate on one would be
    handing a personal identifier to a service with no reason to hold it.
    `ranked_for` is the exception and it is a query parameter M15 documents,
    used only when M02 has already authorised the caller for that candidate.
    """
    dep = deps.get("M15")
    if dep is None or not dep.base_url or not deps.is_available("M15"):
        return None
    try:
        with urllib.request.urlopen(
            f"{dep.base_url.rstrip('/')}{path}", timeout=timeout
        ) as response:
            return json.loads(response.read())
    except Exception:
        return None


def resolve_company(deps: Any, name: str) -> dict[str, Any] | None:
    """The company this posting is for, as M15 spells it.

    M15's search matches canonical names AND aliases, which is the whole point
    of asking: M02 read "Cognizant Technology Solutions" off a brochure and M15
    knows that is the same company as "CTS".

    An exact canonical match wins over a fragment match. "Tata" matches three
    companies and the shortest is not necessarily right, but an exact name is
    never ambiguous.
    """
    query = (name or "").strip()
    if len(query) < 2:
        return None

    rows = m15_get(deps, f"/v1/companies?q={urllib.parse.quote(query)}")
    if not isinstance(rows, list) or not rows:
        return None

    needle = normalise_alias(query)
    for row in rows:
        if normalise_alias(str(row.get("canonical_name") or "")) == needle:
            return row
    for row in rows:
        if any(normalise_alias(str(alias)) == needle for alias in row.get("aliases") or []):
            return row

    if len(rows) == 1:
        return rows[0]
    # Several partial matches and no exact one. "Tech" matching four companies
    # is not a resolution, and picking the first would put another company's
    # bond figure on this posting's page.
    return None


def build_brief(
    deps: Any,
    *,
    company_name: str,
    role_title: str,
    archetype: str | None,
    eligibility: dict[str, Any],
    requirements: list[dict[str, Any]],
    candidate_id: str | None = None,
) -> CompanyBrief | None:
    """Everything M15 can add to this posting, or `None` if it cannot add any.

    `None` means M15 is unreachable or does not know this company. An empty
    brief with `report_count: 0` means M15 knows the company and nobody has
    reported a drive yet — the second is a page that invites a submission and
    the first is a page that names a module that is down.

    Two calls: the company list to resolve the name, then the assembled page.
    The page is the right source rather than `/questions` because it carries
    the fact blocks, the report count and M15's own `data_sufficiency` in one
    response — and because the topics live on the claims, where the
    corroboration counts are.
    """
    company = resolve_company(deps, company_name)
    if company is None:
        return None

    company_id = str(company.get("id"))
    variants = m15_get(deps, f"/v1/companies/{company_id}/variants") or []
    variant, reason = pick_variant(
        variants if isinstance(variants, list) else [],
        role_title=role_title,
        archetype=archetype,
    )

    # Gap-weights M15's ordering for this student. M02 has already checked at
    # `enforce_access` that the caller may see this candidate.
    tail = f"&for_candidate={candidate_id}" if candidate_id else ""

    def fetch(query: str) -> dict[str, Any]:
        # A page assembles claims across several blocks, so it is slower than
        # the list. Still inside M02's own §16 budget, and the alternative is
        # not asking.
        got = m15_get(deps, f"/v1/companies/{company_id}/page?{query}{tail}", timeout=4.0)
        return got if isinstance(got, dict) else {}

    page: dict[str, Any] = {}
    shares: dict[str, float] = {}
    weight = 0.0
    scope = "none"

    if variant:
        page = fetch(f"variant={variant['id']}")
        shares, weight = topic_shares(page)
        if shares:
            scope = "drive"

    if not shares:
        # The drive-scoped page can be empty while the company has fourteen
        # claims: students submit experiences without always naming the variant
        # they sat. Asking for the drive first is still right — TCS NQT and TCS
        # Digital are different interviews — but an empty precise answer is not
        # "this drive asks about nothing", and treating it as one is the scope
        # narrowing silently.
        company_page = fetch("")
        company_shares, company_weight = topic_shares(company_page)
        if company_shares:
            shares, weight, scope = company_shares, company_weight, "company"
            # And the page too, not only the shares. `data_sufficiency` and
            # `report_count` have to come from whichever page ANSWERED: the
            # variant-scoped one reported "none" beside thirty-four units of
            # corroborated evidence, because it was describing a page with no
            # blocks in it.
            page = company_page
        elif not page:
            page = company_page
    report_count = int(page.get("report_count") or company.get("report_count") or 0)

    return CompanyBrief(
        company_id=company_id,
        company_name=str(page.get("company_name") or company.get("canonical_name") or company_name),
        aliases=[str(a) for a in company.get("aliases") or []],
        report_count=report_count,
        drive_variant_id=str(variant["id"]) if variant else None,
        drive_variant_name=str(variant.get("name")) if variant else None,
        variant_reason=reason,
        facts=cross_check(eligibility, variant),
        observed_topics={topic: round(share, 3) for topic, share in shares.items()},
        evidence_weight=round(weight, 2),
        topics_scope=scope,
        evidence_boost=evidence_boost(requirements, shares, seen=weight),
        # M15's own judgement, passed through rather than recomputed. It owns
        # that word, and a second opinion derived here would eventually
        # disagree with the company page the student opens in the next tab.
        data_sufficiency=str(page.get("data_sufficiency") or "none"),
    )
