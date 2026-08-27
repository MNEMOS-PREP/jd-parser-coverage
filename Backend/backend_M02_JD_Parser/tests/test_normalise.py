"""Stage 1 — getting the job out of the document it arrived in (§6.1, EC-2.4).

Every case here came from one real file: Cognizant's 2027 Ace Team brochure,
12,446 characters over 365 lines, sitting in `Testing/JD_Testing/`. Before this
stage existed that document's HIGHEST-weighted requirement was "All rights
reserved" and its second was "© 2026-2027 Cognizant" — the footer appears once
per page, and §6.4 counts repetition as emphasis, so the parser concluded the
most important thing the job asks for is a legal notice.

It did exactly what it was told. That is why the fix is upstream of it.
"""

from __future__ import annotations

from backend_M02_JD_Parser.normalise import (
    normalise,
    rejoin_layout,
    strip_boilerplate,
    too_thin,
)
from test_api import _parsed

# ---------------------------------------------------------------------------
#  Boilerplate
# ---------------------------------------------------------------------------


def test_a_page_footer_does_not_become_a_requirement():
    """The exact line, from the exact document, eight times over."""
    text = "\n".join(
        [
            "Requirements:",
            "- Python",
            "© 2026-2027 Cognizant. All rights reserved.",
            "- SQL",
            "© 2026-2027 Cognizant. All rights reserved.",
            "- Docker",
            "© 2026-2027 Cognizant. All rights reserved.",
        ]
    )

    cleaned = strip_boilerplate(text)

    assert "All rights reserved" not in cleaned
    assert "Python" in cleaned and "SQL" in cleaned and "Docker" in cleaned


def test_a_repeated_line_is_furniture_even_without_a_rule_for_it():
    """The structural half, and the half that survives the 51st campus email.

    A rule list is always one company behind. A line appearing three times in
    one document is a header or a footer whatever it says.
    """
    text = "\n".join(["Acme Internal Use Only", "Requirements:", "- Python"] * 3)

    cleaned = strip_boilerplate(text)

    assert "Acme Internal Use Only" not in cleaned


def test_a_line_said_twice_is_left_alone():
    """Below the threshold. A requirement stated twice is emphasis, not
    furniture, and §6.4 is supposed to count it."""
    text = "Requirements:\n- Python\nWe use Python heavily.\n- SQL"

    assert "Python heavily" in strip_boilerplate(text)


def test_an_email_signature_goes():
    text = "\n".join(
        [
            "Requirements:",
            "- Python",
            "",
            "Regards,",
            "Placement Cell, Amrita Vishwa Vidyapeetham",
            "www.amrita.edu",
        ]
    )

    cleaned = strip_boilerplate(text)

    assert "Placement Cell" not in cleaned
    assert "www.amrita.edu" not in cleaned
    assert "Python" in cleaned


# ---------------------------------------------------------------------------
#  Layout damage
# ---------------------------------------------------------------------------


def test_a_bullet_on_its_own_line_finds_its_item():
    """A PDF text layer does this constantly, and a detached glyph is invisible
    to every enumeration rule downstream."""
    text = "Requirements:\n•\nBuild and orchestrate multi-agent AI systems.\n•\nDeploy LLMs."

    rejoined = rejoin_layout(text)

    assert "• Build and orchestrate multi-agent AI systems." in rejoined
    assert "• Deploy LLMs." in rejoined


def test_a_line_broken_mid_phrase_is_rejoined():
    """ "React /" was a requirement called "React /".

    The column broke where the layout ran out of width, not where the list ran
    out of items.
    """
    text = "Python, Java / .NET, JavaScript / TypeScript, React /\nAngular, REST APIs, SQL"

    rejoined = rejoin_layout(text)

    assert "React / Angular" in rejoined
    assert rejoined.count("\n") == 0, "one broken line should become one line"


def test_prose_is_not_reflowed():
    """Joining every line that does not end in a full stop would flatten a
    two-column layout into one sentence and destroy the enumeration structure
    `_list_lines` reads."""
    text = "Requirements:\n- Strong Python\n- Good SQL\n- Docker experience"

    assert rejoin_layout(text) == text


# ---------------------------------------------------------------------------
#  EC-2.4 — is there a job in here at all?
# ---------------------------------------------------------------------------


def test_a_short_posting_is_not_too_thin():
    """§3.2.1 trap 1: *"the 40-word campus JD is the MEDIAN, not the edge
    case."*

    The first version of this check refused anything under thirty words and
    broke ninety-one tests. "Looking for SDE trainees. Good knowledge of DSA
    and OOPs." is eleven words and a perfectly real posting — the archetype
    library exists precisely to handle it.
    """
    short = "Looking for SDE trainees. Good knowledge of DSA and OOPs."

    assert too_thin(short, normalise(short)) is False


def test_an_email_thread_with_a_job_buried_in_it_is_too_thin():
    """EC-2.4's actual case: what identifies it is the RATIO, not the length.

    A document that lost most of itself to the stripper was mostly not a job
    description, and parsing the remainder returns three requirements off a
    disclaimer.
    """
    original = "\n".join(
        [
            "From: placements@example.edu",
            "Sent: Monday",
            "Subject: FW: Drive",
            "",
            "Dear students, please find below.",
            "",
            "Regards,",
            "Placement Cell",
            "",
            "-------- Forwarded message --------",
            "This email and any attachments are confidential and intended solely for the "
            "intended recipient of this message.",
            "Disclaimer: the views expressed are those of the sender.",
            "www.example.edu",
            "© 2026 Example University. All rights reserved.",
            "Unsubscribe from these alerts",
            "Follow us on LinkedIn",
        ]
    )

    assert too_thin(original, normalise(original)) is True


# ---------------------------------------------------------------------------
#  End to end, through the parse
# ---------------------------------------------------------------------------


BROCHURE_SHAPED = """Cognizant Ace Team Program

© 2026-2027 Cognizant. All rights reserved.

Technologies & Skills

Python, Java / .NET, JavaScript / TypeScript, React /
Angular, REST APIs, SQL

© 2026-2027 Cognizant. All rights reserved.

Eligibility criteria
• Students graduating in 2027 with B.E/B. Tech/M.E/M. Tech degrees.
• Students with standing arrears are NOT eligible to apply.

© 2026-2027 Cognizant. All rights reserved.
"""


def test_the_brochures_footer_is_not_its_top_requirement(client, m04):
    """The whole reason this stage exists."""
    body = _parsed(client, BROCHURE_SHAPED)
    texts = [r["text"] for r in body["requirements"]]

    assert not any("rights reserved" in t.lower() for t in texts)
    assert not any("cognizant" in t.lower() for t in texts)


def test_a_compound_heading_still_opens_a_list(client, m04):
    """ "Technologies & Skills" is a heading and `_HEADING_RE` wanted the word
    alone on the line.

    The parser only ever read that brochure's skill tables because the PDF
    layer happened to break "Languages & Frameworks" into two lines, the second
    of which matched by itself. Fixing the layout removed the accident and took
    forty real requirements with it.
    """
    body = _parsed(client, BROCHURE_SHAPED)
    texts = [r["text"] for r in body["requirements"]]

    assert "Python" in texts
    assert "SQL" in texts
    # And the line the column broke in half is one requirement again.
    assert "React / Angular" in texts
    assert "React /" not in texts


def test_the_eligibility_a_brochure_actually_writes(client, m04):
    """Three phrasings that all matched nothing before this document was read:
    "graduating in 2027", "standing arrears", and degree plurals."""
    body = _parsed(client, BROCHURE_SHAPED)
    eligibility = body["eligibility"]

    assert eligibility["year_of_passing"] == [2027]
    assert eligibility["max_backlogs_active"] == 0
    # Degrees are not branches. The old branch pattern matched any run of
    # capitals joined by slashes and produced `["AIML"]` off "AI/ML" elsewhere
    # in the document — telling a student they are ineligible for a drive that
    # never excluded them.
    assert eligibility["allowed_branches"] == []


def test_degree_text_does_not_become_a_requirement(client, m04):
    """ "B.E/B. Tech/M.E/M. Tech degrees" split into "Tech/M.E/M" and
    "Tech degrees", neither of which contains a recognisable degree name, so
    both survived `_ELIGIBILITY` as skills."""
    body = _parsed(client, BROCHURE_SHAPED)
    texts = [r["text"] for r in body["requirements"]]

    assert not any("tech" in t.lower() and "degree" in t.lower() for t in texts)
    assert "Tech/M.E/M" not in texts
