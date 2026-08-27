"""The model reads the posting; the posting decides what counts (§6.2).

── Why a model, when the lexicon already scores 0.857 ──────────────────────────

Because of WHERE the remaining errors are. The deterministic extractor scores
1.000 on seven of twelve golden documents and 0.000 on this one:

    "You will write SQL against our warehouse, build dashboards in Tableau,
     and present findings to business stakeholders."

No heading, no bullet, and no delimiter pattern that separates it from any
other sentence containing commas. A wider regex reads prose as a list; a
narrower one reads that as prose. The rule does not exist. Adding lexicon
entries is how a parser stays one posting behind for ever, which is the failure
this module has hit four separate times in a day: a heading vocabulary that did
not know "Technologies & Skills", an eligibility filter that did not know
"standing arrears", a batch pattern that did not know "graduating in 2027", a
branch matcher that thought "AI/ML" was a branch.

── What makes it safe: the model proposes, it does not decide ──────────────────

**Every proposed requirement must verbatim-resolve to a span in the document.**
If `requirement_pattern(label).search(text)` finds nothing, the label is
DROPPED — not stored with `span=None`, not stored at all.

That is stricter than §6.2, which says non-resolving requirements are "kept but
marked". It is stricter on purpose. This module already has a home for
requirements the document does not state: the archetype backfill, where they
carry `source="archetype"`, weigh 0.75, and say "standard for this role" on the
screen. A model's paraphrase entering as `source="jd"` would be a sentence
attributed to a company that never wrote it, and every downstream module treats
`source="jd"` as ground truth.

So the model can only ever point AT the document. It cannot add to it. That
turns the interesting failure mode — hallucination — into a dropped row and a
log line, and it costs nothing in the case the model is right, because a
requirement that is really in the posting resolves by construction.

── And it does not replace the lexicon, it joins it ────────────────────────────

§6.2: *"Disjunction detection is ALSO run as a deterministic regex pass and
merged with the LLM's groups — belt and braces, because getting this wrong is
visible and embarrassing."* The same reasoning applies to the requirements
themselves. The two passes fail differently:

    the lexicon    misses prose, never invents
    the model      reads prose, would invent if allowed to

Union, deduplicated, span-checked. The lexicon is the floor and the model is
the ceiling, and Rule 2 falls back to the floor with no key configured — which
is CI, a fresh clone, and any deployment that chooses not to pay for a model.
"""

from __future__ import annotations

import logging
import re

from backend_M02_JD_Parser import llm
from backend_M02_JD_Parser.extract import (
    _acceptable,
    _clean,
    _list_lines,
    requirement_pattern,
)
from backend_M02_JD_Parser.safety import as_untrusted_data

log = logging.getLogger("uvicorn.error")

#: Language that means a sentence is about what the CANDIDATE must have.
#:
#: A triage filter, not an extraction one, and the distinction is what makes a
#: word list acceptable here. Deciding whether a sentence names a requirement is
#: the model's job precisely because no list can do it. Deciding whether a
#: sentence is even addressed to the candidate is cheap, and being wrong costs
#: nothing dangerous: the deterministic pass has already read the whole
#: document, so a line dropped here is one the lexicon already had its chance
#: at.
_ABOUT_THE_CANDIDATE = re.compile(
    r"\b(?:you|your|candidate|applicant|student|we\s+(?:are\s+)?(?:look|seek|expect|want)"
    r"|require|required|requirement|must|should|expect|"
    r"experience|knowledge|skill|proficien|familiar|understand|expos|"
    r"ability|able|comfortable|hands.on|work(?:ing)?\s+(?:with|on|in)|"
    r"strong|solid|good|excellent|prefer)\w*",
    re.IGNORECASE,
)

#: A ceiling on the PROSE sent to the model, not on the document.
#:
#: Sized well under the context window on purpose. `gpt-oss` emits reasoning
#: tokens that are billed and counted but never returned as content, so a large
#: prompt spends its budget thinking and returns an empty completion — which is
#: exactly what the real 12,446-character brochure produced: HTTP 400,
#: `json_validate_failed`, `failed_generation: ""`.
#:
#: Lowered again to 2,500 once the failure was measured properly: the binding
#: constraint is tokens per MINUTE, not context, because most of a completion
#: is reasoning. 2,000 characters of triaged prose returned 28 requirements;
#: 4,000 returned HTTP 429.
MAX_CHARS = 2_500

#: Lines shorter than this carry no prose worth a model call — they are
#: headings, fragments and table cells the lexicon has already read.
MIN_PROSE_WORDS = 6

#: More than this from one posting and the model is describing rather than
#: extracting. The largest golden document states sixteen.
MAX_PROPOSALS = 40

_SYSTEM = """You extract job requirements from a job description.

Return ONLY skills, technologies, tools, and named competencies that the \
document explicitly mentions. Copy each one EXACTLY as it is written in the \
document — same words, same spelling, same case. Do not translate, expand \
abbreviations, normalise, or invent.

Rules:
- A requirement is a NOUN PHRASE naming a thing: "Python", "System design", \
"communication". Never a verb phrase describing an activity: not "Build \
pipelines", not "Design solutions".
- Skip eligibility criteria: CGPA, backlogs, batch year, degree, branch, bond, \
package, location. Those are handled elsewhere.
- Skip company marketing, awards, the selection process, and legal notices.
- Skip responsibilities written as instructions to the employee.
- If the document offers a choice ("Java or Python"), list each alternative \
separately.

If the document names no requirements, return an empty list."""


def prose_of(text: str) -> str:
    """The lines the lexicon did NOT claim.

    This is the whole idea. `_list_lines` returns everything that enumerates —
    bullets, delimited runs, anything under a heading — and the lexicon reads
    those well. What is left is prose, which is the one thing no regex
    separates from a list of requirements, and therefore the only part worth
    paying a model to read.

    Two things fall out of it. The prompt shrinks to a fraction of a brochure,
    which is what stops the reasoning budget swallowing the answer. And the
    model is asked the question it is actually better at, instead of being
    asked to re-do work that is already correct.
    """
    claimed = {" ".join(line.split()) for line in _list_lines(text)}
    kept = [
        line
        for raw in text.splitlines()
        if (line := raw.strip())
        and " ".join(line.split()) not in claimed
        and len(line.split()) >= MIN_PROSE_WORDS
        # Triage. Half a brochure's prose is awards and marketing, which costs
        # tokens and contains no requirement.
        and _ABOUT_THE_CANDIDATE.search(line)
    ]
    return "\n".join(kept)[:MAX_CHARS]


def _user(prose: str) -> str:
    return "Extract the requirements from this job description.\n\n" + as_untrusted_data(prose)


_SCHEMA = {
    "type": "object",
    "properties": {
        "requirements": {
            "type": "array",
            "items": {"type": "string"},
        }
    },
    "required": ["requirements"],
    "additionalProperties": False,
}


def propose(text: str) -> tuple[list[str], str]:
    """Requirement labels the model found AND the document confirms.

    Returns `(labels, reason)`. `reason` is empty on success and says why on
    every failure — no key, timeout, bad JSON, schema violation — because "why
    is this posting's list thin?" should be answerable without reading code.

    A label survives only if:

      · `_acceptable` would accept it, so the model cannot bypass the
        eligibility filter or the word cap the lexicon obeys; and
      · `requirement_pattern` finds it in the document, verbatim.

    The second is the one that matters. It is the difference between a model
    that reads a posting and a model that writes one.
    """
    client = llm.get_llm()
    if not client.available:
        return [], "no model configured"

    prose = prose_of(text)
    if not prose.strip():
        # Every line in this posting enumerates, so the lexicon has read all of
        # it and there is nothing left for a model to add. Not a failure: a
        # well-structured JD is the case the deterministic pass is best at.
        return [], ""

    result = client.structured(
        job=llm.JOB_EXTRACT,
        system=_SYSTEM,
        user=_user(prose),
        schema=_SCHEMA,
    )
    if not result.ok or not result.data:
        return [], result.reason or "model returned nothing"

    raw = result.data.get("requirements") or []
    if not isinstance(raw, list):
        return [], "model returned a non-list"

    kept: list[str] = []
    dropped: list[str] = []
    seen: set[str] = set()

    for item in raw[:MAX_PROPOSALS]:
        if not isinstance(item, str):
            continue
        label = _clean(item)
        if not label or not _acceptable(label):
            dropped.append(item)
            continue
        # The document decides. A label the model produced that is not in the
        # posting is a paraphrase at best, and `source="jd"` is a claim about
        # what the company wrote.
        if requirement_pattern(label).search(text) is None:
            dropped.append(item)
            continue
        key = label.casefold()
        if key in seen:
            continue
        seen.add(key)
        kept.append(label)

    if dropped:
        # Worth a line: a model that starts paraphrasing shows up here as a
        # rising drop count long before anybody notices thin requirement lists.
        log.info(
            "M02 dropped %d of %d model proposals (not verbatim in the document): %s",
            len(dropped),
            len(raw),
            ", ".join(repr(d) for d in dropped[:5]),
        )

    return kept, ""


def merge(lexicon: list[str], proposed: list[str]) -> list[str]:
    """Both passes, deduplicated, lexicon first.

    §6.2 runs the deterministic pass alongside the model and merges — "belt and
    braces, because getting this wrong is visible and embarrassing". The two
    fail differently, which is the whole reason to keep both: the lexicon
    misses prose and never invents, the model reads prose and would invent if
    the span check let it.

    Lexicon order first so document order is preserved for everything the
    deterministic pass found, and the model's additions land after. `locate`
    re-sorts by position anyway, so this only decides tie-breaks.
    """
    seen = {label.casefold() for label in lexicon}
    return [*lexicon, *(label for label in proposed if label.casefold() not in seen)]
