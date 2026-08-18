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
            "raw_text": "Looking for Dynamic Programming expertise."
        }
    )
    assert res.status_code == 201
    data = res.json()
    assert data["company_name"] == "Google"
    assert "Dynamic Programming" in data["required_skills"]

    jd_id = data["id"]
    res_get = client.get(f"/v1/jds/{jd_id}")
    assert res_get.status_code == 200
    assert res_get.json()["id"] == jd_id

def test_jd_coverage(client):
    # Create a JD with Dynamic Programming
    res_parse = client.post(
        "/v1/jds/parse",
        json={
            "company_name": "Google",
            "role_title": "Engineer",
            "raw_text": "Looking for Dynamic Programming expertise."
        }
    )
    data = res_parse.json()
    jd_id = data["id"]
    candidate_id = str(uuid.uuid4())

    # Get coverage (M04 mock return / fallback will empty mastery)
    res_cov = client.get(f"/v1/jds/{jd_id}/coverage/{candidate_id}")
    assert res_cov.status_code == 200
    cov_data = res_cov.json()
    assert cov_data["coverage_score"] == 0.0
    assert "Dynamic Programming" in cov_data["missing"]
