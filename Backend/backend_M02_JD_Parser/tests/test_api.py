import uuid

import pytest
from backend_M02_JD_Parser.router import FALLBACK_CONCEPTS


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
    """The degradation is reportable, not merely absent."""
    deps = client.get("/v1/deps").json()
    assert [d["module_id"] for d in deps] == ["M04"]
    assert deps[0]["available"] is False
    assert deps[0]["base_url"] == "http://127.0.0.1:8104"
    assert deps[0]["required"] is False
    assert "M04" in deps[0]["on_missing"]


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

    assert body["requirements"], "no requirements to check"
    for requirement in body["requirements"]:
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


def test_a_requirement_says_whether_anything_can_test_it(client, m04):
    """§3.2.3: mark it `unmeasurable` and say so rather than faking a score.

    `measurable` and `concept_source` travel with the requirement so a caller
    cannot mistake an offline guess for an ontology-confirmed id — the same
    provenance rule the flat lists already carried, now attached to the row
    it describes.
    """
    body = _parse_response(client).json()

    for requirement in body["requirements"]:
        if requirement["measurable"]:
            assert requirement["concept_ids"], "measurable with no concept id"
            assert requirement["concept_source"] in {"m04", "offline_fallback"}
        else:
            assert requirement["concept_ids"] == []


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

    assert body["required_skills"] == []


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
            "raw_text": (
                "Engineer\n\nRequirements:\n"
                "- Dynamic Programming or Recursion\n"
                "- SQL\n"
            ),
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
