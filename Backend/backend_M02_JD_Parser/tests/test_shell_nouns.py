"""Every /v1 noun M02 serves is routed to M02 by the shell.

Platform_Shell proxies one origin by the FIRST path segment — `/v1/<noun>` goes
to one backend. Until 2026-10-02 M02 served two nouns other modules own
(`companies`, M15's; `sessions`, M05's), so through the shell the company
picker rendered M15's answer and the coverage view 404'd; and three nouns it
did own (`doors`, `archetypes`, `performance`) were in nobody's table at all.
Server-to-server callers never noticed, which is why it lasted.

Read from the shell's own `vite.config.ts` rather than a copy of it — a copy is
one change behind the day it is taken. Skipped when the shell is not checked
out next door.
"""

from __future__ import annotations

import pathlib
import re

import pytest
from backend_M02_JD_Parser.app import app

SHELL = pathlib.Path(__file__).resolve().parents[4] / "Platform_Shell" / "vite.config.ts"
#: Every module answers /v1/deps for itself; the shell handles it separately.
SHARED = {"deps"}


def shell_owners() -> dict[str, str]:
    text = SHELL.read_text(encoding="utf-8")
    table = text[text.index("const OWNER") : text.index("};", text.index("const OWNER"))]
    return dict(re.findall(r'^\s*"?([a-z-]+)"?:\s*"(m\d\d)"', table, flags=re.M))


@pytest.mark.skipif(not SHELL.exists(), reason="Platform_Shell is not checked out next door")
def test_every_m02_noun_is_routed_to_m02():
    owners = shell_owners()
    nouns = {
        path.split("/")[2]
        for path in app.openapi()["paths"]
        if path.startswith("/v1/") and path.split("/")[2] not in SHARED
    }
    wrong = {noun: owners.get(noun, "nobody") for noun in nouns if owners.get(noun) != "m02"}
    assert not wrong, f"M02 serves nouns the shell routes elsewhere: {wrong}"


def test_every_route_that_names_a_student_refuses_strangers():
    """Platform_Core's own check (v0.11.0), on the guard that replaced M02's
    hand-written copy: every route whose path or query names a student, found
    from the OpenAPI document, asked as nobody and as another student."""
    from ai_core.testing import assert_refuses_strangers
    from fastapi.testclient import TestClient

    checked = assert_refuses_strangers(TestClient(app), app, expect_at_least=5)
    assert ("POST", "/v1/coverage/{session_id}/{candidate_id}") in checked
