"""§2.3 door 1, and the ratio that says whether it was worth building.

The spec's input screen has three doors and this module shipped with two. The
missing one is not a small one: §2.3 calls the campus-drive chips *"the
highest-value element on this screen"*, because a student whose drive is on the
calendar should never have to go and find the posting.

It stayed missing because M02 has no company table and should not grow one —
§3.2's fifth hard part is that "TCS", "Tata Consultancy Services", "TCS Digital"
and "TCS NQT" are one company and four drives, and that a second copy of that
table is how two modules start disagreeing. M15 owns it and M15 now runs, so
door 1 is built against it.
"""

from __future__ import annotations

import uuid

import pytest
from backend_M02_JD_Parser import company as m15_client
from backend_M02_JD_Parser import router as router_module

COMPANY_ID = "11111111-1111-1111-1111-111111111111"
DRIVE_ID = "22222222-2222-2222-2222-222222222222"


@pytest.fixture
def m15_drives(monkeypatch):
    """A running M15 with one company and two drives.

    Patched at `m15_get`, which is the whole M15 surface M02 uses, so the fake
    describes the contract rather than the transport.
    """

    def install(*, variants=None, available=True):
        rows = {
            "/v1/companies": [
                {
                    "id": COMPANY_ID,
                    "canonical_name": "Tata Consultancy Services",
                    "aliases": ["TCS", "TCS Digital"],
                    "report_count": 4,
                }
            ],
            f"/v1/companies/{COMPANY_ID}/variants": (
                variants
                if variants is not None
                else [
                    {
                        "id": DRIVE_ID,
                        "name": "Digital",
                        "role_archetype": "sde",
                        "typical_package_lpa": 7.0,
                        "bond_months": 18,
                        "typical_locations": ["Chennai", "Pune"],
                    },
                    {
                        "id": "33333333-3333-3333-3333-333333333333",
                        "name": "Ninja",
                        "role_architype_typo_guard": None,
                        "role_archetype": "sde",
                        "typical_package_lpa": 3.6,
                        "typical_locations": ["Chennai"],
                    },
                ]
            ),
        }

        def fake_get(deps, path, timeout=2.0):
            if not available:
                return None
            # Longest prefix first. "/v1/companies/{id}/variants" also starts
            # with "/v1/companies", so insertion order would answer the variants
            # call with the company list — and the drives would come back empty
            # while every other part of the fake looked correct.
            for prefix in sorted(rows, key=len, reverse=True):
                if path.startswith(prefix):
                    return rows[prefix]
            return None

        monkeypatch.setattr(m15_client, "m15_get", fake_get)
        monkeypatch.setattr(router_module, "m15_get", fake_get)

        class _Deps:
            def get(self, module_id):
                return type("D", (), {"base_url": "http://m15.test"})()

            def is_available(self, module_id):
                return available

        def registry():
            return _Deps()

        # `conftest` clears this cache between tests, so the stub has to carry
        # the same attribute the real `lru_cache`-wrapped function does.
        registry.cache_clear = lambda: None
        monkeypatch.setattr(router_module, "dependency_registry", registry)

    return install


# ---------------------------------------------------------------------------
#  The picker
# ---------------------------------------------------------------------------


def test_the_company_list_carries_the_aliases_a_student_might_search(client, m15_drives):
    """A student searching "CTS" has to recognise "Cognizant" in the result."""
    m15_drives()

    rows = client.get("/v1/doors/companies?q=tcs").json()

    assert rows[0]["name"] == "Tata Consultancy Services"
    assert "TCS" in rows[0]["aliases"]
    assert rows[0]["report_count"] == 4


def test_the_drives_are_the_chips_and_carry_their_figures(client, m15_drives):
    """§2.3's highest-value element. A chip that says only "Digital" makes the
    student click to find out what they are picking."""
    m15_drives()

    drives = client.get(f"/v1/doors/companies/{COMPANY_ID}/drives").json()

    digital = next(d for d in drives if d["name"] == "Digital")
    assert digital["typical_package_lpa"] == 7.0
    assert digital["bond_months"] == 18
    assert digital["typical_locations"] == ["Chennai", "Pune"]


@pytest.mark.gate
def test_m15s_archetype_is_translated_into_m02s(client, m15_drives):
    """M15 writes `sde`; M02's archetype ids are `sde_1`.

    A chip whose `archetype_id` stays null cannot build a requirement set, so
    getting this wrong disables the door silently rather than breaking it
    loudly.
    """
    m15_drives()

    drives = client.get(f"/v1/doors/companies/{COMPANY_ID}/drives").json()

    assert all(d["archetype_id"] == "sde_1" for d in drives)


def test_m15_down_is_an_empty_list_not_an_error(client, m15_drives):
    """Rule 2. The other two doors have to keep working, and an exception here
    would take the whole input screen down over an optional one."""
    m15_drives(available=False)

    assert client.get("/v1/doors/companies").json() == []
    assert client.get(f"/v1/doors/companies/{COMPANY_ID}/drives").json() == []


# ---------------------------------------------------------------------------
#  Walking through the door
# ---------------------------------------------------------------------------


def test_a_drive_becomes_a_requirement_set(client, m15_drives, m04):
    m15_drives()

    res = client.post("/v1/jds/from-drive", json={"company_id": COMPANY_ID, "drive_id": DRIVE_ID})

    assert res.status_code == 201, res.text
    jd = res.json()
    assert jd["company_name"] == "Tata Consultancy Services"
    assert jd["role_title"] == "Digital"
    assert jd["role_archetype"] == "sde_1"
    assert jd["requirements"], "the archetype requirement set did not land"
    assert jd["raw_text"] == "", (
        "a synthesised posting would make the read-back quote sentences no company published"
    )


def test_the_drives_reported_figures_become_the_eligibility(client, m15_drives, m04):
    """There is no posting to read a package off, and a reported figure beats
    none — it is the only thing on this record that came from anywhere real."""
    m15_drives()

    jd = client.post(
        "/v1/jds/from-drive", json={"company_id": COMPANY_ID, "drive_id": DRIVE_ID}
    ).json()

    assert jd["eligibility"]["package_lpa_total"] == 7.0
    assert jd["eligibility"]["bond_months"] == 18


@pytest.mark.gate
def test_two_drives_at_one_company_do_not_share_a_requirement_set(client, m15_drives, m04):
    """The reason the chip matters more than the company.

    TCS Digital and TCS Ninja are different interviews. Caching them together
    would give a student sitting one an average of the two, which is the §3.2
    failure this whole door exists to avoid.
    """
    m15_drives()

    digital = client.post(
        "/v1/jds/from-drive", json={"company_id": COMPANY_ID, "drive_id": DRIVE_ID}
    ).json()
    ninja = client.post(
        "/v1/jds/from-drive",
        json={"company_id": COMPANY_ID, "drive_id": "33333333-3333-3333-3333-333333333333"},
    ).json()

    assert digital["id"] != ninja["id"]
    assert digital["content_sha256"] != ninja["content_sha256"]


def test_the_same_drive_twice_is_one_parse(client, m15_drives, m04):
    """Shared like any other parse: two students sitting TCS Digital are
    looking at one requirement set, because it IS one."""
    m15_drives()
    body = {"company_id": COMPANY_ID, "drive_id": DRIVE_ID}

    first = client.post("/v1/jds/from-drive", json=body)
    second = client.post("/v1/jds/from-drive", json=body)

    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]


def test_a_drive_for_a_role_we_do_not_know_says_so(client, m15_drives, m04):
    """Refused with a sentence naming what to do instead, rather than a
    requirement set for a role nobody chose."""
    m15_drives(
        variants=[{"id": DRIVE_ID, "name": "Actuarial Graduate", "role_archetype": "actuary"}]
    )

    res = client.post("/v1/jds/from-drive", json={"company_id": COMPANY_ID, "drive_id": DRIVE_ID})

    assert res.status_code == 422
    assert "Pick a role instead" in res.json()["detail"]


def test_m15_down_names_the_module_rather_than_404ing(client, m15_drives):
    """ "No such drive" and "the module that knows about drives is not running"
    lead to completely different actions, and only one is the student's."""
    m15_drives(available=False)

    res = client.post("/v1/jds/from-drive", json={"company_id": COMPANY_ID, "drive_id": DRIVE_ID})

    assert res.status_code == 503
    assert "M15" in res.json()["detail"]
    assert "paste" in res.json()["detail"]


def test_an_unknown_drive_at_a_known_company_is_a_404(client, m15_drives, m04):
    m15_drives()

    res = client.post(
        "/v1/jds/from-drive", json={"company_id": COMPANY_ID, "drive_id": str(uuid.uuid4())}
    )

    assert res.status_code == 404


# ---------------------------------------------------------------------------
#  AC-2.7
# ---------------------------------------------------------------------------


def test_the_ratio_is_empty_before_anything_is_parsed(client):
    """Different from a set of zeroes."""
    assert client.get("/v1/doors").json() == []


def test_each_door_is_counted_under_its_own_name(client, m15_drives, m04):
    """§13's drive-chip versus manual-paste ratio, which had nothing to measure
    until the chips existed."""
    m15_drives()

    client.post("/v1/jds/from-drive", json={"company_id": COMPANY_ID, "drive_id": DRIVE_ID})
    client.post("/v1/jds/from-role", json={"archetype_id": "sde_1"})
    client.post(
        "/v1/jds/parse",
        json={
            "company_name": "Acme",
            "role_title": "Engineer",
            "raw_text": "Requirements:\n- Dynamic Programming\n- SQL\n",
        },
    )

    usage = {row["door"]: row for row in client.get("/v1/doors").json()}

    assert usage["drive_chip"]["count"] == 1
    assert usage["role_only"]["count"] == 1
    assert usage["posting"]["count"] == 1
    assert sum(row["share"] for row in usage.values()) == pytest.approx(1.0, abs=0.01)


def test_pasting_and_uploading_are_one_door(client, m04):
    """§2.3 counts "bring me the posting" as a single way in. A student who
    forwards the mail as an attachment made the same choice as one who copied
    its body."""
    for i in range(2):
        client.post(
            "/v1/jds/parse",
            json={
                "company_name": f"Acme {i}",
                "role_title": "Engineer",
                "raw_text": "Requirements:\n- Recursion\n- Hashing\n",
            },
        )

    usage = client.get("/v1/doors").json()

    assert len(usage) == 1
    assert usage[0]["door"] == "posting"
    assert usage[0]["share"] == 1.0
