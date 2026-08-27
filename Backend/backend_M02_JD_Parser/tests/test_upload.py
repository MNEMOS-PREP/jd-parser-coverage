"""A job description arriving as a file (FR-2.1).

§1 calls the input *"usually a badly formatted blob from a placement-portal
email"*. The tests that matter here are the two ends of that: that an upload
lands in exactly the same place a paste does, and that a file we cannot read is
refused with a sentence rather than parsed into an empty JD.

The second is the dangerous one. An empty requirement list is the single most
misleading thing this module can produce — it renders as a clean screen saying
the job asks for nothing, and a student would believe it.
"""

from __future__ import annotations

import io
import uuid

import pytest

UPLOAD_JD = """Software Engineer, Backend

Requirements:
- Strong Python and SQL
- Experience with Docker

Nice to have:
- Kubernetes

Eligibility: minimum 7.5 CGPA, 2026 batch.
"""


def _upload(client, data: bytes, filename: str, mime: str = "application/octet-stream"):
    return client.post(
        "/v1/jds/upload",
        files={"file": (filename, io.BytesIO(data), mime)},
        data={"company_name": "Acme", "role_title": "Backend Engineer"},
    )


def _pdf_bytes(text: str) -> bytes:
    """A real PDF with a real text layer, built rather than fixtured.

    A checked-in binary fixture is a file nobody can read in a diff and nobody
    updates when the assertion changes. This is generated from the same string
    the paste test uses, which is what makes the equivalence assertion mean
    anything.
    """
    import pymupdf

    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), text, fontsize=10)
    data = document.tobytes()
    document.close()
    return data


def _docx_bytes(text: str) -> bytes:
    import docx

    document = docx.Document()
    for line in text.split("\n"):
        document.add_paragraph(line)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
#  The formats
# ---------------------------------------------------------------------------


def test_a_plain_text_upload_parses(client, m04):
    res = _upload(client, UPLOAD_JD.encode("utf-8"), "jd.txt", "text/plain")

    assert res.status_code == 201, res.text
    body = res.json()
    assert "SQL" in body["required_skills"]
    assert body["eligibility"]["min_cgpa"] == 7.5


def test_a_docx_upload_parses(client, m04):
    res = _upload(client, _docx_bytes(UPLOAD_JD), "jd.docx")

    assert res.status_code == 201, res.text
    body = res.json()
    assert "SQL" in body["required_skills"]
    assert body["eligibility"]["min_cgpa"] == 7.5


def test_a_docx_table_becomes_readable_eligibility(client, m04):
    """Campus postings put CGPA, batch and bond in a two-column grid.

    Flattened to "key: value" so `extract_eligibility` sees the shape it sees
    in prose — otherwise the most consequential block in the posting arrives as
    a set of orphaned cells and is read as nothing at all.
    """
    import docx

    document = docx.Document()
    document.add_paragraph("Backend Engineer")
    document.add_paragraph("Requirements:")
    document.add_paragraph("- Strong SQL")
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Minimum CGPA"
    table.cell(0, 1).text = "7.5"
    table.cell(1, 0).text = "Batch"
    table.cell(1, 1).text = "2026"
    buffer = io.BytesIO()
    document.save(buffer)

    res = _upload(client, buffer.getvalue(), "jd.docx")

    assert res.status_code == 201, res.text
    assert res.json()["eligibility"]["min_cgpa"] == 7.5


def test_a_pdf_upload_parses(client, m04):
    res = _upload(client, _pdf_bytes(UPLOAD_JD), "jd.pdf", "application/pdf")

    assert res.status_code == 201, res.text
    assert "SQL" in res.json()["required_skills"]


# ---------------------------------------------------------------------------
#  One pipeline, two doors
# ---------------------------------------------------------------------------


@pytest.mark.gate
def test_an_uploaded_jd_is_the_same_row_as_the_pasted_one(client, m04):
    """The upload route has no parsing logic of its own, and this proves it.

    Two entry points with two pipelines is how one of them quietly stops
    getting the extraction fixes. The content hash is the evidence: upload the
    same posting after pasting it and the answer is 200 from the cache with the
    same id, not a second 201.
    """
    pasted = client.post(
        "/v1/jds/parse",
        json={
            "company_name": "Acme",
            "role_title": "Backend Engineer",
            "raw_text": UPLOAD_JD.strip(),
        },
    )
    assert pasted.status_code == 201, pasted.text

    uploaded = _upload(client, UPLOAD_JD.encode("utf-8"), "jd.txt", "text/plain")

    assert uploaded.status_code == 200, "an upload of an already-parsed JD created a second row"
    assert uploaded.json()["id"] == pasted.json()["id"]


# ---------------------------------------------------------------------------
#  What it refuses, and how
# ---------------------------------------------------------------------------


def test_a_scanned_pdf_is_refused_not_parsed_to_nothing(client, m04):
    """The most misleading thing this module can produce is an empty JD.

    It renders as a clean screen saying the job asks for nothing. There is no
    OCR here, so a PDF with no text layer says so rather than succeeding into
    a lie.
    """
    import pymupdf

    document = pymupdf.open()
    document.new_page()
    blank = document.tobytes()
    document.close()

    res = _upload(client, blank, "scan.pdf", "application/pdf")

    assert res.status_code == 422
    assert "no text" in res.json()["detail"]
    assert "paste" in res.json()["detail"].lower()


def test_a_zip_is_told_what_to_do_about_it(client, m04):
    """ "Unsupported file type" is a dead end. This is an instruction."""
    res = _upload(client, b"PK\x03\x04" + b"\x00" * 200, "stuff.zip")

    assert res.status_code == 422
    assert "zip" in res.json()["detail"].lower()
    assert "inside it" in res.json()["detail"]


def test_the_old_doc_format_is_named_rather_than_guessed_at(client, m04):
    res = _upload(client, b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 100, "jd.doc")

    assert res.status_code == 422
    assert ".doc" in res.json()["detail"]


def test_the_extension_is_not_trusted(client, m04):
    """Sniffed by magic bytes, because renaming a file is a thing people do.

    Trusting the name here means a `.docx` renamed to `.pdf` reaches the PDF
    parser and the student gets a stack trace instead of a sentence.
    """
    res = _upload(client, _docx_bytes(UPLOAD_JD), "jd.pdf", "application/pdf")

    assert res.status_code == 201, "a mislabelled docx should still be read as a docx"
    assert "SQL" in res.json()["required_skills"]


def test_an_empty_file_says_so(client, m04):
    res = _upload(client, b"", "empty.pdf")

    assert res.status_code == 422
    assert "empty" in res.json()["detail"].lower()


def test_an_oversized_file_is_refused_by_size(client, m04):
    """A JD is a page or two. Past that it is the wrong file, and reading it
    into memory to find out is how an upload endpoint exhausts a server."""
    res = _upload(client, b"%PDF-" + b"0" * (6 * 1024 * 1024), "huge.pdf")

    assert res.status_code == 413
    assert "MB" in res.json()["detail"]


# ---------------------------------------------------------------------------
#  Identity
# ---------------------------------------------------------------------------


def test_a_posting_is_still_not_personal_data(session, m04):
    """The upload route stays ungated, like every other JD route.

    FR-2.12 caches one parse across students on purpose. Gating this would give
    two students preparing for the same drive a private copy each of a public
    document and protect nothing. `test_access.py` states the same boundary for
    the paste route.
    """
    from backend_M02_JD_Parser.app import app
    from backend_M02_JD_Parser.router import get_db
    from fastapi.testclient import TestClient

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    anonymous = TestClient(app)
    try:
        res = _upload(anonymous, UPLOAD_JD.encode("utf-8"), "jd.txt", "text/plain")
        assert res.status_code == 201, res.text
    finally:
        app.dependency_overrides.clear()


def test_a_candidate_scoped_route_is_still_gated(client, m04):
    """The boundary has not moved: the JD is the company's, the gap is yours."""
    res = _upload(client, UPLOAD_JD.encode("utf-8"), "jd.txt", "text/plain")
    jd_id = res.json()["id"]

    from backend_M02_JD_Parser.app import app
    from fastapi.testclient import TestClient

    stranger = TestClient(app, headers={"X-Role": "student", "X-Candidate-Id": str(uuid.uuid4())})
    assert stranger.get(f"/v1/jds/{jd_id}/coverage/{uuid.uuid4()}").status_code == 403
