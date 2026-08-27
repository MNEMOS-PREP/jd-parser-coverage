"""The company brief (FR-2.13, §3.2 hard part 5).

A JD says what a company WANTS. M15 holds what it ASKED. These tests are about
keeping the second from quietly becoming the first.

The client is faked rather than mocked at the socket: `build_brief` takes the
dependency registry as an argument precisely so a test can hand it one, and a
fake that answers three paths is a better description of the contract than a
patched `urlopen` is.
"""

from __future__ import annotations

import uuid

import pytest
from backend_M02_JD_Parser import company as m15
from backend_M02_JD_Parser.company import (
    MAX_EVIDENCE_BOOST,
    MIN_EVIDENCE_BOOST,
    MIN_EVIDENCE_WEIGHT,
    cross_check,
    evidence_boost,
    pick_variant,
    same_archetype,
    topic_shares,
)


def _page(*claims, sufficiency: str = "good", reports: int = 9) -> dict:
    """An M15 company page, in the shape the live module actually sends.

    Each claim is `(block, topics, corroboration, state)`. Written out rather
    than abbreviated because the shape IS the contract, and the first version
    of these tests passed against a payload M15 does not produce.
    """
    blocks: dict[str, dict] = {}
    for block, topics, corroboration, state in claims:
        blocks.setdefault(block, {"kind": block, "claims": []})["claims"].append(
            {
                "structured": {"topics": list(topics)},
                "corroboration_count": corroboration,
                "verification_state": state,
                "is_stale": False,
            }
        )
    return {
        "fact_blocks": blocks,
        "report_count": reports,
        "data_sufficiency": sufficiency,
        "company_name": "Cognizant",
    }


def _tech(topics, corroboration=2, state="confirmed"):
    return ("questions_tech", topics, corroboration, state)


# ---------------------------------------------------------------------------
#  Picking the drive — §3.2 hard part 5
# ---------------------------------------------------------------------------


def _variant(name: str, archetype: str = "", **extra) -> dict:
    return {"id": str(uuid.uuid4()), "name": name, "role_archetype": archetype, **extra}


@pytest.mark.gate
def test_m15s_archetype_vocabulary_is_not_m02s(monkeypatch):
    """M15's seeded variants say `sde`. M02's archetype ids are `sde_1`.

    Comparing them directly is an integration that silently never matches, and
    it is what the first version of this module did — no unit test noticed,
    because the test wrote both sides of the comparison. Running it against the
    live module found it in one call.

    Resolved through M02's own archetype titles rather than a translation
    table: `sde_1` already lists "sde" and "software engineer", because that is
    how a role title is matched in the first place (§6.3).
    """
    assert same_archetype("sde", "sde_1")
    assert same_archetype("software engineer", "sde_1")
    assert same_archetype("Software Engineer", "sde_1")
    assert not same_archetype("sde", "qa_engineer")
    assert not same_archetype("", "sde_1")
    assert not same_archetype("sde", None)


def test_the_archetype_beats_the_title_because_it_survives_rewording():
    """ "SDE-1" and "Software Development Engineer" share no tokens."""
    variants = [
        _variant("Analyst Programme", "business_analyst"),
        # `sde`, the way M15 actually writes it.
        _variant("Engineering Drive", "sde"),
    ]

    chosen, reason = pick_variant(variants, role_title="SDE-1", archetype="sde_1")

    assert chosen is not None
    assert chosen["name"] == "Engineering Drive"
    assert "sde 1" in reason or "sde" in reason


def test_the_title_separates_two_drives_for_one_archetype():
    """ "TCS NQT" and "TCS Digital" are both `software_engineer`.

    Which is exactly the case §3.2 calls out: one company, four drives, and the
    archetype cannot tell them apart because it was never meant to.
    """
    variants = [
        _variant("TCS NQT", "sde"),
        _variant("TCS Digital", "sde"),
    ]

    chosen, reason = pick_variant(variants, role_title="TCS Digital Developer", archetype="sde_1")

    assert chosen is not None
    assert chosen["name"] == "TCS Digital"
    assert "digital" in reason.lower()


@pytest.mark.gate
def test_two_equally_matching_drives_are_refused_rather_than_guessed():
    """The §6.3 coin toss one layer down, and it costs more here.

    Getting the archetype wrong plans the wrong questions. Getting the DRIVE
    wrong puts another interview's package, bond and topic distribution on this
    posting's page, and the student prepares against it.
    """
    variants = [
        _variant("Ninja", "sde"),
        _variant("Digital", "sde"),
    ]

    chosen, reason = pick_variant(variants, role_title="Software Engineer", archetype="sde_1")

    assert chosen is None
    assert "equally" in reason or "does not say" in reason
    assert reason, "a refusal with no reason is a blank space on the page"


def test_a_single_drive_is_still_a_stated_choice():
    variants = [_variant("Campus Drive 2027")]

    chosen, reason = pick_variant(variants, role_title="Engineer", archetype=None)

    assert chosen is not None
    assert "only drive" in reason


def test_no_drives_is_no_choice_and_no_reason():
    assert pick_variant([], role_title="Engineer", archetype="sde_1") == (None, "")


# ---------------------------------------------------------------------------
#  Cross-checking the posting against the reports
# ---------------------------------------------------------------------------


def test_the_posting_and_the_reports_disagreeing_is_the_row_that_matters():
    facts = cross_check(
        {"package_lpa_total": 6.5},
        _variant("Digital", typical_package_lpa=4.2),
    )

    package = next(f for f in facts if f.field == "package")
    assert package.relation == "differs"
    assert package.stated == "6.5 LPA"
    assert package.observed == "4.2 LPA"


def test_a_bond_the_posting_never_mentions_is_an_addition_not_a_disagreement():
    """Postings leave the bond out constantly. Absence is not conflict, and a
    student reads the two completely differently."""
    facts = cross_check({}, _variant("Digital", bond_months=18))

    bond = next(f for f in facts if f.field == "bond")
    assert bond.relation == "absent"
    assert bond.stated is None
    assert bond.observed == "18 months"


def test_agreement_is_carried_too():
    """ "The posting says 18 months and so do the reports" is a fact a student
    has learned. It is not the same as silence."""
    facts = cross_check(
        {"bond_months": 18},
        _variant("Digital", bond_months=18),
    )

    assert next(f for f in facts if f.field == "bond").relation == "agrees"


def test_nothing_is_claimed_about_a_drive_we_could_not_pick():
    assert cross_check({"bond_months": 18}, None) == []


def test_a_field_m15_has_no_figure_for_produces_no_row():
    """Silence on both sides is not a finding."""
    facts = cross_check({"package_lpa_total": 6.5}, _variant("Digital"))
    assert facts == []


# ---------------------------------------------------------------------------
#  Evidence about weight
# ---------------------------------------------------------------------------


def test_a_claim_naming_two_topics_is_about_both():
    """`RankedQuestion.topic` is one string and usually null; the CLAIM carries
    `topics`, a list, because a coding question is about arrays AND strings.

    Reading the singular field is what made the first version of this see two
    topics on a page that names fourteen.
    """
    shares, weight = topic_shares(_page(_tech(["arrays", "strings"], corroboration=2)))

    assert set(shares) == {"arrays", "strings"}
    assert weight == 4.0, "each topic carries the claim's corroboration"


def test_a_topic_two_students_agree_on_outweighs_one_nobody_confirmed():
    """M15 has already decided what a report is worth: two independent reports
    are what promote a claim to `confirmed`.

    Counting rows throws that away and treats one person's memory as equal to
    four people agreeing.
    """
    shares, _ = topic_shares(
        _page(_tech(["dbms"], corroboration=4), _tech(["kubernetes"], corroboration=1))
    )

    assert shares["dbms"] > shares["kubernetes"]


@pytest.mark.gate
def test_a_contested_claim_is_not_evidence():
    """Not weak evidence — evidence somebody who sat the same drive says is
    wrong. Averaging the two is how a page asserts something nobody agrees
    with."""
    shares, weight = topic_shares(
        _page(_tech(["dbms"], 3, "confirmed"), _tech(["blockchain"], 5, "contested"))
    )

    assert "blockchain" not in shares
    assert weight == 3.0


def test_an_uncorroborated_claim_still_counts_as_one_student():
    shares, weight = topic_shares(_page(_tech(["dbms"], corroboration=0)))

    assert weight == 1.0


def test_a_page_with_no_blocks_is_no_evidence():
    assert topic_shares({}) == ({}, 0.0)


def test_a_topic_is_matched_by_the_platforms_own_normaliser():
    """`normalise_alias`, from `ai_core.concepts` — the same function M02's
    de-duplication uses and M04 resolves concepts with.

    A lookup table from M15's topic strings to M02's labels is the hardcoded
    version, and the topics come from student submissions: they are open-ended
    by construction and the table would be wrong within a week.
    """
    shares, seen = topic_shares(_page(_tech(["Dynamic Programming"], 8), _tech(["SQL"], 8)))
    requirements = [
        {"id": "R-1", "text": "dynamic programming"},
        {"id": "R-2", "text": "SQL"},
    ]

    boost = evidence_boost(requirements, shares, seen=seen)

    assert set(boost) == {"R-1", "R-2"}


@pytest.mark.gate
def test_too_few_reports_is_no_evidence_at_all():
    """Four students remembering four different questions is not a distribution.

    This is the difference between reading evidence and reading noise, and the
    failure is silent: a plan reordered by three submissions looks exactly like
    a plan reordered by three hundred.
    """
    shares, seen = topic_shares(_page(_tech(["topic zero"], 1), _tech(["topic one"], 1)))

    assert seen < MIN_EVIDENCE_WEIGHT
    assert evidence_boost([{"id": "R-1", "text": "topic zero"}], shares, seen=seen) == {}


def test_an_evenly_spread_drive_moves_nothing():
    """Normalising by the LARGEST share would make the top topic 1.25 at every
    company, including one whose questions are perfectly evenly spread.

    That is a statement about arithmetic, not about the company. Against the
    FLAT share, an even spread is exactly 1.0 everywhere, which is the truth:
    this drive favours nothing.
    """
    shares, seen = topic_shares(
        _page(*[_tech([t], 3) for t in ("alpha", "bravo", "charlie", "delta")])
    )
    requirements = [
        {"id": f"R-{i}", "text": t} for i, t in enumerate(("alpha", "bravo", "charlie", "delta"))
    ]

    boost = evidence_boost(requirements, shares, seen=seen)

    assert all(value == pytest.approx(1.0, abs=0.01) for value in boost.values()), boost


def test_the_boost_is_bounded_in_both_directions():
    """Nine submissions must not overrule what the company wrote down.

    §6.4's weights are a product of five terms and this is deliberately the
    smallest. A drive where every reported question is about one topic still
    only nudges it.
    """
    shares, seen = topic_shares(_page(_tech(["recursion"], 40), _tech(["sql"], 1)))
    requirements = [
        {"id": "R-1", "text": "recursion"},
        {"id": "R-2", "text": "sql"},
    ]

    boost = evidence_boost(requirements, shares, seen=seen)

    assert boost["R-1"] == MAX_EVIDENCE_BOOST
    assert boost["R-2"] == MIN_EVIDENCE_BOOST


def test_a_requirement_m15_never_mentions_keeps_its_weight_exactly():
    """Absent from `evidence_boost`, not present as 1.0.

    A caller has to be able to tell "no adjustment" from "M15 said nothing",
    and a requirement is not marked down for the silence of a module that may
    simply have no reports for this drive.
    """
    shares, seen = topic_shares(_page(_tech(["recursion"], 9)))

    boost = evidence_boost([{"id": "R-9", "text": "Kubernetes"}], shares, seen=seen)

    assert "R-9" not in boost


def test_a_three_letter_topic_is_a_word_not_a_coincidence():
    """`oop` was M15's joint-top topic for TCS and the requirement labelled
    "Object Oriented Programming (OOP)" got no boost at all.

    The character-length floor that stops `"c"` matching inside `"recursion"`
    also threw away `oop`, `sql`, `aws` and `git` — three-character words that
    are most of what a fresher posting is made of. Word boundaries are what
    separates the two cases, and they need no floor.
    """
    shares, seen = topic_shares(_page(_tech(["oop"], 9)))

    boost = evidence_boost(
        [{"id": "R-1", "text": "Object Oriented Programming (OOP)"}], shares, seen=seen
    )

    assert boost.get("R-1"), "a three-letter topic that IS a word was dropped"


def test_the_best_matching_topic_wins_not_the_first():
    """ "dbms" and "dbms normalisation" can both match one requirement, and
    dictionary iteration order should not decide which."""
    shares, seen = topic_shares(_page(_tech(["dbms"], 12), _tech(["dbms normalisation"], 1)))

    boost = evidence_boost(
        [{"id": "R-1", "text": "DBMS normalisation and indexing"}], shares, seen=seen
    )

    assert boost["R-1"] > 1.0


def test_a_short_topic_does_not_match_by_coincidence():
    """`"c" in "recursion"` is the bug this repository has already fixed twice.

    Once in `drop_redundant` (`"sql" in "nosql"`) and once in the span check
    (`\\bNET\\b` inside `.NET`). Substring matching is useful here and it needs
    the same floor.
    """
    shares, seen = topic_shares(_page(_tech(["C"], 9)))

    boost = evidence_boost([{"id": "R-1", "text": "Recursion"}], shares, seen=seen)

    assert boost == {}


# ---------------------------------------------------------------------------
#  Resolving the company
# ---------------------------------------------------------------------------


class _FakeDeps:
    """A dependency registry that answers for M15 and nothing else."""

    def __init__(self, available: bool = True):
        self._available = available

    def get(self, module_id):
        if module_id != "M15":
            return None
        return type("Dep", (), {"base_url": "http://m15.test"})()

    def is_available(self, module_id):
        return self._available and module_id == "M15"


@pytest.fixture
def m15_answers(monkeypatch):
    """Route M15 paths to a dict, so a test states the upstream as data."""

    def install(routes: dict):
        def fake_get(deps, path, timeout=2.0):
            if deps.get("M15") is None or not deps.is_available("M15"):
                return None
            for prefix, payload in routes.items():
                if path.startswith(prefix):
                    return payload
            return None

        monkeypatch.setattr(m15, "m15_get", fake_get)

    return install


def test_an_exact_canonical_name_wins_over_a_fragment(m15_answers):
    m15_answers(
        {
            "/v1/companies": [
                {"id": "1", "canonical_name": "Tata Elxsi", "aliases": []},
                {"id": "2", "canonical_name": "Tata Consultancy Services", "aliases": ["TCS"]},
            ]
        }
    )

    row = m15.resolve_company(_FakeDeps(), "Tata Consultancy Services")

    assert row["id"] == "2"


def test_an_alias_resolves_the_same_company(m15_answers):
    """§3.2 hard part 5, and the reason M02 asks rather than keeping a table."""
    m15_answers(
        {
            "/v1/companies": [
                {"id": "2", "canonical_name": "Tata Consultancy Services", "aliases": ["TCS"]},
            ]
        }
    )

    assert m15.resolve_company(_FakeDeps(), "TCS")["id"] == "2"


@pytest.mark.gate
def test_several_partial_matches_resolve_to_nothing(m15_answers):
    """Picking the first would put another company's bond on this page."""
    m15_answers(
        {
            "/v1/companies": [
                {"id": "1", "canonical_name": "Tech Mahindra", "aliases": []},
                {"id": "2", "canonical_name": "Techlabs", "aliases": []},
            ]
        }
    )

    assert m15.resolve_company(_FakeDeps(), "Tech") is None


def test_m15_being_down_is_not_an_error(m15_answers):
    m15_answers({"/v1/companies": [{"id": "1", "canonical_name": "X", "aliases": []}]})

    assert m15.resolve_company(_FakeDeps(available=False), "X") is None


# ---------------------------------------------------------------------------
#  The whole brief
# ---------------------------------------------------------------------------


def _brief(m15_answers, page, *, variants=None):
    m15_answers(
        {
            "/v1/companies/c1/variants": variants
            if variants is not None
            else [_variant("Digital", "sde", bond_months=18)],
            "/v1/companies/c1/page": page,
            "/v1/companies": [
                {
                    "id": "c1",
                    "canonical_name": "Cognizant",
                    "aliases": ["CTS"],
                    "report_count": page.get("report_count", 0),
                }
            ],
        }
    )
    return m15.build_brief(
        _FakeDeps(),
        company_name="Cognizant",
        role_title="Digital Engineer",
        archetype="sde_1",
        eligibility={"package_lpa_total": 6.5},
        requirements=[
            {"id": "R-1", "text": "Recursion"},
            {"id": "R-2", "text": "SQL"},
        ],
    )


def test_the_brief_carries_the_alias_the_student_may_know(m15_answers):
    brief = _brief(m15_answers, _page(_tech(["recursion"], 9)))

    assert brief is not None
    assert brief.company_name == "Cognizant"
    assert "CTS" in brief.aliases
    assert brief.drive_variant_name == "Digital"


def test_a_company_with_no_reports_is_a_brief_not_an_absence(m15_answers):
    """M15 knows the company and nobody has reported a drive.

    Different from M15 being down and different from M15 not knowing the
    company: this is a page that invites a submission.
    """
    brief = _brief(m15_answers, _page(sufficiency="none", reports=0))

    assert brief is not None
    assert brief.report_count == 0
    assert brief.evidence_boost == {}
    assert brief.data_sufficiency == "none"


def test_m15s_own_word_for_its_evidence_is_passed_through(m15_answers):
    """`data_sufficiency` is M15's judgement and M02 does not second-guess it.

    A word derived here would eventually disagree with the company page the
    student opens in the next tab, and two screens describing one body of
    evidence differently is worse than either word being imperfect.
    """
    brief = _brief(m15_answers, _page(_tech(["dbms"], 2), sufficiency="thin", reports=2))

    assert brief is not None
    assert brief.data_sufficiency == "thin"


def test_an_unknown_company_is_none(m15_answers):
    m15_answers({"/v1/companies": []})

    assert (
        m15.build_brief(
            _FakeDeps(),
            company_name="Nobody Ltd",
            role_title="Engineer",
            archetype=None,
            eligibility={},
            requirements=[],
        )
        is None
    )
