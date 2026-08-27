import uuid

import pytest
from backend_M02_JD_Parser.app import app
from backend_M02_JD_Parser.router import FALLBACK_CONCEPTS
from fastapi.testclient import TestClient


def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "module": "M02"}


def test_parse_jd(client):
    res = client.post(
        "/v1/jds/parse",
        json={
            "company_name": "Google",
            "role_title": "Engineer",
            "raw_text": "Looking for Dynamic Programming expertise.",
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["company_name"] == "Google"
    assert "Dynamic Programming" in data["required_skills"]

    jd_id = data["id"]
    res_get = client.get(f"/v1/jds/{jd_id}")
    assert res_get.status_code == 200
    assert res_get.json()["id"] == jd_id


def test_parse_marks_offline_provenance(client):
    """With M04 unreachable, every id we hand out says where it came from.

    The scan and the resolution are separately attributed: an id from the
    offline table must not be indistinguishable from one M04 confirmed.
    """
    res = client.post(
        "/v1/jds/parse",
        json={
            "company_name": "Google",
            "role_title": "Engineer",
            "raw_text": "Strong SQL and Dynamic Programming.",
        },
    )
    data = res.json()
    assert data["scanned_against"] == "offline_lexicon"
    assert set(data["concept_source"].values()) == {"offline_fallback"}
    assert data["resolved_concepts"]["SQL"] == "concept:sql_basics"


def test_coverage_is_null_not_zero_when_m04_is_down(client):
    """Rule 2. An outage narrows what we can say; it does not become a verdict.

    The old behaviour returned coverage_score 0.0 with every requirement in
    `missing` and gap_severity 1.0 — a confident statement that the student
    meets none of this JD, produced by a service that was never asked.
    """
    res_parse = client.post(
        "/v1/jds/parse",
        json={
            "company_name": "Google",
            "role_title": "Engineer",
            "raw_text": "Looking for Dynamic Programming expertise.",
        },
    )
    jd_id = res_parse.json()["id"]
    candidate_id = str(uuid.uuid4())

    res_cov = client.get(f"/v1/jds/{jd_id}/coverage/{candidate_id}")
    assert res_cov.status_code == 200
    cov = res_cov.json()

    assert cov["coverage_score"] is None
    assert cov["measured_against"] is None
    assert cov["measured_count"] == 0
    assert "Dynamic Programming" in cov["not_measured"]
    assert cov["states"]["Dynamic Programming"] == "not_measured"
    assert cov["weak"] == []
    assert cov["covered"] == []
    # Severity says "probe this", not "the student failed this".
    assert cov["gap_severity"]["Dynamic Programming"] == 0.6


def test_coverage_names_the_missing_module(client):
    """The degradation is reported, not merely absent. A caller rendering this
    can name M04 instead of showing an empty panel."""
    res_parse = client.post(
        "/v1/jds/parse",
        json={"company_name": "X", "role_title": "Y", "raw_text": "Recursion."},
    )
    jd_id = res_parse.json()["id"]
    cov = client.get(f"/v1/jds/{jd_id}/coverage/{uuid.uuid4()}").json()

    assert cov["degraded"], "an unreachable M04 must be reported, not silently absent"
    assert cov["degraded"][0]["needs_module"] == "M04"
    assert "M04" in cov["degraded"][0]["explanation"]


def test_coverage_scores_only_what_m04_measured(client, m04_mastery):
    """coverage_score is a fraction of what we could check, never of the whole
    JD — so an unmeasured requirement can never depress it."""
    m04_mastery(
        {
            "measured": [
                {"concept_id": "concept:dynamic_programming", "mastery_p": 0.82},
                {"concept_id": "concept:sql_basics", "mastery_p": 0.20},
                # Recursion deliberately absent: M04 is up and has not measured it.
            ]
        }
    )
    res_parse = client.post(
        "/v1/jds/parse",
        json={
            "company_name": "Google",
            "role_title": "Engineer",
            "raw_text": "Dynamic Programming, SQL and Recursion.",
        },
    )
    jd_id = res_parse.json()["id"]
    cov = client.get(f"/v1/jds/{jd_id}/coverage/{uuid.uuid4()}").json()

    assert cov["measured_against"] == "M04"
    assert cov["states"]["Dynamic Programming"] == "strong"
    assert cov["states"]["SQL"] == "weak"
    assert cov["states"]["Recursion"] == "not_measured"
    # 2 measured, 1 of them covered. The unmeasured third is not in the divisor.
    assert cov["measured_count"] == 2
    assert cov["coverage_score"] == 0.5


def test_mastery_none_from_a_live_m04_is_still_not_measured(client, m04_mastery):
    """M04 publishes mastery_p as None for anything it will not claim. That is
    'not measured', not zero — M15 fixed the same bug on its own side."""
    m04_mastery({"measured": [{"concept_id": "concept:recursion", "mastery_p": None}]})
    res_parse = client.post(
        "/v1/jds/parse",
        json={"company_name": "X", "role_title": "Y", "raw_text": "Recursion."},
    )
    jd_id = res_parse.json()["id"]
    cov = client.get(f"/v1/jds/{jd_id}/coverage/{uuid.uuid4()}").json()

    assert cov["states"]["Recursion"] == "not_measured"
    assert cov["coverage_score"] is None


def test_unmappable_requirement_is_reported_not_scored(client, m04_mastery):
    """Spec EC-2.8: a requirement that maps to no concept is stated as
    untestable rather than counted as a gap — and never dropped, because a
    requirement we cannot test is still one the student has to meet."""
    m04_mastery(
        {"measured": [{"concept_id": "concept:recursion", "mastery_p": 0.9}]},
        extra_concepts=[{"name": "Go-getter attitude", "aliases": ["go-getter"]}],
        extra_resolutions={"Go-getter attitude": None},
    )
    res_parse = client.post(
        "/v1/jds/parse",
        json={
            "company_name": "X",
            "role_title": "Y",
            "raw_text": "Recursion, and a go-getter attitude.",
        },
    )
    parsed = res_parse.json()
    assert parsed["unresolved_skills"] == ["Go-getter attitude"]
    assert "Go-getter attitude" not in parsed["resolved_concepts"]

    jd_id = parsed["id"]
    cov = client.get(f"/v1/jds/{jd_id}/coverage/{uuid.uuid4()}").json()
    assert cov["unmeasurable"] == ["Go-getter attitude"]
    assert cov["states"]["Go-getter attitude"] == "unmeasurable"
    assert "Go-getter attitude" not in cov["gap_severity"]
    assert cov["requirement_count"] == 2
    # The untestable one is outside the score entirely, not a zero inside it.
    assert cov["coverage_score"] == 1.0


def test_unknown_jd_is_404(client):
    assert client.get(f"/v1/jds/{uuid.uuid4()}").status_code == 404
    assert client.get(f"/v1/jds/{uuid.uuid4()}/coverage/{uuid.uuid4()}").status_code == 404


def test_deps_names_the_missing_module(client):
    """The degradation is reportable, not merely absent.

    Both upstreams are listed, and neither is required. M01 joined on
    2026-08-27 for FR-2.15: the eligibility comparison needs the student's own
    CGPA, which lives in M01 and nowhere else.
    """
    deps = {d["module_id"]: d for d in client.get("/v1/deps").json()}
    assert set(deps) == {"M04", "M01"}

    assert deps["M04"]["available"] is False
    assert deps["M04"]["base_url"] == "http://127.0.0.1:8104"
    assert deps["M04"]["required"] is False
    assert "M04" in deps["M04"]["on_missing"]

    assert deps["M01"]["required"] is False, "a missing resume must never stop a JD being parsed"
    assert "M01" in deps["M01"]["on_missing"]


def test_deps_reports_a_live_upstream(client, m04_mastery):
    m04_mastery({"measured": []})
    assert client.get("/v1/deps").json()[0]["available"] is True


def test_coverage_carries_the_concept_ids_and_their_provenance(client):
    """A caller has to be able to show WHICH concept a requirement matched and
    WHERE that id came from. Both travel with the gap, not just the label."""
    res_parse = client.post(
        "/v1/jds/parse",
        json={"company_name": "X", "role_title": "Y", "raw_text": "SQL and hashing."},
    )
    jd_id = res_parse.json()["id"]
    cov = client.get(f"/v1/jds/{jd_id}/coverage/{uuid.uuid4()}").json()

    assert cov["resolved_concepts"]["SQL"] == "concept:sql_basics"
    assert cov["concept_source"]["SQL"] == "offline_fallback"
    assert cov["scanned_against"] == "offline_lexicon"


def test_status_reports_the_platform_registry(client):
    """Not this module's opinion of itself - the shared registry's."""
    res = client.get("/status")
    assert res.status_code == 200
    body = res.json()
    assert body["id"] == "M02"
    assert body["implemented"] is True
    assert body["reserved_port"] == 8102


# ---------------------------------------------------------------------------
#  Extraction: what the JD asks for, before the ontology has an opinion
#
#  `test_unmappable_requirement_is_reported_not_scored` above asserts the right
#  thing and used to pass for the wrong reason: it injects a concept INTO M04
#  and then makes M04 fail to resolve it. That internal inconsistency was the
#  only path by which the old extraction could report an unmappable
#  requirement, because a label reached the resolver only by having come from
#  the resolver. A requirement the ontology has never heard of — which is most
#  of a real JD — could not get there.
# ---------------------------------------------------------------------------


def _parse(client, text):
    return client.post(
        "/v1/jds/parse",
        json={"company_name": "X", "role_title": "Y", "raw_text": text},
    ).json()


def test_an_everyday_word_is_not_a_requirement(client, m04_mastery):
    """The worst of the old failures, because it was wrong rather than thin.

    "Solid" is an alias of SOLID Principles. Matched in running prose, a retail
    sales posting that says in as many words that no engineering is required
    yielded a software-design requirement — and a requirement invented from an
    adjective does not stay cosmetic, because M05 selects questions from it.
    """
    m04_mastery(
        {"measured": []}, extra_concepts=[{"name": "SOLID Principles", "aliases": ["solid"]}]
    )
    parsed = _parse(
        client,
        "We want a solid communicator with a solid track record in retail sales. "
        "No engineering required.",
    )

    assert "SOLID Principles" not in parsed["required_skills"]
    assert parsed["required_skills"] == []


def test_requirements_outside_the_ontology_are_reported_not_dropped(client, m04_mastery):
    """A real JD is mostly technologies, and the ontology holds none of them.

    That is fine — but it has to arrive as "we cannot measure these", never as
    a requirement list with everything quietly missing from it.
    """
    m04_mastery({"measured": []})
    parsed = _parse(
        client,
        "Required: Python, Docker, Kubernetes, React.\nRecursion is a plus.",
    )

    for tech in ("Python", "Docker", "Kubernetes", "React"):
        assert tech in parsed["required_skills"], tech
        assert tech in parsed["unresolved_skills"], tech
    # And the one thing the ontology does know still resolves.
    assert "Recursion" in parsed["resolved_concepts"]


def test_unmeasurable_requirements_reach_coverage(client, m04_mastery):
    """The end of the chain: an unmappable requirement is stated on the
    coverage report as untestable rather than scored as a gap or dropped."""
    m04_mastery({"measured": []})
    parsed = _parse(client, "Required: Python, Kubernetes.")
    cov = client.get(f"/v1/jds/{parsed['id']}/coverage/{uuid.uuid4()}").json()

    assert set(cov["unmeasurable"]) == {"Python", "Kubernetes"}
    assert cov["states"]["Python"] == "unmeasurable"


def test_qualifiers_are_stripped_from_the_requirement(client, m04_mastery):
    """ "strong Python" is a claim about Python, not about strength."""
    m04_mastery({"measured": []})
    parsed = _parse(client, "Required: strong Python, hands-on Docker, experience with React.")

    assert parsed["required_skills"] == ["Python", "Docker", "React"]


# ---------------------------------------------------------------------------
#  FR-2.12 — one parse, sixty students
# ---------------------------------------------------------------------------

CACHED_JD = """Software Engineer, Backend

Requirements:
- Strong Python and SQL
- Experience with Docker and Kubernetes
"""


# Not `_parse` — this file already has one, which returns the parsed body. The
# cache tests need the RESPONSE, because 201-vs-200 is the thing being asserted.
def _parse_response(client, text=CACHED_JD, company="Acme", role="Backend Engineer"):
    return client.post(
        "/v1/jds/parse",
        json={"company_name": company, "role_title": role, "raw_text": text},
    )


def test_the_same_jd_is_parsed_once_and_shared(client, m04):
    """§3.2.4: *"The same JD is pasted by 60 students… the parse is shared, the
    gap analysis is per-student."*

    Looked up globally rather than per candidate, which is the whole point: a
    resume belongs to one person, a posting belongs to a company and sixty
    people are preparing for it.
    """
    first = _parse_response(client)
    second = _parse_response(client)

    assert first.status_code == 201
    assert second.status_code == 200, "a second paste created a second row"
    assert first.json()["id"] == second.json()["id"]


def test_whitespace_does_not_defeat_the_cache(client, m04):
    """Sixty pastes of one posting differ by line breaks.

    A copy out of a PDF, out of a portal and out of an email are the same
    document formatted three ways. Hashing them raw makes the cache miss every
    time and the module look like it never had one.
    """
    first = _parse_response(client)
    reflowed = CACHED_JD.replace("\n", "\n  ").replace("- ", "-   ")
    second = _parse_response(client, text=reflowed)

    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]


def test_the_same_text_under_a_different_company_is_a_different_jd(client, m04):
    """Company and role are IN the hash, not just the text.

    Two drives can post identical boilerplate. Returning the first one's label
    to the second student would put the wrong company name on their coverage
    screen — a quiet error on the one field they would never think to check.
    """
    first = _parse_response(client, company="Acme")
    second = _parse_response(client, company="Globex")

    assert second.status_code == 201
    assert second.json()["id"] != first.json()["id"]
    assert second.json()["company_name"] == "Globex"


def test_the_digest_is_returned_so_a_client_can_see_the_sharing(client, m04):
    body = _parse_response(client).json()

    assert len(body["content_sha256"]) == 64


# ---------------------------------------------------------------------------
#  FR-2.2 — a requirement points at the characters it came from
# ---------------------------------------------------------------------------


@pytest.mark.gate
def test_every_requirement_span_resolves_verbatim(client, m04):
    """The platform's one contract above the others.

    M01 calls `SourceSpan` "the atom of traceability — everything downstream
    cites one of these", and asserts exactly this about its claims. M02
    produced a list of strings, so M05 could not cite the JD line a grounded
    question came from and a student could not check a requirement we said
    their posting contained.

    A span that does not resolve is worse than no span: it is a citation to
    the wrong words.
    """
    body = _parse_response(client).json()
    raw = body["raw_text"]

    # Only the ones that came from the POSTING. An archetype backfill has
    # `source="archetype"` and `span=None` on purpose (FR-2.6): nothing in the
    # document said it, so there is nothing to point at, and asserting a span
    # on one would be asserting a citation to words nobody wrote.
    stated = [r for r in body["requirements"] if r["source"] == "jd"]

    assert stated, "no requirements to check"
    for requirement in stated:
        span = requirement["span"]
        assert span is not None, f"{requirement['text']} was located nowhere"
        assert raw[span["start"] : span["end"]] == span["text"], (
            f"{requirement['text']}'s span points at {raw[span['start'] : span['end']]!r}"
        )


def test_requirements_are_in_the_order_the_posting_writes_them(client, m04):
    """Ordered by position, not by whatever order resolution finished in.

    Nothing here ranks requirements by importance — `necessity` and `weight`
    are not built — so document order is the only ordering this module can
    claim without inventing one.
    """
    body = _parse_response(client).json()
    requirements = body["requirements"]
    starts = [r["span"]["start"] for r in requirements if r["span"]]

    assert starts == sorted(starts)
    # Numbered AFTER sorting, so R-1 is the first requirement in the document
    # rather than the first one the resolver happened to finish. Asserted as a
    # property rather than against a fixed count: what this JD yields depends
    # on the extraction rules, and pinning the number here would make an
    # ordering test fail whenever those change.
    assert [r["id"] for r in requirements] == [f"R-{n}" for n in range(1, len(requirements) + 1)]


def test_grounded_and_testable_are_different_questions(client, m04):
    """One boolean was answering both, and the answer was wrong for one of them.

    GROUNDED means a concept id exists, so M04 can supply mastery,
    prerequisites and an adaptive ladder. TESTABLE means a question can be put
    in front of the student at all — including one M05 generates from the
    requirement text, for something the ontology has never heard of.

    M04's ontology is 120 interview concepts and two of them are
    technology-shaped, so a modern stack grounds almost nowhere. Reading "no
    concept id" as "unaskable" reported 72 of 73 requirements untestable on a
    real posting where 72 are perfectly askable.
    """
    body = _parse_response(client).json()

    for requirement in body["requirements"]:
        if requirement["grounded"]:
            assert requirement["concept_ids"], "grounded with no concept id"
            assert requirement["concept_source"] in {"m04", "offline_fallback"}
            assert requirement["testable"], "grounded implies testable"
        else:
            assert requirement["concept_ids"] == []


def test_an_ungrounded_requirement_the_posting_states_is_still_testable(client, m04):
    """Kubernetes is not in M04's ontology and never will be.

    It is still a thing a company asked for, at a real offset, that a verbal
    round can carry — so M05 can generate a question citing the line the
    company wrote. Weaker than the grounded case, which comes with a mastery
    prior and an adaptive ladder, and not the same as nothing.
    """
    body = _parsed(client, "Backend\n\nRequirements:\n- Kubernetes\n- Terraform\n")
    by_text = {r["text"]: r for r in body["requirements"]}

    kubernetes = by_text["Kubernetes"]
    assert kubernetes["grounded"] is False, "the ontology holds concepts, not technologies"
    assert kubernetes["testable"] is True
    assert kubernetes["span"] is not None, "a generated question must cite the posting"
    assert kubernetes["measured_by"], "and a round has to be able to carry it"


def test_something_nothing_can_produce_evidence_about_is_neither(client, m04):
    """§3.2.1 trap 3's third tier survives the distinction.

    "A go-getter attitude" has an empty `measured_by`: no round here produces
    evidence about it, so it is not grounded and not testable, and saying so is
    the point.
    """
    body = _parsed(client, "Backend\n\nRequirements:\n- A go-getter attitude\n- SQL\n")
    by_text = {r["text"]: r for r in body["requirements"]}

    attitude = by_text["go-getter attitude"]
    assert attitude["grounded"] is False
    assert attitude["testable"] is False
    assert attitude["measured_by"] == []


def test_the_flat_list_and_the_requirements_agree(client, m04):
    """`required_skills` is kept because callers read it, exactly as M01 keeps
    `parsed_skills` beside `skill_mentions`. Two lists that disagree is worse
    than one list, so they are asserted to be the same labels."""
    body = _parse_response(client).json()

    assert sorted(body["required_skills"]) == sorted(r["text"] for r in body["requirements"])


# ---------------------------------------------------------------------------
#  FR-2.4 — eligibility, kept instead of thrown away
# ---------------------------------------------------------------------------

ELIGIBLE_JD = """Software Engineer, Backend

Eligibility: minimum 7.5 CGPA, no active backlogs, 2026 batch. 2 year bond.

Requirements:
- Python, SQL, Docker
"""


def test_eligibility_is_extracted_rather_than_discarded(client, m04):
    """`_ELIGIBILITY` recognised these lines and threw them away.

    Keeping them OUT of the requirement list is right — §3.2.2: a CGPA cutoff
    is a hard filter, not an interview topic. Keeping them nowhere was the bug,
    and it made FR-2.15's whole sentence impossible: a module that never stored
    the cutoff cannot tell a student they miss it.
    """
    body = _parse_response(client, text=ELIGIBLE_JD).json()
    eligibility = body["eligibility"]

    assert eligibility["stated"] is True
    assert eligibility["min_cgpa"] == 7.5
    assert eligibility["max_backlogs_active"] == 0
    assert eligibility["year_of_passing"] == [2026]
    assert eligibility["bond_months"] == 24


def test_eligibility_never_becomes_a_requirement(client, m04):
    """The half that was already right, asserted so it stays right.

    A CGPA cutoff filed under skills is a number the ontology can never resolve
    sitting in the unmapped queue for ever — and a coverage plan allocating
    interview questions to "7.5 CGPA".
    """
    body = _parse_response(client, text=ELIGIBLE_JD).json()

    for label in body["required_skills"]:
        assert "cgpa" not in label.lower()
        assert "backlog" not in label.lower()
        assert "batch" not in label.lower()


def test_eligibility_spans_point_at_the_words_they_came_from(client, m04):
    """A student told they miss a cutoff is being told something with real
    consequences, and the only honest version points at the line."""
    body = _parse_response(client, text=ELIGIBLE_JD).json()
    raw = body["raw_text"]

    spans = body["eligibility"]["raw_spans"]
    assert spans
    for span in spans:
        assert raw[span["start"] : span["end"]] == span["text"]


def test_a_posting_that_states_no_bar_says_so_rather_than_zero(client, m04):
    """`stated: false`, not `min_cgpa: 0`.

    "This JD does not state a cutoff" and "this JD has no cutoff" are different
    facts. A permissive default would tell a student they are eligible for a
    drive nobody has checked them against, which is the one wrong answer this
    field exists to prevent.
    """
    body = _parse_response(
        client, text="Backend Engineer.\n\nRequirements:\n- Python, SQL\n"
    ).json()
    eligibility = body["eligibility"]

    assert eligibility["stated"] is False
    assert eligibility["min_cgpa"] is None
    assert eligibility["max_backlogs_active"] is None


def test_a_percentage_cutoff_is_not_read_as_a_cgpa(client, m04):
    """ "70% throughout academics" is a real bar and it is not a CGPA.

    Storing 70.0 in `min_cgpa` would tell every student on a ten-point scale
    that they are ineligible.
    """
    body = _parse_response(client, text="Requires 70% throughout academics.\n").json()

    assert body["eligibility"]["min_cgpa"] is None


# ---------------------------------------------------------------------------
#  A bulleted requirement is a requirement, however long it is
# ---------------------------------------------------------------------------


def test_a_requirement_written_as_a_sentence_is_not_lost(client, m04):
    """`- Experience with Docker and Kubernetes` used to extract NOTHING.

    Six tokens, no delimiter, so the line-length rule inherited from M01 read
    it as prose. In a resume's SKILLS block that rule is right; a job
    description writes its requirements as sentences on purpose, and two real
    requirements were silently missing from every coverage plan built on that
    posting.
    """
    body = _parse_response(
        client,
        text="Requirements:\n- Strong Python and SQL\n- Experience with Docker and Kubernetes\n",
    ).json()

    assert "Docker" in body["required_skills"]
    assert "Kubernetes" in body["required_skills"]


def test_a_prose_bullet_still_yields_nothing(client, m04):
    """The other side of the line, and the reason the rule existed.

    The word cap moved from the LINE to the LABEL, where `_acceptable` was
    already applying it. A bullet of genuine prose survives `_clean` as one
    long label and is refused — so recovering real requirements did not buy
    invented ones.
    """
    body = _parse_response(
        client,
        text=(
            "Requirements:\n"
            "- We are looking for someone who thrives in ambiguity and enjoys mentoring juniors\n"
        ),
    ).json()

    # From the POSTING. The archetype backfills this to eight requirements
    # because it yielded fewer than five (FR-2.6) — right behaviour, and a
    # different question from the one this test asks.
    assert [r for r in body["requirements"] if r["source"] == "jd"] == []


def test_a_numbered_list_is_a_list(client, m04):
    """M01 §3.2.2: bullet detection is "a line-classification problem, not a
    character match". `1.` and `a)` are markers too."""
    body = _parse_response(
        client, text="Requirements:\n1. Familiarity with Kubernetes\n2. SQL\n"
    ).json()

    assert set(body["required_skills"]) >= {"Kubernetes", "SQL"}


# ---------------------------------------------------------------------------
#  Necessity and weight (FR-2.2, §6.4)
# ---------------------------------------------------------------------------


NECESSITY_JD = """Software Engineer, Backend

Requirements:
- Strong Python and SQL
- Good knowledge of DSA, OOPs, DBMS

Nice to have:
- Familiarity with Kubernetes
- Exposure to Kafka
"""


def _parsed(client, text: str) -> dict:
    """Parse and read the body, failing on the status rather than on a TypeError.

    `_parse_response` returns the `Response` on purpose — the caching tests
    assert on 200 vs 201, which is the whole thing they are about. These tests
    only care about the body, and want a readable failure when the parse itself
    is what broke.
    """
    res = _parse_response(client, text)
    assert res.status_code in (200, 201), res.text
    return res.json()


def _by_text(requirements: list[dict], label: str) -> dict:
    for requirement in requirements:
        if requirement["text"] == label:
            return requirement
    raise AssertionError(f"{label!r} not extracted; got {[r['text'] for r in requirements]}")


def test_the_trap_in_the_spec_is_no_longer_flattened(client, m04):
    """§3.2.1 trap 2, verbatim: these two are not equal, and a flat list made them equal.

    The consequence is not cosmetic. FR-2.8 allocates the interview's question
    budget across this list, so a bonus nice-to-have was taking question slots
    from a stated must — the student gets asked about Kubernetes instead of
    about the thing that will actually decide the interview.
    """
    body = _parsed(client, NECESSITY_JD)
    requirements = body["requirements"]

    assert _by_text(requirements, "DSA")["necessity"] == "must"
    assert _by_text(requirements, "Kubernetes")["necessity"] == "could"

    # And the weights follow, which is the half that downstream reads.
    assert _by_text(requirements, "DSA")["weight"] > _by_text(requirements, "Kubernetes")["weight"]


def test_a_heading_governs_the_lines_under_it(client, m04):
    """ "Familiarity with Kubernetes" is a `could` because of where it sits.

    Its own line carries no "bonus" or "plus" — only the heading two lines up
    does. Reading the line alone would file it as a neutral `should` and give it
    twice the weight the posting intends.
    """
    body = _parsed(client, NECESSITY_JD)

    assert _by_text(body["requirements"], "Kafka")["necessity"] == "could"


def test_silence_is_should_and_not_must(client, m04):
    """The default has to be the honest one.

    A posting that names a technology under a neutral heading with no modal word
    has not said the requirement is firm. Defaulting to `must` would put maximum
    weight on every unqualified line — a flat list wearing a necessity field.
    """
    body = _parsed(client, "Backend Engineer\n\nQualifications:\n- Python\n- SQL\n- Docker\n")

    assert {r["necessity"] for r in body["requirements"]} == {"should"}


def test_weights_are_a_distribution(client, m04):
    """They sum to 1, because a question budget is divided and not scored.

    A weight that is an independent 0-1 score per requirement cannot be split
    into "three questions here, one there" without renormalising at every call
    site, and one of those call sites will forget.
    """
    body = _parsed(client, NECESSITY_JD)
    weights = [r["weight"] for r in body["requirements"]]

    assert weights, "no requirements extracted"
    assert all(0.0 <= weight <= 1.0 for weight in weights)
    assert abs(sum(weights) - 1.0) < 0.01


def test_repetition_counts_as_emphasis(client, m04):
    """A posting that says "Python" four times is leaning on it.

    §6.4 is explicit that repetition is emphasis. It is also the signal that
    survives a posting with no headings and no modal language at all, which is
    most of them.
    """
    body = _parsed(
        client,
        "Data Engineer\n\nWe use Python across the stack, and Python is the language\n"
        "every service is written in.\n\nSkills:\n- Python\n- SQL\n",
    )

    assert _by_text(body["requirements"], "Python")["mentions"] == 3
    assert _by_text(body["requirements"], "SQL")["mentions"] == 1

    # Same necessity, same heading, adjacent positions: repetition is the only
    # thing separating them, and it has to actually move the number.
    assert (
        _by_text(body["requirements"], "Python")["weight"]
        > _by_text(body["requirements"], "SQL")["weight"]
    )

    # Same necessity, same heading, same-ish position: repetition is the only
    # thing separating them, and it has to actually move the number.
    assert (
        _by_text(body["requirements"], "Python")["weight"]
        > _by_text(body["requirements"], "SQL")["weight"]
    )


# ---------------------------------------------------------------------------
#  Disjunctions (FR-2.3)
# ---------------------------------------------------------------------------


DISJUNCTION_JD = """Backend Engineer

Requirements:
- Experience with Docker or Kubernetes
- SQL
"""

SLASH_JD = """Backend Engineer

Requirements:
- Java/Python/C++
- CI/CD pipelines
- SQL
"""


def _group_over(body: dict, *labels: str) -> dict:
    """The group whose members are exactly `labels`, by requirement id."""
    by_id = {r["id"]: r["text"] for r in body["requirements"]}
    wanted = set(labels)
    for group in body["requirement_groups"]:
        if {by_id.get(rid) for rid in group["requirement_ids"]} == wanted:
            return group
    raise AssertionError(
        f"no group over {sorted(wanted)}; groups="
        + repr([[by_id.get(r) for r in g["requirement_ids"]] for g in body["requirement_groups"]])
    )


def test_or_is_one_requirement_with_two_answers(client, m04):
    """§3.2.1: *"'Java/Python/C++' is a disjunction, not three requirements."*

    What actually happened was worse than the spec's version. One bullet,
    `- Experience with Docker or Kubernetes`, produced THREE requirements: both
    alternatives and a phantom "Docker or Kubernetes" compound that no ontology
    will ever resolve — so it sat in the unmapped queue permanently, and once
    weights landed it was drawing a full requirement's worth of them.
    """
    body = _parsed(client, DISJUNCTION_JD)
    texts = [r["text"] for r in body["requirements"]]
    assert "Docker or Kubernetes" not in texts, "the phantom compound is still a requirement"
    assert "Docker" in texts and "Kubernetes" in texts

    group = _group_over(body, "Docker", "Kubernetes")
    assert group["satisfaction"] == "any_of"
    # The group quotes the words it was read from, so the screen can point at
    # the line rather than asserting a choice the student cannot check.
    assert "Docker or Kubernetes" in group["text"]


def test_alternatives_share_one_requirements_weight(client, m04):
    """Two ways to satisfy one demand is still one demand.

    Leaving both members at full weight makes a two-way choice count double a
    plain requirement — the same distortion the phantom compound caused,
    arriving by a different route.
    """
    body = _parsed(client, DISJUNCTION_JD)
    by_text = {r["text"]: r for r in body["requirements"]}

    docker = by_text["Docker"]["weight"]
    kubernetes = by_text["Kubernetes"]["weight"]
    sql = by_text["SQL"]["weight"]

    assert docker == pytest.approx(kubernetes)
    # Same necessity and heading, so the pair together should weigh about what
    # the single requirement does — not twice it.
    assert docker + kubernetes == pytest.approx(sql, rel=0.35)
    assert sum(r["weight"] for r in body["requirements"]) == pytest.approx(1.0, abs=0.01)


def test_a_slash_splits_only_when_the_ontology_knows_the_parts(client, m04):
    """`Java/Python/C++` is three; `CI/CD` is one; nothing in the text says which.

    `_DELIMITERS` refuses to split on `/` because a wrong split fabricates a
    skill, and "CI/CD" and "TCP/IP" are single names far more often than
    "React/Angular" is two. So the question is asked rather than guessed at:
    the parts are probed, and the compound splits only where at least two of
    them are things M04 has heard of.
    """
    m04.up(
        concepts=list(FALLBACK_CONCEPTS),
        resolved={
            "Java": "concept:java",
            "Python": "concept:python",
            "C++": "concept:cpp",
            "SQL": "concept:sql_basics",
        },
    )
    body = _parsed(client, SLASH_JD)
    texts = [r["text"] for r in body["requirements"]]

    assert "Java/Python/C++" not in texts
    assert {"Java", "Python", "C++"} <= set(texts)
    assert _group_over(body, "Java", "Python", "C++")["satisfaction"] == "any_of"

    # And the one that is a single name stays a single name.
    assert "CI/CD pipelines" in texts
    assert "CI" not in texts and "CD" not in texts


def test_with_m04_down_a_slash_compound_stays_whole(client, m04):
    """Rule 2: a missing dependency narrows scope, it does not fabricate.

    Nothing offline can tell "Java/Python/C++" from "CI/CD", so neither splits.
    The requirement is still reported, still weighted, and still unmapped —
    which is the honest state, and visibly different from three confident
    requirements the ontology never confirmed.
    """
    body = _parsed(client, SLASH_JD)
    texts = [r["text"] for r in body["requirements"]]

    assert "Java/Python/C++" in texts
    assert body["requirement_groups"] == []
    assert "Java/Python/C++" in body["unresolved_skills"]


def test_a_one_letter_concept_does_not_delete_the_rest_of_the_posting(client, m04):
    """`drop_redundant` compared normalised aliases with a raw substring test.

    `normalise_alias` strips punctuation, so "C++" becomes the single letter
    `c` — and `"c" in "ci cd pipelines"` is True. Resolving C++ removed every
    unresolved requirement containing the letter, which is most of a posting.
    "R" and "Go" are worse.

    Nothing caught it because nothing short had ever resolved: the offline
    table holds five multi-word concepts. Splitting "Java/Python/C++" is what
    first put a one-letter alias into `resolved`, and "CI/CD pipelines"
    disappeared from the response with no error anywhere.
    """
    m04.up(
        concepts=list(FALLBACK_CONCEPTS),
        resolved={"C++": "concept:cpp", "Java": "concept:java", "Python": "concept:python"},
    )
    body = _parsed(
        client,
        "Backend Engineer\n\nRequirements:\n- Java/Python/C++\n- CI/CD pipelines\n"
        "- Container orchestration\n",
    )
    texts = [r["text"] for r in body["requirements"]]

    assert "CI/CD pipelines" in texts
    assert "Container orchestration" in texts


def test_a_shorter_name_inside_a_longer_one_is_a_different_technology(client, m04):
    """NoSQL is not SQL, and whole-word containment is what says so.

    The same substring test that deleted "CI/CD pipelines" would drop "NoSQL"
    the moment "SQL" resolved — collapsing two genuinely different requirements
    into one, and telling a student they are covered on a database they have
    never used.
    """
    m04.up(concepts=list(FALLBACK_CONCEPTS), resolved={"SQL": "concept:sql_basics"})
    body = _parsed(client, "Data Engineer\n\nRequirements:\n- SQL\n- NoSQL\n")
    texts = [r["text"] for r in body["requirements"]]

    assert "SQL" in texts and "NoSQL" in texts


def test_a_choice_is_met_by_one_of_its_answers(client, m04_mastery):
    """§3.2.1's "33% qualified", arriving at the one number the student reads.

    The posting says "Dynamic Programming or Recursion". This student is strong
    on Dynamic Programming and weak on Recursion. Before groups existed both
    were scored as separate demands, so the alternative they did not take
    counted against them: 1 covered out of 2 measured, a coverage score of 0.5
    for a requirement they fully meet.

    Recursion is not a gap here, and it is not silence either —
    `met_by_alternative` names the answer that satisfied the same requirement,
    so "why is nothing being said about Recursion" has an answer on screen.
    """
    m04_mastery(
        {
            "measured": [
                {"concept_id": "concept:dynamic_programming", "mastery_p": 0.85},
                {"concept_id": "concept:recursion", "mastery_p": 0.15},
                {"concept_id": "concept:sql_basics", "mastery_p": 0.90},
            ]
        }
    )
    res = client.post(
        "/v1/jds/parse",
        json={
            "company_name": "Acme",
            "role_title": "Engineer",
            "raw_text": ("Engineer\n\nRequirements:\n- Dynamic Programming or Recursion\n- SQL\n"),
        },
    )
    assert res.status_code == 201, res.text
    jd_id = res.json()["id"]

    cov = client.get(f"/v1/jds/{jd_id}/coverage/{uuid.uuid4()}").json()

    assert cov["states"]["Dynamic Programming"] == "strong"
    assert cov["states"]["Recursion"] == "met_by_alternative"
    assert cov["met_by_alternative"]["Recursion"] == "Dynamic Programming"

    # The alternative not taken is not a gap, and does not sit in the divisor.
    assert "Recursion" not in cov["weak"]
    assert "Recursion" not in cov["gap_severity"]
    assert cov["measured_count"] == 2
    assert cov["coverage_score"] == 1.0


def test_a_choice_nobody_answered_is_still_a_gap(client, m04_mastery):
    """The group must not become a way to hide a miss.

    Weak on both alternatives is weak on the requirement. One of them carries
    that — the better-placed one — so the gap is reported once rather than
    twice, which is the only thing the group changes here.
    """
    m04_mastery(
        {
            "measured": [
                {"concept_id": "concept:dynamic_programming", "mastery_p": 0.20},
                {"concept_id": "concept:recursion", "mastery_p": 0.10},
            ]
        }
    )
    res = client.post(
        "/v1/jds/parse",
        json={
            "company_name": "Acme",
            "role_title": "Engineer",
            "raw_text": "Engineer\n\nRequirements:\n- Dynamic Programming or Recursion\n",
        },
    )
    jd_id = res.json()["id"]
    cov = client.get(f"/v1/jds/{jd_id}/coverage/{uuid.uuid4()}").json()

    # The stronger of two weak answers represents the group, and is still weak.
    assert cov["weak"] == ["Dynamic Programming"]
    assert cov["states"]["Recursion"] == "met_by_alternative"
    assert cov["coverage_score"] == 0.0


def test_a_requirement_inside_an_over_long_line_is_not_lost(client, m04):
    """`- Strong programming skills in Java or Python` yielded NOTHING.

    Found by parsing an ordinary campus posting and reading the output: the
    single most important line on it was absent. `_clean` leaves six words,
    `_acceptable` refuses that for the word cap, and `extract_surface_forms`
    bailed on the fragment before ever trying its conjunction parts — so both
    alternatives went with it.

    Same shape as the bullet-length bug: a cap applied one level too high
    throws away the thing it was meant to filter around.
    """
    body = _parsed(
        client,
        "Backend Engineer\n\nRequirements:\n- Strong programming skills in Java or Python\n",
    )
    texts = [r["text"] for r in body["requirements"]]

    assert "Java" in texts and "Python" in texts
    # And it is a choice, not two demands.
    assert body["requirement_groups"][0]["requirement_ids"] == ["R-1", "R-2"]


def test_rescuing_a_requirement_does_not_invent_one(client, m04):
    """The first attempt at the fix above created a skill called
    "enjoys mentoring juniors".

    Splitting an over-long fragment on "and" cuts prose into pieces that are
    short enough to pass the cap. Recovering a real requirement is not worth
    inventing one — a missed requirement shows up as a thin list, an invented
    one becomes an interview question about something nobody asked for.

    So a part rescued from an over-long fragment has to look like a NAME.
    Postings capitalise their technologies; prose about attitude does not.
    """
    body = _parsed(
        client,
        "Backend Engineer\n\nRequirements:\n"
        "- We are looking for someone who thrives in ambiguity and enjoys mentoring juniors\n",
    )

    # From the POSTING. The archetype backfills this to eight requirements
    # because it yielded fewer than five (FR-2.6) — right behaviour, and a
    # different question from the one this test asks.
    assert [r for r in body["requirements"] if r["source"] == "jd"] == []


def test_familiarity_describes_depth_not_optionality(client, m04):
    """ "Familiarity with Git" under Requirements is required, shallowly.

    `_COULD` matched "familiarity with", so a stated requirement landed in the
    nice-to-have band and earned a third of the weight — a third of the
    interview time — that the posting asked for. The words describe how deeply
    the student needs to know it, not whether they need to.

    The heading is what decides, and under "Nice to have:" the same words are
    a `could`, which is the case §3.2.1 is actually about.
    """
    body = _parsed(
        client,
        "Backend Engineer\n\nRequirements:\n- Familiarity with Git\n\n"
        "Nice to have:\n- Familiarity with Docker\n",
    )
    by_text = {r["text"]: r for r in body["requirements"]}

    assert by_text["Git"]["necessity"] == "must"
    assert by_text["Docker"]["necessity"] == "could"
    assert by_text["Git"]["weight"] > by_text["Docker"]["weight"]


# ---------------------------------------------------------------------------
#  The coverage plan (FR-2.8, §6.5)
# ---------------------------------------------------------------------------


UNTESTABLE_JD = """Backend Engineer

Requirements:
- SQL
- A go-getter attitude
- Passionate about technology
- Self-starter mindset
- Positive attitude
"""

PLAN_DISJUNCTION_JD = """Backend

Requirements:
- Dynamic Programming or Recursion
- SQL
"""

PLAN_JD = """Backend Engineer

Requirements:
- Dynamic Programming
- SQL
- Recursion

Nice to have:
- Hashing
"""


def _plan(client, jd_id, candidate_id, minutes=45):
    res = client.post(f"/v1/jds/{jd_id}/plan/{candidate_id}", json={"minutes": minutes})
    assert res.status_code == 200, res.text
    return res.json()


def _parse_for_plan(client):
    res = client.post(
        "/v1/jds/parse",
        json={"company_name": "Acme", "role_title": "Backend", "raw_text": PLAN_JD},
    )
    assert res.status_code in (200, 201), res.text
    return res.json()["id"]


def test_every_measurable_must_have_gets_at_least_one_question(client, m04_mastery):
    """FR-2.9, and it is a hard constraint rather than a tendency.

    A plan that skips a stated must-have because the optimiser found better
    value elsewhere has failed at the one thing the student asked it for.
    """
    m04_mastery({"measured": [{"concept_id": "concept:dynamic_programming", "mastery_p": 0.95}]})
    jd_id = _parse_for_plan(client)

    plan = _plan(client, jd_id, uuid.uuid4())
    budget = {a["requirement_text"]: a["question_budget"] for a in plan["allocations"]}

    # Strong AND a must-have: still gets a question, because the posting leans
    # on it and mastery is a posterior, not a certificate.
    assert budget.get("Dynamic Programming", 0) >= 1
    assert budget.get("SQL", 0) >= 1
    assert budget.get("Recursion", 0) >= 1
    assert plan["uncovered"] == []


def test_the_budget_does_not_collapse_onto_the_worst_gap(client, m04_mastery):
    """§6.5: *"without it the optimiser dumps the entire budget on the single
    worst gap, producing a mock that is 9 DBMS questions."*

    The log utility is what stops that, and the cap is the backstop. A linear
    objective under one constraint always puts everything on the best ratio.
    """
    m04_mastery(
        {
            "measured": [
                {"concept_id": "concept:sql_basics", "mastery_p": 0.05},
                {"concept_id": "concept:dynamic_programming", "mastery_p": 0.80},
                {"concept_id": "concept:recursion", "mastery_p": 0.75},
            ]
        }
    )
    jd_id = _parse_for_plan(client)

    # 90 minutes. Since `measured_by` landed, DP, Recursion and Hashing are
    # CODING requirements at twelve minutes a question and only SQL is a
    # three-and-a-half-minute verbal one — so 30 minutes now buys the must-have
    # floor and nothing else, and there is no room left to differentiate in.
    # That is the correct economics, not a regression: a half-hour session
    # cannot hold eight DSA questions and never could.
    plan = _plan(client, jd_id, uuid.uuid4(), minutes=90)
    budget = {a["requirement_text"]: a["question_budget"] for a in plan["allocations"]}

    assert budget["SQL"] <= 4, "the per-requirement cap did not hold"
    # The worst gap leads, but it does not take everything.
    assert budget["SQL"] > budget["Dynamic Programming"]
    assert len([a for a in plan["allocations"] if a["question_budget"] > 0]) >= 3


def test_two_students_on_one_posting_get_different_plans(client, m04_mastery):
    """§10's differentiation test, and §3.2.1's trap 4.

    *"'Every SDE mock = 4 DSA + 2 OOP + 2 HR' is not planning, it is a
    constant. The entire value is that the plan changes based on THIS student's
    gaps against THIS JD."* If two students with opposite Skill Graphs get the
    same allocation, the planner is a template and the module has failed at the
    thing it is named after.
    """
    fake = m04_mastery(
        {
            "measured": [
                {"concept_id": "concept:sql_basics", "mastery_p": 0.10},
                {"concept_id": "concept:dynamic_programming", "mastery_p": 0.90},
                {"concept_id": "concept:recursion", "mastery_p": 0.85},
            ]
        }
    )
    jd_id = _parse_for_plan(client)
    plan_a = _plan(client, jd_id, uuid.uuid4(), minutes=90)

    fake.up(
        mastery={
            "measured": [
                {"concept_id": "concept:sql_basics", "mastery_p": 0.90},
                {"concept_id": "concept:dynamic_programming", "mastery_p": 0.10},
                {"concept_id": "concept:recursion", "mastery_p": 0.15},
            ]
        }
    )
    plan_b = _plan(client, jd_id, uuid.uuid4(), minutes=90)

    a = {x["requirement_text"]: x["question_budget"] for x in plan_a["allocations"]}
    b = {x["requirement_text"]: x["question_budget"] for x in plan_b["allocations"]}

    assert a != b, "two opposite students got the same plan - this is a template"
    # Directional, not merely different: the student weak on SQL is asked about
    # SQL more than the one who is strong on it, and the reverse for DP.
    assert a["SQL"] > b["SQL"]
    assert b["Dynamic Programming"] > a["Dynamic Programming"]


def test_a_session_too_short_says_so_instead_of_dropping_a_must(client, m04_mastery):
    """EC-2.11: `uncovered` populated AND an explicit suggestion.

    Silently fitting what fits is the failure mode that looks like success -
    the student reads a tidy plan and never learns the posting asked for more.
    """
    m04_mastery({"measured": []})
    jd_id = _parse_for_plan(client)

    plan = _plan(client, jd_id, uuid.uuid4(), minutes=4)

    assert plan["uncovered"], "a 4-minute session covered every must-have"
    assert plan["suggestion"]
    assert "more minute" in plan["suggestion"]


def test_an_alternative_already_met_earns_no_questions(client, m04_mastery):
    """FR-2.3 reaching the plan.

    The posting said "Dynamic Programming or Recursion" and the student
    answered with Dynamic Programming. Spending interview time on Recursion is
    asking about something this job does not require.
    """
    m04_mastery(
        {
            "measured": [
                {"concept_id": "concept:dynamic_programming", "mastery_p": 0.95},
                {"concept_id": "concept:recursion", "mastery_p": 0.05},
            ]
        }
    )
    res = client.post(
        "/v1/jds/parse",
        json={
            "company_name": "Acme",
            "role_title": "Backend",
            "raw_text": PLAN_DISJUNCTION_JD,
        },
    )
    jd_id = res.json()["id"]

    plan = _plan(client, jd_id, uuid.uuid4())
    budget = {a["requirement_text"]: a["question_budget"] for a in plan["allocations"]}

    assert "Recursion" not in budget
    assert budget.get("Dynamic Programming", 0) >= 1


def test_the_plan_never_overspends_the_session(client, m04_mastery):
    """The constraint that makes it a plan rather than a wish list."""
    m04_mastery({"measured": []})
    jd_id = _parse_for_plan(client)

    for minutes in (5, 15, 30, 45, 60, 120):
        plan = _plan(client, jd_id, uuid.uuid4(), minutes=minutes)
        assert plan["allocated_minutes"] <= minutes, f"overspent at {minutes} minutes"


@pytest.mark.gate
def test_a_plan_is_a_gap_analysis_and_is_gated_like_one(client, m04_mastery, session):
    """`candidate_id` is in the PATH so `enforce_access` sees it.

    In the body it would have been unauthenticated by omission - the router
    dependency keys on the path parameter, and a plan is a gap analysis with a
    schedule attached.
    """
    m04_mastery({"measured": []})
    jd_id = _parse_for_plan(client)

    stranger = TestClient(app, headers={"X-Role": "student", "X-Candidate-Id": str(uuid.uuid4())})
    res = stranger.post(f"/v1/jds/{jd_id}/plan/{uuid.uuid4()}", json={"minutes": 45})

    assert res.status_code == 403


def test_a_session_longer_than_the_posting_needs_says_so(client, m04_mastery):
    """The other end of EC-2.11, and the honest half of trap 4.

    Three coding requirements at twelve minutes and one verbal at three and a
    half, four questions each, is about 158 minutes. Past that the plan
    genuinely IS the same for every student — everything is capped and there is
    nothing left to differentiate WITH.

    §3.2.1 says a plan that is the same for everybody is a template. It is not
    a bug here, but it looks exactly like one from the outside, so the plan
    reports it rather than presenting a saturated allocation as if it were
    tailored.
    """
    m04_mastery({"measured": []})
    jd_id = _parse_for_plan(client)

    plan = _plan(client, jd_id, uuid.uuid4(), minutes=240)

    assert plan["saturated"] is True
    assert plan["suggestion"]
    assert "four-question cap" in plan["suggestion"]
    # And not confused with the too-short case, which is the other suggestion.
    assert plan["uncovered"] == []


def test_a_normal_session_is_not_saturated(client, m04_mastery):
    """The flag has to be off in the case it is not about, or it is noise."""
    m04_mastery({"measured": []})
    jd_id = _parse_for_plan(client)

    assert _plan(client, jd_id, uuid.uuid4(), minutes=90)["saturated"] is False


def test_saturation_blames_the_ontology_when_the_ontology_is_the_cause(client, m04_mastery):
    """ "This posting only has enough in it for 14 minutes" was the wrong sentence.

    Found by running the module and reading the plan: one requirement testable,
    four questions, and a message saying the POSTING was small. It was not.

    The fixture changed on 2026-08-27 when `grounded` and `testable` were
    separated. It used to be five technologies, four of which the ontology does
    not hold — and those are ungrounded, not untestable, because M05 can
    generate a question about Kubernetes from the line the company wrote. The
    only genuinely untestable requirements are the ones with an empty
    `measured_by`: attitudes, which no round produces evidence about.
    """
    m04_mastery({"measured": []})
    res = client.post(
        "/v1/jds/parse",
        json={
            "company_name": "Acme",
            "role_title": "Backend",
            "raw_text": UNTESTABLE_JD,
        },
    )
    jd_id = res.json()["id"]

    plan = _plan(client, jd_id, uuid.uuid4(), minutes=90)

    assert plan["saturated"] is True
    assert len(plan["unmeasurable"]) > len(plan["allocations"])
    assert "can be tested at all" in plan["suggestion"]
    assert "This posting only has enough" not in plan["suggestion"]


# ---------------------------------------------------------------------------
#  Eligibility, the rest of it (FR-2.4)
# ---------------------------------------------------------------------------


FULL_ELIGIBILITY_JD = """Company: XYZ Technologies
Role: Software Engineer Trainee
Package: 6.5 LPA (4.5 fixed + 2 variable)
Eligibility: 7.5 CGPA, no active backlogs, CSE/IT/ECE
Location: Bangalore / Chennai
No backlogs in the entire academic career.
Bond: 18 months
Batch of 2026
"""


def test_the_whole_eligibility_block_is_read(client, m04):
    """§5's `EligibilityCriteria`, complete.

    This is the module's own sample JD, the one the paste screen offers. Four
    of its fields were being read and five were being dropped — including the
    package, which is the number a student decides on.
    """
    body = _parsed(client, FULL_ELIGIBILITY_JD)
    eligibility = body["eligibility"]

    assert eligibility["min_cgpa"] == 7.5
    assert eligibility["max_backlogs_active"] == 0
    assert eligibility["max_backlogs_history"] == 0
    assert eligibility["allowed_branches"] == ["CSE", "IT", "ECE"]
    assert eligibility["location"] == ["Bangalore", "Chennai"]
    assert eligibility["package_lpa_total"] == 6.5
    assert eligibility["package_lpa_fixed"] == 4.5
    assert eligibility["year_of_passing"] == [2026]
    assert eligibility["bond_months"] == 18


def test_a_bond_written_with_a_colon_is_still_a_bond(client, m04):
    """ "Bond: 18 months" read as NO BOND.

    The pattern required a space where a posting writes a colon — and a colon
    is how a posting labels a field. On this module's own sample JD. The
    difference is a student signing an eighteen-month commitment knowingly
    versus finding out at the offer letter.
    """
    for text, months in (
        ("Bond: 18 months", 18),
        ("Bond: 2 years", 24),
        ("2 year bond", 24),
        ("Service agreement of 24 months", 24),
    ):
        body = _parsed(client, f"Engineer\n\nRequirements:\n- SQL\n\n{text}\n")
        assert body["eligibility"]["bond_months"] == months, text


BOTH_BACKLOG_BARS_JD = """Engineer

Requirements:
- SQL

No backlogs in the entire academic career.
"""

ACTIVE_BACKLOGS_ONLY_JD = """Engineer

Requirements:
- SQL

No active backlogs.
"""


def test_history_backlogs_are_a_stricter_bar_than_active_ones(client, m04):
    """A student who cleared an old arrear passes one bar and fails the other.

    Two fields because they are two rules — but "no backlogs in the entire
    academic career" is the STRICTER of the two and implies the other, so both
    are set. A posting that wants no backlogs ever certainly does not want
    current ones.

    Where they come apart is the common phrasing: "no ACTIVE backlogs" sets
    only `max_backlogs_active`, and a student with a cleared arrear passes.
    """
    both = _parsed(client, BOTH_BACKLOG_BARS_JD)["eligibility"]

    assert both["max_backlogs_history"] == 0
    assert both["max_backlogs_active"] == 0, "the stricter bar implies the looser one"

    active_only = _parsed(client, ACTIVE_BACKLOGS_ONLY_JD)["eligibility"]

    assert active_only["max_backlogs_active"] == 0
    assert active_only["max_backlogs_history"] is None, "a cleared arrear is still allowed here"


def test_no_branches_named_is_empty_not_all_branches(client, m04):
    """Empty means we found no restriction, NOT that we verified there is none.

    The distinction matters at the point where a screen wants to say "you are
    eligible": it can say "no branch restriction stated" and it cannot say
    "your branch is allowed".
    """
    body = _parsed(client, "Engineer\n\nRequirements:\n- SQL\n\nMinimum 7.0 CGPA.\n")

    assert body["eligibility"]["allowed_branches"] == []
    assert body["eligibility"]["stated"] is True, "a CGPA cutoff is still a stated criterion"


# ---------------------------------------------------------------------------
#  FR-2.16 / AC-2.5 — the parse is timed
# ---------------------------------------------------------------------------


def test_a_parse_records_how_long_it_took(client, m04):
    """§11 budgets a cold parse at 8 s and it was never timed.

    Unknown is worse than missed: a missed budget is a bug report, an unknown
    one is a blank space where everybody assumes it is fine.
    """
    body = _parsed(client, CACHED_JD)

    assert body["parse_ms"] >= 0
    assert body["stage_ms"], "no stage breakdown"
    assert "normalise" in body["stage_ms"]
    assert "extract" in body["stage_ms"]


def test_performance_is_empty_before_anything_is_parsed(session, m04):
    """Different from a zero, and the endpoint says so rather than showing one."""
    from backend_M02_JD_Parser.app import app
    from backend_M02_JD_Parser.router import get_db
    from fastapi.testclient import TestClient

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    fresh = TestClient(app, headers={"X-Role": "admin", "X-Candidate-Id": "test-admin"})
    try:
        assert fresh.get("/v1/performance").json() == []
    finally:
        app.dependency_overrides.clear()


def test_performance_reports_p95_per_stage_against_the_budget(client, m04):
    """Measured over stored rows rather than a benchmark script.

    A benchmark measures the machine it ran on; §11's budget is a claim about
    what a student waits for.
    """
    for i in range(3):
        _parsed(client, f"Engineer {i}\n\nRequirements:\n- Python\n- SQL\n- Docker\n")

    rows = client.get("/v1/performance").json()
    by_stage = {r["stage"]: r for r in rows}

    assert "total" in by_stage
    assert by_stage["total"]["budget_ms"] == 8_000, "§11's cold-parse budget"
    assert by_stage["total"]["samples"] >= 3
    for row in rows:
        # The sample count travels with every number, because a p95 over three
        # parses is not a p95 and the reader has to be able to see that.
        assert row["samples"] >= 1
        assert row["within_budget"] == (row["p95_ms"] <= row["budget_ms"])


# ---------------------------------------------------------------------------
#  FR-2.8's rounds, and the two edge cases that are the same mechanism
# ---------------------------------------------------------------------------


def test_the_plan_is_a_sequence_of_rounds(client, m04_mastery):
    """§5 declares `rounds` and never defines `PlannedRound`.

    One per MODALITY, because that is what a student sits — a coding round is a
    different room from an HR round — and `measured_by` is what made the
    distinction real. Before it, everything was priced verbally and a round
    would have been one bucket holding everything.
    """
    m04_mastery({"measured": []})
    jd_id = _parse_for_plan(client)

    plan = _plan(client, jd_id, uuid.uuid4(), minutes=90)

    assert plan["rounds"], "no rounds"
    assert sum(r["minutes"] for r in plan["rounds"]) == pytest.approx(
        plan["allocated_minutes"], abs=0.01
    )
    assert sum(r["question_count"] for r in plan["rounds"]) == sum(
        a["question_budget"] for a in plan["allocations"]
    )
    # Cheapest first, so a session opens on a warm-up rather than on twenty
    # minutes of system design.
    costs = [
        {"verbal": 3.5, "coding": 12.0, "design": 20.0}[r["round_type"]] for r in plan["rounds"]
    ]
    assert costs == sorted(costs)


def test_no_history_says_the_session_is_a_diagnostic(client, m04_mastery):
    """EC-2.10: *"all gaps not_measured; plan is broad-coverage diagnostic;
    copy explains why."*

    The state was already right. The copy did not exist, so a student on their
    first day read a plan identical to one built for somebody we had measured
    ten times.
    """
    m04_mastery({"measured": []})
    jd_id = _parse_for_plan(client)

    plan = _plan(client, jd_id, uuid.uuid4(), minutes=60)

    assert plan["difficulty"] == "diagnostic"
    assert "measured" in plan["difficulty_note"]


def test_strong_everywhere_goes_looking_for_the_ceiling(client, m04_mastery):
    """EC-2.9: *"you're ready — let's find your ceiling."*"""
    m04_mastery(
        {
            "measured": [
                {"concept_id": "concept:dynamic_programming", "mastery_p": 0.95},
                {"concept_id": "concept:recursion", "mastery_p": 0.93},
                {"concept_id": "concept:sql_basics", "mastery_p": 0.91},
                {"concept_id": "concept:hashing", "mastery_p": 0.92},
            ]
        }
    )
    jd_id = _parse_for_plan(client)

    plan = _plan(client, jd_id, uuid.uuid4(), minutes=90)

    assert plan["difficulty"] == "final_boss"
    assert "ceiling" in plan["difficulty_note"] or "harder" in plan["difficulty_note"]


def test_an_unmeasured_student_is_never_told_they_are_ready(client, m04_mastery):
    """`diagnostic` beats `final_boss` on a tie, deliberately.

    "You're ready" said to somebody nobody has tested is a guess dressed as
    praise, and it is the more damaging of the two errors: it stops a student
    preparing.
    """
    m04_mastery({"measured": []})
    jd_id = _parse_for_plan(client)

    plan = _plan(client, jd_id, uuid.uuid4(), minutes=60)

    assert plan["difficulty"] != "final_boss"
