"""Getting a job description out of a file (FR-2.1).

§1 describes the input as *"usually a badly formatted blob from a
placement-portal email"*. Until now the only way in was `raw_text`, which
assumes the student can select the text — and a placement-cell mail arrives as
an attachment at least as often as it arrives as a body.

── Much smaller than M01's equivalent, deliberately ────────────────────────────

M01's `documents.py` is eight hundred lines because a resume needs per-word
bounding boxes, page rasterisation, column detection and OCR: it renders the
document back to the student with the parsed spans drawn on top of it. A job
description needs none of that. Everything downstream of this file — the
requirement extraction, the eligibility block, the weights — operates on a
string, and the screen quotes that string rather than the original page.

So this converts to text and stops. What it does keep from M01 is the part that
is about the student rather than the format:

  · sniff by MAGIC BYTES, never by the extension. Renaming `report.docx` to
    `jd.pdf` is a thing people do, and the error it produces if you trust the
    name is a parser stack trace.
  · every refusal names the fix. "Unsupported file type" is a dead end;
    "that is a zip — upload the PDF inside it" is an instruction.

── The one thing this refuses to do ────────────────────────────────────────────

There is no OCR. A scanned PDF with no text layer comes back with a message
saying so, rather than an empty parse that looks like a JD with no requirements
in it. An empty requirement list is the single most misleading thing this
module can produce: it renders as a clean screen saying the job asks for
nothing, and a student would believe it.
"""

from __future__ import annotations

import io
import re

#: Magic bytes. The extension is a claim the uploader makes; these are what the
#: file actually is.
_PDF = b"%PDF-"
_ZIP = b"PK\x03\x04"
_OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"  # legacy .doc, and .xls
_RTF = b"{\\rtf"


class UnreadableDocument(Exception):
    """A file we will not guess at, with a sentence the student can act on.

    Carries the message rather than a code because there is exactly one place
    this is rendered and the fix differs per cause: a zip needs unzipping, a
    scan needs a text layer, a `.doc` needs re-saving. A single "unsupported
    file" string would collapse three different instructions into none.
    """


def sniff(data: bytes, filename: str | None = None) -> str:
    """`pdf`, `docx` or `text` — or an `UnreadableDocument` naming the fix."""
    if not data:
        raise UnreadableDocument("That file is empty.")

    if data.startswith(_PDF):
        return "pdf"

    if data.startswith(_ZIP):
        # Both .docx and a plain .zip start this way; a .docx always contains
        # this part, and a zip of holiday photos does not.
        if b"word/document.xml" in data[:8192] or b"[Content_Types].xml" in data[:4096]:
            return "docx"
        raise UnreadableDocument(
            "That is a zip archive, not a job description. Upload the PDF or .docx inside it."
        )

    if data.startswith(_OLE):
        raise UnreadableDocument(
            "That is the old .doc format, which cannot be read reliably. "
            "Save it as PDF or .docx, or paste the text instead."
        )

    if data.startswith(_RTF):
        raise UnreadableDocument(
            "RTF is not supported. Save as PDF or .docx, or paste the text instead."
        )

    # Anything that decodes as UTF-8 and has letters in it is a text file —
    # .txt, .md, or the .eml a placement cell forwarded.
    try:
        decoded = data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    else:
        if any(character.isalpha() for character in decoded):
            return "text"

    name = f" ({filename})" if filename else ""
    raise UnreadableDocument(
        f"I cannot read that file type{name}. Upload a PDF, a .docx, or a .txt — "
        "or paste the text straight into the box."
    )


def _from_pdf(data: bytes) -> str:
    import pymupdf

    try:
        document = pymupdf.open(stream=data, filetype="pdf")
    except Exception as error:  # pragma: no cover - corrupt file
        raise UnreadableDocument(
            "That PDF could not be opened — it may be corrupt or password-protected. "
            "Try re-saving it, or paste the text instead."
        ) from error

    with document:
        if document.needs_pass:
            raise UnreadableDocument(
                "That PDF is password-protected. Remove the password, or paste the text instead."
            )
        pages = [page.get_text("text") for page in document]

    text = "\n".join(pages)
    if not text.strip():
        # A scan. Refused loudly rather than parsed to nothing: an empty
        # requirement list renders as a clean screen saying this job asks for
        # nothing, which a student would believe.
        raise UnreadableDocument(
            "That PDF has no text in it — it looks like a scan or a photo. "
            "We cannot read those yet. Paste the text instead."
        )
    return text


def _from_docx(data: bytes) -> str:
    import docx

    try:
        document = docx.Document(io.BytesIO(data))
    except Exception as error:  # pragma: no cover - corrupt file
        raise UnreadableDocument(
            "That .docx could not be opened. Try re-saving it, or paste the text instead."
        ) from error

    lines = [paragraph.text for paragraph in document.paragraphs]

    # Tables carry the eligibility block more often than not — a campus posting
    # puts CGPA, batch and bond in a two-column grid. Flattened to "key: value"
    # so `extract_eligibility` sees the same shape it sees in prose.
    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if len(cells) >= 2:
                lines.append(f"{cells[0]}: {' '.join(cells[1:])}")
            elif cells:
                lines.append(cells[0])

    text = "\n".join(lines)
    if not text.strip():
        raise UnreadableDocument("That .docx has no text in it. Paste the job description instead.")
    return text


#: Three or more blank lines become two. A PDF's text layer is full of them and
#: `_list_lines` treats a blank line as the end of an enumeration, so the noise
#: is not cosmetic — it truncates requirement lists.
_RUNS_OF_BLANKS = re.compile(r"\n{3,}")

#: Trailing spaces before a newline, which PDF extraction produces constantly
#: and which make a heading fail to match `_HEADING_RE`'s `\s*$`.
_TRAILING_SPACE = re.compile(r"[ \t]+\n")


def to_text(data: bytes, filename: str | None = None) -> str:
    """The job description as text, whatever it arrived as.

    Normalised on the way out, because the extractor downstream is sensitive to
    exactly the two things a PDF text layer gets wrong: runs of blank lines,
    which end an enumeration early, and trailing spaces, which stop a heading
    matching. Neither is cosmetic here.
    """
    kind = sniff(data, filename)

    if kind == "pdf":
        text = _from_pdf(data)
    elif kind == "docx":
        text = _from_docx(data)
    else:
        text = data.decode("utf-8", errors="replace")

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _TRAILING_SPACE.sub("\n", text)
    return _RUNS_OF_BLANKS.sub("\n\n", text).strip()
