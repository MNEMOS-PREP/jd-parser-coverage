import uuid

import pytest


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
            f"{requirement['text']}'s span points at {raw[span['start']:span['end']]!r}"
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
