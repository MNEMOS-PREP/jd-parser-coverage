"""What script a posting is written in (EC-2.6).

§12 EC-2.6: *"JD in Hindi/Tamil — detect, translate for parsing, keep the
original for display."*

Until now nothing detected anything. A Devanagari posting went through the
whole pipeline, matched no lexicon entry, extracted nothing, and produced a
clean screen saying the job asks for no skills — which is the §3.2.1 failure
this module is most careful about everywhere else and was making silently here.

── Detect, yes. Translate, no — and that is a decision, not a gap ──────────────

The edge case asks for translation, and translating would break the contract
the rest of the module is built on. Every requirement carries a `SourceSpan`
into `raw_text`, and §5's promise is that a student can be shown the line the
company wrote. Offsets into a translation point at text no company published,
so a translated parse either loses provenance or cites a sentence that does not
exist.

It is also unnecessary. The §6.2 model pass landed on 2026-08-27 and reads Hindi
without being asked to, so the extraction that matters already works on the
original — which is exactly why the spans must stay pointed at the original.

So this module detects, records, and says so on the screen. What a non-Latin
posting loses is the deterministic lexicon tier, not the parse.

── Why Unicode blocks and not a language library ──────────────────────────────

`langdetect` and friends are a wheel to install, a model to load, and a
probability to interpret, in exchange for distinguishing Hindi from Marathi —
two languages that share a script and, for this module's purposes, share an
answer. Script is the resolution the decision actually needs: the lexicon is
Latin, so the question is whether the posting is.

Counting characters in a Unicode range is exact, needs nothing, and runs in
microseconds on a document this size.
"""

from __future__ import annotations

import unicodedata

#: Script name -> the Unicode ranges that identify it.
#:
#: The eight scripts a campus in India actually receives postings in, plus
#: Latin. Not a language list — Hindi and Marathi are both Devanagari and this
#: module has one answer for both.
_RANGES: tuple[tuple[str, tuple[tuple[int, int], ...]], ...] = (
    ("latin", ((0x0041, 0x005A), (0x0061, 0x007A), (0x00C0, 0x024F))),
    ("devanagari", ((0x0900, 0x097F), (0xA8E0, 0xA8FF))),
    ("bengali", ((0x0980, 0x09FF),)),
    ("gurmukhi", ((0x0A00, 0x0A7F),)),
    ("gujarati", ((0x0A80, 0x0AFF),)),
    ("odia", ((0x0B00, 0x0B7F),)),
    ("tamil", ((0x0B80, 0x0BFF),)),
    ("telugu", ((0x0C00, 0x0C7F),)),
    ("kannada", ((0x0C80, 0x0CFF),)),
    ("malayalam", ((0x0D00, 0x0D7F),)),
)

#: Share of letters that must be non-Latin before the posting is called
#: non-Latin.
#:
#: Not a majority. A campus posting written in Hindi still carries "Java",
#: "SQL" and the company's own name in Latin, and a real one seen at 40%
#: Devanagari is a Hindi posting by any reading. The threshold answers "is the
#: Latin lexicon going to be enough", and at a fifth of the document it is
#: already not.
NON_LATIN_SHARE = 0.20


def script_counts(text: str) -> dict[str, int]:
    """How many letters of each script the text contains.

    Letters only. Digits, punctuation and whitespace are script-neutral and
    counting them would dilute every share by however much formatting the PDF
    happened to carry.
    """
    counts: dict[str, int] = {}
    for char in text:
        if not unicodedata.category(char).startswith("L"):
            continue
        code = ord(char)
        for name, ranges in _RANGES:
            if any(low <= code <= high for low, high in ranges):
                counts[name] = counts.get(name, 0) + 1
                break
    return counts


def dominant_script(text: str) -> tuple[str, float]:
    """The script this posting is written in, and how much of it that is.

    Returns `("latin", share)` for an ordinary posting. The share is of LETTERS,
    so a document that is mostly a salary table does not read as scriptless.

    An empty or digits-only document is `("latin", 1.0)`: there is nothing to
    detect, and calling that "unknown" would put a warning on a screen about a
    document that has no problem.
    """
    counts = script_counts(text)
    total = sum(counts.values())
    if not total:
        return "latin", 1.0

    non_latin = {name: n for name, n in counts.items() if name != "latin"}
    if non_latin:
        best, count = max(non_latin.items(), key=lambda pair: pair[1])
        share = count / total
        if share >= NON_LATIN_SHARE:
            return best, round(share, 3)

    return "latin", round(counts.get("latin", 0) / total, 3)


def note_for(script: str, share: float) -> str:
    """What the screen says, in words a student can act on.

    Names what still works rather than only what does not — the posting is
    parsed, and the deterministic tier is the part that is thin. A message that
    said "unsupported language" would tell a student to give up on a page that
    is about to show them requirements.
    """
    if script == "latin":
        return ""
    return (
        f"This posting is written mostly in {script.title()} "
        f"({int(share * 100)}% of its letters). We read it as written and the "
        "requirements below come from the posting itself — but our skill "
        "dictionary is English, so we may have missed some. Worth checking the "
        "list against the original."
    )
