import uuid


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
