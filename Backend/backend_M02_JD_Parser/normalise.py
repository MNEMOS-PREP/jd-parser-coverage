"""Stage 1 — get the job out of the document it arrived in (§6.1, EC-2.4).

§6.1: *"Strip boilerplate (email signatures, 'Regards, Placement Cell',
forwarded-message headers, disclaimers) with a rule list built from 50 real
campus emails."*

Written against a real one: Cognizant's 2027 Ace Team brochure, 12,446
characters over 365 lines. Before this file existed, that document's
highest-weighted requirement was **"All rights reserved"**, and its second was
"© 2026-2027 Cognizant". The copyright footer appears eight times, once per
page, and repetition is emphasis (§6.4) — so the parser did exactly what it was
told and concluded that the most important thing this job asks for is a legal
notice.

── Two problems, and the second is the one nobody writes down ──────────────────

**Boilerplate** is the one the spec names: footers, disclaimers, signatures.
Handled by a rule list AND by a structural rule that needs no list — a line
appearing three or more times in one document is furniture, not content. The
structural half is what survives contact with the fifty-first campus email,
because the rule list is always one company behind.

**Layout damage** is the one that actually costs requirements. A PDF's text
layer does not break lines where the sentence breaks; it breaks them where the
column does. That brochure yields:

    '•'
    'Build and orchestrate multi-agent AI systems.'

    'React /'
    'Angular'

    'Prompt'
    'Engineering & Structured Outputs'

A bullet on its own line is not a bullet as far as `_BULLET` is concerned, and
`React /` is a requirement called "React /". Six of that document's fifty-seven
requirements were fragments of this kind, and two of them — "Prompt" and
"Engineering & Structured Outputs" — are halves of one skill that reads as two
unrelated ones.

── What this deliberately does NOT do ──────────────────────────────────────────

It does not reflow prose. Joining every line that does not end in a full stop
would turn a two-column layout into one long sentence and destroy the
enumeration structure `_list_lines` depends on. Only lines ending in an
UNAMBIGUOUS continuation character are joined: a trailing `/`, `&` or `,` is
not a place any writer ends a thought.
"""

from __future__ import annotations

import re

#: Legal and administrative furniture. Matched against the WHOLE line, because
#: these are lines rather than phrases — "confidential" inside a requirement is
#: a requirement about confidentiality.
_BOILERPLATE_LINE = re.compile(
    r"^\s*(?:"
    r"©.*|\(c\)\s*\d{4}.*|copyright\s.*|"
    r"all\s+rights\s+reserved\.?|"
    r".*\ball\s+rights\s+reserved\b.*|"
    r"page\s+\d+(?:\s+of\s+\d+)?|\d+\s*/\s*\d+|"
    r"(?:this\s+)?(?:e-?mail|message).*(?:confidential|intended\s+recipient).*|"
    r"disclaimer\s*:?.*|"
    # `rejoin_layout` runs first and a sign-off ends in a comma, so
    # "Regards," is already joined to "Placement Cell, Example University"
    # by the time this sees it. The old tail allowed four bare words and no
    # punctuation, so the joined line matched nothing and three lines of
    # signature became three requirements.
    r"(?:thanks|regards|best\s+regards|warm\s+regards|sincerely)[\s,.!]*.{0,80}|"
    r"(?:from|sent|to|cc|bcc|subject)\s*:\s*.*|"
    r"-{3,}\s*(?:original\s+message|forwarded\s+message).*|"
    r"placement\s+(?:cell|office|team)\s*[,.]?\s*.*|"
    # §6.1: *"Detect and separate the ADMINISTRATIVE block (dates, venue,
    # registration link) from the role block."* These are labels on a form,
    # not requirements, and an unheaded line that enumerates now reads
    # "Role: Software Engineer Trainee" as a skill.
    r"(?:venue|date|time|registration|register|drive\s+date|reporting\s+time|mode\s+of\s+(?:test|interview)|last\s+date)\s*:.*|"
    r"unsubscribe.*|"
    r"follow\s+us\s+on.*|"
    r"www\.\S+|https?://\S+"
    r")\s*$",
    re.IGNORECASE,
)

#: A line repeated this many times in one document is furniture.
#:
#: The structural half of the stripper, and the half that survives the
#: fifty-first campus email. A page footer repeats once per page; a real
#: requirement written three times is unusual enough that losing it costs less
#: than keeping eight copies of a copyright notice — and §6.4 counts
#: repetition as EMPHASIS, so furniture does not merely add noise, it outranks
#: the content.
REPEAT_THRESHOLD = 3

#: Short lines only. A long line repeated is more likely a real requirement the
#: posting stresses than a footer.
MAX_REPEAT_LENGTH = 80

#: A line that is nothing but a list glyph. The PDF text layer puts these on
#: their own line constantly, and a bullet detached from its item is invisible
#: to every enumeration rule downstream.
_LONE_BULLET = re.compile(r"^\s*[-*•·▪‣⁃–—]\s*$")

#: A line ending mid-phrase. No writer ends a thought on a slash or an
#: ampersand, so these are layout breaks rather than sentence breaks.
_CONTINUES = re.compile(r"[/&,]\s*$|\b(?:and|or|with|of|in|for|the|a|an)\s*$", re.IGNORECASE)

#: EC-2.4: *"if < 30 words survive, prompt for a paste of just the JD."*
MIN_WORDS = 30

#: …but only when normalisation is what removed them.
#:
#: The first version of this refused anything under 30 words and broke 91 tests,
#: which was the right answer to the wrong question. §3.2.1 trap 1 is explicit
#: that *"the 40-word campus JD is the MEDIAN, not the edge case"* — and
#: "Looking for SDE trainees. Good knowledge of DSA and OOPs." is eleven words
#: and a perfectly real posting. The archetype library exists precisely to
#: handle it.
#:
#: EC-2.4 is about an EMAIL THREAD: 400 words of signature, disclaimer and
#: forwarded headers wrapped around 12 words of job. What identifies that case
#: is not the survivor's length, it is the RATIO — a document that lost most of
#: itself to the stripper was mostly not a job description.
SURVIVAL_RATIO = 0.35


def _repeated_lines(lines: list[str]) -> set[str]:
    counts: dict[str, int] = {}
    for line in lines:
        key = " ".join(line.split()).lower()
        if key and len(key) <= MAX_REPEAT_LENGTH:
            counts[key] = counts.get(key, 0) + 1
    return {key for key, count in counts.items() if count >= REPEAT_THRESHOLD}


def strip_boilerplate(text: str) -> str:
    """Remove the furniture, keep the job.

    Two passes over the same lines: the rule list catches what campus emails
    have in common, and the repeat count catches what THIS document repeats.
    Neither alone is enough — the list misses a company's own footer, and the
    count misses a disclaimer that appears once.
    """
    lines = text.splitlines()
    repeated = _repeated_lines(lines)

    kept: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            kept.append("")
            continue
        if _BOILERPLATE_LINE.match(stripped):
            continue
        if " ".join(stripped.split()).lower() in repeated:
            continue
        kept.append(line)

    return "\n".join(kept)


def rejoin_layout(text: str) -> str:
    """Undo the line breaks a PDF column put in, without reflowing prose.

    Two joins, both narrow:

      · a line that is ONLY a bullet glyph takes the next line as its item;
      · a line ending in `/`, `&`, `,` or a dangling conjunction continues.

    Anything else is left alone. Joining every line that does not end in a full
    stop would flatten a two-column layout into one sentence and destroy the
    enumeration structure `_list_lines` reads.
    """
    lines = text.splitlines()
    out: list[str] = []
    index = 0

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if _LONE_BULLET.match(stripped):
            # Find the next non-blank line and attach the glyph to it. Blank
            # lines between a bullet and its text are common in a text layer
            # and mean nothing.
            look = index + 1
            while look < len(lines) and not lines[look].strip():
                look += 1
            if look < len(lines):
                out.append(f"• {lines[look].strip()}")
                index = look + 1
                continue
            index += 1
            continue

        # A run of continuations, joined in one pass — "React /" then "Angular"
        # then "/ Vue" is one item broken twice.
        joined = stripped
        while _CONTINUES.search(joined) and index + 1 < len(lines):
            nxt = lines[index + 1].strip()
            if not nxt or _LONE_BULLET.match(nxt):
                break
            joined = f"{joined} {nxt}"
            index += 1

        out.append(joined)
        index += 1

    return "\n".join(out)


def normalise(text: str) -> str:
    """§6.1's whole stage: layout first, then furniture.

    Order matters. Stripping first would leave a lone bullet whose item was a
    footer, and rejoining first means a boilerplate line arrives whole and gets
    matched as one.
    """
    return strip_boilerplate(rejoin_layout(text)).strip()


def too_thin(original: str, normalised: str) -> bool:
    """EC-2.4: was the job description the smaller part of what arrived?

    Two conditions, and both are needed. A short document that survives intact
    is a terse posting and the archetype backfills it. A long document that
    normalises down to nothing was an email with a job mentioned in it, and
    parsing the remainder gives three requirements off a disclaimer.
    """
    surviving = len(normalised.split())
    if surviving >= MIN_WORDS:
        return False

    started_with = len(original.split())
    if started_with < MIN_WORDS:
        # It was always short. That is allowed — see `SURVIVAL_RATIO`.
        return False

    return surviving < started_with * SURVIVAL_RATIO
