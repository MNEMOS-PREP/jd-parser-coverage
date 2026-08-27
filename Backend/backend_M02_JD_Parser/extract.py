"""Surface forms: what the document actually says, before anything resolves it.

── Written twice, on purpose, for now ──────────────────────────────────────────

This file is byte-identical to M01's `extract.py`. It belongs in
`ai_core.concepts`, whose own docstring already names both callers - "M01 maps
resume surface forms to concept ids, M02 maps JD requirements to concept ids" -
and says the normalisation "has to be identical on both sides of that call".

It is not there yet because `ai_core` is pinned by git tag in six modules, so
moving it means a release, a tag and six reinstalls, and because this platform
promotes a contract to core AFTER it has been written twice rather than before.
This is the second writing. It is now due, and it is the next Platform_Core
bump.

── The bug this file exists to fix ─────────────────────────────────────────────

The previous extraction ran the wrong way round. It walked M04's 120 concepts
and regex-matched each concept's name and aliases against the document, which
means it could only ever return things that were already in the ontology. Two
consequences, both bad, both measured before this was written:

  1. Anything the student wrote that is not an ontology concept was INVISIBLE.
     The ontology holds interview concepts - binary search, normalisation,
     asking clarifying questions - not technologies. A SKILLS line reading
     "Python, Java, C++, React, Node.js, Docker, Kubernetes, AWS, TensorFlow,
     PyTorch, PostgreSQL, MongoDB, Git, Linux" produced no skills at all,
     byte-identical to submitting an empty string. A JD listing Python, SQL,
     data structures, algorithms, Docker, Kubernetes, Java and Go produced
     exactly one requirement: SQL Queries.

  2. `unresolved_skills` was structurally unreachable. Labels only entered the
     loop by coming FROM M04, and were then handed back to M04 to resolve, so
     they resolved by construction. The module's stated promise - "skills the
     ontology cannot map are kept rather than dropped" - could never fire,
     because nothing was ever detected to keep. The frontend has always had a
     hatched group ready to render those. It has never had one to render.

So extraction now reads the document first and resolves second, which is the
order the specification describes and the only order in which "we could not
map this" is a thing the module is able to say.

── Ambiguity, and why single words are treated differently ─────────────────────

Scanning prose for ontology aliases is still useful - a project bullet saying
"using dynamic programming" is real evidence - but 25 of the ontology's aliases
are also ordinary English words. Measured against the live ontology, the old
scan produced:

    "Full stack developer. Class of 2026. Worked within the scope of a team."
        -> Classes and Objects, Functions and Scope, Stacks

    "A solid communicator who avoids guessing."
        -> SOLID Principles, Handling What You Don't Know

Those are not near-misses; they are requirements invented out of adjectives,
and downstream they would become interview questions. The rule here is
structural rather than a hand-maintained blocklist that drifts as the ontology
grows: a MULTI-WORD alias may match anywhere, because "dynamic programming" in
running text means what it says, while a SINGLE-WORD alias that is also an
everyday English word may only be matched where the document is enumerating -
inside a skills or requirements list, where "stack" is a claim and not an
adjective.
"""

from __future__ import annotations

import re
from typing import Any

from ai_core.concepts import normalise_alias
from pydantic import BaseModel, Field, computed_field

from backend_M02_JD_Parser.classify import kind_of, measured_by, seniority_of

#: Longer than this and it is a sentence, not a skill. Five words admits
#: "object oriented programming in java" and rejects a project bullet.
MAX_WORDS = 5

#: Headings that introduce an enumeration. The list is deliberately about the
#: SHAPE of the document rather than about any one resume template - every one
#: of these is a word that means "what follows is a list".
_HEADINGS = (
    "skills",
    "technical skills",
    "core skills",
    "key skills",
    "technology",
    "technologies",
    "tech stack",
    "tools",
    "tooling",
    "languages",
    "programming languages",
    "frameworks",
    "libraries",
    "competencies",
    "core competencies",
    "areas of expertise",
    "expertise",
    "requirements",
    "required",
    "required skills",
    "must have",
    "must haves",
    "nice to have",
    "good to have",
    "preferred",
    "preferred skills",
    "qualifications",
    "you will need",
    "what we are looking for",
    # A placement mail labels the requirements block "JD:" and nothing else.
    # Without this, "JD: Good knowledge of DSA, OOPs, DBMS." reads as prose and
    # a whole posting's requirements are invisible.
    "jd",
    "job description",
    "job role",
    # NOT "responsibilities". The TODO said so before this was tried and was
    # right: a responsibilities block is written in VERBS — "Build and
    # orchestrate multi-agent AI systems", "Design AI-native solutions" — and
    # `_split_conjunctions` turns each into "Build", "Design", "Deploy". On the
    # real brochure that produced sixteen requirements that are not things,
    # they are instructions to the person doing the job.
    #
    # Reading them properly needs a label-level test of *does this name a thing
    # rather than an action*, which does not exist. Until it does, the section
    # stays unread — a missing requirement is visible as a thin list, an
    # invented one becomes an interview question about a verb.
    "desired skills",
    "technical skills required",
    "eligibility",
    "eligibility criteria",
)

#: A heading is the whole line ("SKILLS"), or a label with an explicit
#: separator ("Required: Python, SQL"). Without the separator requirement,
#: "Preferred candidates will have a degree" parses as a list of one skill
#: called "candidates will have a degree".
_HEADING_RE = re.compile(
    r"^\s*(?:[-*•·]\s*)?(" + "|".join(re.escape(h) for h in _HEADINGS) + r")"
    r"\s*(?:[:–\-]\s*(.*))?\s*$",
    re.IGNORECASE,
)

#: A COMPOUND heading: "Languages & Frameworks", "Technologies & Skills",
#: "Cloud & DevOps", "Additional skills".
#:
#: `_HEADING_RE` above wants the heading word to be the whole line, and real
#: documents write two of them joined. Cognizant's brochure lays its skills out
#: as a table whose left column reads "Languages & Frameworks" and whose right
#: column is the actual list — and the parser only ever saw those lists because
#: the PDF text layer happened to break the heading into "Languages &" and
#: "Frameworks", the second of which matched by itself.
#:
#: Fixing the layout damage (§6.1) removed that accident and took forty real
#: requirements with it. This is the rule that should have been carrying them.
#:
#: Deliberately narrow: a heading word, at most five words total, and NO
#: sentence-ending punctuation. "Preferred candidates will have a degree" is
#: seven words and keeps its full stop, so it stays prose — which is the exact
#: failure `_HEADING_RE`'s separator requirement was written to prevent.
_HEADING_WORDS = re.compile(
    r"(?<![\w-])(?:" + "|".join(re.escape(h) for h in _HEADINGS) + r")(?![\w-])",
    re.IGNORECASE,
)


#: Headings that may introduce an INLINE list and never open a bare one.
#:
#: A placement mail writes "JD: Good knowledge of DSA, OOPs, DBMS." — the
#: requirements are on the same line and that is the only form worth reading.
#: A brochure writes "Job description" as a section header over a
#: RESPONSIBILITIES table, and opening a list there produces "Build", "Design",
#: "Deploy" — verbs, sixteen of them, none of which is a thing anybody has.
#:
#: The distinction is already in the parse: a heading with a remainder is
#: inline, one without opens the lines below it. These simply decline the
#: second job.
_INLINE_ONLY = frozenset({"jd", "job description", "job role"})


def _looks_like_a_heading(line: str) -> bool:
    stripped = line.strip().rstrip(":")
    if not stripped or stripped.endswith((".", "!", "?")):
        return False
    words = stripped.split()
    if not 1 <= len(words) <= 5:
        return False
    return bool(_HEADING_WORDS.search(stripped))


#: Commas, semicolons, pipes and bullets separate list items. NOT the forward
#: slash: "CI/CD" and "TCP/IP" are single names far more often than
#: "React/Angular" is two, and a wrong split is a fabricated skill.
#: A sentence boundary ends a list item too - "SQL and data structures. Docker
#: is a plus" is two requirements. Matched as a period FOLLOWED BY SPACE, so
#: "Node.js", "B.Tech" and ".NET" survive intact.
_DELIMITERS = re.compile(r"[,;|•·]|\.\s+")

#: "strong Python" is a claim about Python. Strip the adverbial run-up so the
#: label that reaches the resolver is the thing being claimed.
_LEADING_NOISE = re.compile(
    r"^(?:and|or|either|both|any\s+of|one\s+of|at\s+least|with|in|using|strong|"
    r"solid|good|excellent|deep|basic|advanced|"
    r"working|solid\s+grasp\s+of|hands[-\s]?on|proficiency\s+(?:in|with)|"
    r"proficient\s+(?:in|with)|experience\s+(?:with|in|of)|familiarity\s+with|"
    r"knowledge\s+of|understanding\s+of|exposure\s+to|expertise\s+in|"
    r"comfortable\s+with|fluent\s+in|grasp\s+of|"
    # "programming skills in Java", "coding skills with Python". The run-up is
    # about the student's relationship to the thing; the thing is the label.
    r"(?:\w+\s+)?skills?\s+(?:in|with)|(?:\w+\s+)?background\s+(?:in|with)|"
    # "Must be a team player", "Should have a go-getter attitude", "Ability to
    # work in teams". The claim is the noun at the end; everything before it
    # describes the student's relationship to it, and `necessity` already
    # carries that separately.
    r"must\s+be(?:\s+an?)?|should\s+be(?:\s+an?)?|must\s+have(?:\s+an?)?|"
    r"should\s+have(?:\s+an?)?|ability\s+to|able\s+to|willing(?:ness)?\s+to|"
    r"any\s+one\s+of|at\s+least\s+one\s+of|"
    # A bare article last, because `_clean` peels one layer per pass and "A
    # go-getter attitude" only reaches this once nothing else matches.
    r"an?|the)\s+",
    re.IGNORECASE,
)

_TRAILING_NOISE = re.compile(
    r"\s*(?:\((?:optional|preferred|a\s+plus|nice\s+to\s+have|good\s+to\s+have)\)|"
    r"is\s+a\s+plus|a\s+plus|is\s+required|required|preferred|optional|"
    r"is\s+a\s+must|a\s+must|etc\.?|and\s+more|or\s+similar|or\s+equivalent)\s*$",
    re.IGNORECASE,
)

#: "(GitHub Copilot" and "Claude)" are one parenthetical that a comma split
#: in half, and "& cloud-native services" is the tail of a joined line. An
#: unpaired bracket or a leading conjunction is punctuation, not part of a
#: technology's name.
_PUNCT_EDGES = re.compile(r"^[\s\-–•·.:;()\[\]&]+|[\s.:;,()\[\]&]+$")

#: Eligibility, not skill. "Must have 2+ years" and "B.Tech with 7.0 CGPA" are
#: real requirements and they belong in a structured eligibility field - which
#: is a separate, unbuilt FR. Filing them under skills would put a number the
#: ontology can never resolve into the "we could not map this" list forever.
_ELIGIBILITY = re.compile(
    r"\b\d+\s*\+?\s*(?:years?|yrs?|months?)\b|\bcgpa\b|\bb\.?\s?tech\b|"
    r"\bdegrees?\b|\bmust\s+have\b|\bminimum\b|\bgraduat\w*\b|\bbatch\s+of\b|"
    r"\bm\.?\s?tech\b|\bmca\b|\bbca\b|\barrears?\b|"
    # "2027 batch" and "no active backlogs" both survived as REQUIREMENTS once
    # an unheaded line could enumerate — the filter knew "batch of" and not
    # "2027 batch", and did not know "backlog" at all.
    r"\b20\d{2}\s+batch\b|\bbacklogs?\b|\bbond\b|\blpa\b|\bpackage\b|"
    # A bare "Tech" is what is left of "B.E/B. Tech/M.E/M. Tech degrees" after
    # the sentence splitter has had it. It is never a requirement on its own —
    # the real ones are named technologies, and "Tech Stack" is consumed as a
    # heading long before it reaches here. Word-anchored, so "FinTech" is
    # untouched.
    r"\btech\b",
    re.IGNORECASE,
)

#: A run of engineering branch codes: "CSE/IT/ECE", "CSE, IT and ECE".
#:
#: This survived as a REQUIREMENT called "CSE/IT/ECE" — a skill nobody has and
#: no ontology holds, sitting in the unmapped queue for ever. The codes are
#: spelled out here rather than reusing `_BRANCHES` because that table is
#: defined with the eligibility parser at the bottom of this file, and
#: `_acceptable` runs long before it.
_BRANCH_RUN = re.compile(
    r"^(?:CSE|IT|ISE|IS|ECE|EEE|EIE|MECH|CIVIL|AIDS|AIML|CSBS|MCA|BCA)"
    r"(?:\s*[/,&]\s*|\s+and\s+|\s+or\s+)"
    r"(?:CSE|IT|ISE|IS|ECE|EEE|EIE|MECH|CIVIL|AIDS|AIML|CSBS|MCA|BCA)"
    r"(?:(?:\s*[/,&]\s*|\s+and\s+|\s+or\s+)"
    r"(?:CSE|IT|ISE|IS|ECE|EEE|EIE|MECH|CIVIL|AIDS|AIML|CSBS|MCA|BCA))*"
    r"\s*(?:only|branches?|students?)?$",
    re.IGNORECASE,
)

#: Fragments that are never a skill however they are punctuated.
_NOISE_FORMS = frozenset(
    {"", "etc", "and", "or", "others", "more", "n a", "na", "tbd", "various", "any"}
)

#: Ontology aliases that are also ordinary English. A single-word alias in this
#: set is only trusted inside an enumeration, never in running prose. Derived
#: from the live 120-concept ontology and kept a little wider than today's
#: collisions, so a new alias does not silently start matching adjectives.
_COMMON_ENGLISH = frozenset(
    """
    solid class classes scope stack stacks interface interfaces grid certificate
    guessing pace precision security functions keys memory state search sort merge
    views tables lists sets processes joins extends array arrays heap heaps
    structuring threads tuning exceptions tries pointers index indexes scheduling
    """.split()
)


def prose_safe_alias(alias: str) -> bool:
    """May this alias be matched in running prose, or only inside a list?

    Multi-word aliases carry their own disambiguation. Single words do not, and
    the everyday ones are how "a solid communicator" became a SOLID Principles
    requirement.
    """
    normalised = normalise_alias(alias)
    if not normalised:
        return False
    if " " in normalised:
        return True
    return normalised not in _COMMON_ENGLISH


def _clean(fragment: str) -> str:
    """One raw list item to the label a resolver should be asked about."""
    text = _PUNCT_EDGES.sub("", fragment)
    # Repeat: "strong hands-on experience with Python" peels one layer per pass.
    for pattern in (_LEADING_NOISE, _TRAILING_NOISE):
        while True:
            stripped = pattern.sub("", text).strip()
            if stripped == text:
                break
            text = stripped
    return _PUNCT_EDGES.sub("", text).strip()


def _acceptable(label: str) -> bool:
    if normalise_alias(label) in _NOISE_FORMS:
        return False
    if _ELIGIBILITY.search(label):
        return False
    if _BRANCH_RUN.match(label.strip()):
        return False
    words = label.split()
    if not words or len(words) > MAX_WORDS:
        return False
    # A fragment with no letters at all is a date, a percentage or a phone
    # number that survived the split.
    return any(ch.isalpha() for ch in label)


def _split_conjunctions(label: str) -> list[str]:
    """ "SQL and data structures" -> the whole, plus each side.

    Both are kept. Which one survives is decided after resolution, by the
    caller, because "Transactions and ACID" is a real concept name and
    "SQL and data structures" is two - and only the resolver knows which.
    """
    parts = re.split(r"\s+(?:and|or)\s+", label, flags=re.IGNORECASE)
    if len(parts) < 2:
        return []
    # Cleaned BEFORE the length cap. "programming skills in Java" is four words
    # and was dropped for it; the four words are a run-up to one, and peeling
    # the run-up first is the difference between extracting Java and losing it.
    cleaned = [_clean(part) for part in parts]
    return [part for part in cleaned if part and len(part.split()) <= 3]


#: A line that opens with a list glyph. §3.2.2 of M01's spec calls bullet
#: detection "a line-classification problem, not a character match", and this is
#: the classification half a JD needs: the marker says "what follows is an item"
#: regardless of how many words the item takes.
_BULLET = re.compile(r"^\s*(?:[-*•·▪‣⁃]|\d+[.)]|[a-z][.)])\s+", re.IGNORECASE)


#: How many words a fragment may have before it stops looking like a list item.
#:
#: Tighter than `MAX_WORDS`, and deliberately: this is the test applied with NO
#: heading vouching for the line, so it has to carry the whole decision alone.
_ENUMERATION_ITEM_WORDS = 3

#: How many delimited fragments make a run look enumerated rather than written.
_ENUMERATION_MIN_ITEMS = 3

#: Longer than this and the line is a sentence, not a list — however many
#: commas it happens to contain.
_ENUMERATION_MAX_LINE_WORDS = 12


def _reads_as_a_list(line: str) -> bool:
    """Does this line enumerate, with nothing above it saying so?

    Three of the twelve golden documents extracted NOTHING before this existed,
    and the first of them is the posting §3.2.1 calls the MEDIAN campus JD:

        "Looking for SDE trainees. Good knowledge of DSA, OOPs and DBMS."

    No heading, so `_list_lines` never entered list mode, so the three
    requirements in that sentence were invisible. The archetype backfill hid it
    at the API level by supplying eight standard ones — which is worse than it
    sounds, because the posting's OWN requirements were the ones being replaced.

    The rule is structural rather than lexical: several delimited fragments,
    each short. That is what a list looks like when nobody labelled it.

        "Good knowledge of DSA, OOPs and DBMS."       -> DSA / OOPs / DBMS
        "write SQL against our warehouse, build       -> fragments of five and
         dashboards in Tableau, and present               seven words
         findings to business stakeholders."

    The second is prose with commas in it, and the word cap is the only thing
    separating them. Set at three rather than five because there is no heading
    vouching for this line — the test carries the decision by itself, and the
    cost of getting it wrong is a fabricated requirement.
    """
    # A whole LINE this long is a sentence, whatever punctuation is in it.
    #
    # This cap is the one that matters, and a twelve-document corpus could not
    # find it: every golden posting is short, so none of them contains a long
    # prose sentence with commas. The real 365-line brochure does, and without
    # this the rule took it from 49 requirements to 139 — "data", "quality",
    # "operations", "Build", "Design", "Beyond delivering working", all cut out
    # of one sentence about delivering solutions across software and data.
    if len(line.split()) > _ENUMERATION_MAX_LINE_WORDS:
        return False

    fragments = [_clean(fragment) for fragment in _DELIMITERS.split(line)]
    fragments = [fragment for fragment in fragments if fragment]
    if len(fragments) < _ENUMERATION_MIN_ITEMS:
        return False

    short = sum(1 for fragment in fragments if len(fragment.split()) <= _ENUMERATION_ITEM_WORDS)
    # Most of them, not all: "Good knowledge of DSA" cleans to "DSA" but a
    # trailing "and DBMS." can arrive with punctuation still attached.
    if short < len(fragments) - 1:
        return False

    # And the items have to look like NAMES. Postings capitalise their
    # technologies — DSA, OOPs, DBMS, Docker — and the prose that fools the
    # length tests does not: "software, data, infrastructure, quality".
    #
    # The same test as the one guarding over-long fragments, for the same
    # reason: with no heading vouching for this line, a wrong answer here
    # fabricates a requirement, and fabricating is worse than missing.
    named = sum(1 for fragment in fragments if any(ch.isupper() for ch in fragment))
    return named >= len(fragments) - 1


def _list_lines(text: str) -> list[str]:
    """The lines of the document that are enumerating something."""
    lines = text.splitlines()
    out: list[str] = []
    in_list = False
    #: Whether anything has actually been collected since the heading opened.
    #:
    #: A blank line closes a list, which is right — it is what stops one
    #: section's items running into the next. But a blank line between a
    #: HEADING and its first item closes nothing, because nothing has started,
    #: and a PDF text layer puts one there constantly:
    #:
    #:     'Technologies & Skills'
    #:     ''
    #:     'Python, Java / .NET, JavaScript / TypeScript, React / Angular'
    #:
    #: That cost the entire skills table of a real brochure. The list opened,
    #: the blank immediately closed it, and the line holding six technologies
    #: was read as prose.
    started = False

    for line in lines:
        if not line.strip():
            if started:
                in_list = False
            continue

        heading = _HEADING_RE.match(line)
        if heading is None and _looks_like_a_heading(line):
            # A compound heading — "Technologies & Skills" — opens a list the
            # same way a bare "Skills" does. No remainder to split off, because
            # a compound heading names the section rather than introducing an
            # inline list.
            in_list = True
            started = False
            continue
        if heading:
            remainder = (heading.group(2) or "").strip()
            if remainder:
                # "Required: Python, SQL" - the list is on the heading line.
                out.append(remainder)
                in_list = False
            elif heading.group(1).strip().lower() in _INLINE_ONLY:
                # "Job description" over a responsibilities table. Named, and
                # deliberately not opened. See `_INLINE_ONLY`.
                in_list = False
            else:
                # "SKILLS" alone - the list is on the lines that follow.
                in_list = True
                started = False
            continue

        if in_list:
            # A BULLET is the enumeration signal, whatever its length.
            #
            # This rule came from M01, where it is right: under a resume's
            # SKILLS heading, a long undelimited line is prose and treating it
            # as a skill list produces nonsense. A job description is the
            # opposite. Its requirements are written as sentences on purpose —
            #
            #     - Experience with Docker and Kubernetes
            #
            # is six tokens with no delimiter, so it extracted NOTHING and two
            # real requirements were silently lost. Everything downstream then
            # operates on a requirement set the posting does not have.
            #
            # `_clean` already knows what to do with it: `_LEADING_NOISE`
            # strips "Experience with", `_split_conjunctions` gives Docker and
            # Kubernetes, and a genuinely prose bullet ("We are looking for
            # someone who thrives in ambiguity") still yields nothing, because
            # it survives `_clean` as one label of more than MAX_WORDS words
            # and `_acceptable` refuses it. The word cap moved from the LINE,
            # where it was throwing away requirements, to the LABEL, where it
            # was already doing the work.
            if _BULLET.match(line) or _DELIMITERS.search(line) or len(line.split()) <= MAX_WORDS:
                out.append(line)
                started = True
            else:
                in_list = False
            continue

        # No heading above it, and it still enumerates. See `_reads_as_a_list`.
        if _reads_as_a_list(line):
            out.append(line)

    return out


def extract_surface_forms(text: str) -> list[str]:
    """Every skill-shaped phrase the document actually contains, in order.

    These are the STUDENT'S words, not the ontology's. Some will resolve to a
    concept and some will not, and the ones that do not are the whole point:
    they are what `unresolved_skills` was always meant to hold.
    """
    seen: set[str] = set()
    forms: list[str] = []

    def add(label: str) -> None:
        cleaned = _clean(label)
        if not _acceptable(cleaned):
            return
        key = normalise_alias(cleaned)
        if key in seen:
            return
        seen.add(key)
        forms.append(cleaned)

    for line in _list_lines(text):
        for fragment in _DELIMITERS.split(line):
            cleaned = _clean(fragment)
            if _acceptable(cleaned):
                add(cleaned)
                for part in _split_conjunctions(cleaned):
                    add(part)
                continue

            # Too long to BE a label, which does not mean it contains none.
            # `- Strong programming skills in Java or Python` cleans to six
            # words, `_acceptable` refuses it for the cap, and both
            # alternatives went with it — the single most important line on the
            # posting, gone.
            #
            # But this is also where prose lives, and the first attempt at this
            # turned "…thrives in ambiguity and enjoys mentoring juniors" into
            # a skill called "enjoys mentoring juniors". Recovering a real
            # requirement is not worth inventing one; that trade is the wrong
            # way round and this module says so everywhere else.
            #
            # So a part rescued from an over-long fragment must look like a
            # NAME rather than a phrase. Postings capitalise their
            # technologies — Java, Python, REST, Kubernetes, C++ — and prose
            # about attitude does not. Lowercase skills in a long sentence are
            # lost, which is the conservative direction: a requirement we
            # missed is visible as a thin list, and one we invented becomes an
            # interview question about something nobody asked for.
            for part in _split_conjunctions(cleaned):
                if any(character.isupper() for character in part):
                    add(part)

    return forms


def scan_prose(text: str, concepts: list[dict[str, Any]]) -> set[str]:
    """Concept names whose name or an unambiguous alias appears in the text.

    This is the old behaviour, kept because it is genuinely useful, minus the
    part that invented requirements out of adjectives.
    """
    found: set[str] = set()
    haystack = text.lower()

    for concept in concepts:
        name = concept.get("name") or ""
        candidates = [name, *concept.get("aliases", [])]
        for candidate in candidates:
            if not candidate or not prose_safe_alias(candidate):
                continue
            if re.search(rf"\b{re.escape(candidate.lower())}\b", haystack):
                found.add(name)
                break

    return found


def _contains_phrase(haystack: str, needle: str) -> bool:
    """Does `needle` appear in `haystack` as whole words?

    A raw `needle in haystack` was the test here until 2026-08-27, and it was
    silently deleting requirements. `normalise_alias` strips punctuation, so
    "C++" normalises to the single letter `c` — and `"c" in "ci cd pipelines"`
    is True. Resolving C++ therefore removed every unresolved requirement whose
    text happened to contain the letter, which is most of them. "R" and "Go"
    are worse.

    It went unnoticed because nothing short ever resolved: the offline table
    holds five multi-word concepts. The disjunction work is what first put
    "C++" into `resolved`, and a whole requirement vanished from the response.

    Whole-word containment also fixes the quieter direction: "SQL" no longer
    matches inside "NoSQL", which is a different technology.
    """
    hay = haystack.split()
    need = needle.split()
    if not need or len(need) > len(hay):
        return False
    return any(hay[index : index + len(need)] == need for index in range(len(hay) - len(need) + 1))


def drop_redundant(unresolved: list[str], resolved: list[str]) -> list[str]:
    """Remove a conjunction phrase once its parts are carrying the meaning.

    `_split_conjunctions` deliberately keeps the whole phrase AND its parts,
    because only the resolver can tell "Transactions and ACID" (one concept)
    from "SQL and data structures" (two). Once it has spoken, a long phrase
    that is fully represented by shorter entries is noise on the student's
    screen - "Docker and Kubernetes" next to "Docker" and "Kubernetes" reads
    as a parser stutter rather than as two requirements.

    Two ways a phrase becomes redundant:

      · it contains a label that resolved, so the resolved one is the claim;
      · every one of its conjunction parts is present in its own right.
    """
    kept: list[str] = []
    resolved_keys = [normalise_alias(r) for r in resolved]
    all_keys = {normalise_alias(x) for x in [*resolved, *unresolved]}

    for label in unresolved:
        key = normalise_alias(label)

        if any(r and r != key and _contains_phrase(key, r) for r in resolved_keys):
            continue

        parts = [normalise_alias(p) for p in _split_conjunctions(label)]
        if parts and all(p in all_keys for p in parts):
            continue

        kept.append(label)

    return kept


# ---------------------------------------------------------------------------
#  Where in the job description each requirement was written (FR-2.2)
# ---------------------------------------------------------------------------
#
# Every other module in this platform holds one contract above the rest: a fact
# points at the characters it came from. M01 calls `SourceSpan` "the atom of
# traceability — everything downstream cites one of these". M02 produced a list
# of strings.
#
# That is not a cosmetic gap. Without an offset:
#
#   · M05 cannot cite the JD line a grounded question came from;
#   · a student cannot check a requirement we claim their JD contains;
#   · "Python" appearing in "no Python required" is indistinguishable from
#     "Python" in the requirements list, because there is nothing to look at.
#
# What is NOT built here is the rest of §5's `Requirement`: `kind`,
# `necessity`, `weight`, `measured_by` and `seniority_signal`. They are omitted
# rather than defaulted — a `necessity: "must"` on every requirement because
# nothing reads the word "preferred" yet is a field that looks derived and is
# not, and the coverage plan would then allocate questions on it.


class SourceSpan(BaseModel):
    """Where in the JD this requirement is written. Offsets into `raw_text`."""

    start: int
    end: int
    #: Verbatim, for mechanical verification — the same property M01 relies on
    #: to prove a span still resolves against the stored artifact.
    text: str


class Requirement(BaseModel):
    """One thing the posting asks for, and where it says so.

    §5's `Requirement`, complete as of 2026-08-27.

    `necessity` and `weight` came first, because they are what the coverage plan
    allocates ON. `kind`, `measured_by` and `seniority_signal` came second,
    because `measured_by` is what lets the plan price a coding question at
    twelve minutes instead of pricing everything the same.

    All of them are derived deterministically, from the posting's own words.
    §6.2 puts extraction behind a structured-output LLM call eventually; that
    call has to have a fallback anyway, and this is it.
    """

    id: str
    text: str
    span: SourceSpan | None
    #: `must` | `should` | `could`, from modal language (§6.4).
    necessity: str = "should"
    #: 0-1, normalised across the set. What the coverage plan allocates on.
    weight: float = 0.0
    #: How many times the posting says it. Repetition IS emphasis (§6.4).
    mentions: int = 1
    #: The `RequirementGroup` this is one alternative of, when the posting
    #: offered a choice. `None` for the ordinary case, which is most of them.
    group_id: str | None = None
    #: §5's `kind`: hard_skill, soft_skill, tool, domain or qualification.
    kind: str = "hard_skill"
    #: How this platform could produce evidence about it. EMPTY is a real
    #: answer (§3.2.1 trap 3): "go-getter attitude" is a requirement the
    #: posting made and nothing here can test, and saying so is the point.
    measured_by: list[str] = Field(default_factory=list)
    #: `intern` | `fresher` | `junior` | `mid` | `senior`, or `None` because
    #: the posting did not say. Never defaulted — this platform's users are
    #: overwhelmingly freshers, so a `fresher` default would always agree and
    #: therefore never inform anything.
    seniority_signal: str | None = None
    concept_ids: list[str] = Field(default_factory=list)
    #: False when nothing in the ontology corresponds to it — "go-getter
    #: attitude". §3.2.3: mark it and say so rather than faking a score.
    measurable: bool = False
    #: Where the id came from, when there is one. `m04` and a five-entry
    #: offline guess are not the same claim.
    concept_source: str | None = None
    source: str = "jd"


def requirement_pattern(label: str) -> re.Pattern[str]:
    """Where this label is written, allowing for the line breaks a page has.

    A space in the label matches any run of whitespace and an internal hyphen
    may be followed by one, because a JD pasted out of a PDF wraps mid-phrase:
    "Multi-\nmodal" and "machine\nlearning" are one requirement each, and a
    literal search finds neither.
    """
    body = r"\s+".join(re.escape(token) for token in label.split())
    body = body.replace(r"\-", r"-\s*")
    return re.compile(r"\b" + body + r"\b", re.IGNORECASE)


# ---------------------------------------------------------------------------
#  Disjunctions (FR-2.3) — the requirement that is one requirement
# ---------------------------------------------------------------------------
#
# §3.2.1: *"'Java/Python/C++' is a disjunction, not three requirements. Missing
# this makes a Python-only student look 33% qualified."*
#
# What was actually happening was worse than that, in three separate ways, all
# visible on one bullet:
#
#     - Experience with Docker or Kubernetes
#         -> "Docker or Kubernetes"   (a requirement, resolves to nothing)
#         -> "Docker"                 (a requirement)
#         -> "Kubernetes"             (a requirement)
#
# THREE requirements from one line: both alternatives, plus a phantom compound
# that no ontology will ever resolve and that therefore sits in the unmapped
# queue for ever. And now that weights exist, the phantom was drawing weight —
# 0.237 of a posting, the same as Docker itself.
#
#     - Java/Python/C++
#         -> "Java/Python/C++"        (one label, unresolvable, weight 0.1)
#
# The slash case does not even split, because `_DELIMITERS` excludes `/` on
# purpose: "CI/CD" and "TCP/IP" are single names far more often than
# "React/Angular" is two, and a wrong split fabricates a skill. That decision
# is right and stays. What is added here is a way to tell the two apart that
# does not involve guessing from punctuation:
#
#   ASK THE ONTOLOGY. A slash compound is a disjunction when at least two of
#   its parts independently resolve to concepts.
#
# "Java", "Python" and "C++" resolve; "CI", "CD", "TCP" and "IP" do not. With
# M04 down and only the offline table to consult, fewer compounds split and the
# rest stay whole — scope narrows, nothing is fabricated, which is the rule.
#
# The English disjunctions ("or", "either", "any one of") need no such test.
# The posting said the word.

#: "Java or Python", "either Java or Kotlin", "any one of Java, Python, C++".
#: `or` must be a whole word — "coordinator" is not a disjunction.
_OR_SPLIT = re.compile(r"\s+or\s+|\s*,\s*(?=[^,]*\s+or\s+)|\s*,\s*", re.IGNORECASE)
_HAS_OR = re.compile(r"\bor\b", re.IGNORECASE)
_ANY_ONE_OF = re.compile(r"^\s*(?:any\s+one\s+of|one\s+of|either)\s+", re.IGNORECASE)


def slash_parts(label: str) -> list[str]:
    """The parts of `A/B/C`, or [] when the label has no slash to split on.

    Syntax only. Whether these are three alternatives or one name with slashes
    in it is a question for the ontology, and the ontology lives behind an HTTP
    client in the router — so the router probes these and adds the ones that
    resolve to the label list, and `disjunction_parts` then sees them.
    """
    if "/" not in label:
        return []
    parts = [part.strip() for part in label.split("/")]
    return parts if len(parts) >= 2 and all(parts) else []


def _or_parts(label: str) -> list[str]:
    """The alternatives in an English disjunction, or [] if it is not one."""
    if not _HAS_OR.search(label):
        return []
    body = _ANY_ONE_OF.sub("", label)
    parts = [_clean(part) for part in _OR_SPLIT.split(body)]
    parts = [part for part in parts if part]
    return parts if len(parts) >= 2 else []


def disjunction_parts(label: str, resolved: dict[str, str]) -> list[str]:
    """The alternatives this label offers, or [] when it is one requirement.

    `resolved` is the ontology's answer for every label in the document, and it
    is what keeps "CI/CD" whole. It is consulted ONLY for the slash form: an
    English "or" is the posting stating the disjunction outright, and a posting
    is allowed to offer alternatives this platform has never heard of.
    """
    parts = _or_parts(label)
    if parts:
        return parts

    parts = slash_parts(label)
    if not parts:
        return []

    known_keys = {normalise_alias(label) for label in resolved}
    known = sum(1 for part in parts if normalise_alias(part) in known_keys)
    return parts if known >= 2 else []


def find_disjunctions(labels: list[str], resolved: dict[str, str]) -> dict[str, list[str]]:
    """Compound label -> its alternatives, for every choice the posting offered.

    Runs on the LABEL list rather than on the finished requirements, because
    `drop_redundant` deletes "Docker or Kubernetes" the moment "Docker" and
    "Kubernetes" are both present — correctly, since the compound is subsumed
    by its parts and resolves to nothing. But it takes the disjunction with it,
    and two requirements where the posting wrote a choice is the exact "33%
    qualified" reading §3.2.1 warns about. So the choice is recorded here,
    while the compound still exists to be read.
    """
    known = {normalise_alias(label) for label in labels}
    found: dict[str, list[str]] = {}
    for label in labels:
        parts = disjunction_parts(label, resolved)
        present = [part for part in parts if normalise_alias(part) in known]
        if len(present) >= 2:
            found[label] = present
    return found


class RequirementGroup(BaseModel):
    """§5's `RequirementGroup`, with only the satisfaction mode M02 can read.

    `all_of` is not emitted, because it is the default and an explicit group
    saying so would carry no information. `n_of` is not emitted, because no
    posting seen so far writes "at least two of", and inventing a group nobody
    wrote is the failure this whole file is about.
    """

    id: str
    satisfaction: str = "any_of"
    #: `Requirement.id`s. Two or more, always — a group of one is not a choice.
    requirement_ids: list[str]
    #: The words the disjunction was written as, so the screen can say
    #: "the posting asked for one of these" and point at the line.
    text: str
    span: SourceSpan | None = None


# ---------------------------------------------------------------------------
#  Necessity and weight (FR-2.2, §6.4)
# ---------------------------------------------------------------------------
#
# §3.2.1 Trap 2: *"'Good knowledge of DSA, OOPs, DBMS' and 'Bonus: familiarity
# with Docker' are not equal, and a flat list makes them equal."*
#
# A flat list is what M02 produced, and it is what the coverage plan would have
# allocated its question budget across — so a bonus nice-to-have would have
# taken interview time from a stated must.
#
# Read from modal language, deterministically. Two places carry it and the
# second is the one the trap is about:
#
#   the line   "Strong Python"            "Docker is a plus"
#   the HEAD   "Required:"                "Bonus:"
#
# A requirement under "Nice to have:" is a `could` even when its own line says
# nothing, which is exactly the Docker case. The line wins when both speak,
# because "Docker (required)" under a Bonus heading is the posting correcting
# itself.

#: Modal language that makes a requirement non-negotiable.
_MUST = re.compile(
    r"\b(?:must\s+have|must\b|required|mandatory|essential|strong(?:ly)?|"
    r"solid\s+(?:knowledge|grasp|understanding)|proficien\w*|expert\w*|"
    r"deep\s+(?:knowledge|understanding)|is\s+a\s+must)\b",
    re.IGNORECASE,
)

#: Language that makes it explicitly optional.
#:
#: "familiarity with", "exposure to" and "awareness of" are deliberately NOT
#: here. They describe DEPTH, not optionality: "Familiarity with Git" under a
#: Requirements heading is required — shallowly — and reading it as a bonus
#: drops a stated requirement into the nice-to-have band, where it earns a
#: third of the interview time it should. The heading decides: under "Nice to
#: have:" the same words are a `could`, which is the case §3.2.1 is about.
_COULD = re.compile(
    r"\b(?:nice\s+to\s+have|good\s+to\s+have|a\s+plus|is\s+a\s+plus|bonus|"
    r"desirable|preferred|optional|advantage|would\s+be\s+(?:great|nice))\b",
    re.IGNORECASE,
)

#: Headings that govern everything under them until the next heading.
_MUST_HEADING = re.compile(
    r"^\s*(?:required|requirements|must\s+have|essential|minimum\s+qualifications|"
    r"what\s+you\s+(?:need|must\s+have)|mandatory)\b",
    re.IGNORECASE,
)
_COULD_HEADING = re.compile(
    r"^\s*(?:bonus|nice\s+to\s+have|good\s+to\s+have|preferred|desirable|optional|"
    r"plus(?:es)?|added\s+advantage|what\s+would\s+set\s+you\s+apart)\b",
    re.IGNORECASE,
)


def _line_bounds(text: str, offset: int) -> tuple[int, int]:
    start = text.rfind("\n", 0, offset) + 1
    end = text.find("\n", offset)
    return start, len(text) if end == -1 else end


def _governing_heading(text: str, line_start: int) -> str:
    """The nearest heading above this line, or "" if there is none.

    Walks up until a line that looks like a heading — one that ends in a colon,
    or that a necessity-heading pattern recognises. A blank line does not stop
    the walk: a JD puts one between the heading and its list about as often as
    it does not.
    """
    for candidate in reversed(text[:line_start].splitlines()):
        stripped = candidate.strip()
        if not stripped:
            continue
        if (
            stripped.endswith(":")
            or _MUST_HEADING.match(stripped)
            or _COULD_HEADING.match(stripped)
        ):
            return stripped
    return ""


def necessity_at(text: str, offset: int) -> str:
    """`must`, `should` or `could` for the requirement written at `offset`.

    `should` is the default, and it is the honest one. A posting that lists a
    technology under a neutral heading with no modal word has not said the
    requirement is negotiable and has not said it is not — and defaulting to
    `must` would put maximum weight on every unqualified line, which is a flat
    list wearing a necessity field.
    """
    line_start, line_end = _line_bounds(text, offset)
    line = text[line_start:line_end]

    # The line wins: "Docker (required)" under a Bonus heading is the posting
    # correcting itself, and the more specific statement is the later one.
    if _COULD.search(line):
        return "could"
    if _MUST.search(line):
        return "must"

    heading = _governing_heading(text, line_start)
    if _COULD_HEADING.match(heading):
        return "could"
    if _MUST_HEADING.match(heading):
        return "must"

    return "should"


#: §6.4's multipliers, verbatim.
_NECESSITY_MULT = {"must": 1.0, "should": 0.6, "could": 0.3}


def _raw_weight(text: str, requirement: Requirement, mentions: int) -> float:
    """§6.4's formula, with the terms this module can actually compute.

    `emphasis_w` is 1.2 for a bulleted line under a must heading. The spec says
    "bold or bulleted", and there is no bold in plain text — claiming one would
    be inventing a signal the input does not carry.

    `source_w` is 1.0 for every requirement here because they all come from the
    JD. It stays in the expression rather than being folded away, so the day
    archetype backfill lands (FR-2.6) the 0.75 has somewhere to go.
    """
    necessity_mult = _NECESSITY_MULT[requirement.necessity]

    if requirement.span is not None and text:
        position_w = 1.0 - 0.4 * (requirement.span.start / len(text))
        line_start, line_end = _line_bounds(text, requirement.span.start)
        bulleted = bool(_BULLET.match(text[line_start:line_end]))
        emphasis_w = 1.2 if bulleted and requirement.necessity == "must" else 1.0
    else:
        # Located nowhere: no position to reward and no line to look at.
        position_w = 0.6
        emphasis_w = 1.0

    repetition_w = min(1.0, 0.6 + 0.2 * (mentions - 1))
    source_w = 1.0 if requirement.source == "jd" else 0.75

    return necessity_mult * position_w * repetition_w * emphasis_w * source_w


class RequirementSet(BaseModel):
    """What `locate` produces: the requirements, and the choices among them.

    Two lists rather than a nested structure, because every consumer wants the
    flat one — coverage iterates requirements, and the group is a lookup it
    consults when deciding whether a miss is really a miss.
    """

    requirements: list[Requirement] = Field(default_factory=list)
    groups: list[RequirementGroup] = Field(default_factory=list)


def locate(
    text: str,
    labels: list[str],
    *,
    resolved: dict[str, str],
    sources: dict[str, str],
    disjunctions: dict[str, list[str]] | None = None,
    inferred: list[str] | None = None,
) -> RequirementSet:
    """Every requirement, with the span it was written at.

    First occurrence only. A JD that says "Python" four times is making one
    requirement four times, and four spans would be four rows in a coverage
    plan that allocates questions per row.

    Ordered by position, so the list reads down the posting rather than in
    whatever order extraction happened to resolve things.

    Disjunctions are folded here rather than after, because weights are
    normalised across the set: dropping a phantom compound afterwards would
    leave the remaining weights summing to less than one.
    """
    found: list[tuple[int, Requirement]] = []

    # One reading for the whole document. A posting says "we are hiring
    # freshers" once, at the top, and every requirement under it inherits that;
    # scanning per requirement would find it on one row and leave the rest
    # silent, which reads as disagreement rather than as one statement.
    seniority = seniority_of(text)
    # §6.3's backfill.
    #
    # `source="archetype"` and `span=None` travel together, and the rule that
    # keeps them together is: a suggested label that TURNS OUT to be in the
    # document is not inferred. It is stated, and extraction simply failed to
    # find it — which happens, because `_list_lines` only enters list mode under
    # one of thirty heading phrases and a posting reading "Looking for SDE
    # trainees. Good knowledge of DSA and OOPs." has no heading at all.
    #
    # Calling that requirement "inferred" would understate what the company
    # asked for AND discount its weight to 0.75 for a demand they made
    # explicitly. So the archetype gets credit for finding it and the posting
    # gets credit for stating it.
    suggested = {normalise_alias(label) for label in (inferred or [])}

    for index, label in enumerate(labels, start=1):
        pattern = requirement_pattern(label)
        match = pattern.search(text)
        mentions = len(pattern.findall(text)) or 1
        span = (
            SourceSpan(start=match.start(), end=match.end(), text=match.group(0)) if match else None
        )
        concept_id = resolved.get(label)
        # Classified against the LINE as well as the label: a bare
        # "communication" is one word, and "excellent written and verbal
        # communication" is where the signal usually is.
        line_start, line_end = _line_bounds(text, match.start()) if match else (0, 0)
        measured = measured_by(label, context=text[line_start:line_end])
        found.append(
            (
                match.start() if match else len(text) + index,
                Requirement(
                    id=f"R-{index}",
                    text=label,
                    span=span,
                    necessity=necessity_at(text, match.start()) if match else "should",
                    mentions=mentions,
                    kind=kind_of(label, measured=measured),
                    measured_by=measured,
                    seniority_signal=seniority,
                    source=(
                        "archetype"
                        if normalise_alias(label) in suggested and span is None
                        else "jd"
                    ),
                    concept_ids=[concept_id] if concept_id else [],
                    measurable=bool(concept_id),
                    concept_source=sources.get(label),
                ),
            )
        )

    found.sort(key=lambda item: item[0])
    ordered = [requirement for _, requirement in found]

    ordered, groups = _fold_disjunctions(text, ordered, disjunctions or {})

    # Weights are normalised ACROSS the set, so they cannot be computed until
    # every requirement is known. §6.4: `weight = raw / sum(all_raw)`.
    raws = [_raw_weight(text, requirement, requirement.mentions) for requirement in ordered]

    # Alternatives SHARE one requirement's weight. "Java or Python" is one thing
    # the posting wants, and leaving both members at full weight would make a
    # two-way choice count double a plain requirement — the same distortion as
    # the phantom compound, arriving by a different route.
    for group in groups:
        members = [i for i, r in enumerate(ordered) if r.group_id == group.id]
        if not members:
            continue
        share = max(raws[i] for i in members) / len(members)
        for i in members:
            raws[i] = share

    total = sum(raws)

    # Renumbered after sorting, so `R-1` is the first requirement in the
    # document rather than the first one the resolver happened to finish.
    renamed = {
        requirement.id: f"R-{position}" for position, requirement in enumerate(ordered, start=1)
    }
    requirements = [
        requirement.model_copy(
            update={
                "id": renamed[requirement.id],
                # An empty set has no weights to normalise; one with zero total
                # raw weight would divide by zero. Neither can happen from a
                # real posting, and both would take the parse down.
                "weight": round(raw / total, 4) if total else 0.0,
            }
        )
        for requirement, raw in zip(ordered, raws, strict=True)
    ]
    groups = [
        group.model_copy(
            update={
                "requirement_ids": [
                    renamed[member] for member in group.requirement_ids if member in renamed
                ]
            }
        )
        for group in groups
    ]
    return RequirementSet(requirements=requirements, groups=groups)


def _fold_disjunctions(
    text: str,
    ordered: list[Requirement],
    disjunctions: dict[str, list[str]],
) -> tuple[list[Requirement], list[RequirementGroup]]:
    """Turn each recorded choice into a group over the requirements it offers.

    The compound is dropped if it survived this far. Keeping it alongside its
    parts is what produced three requirements from one line — and the compound
    is the one of the three that can never resolve to a concept, so it sat in
    the unmapped queue permanently and, once weights existed, drew weight there.

    A choice whose alternatives are not both present as requirements is left
    alone. If `_acceptable` rejected one of them, folding would delete a
    requirement the posting stated, and that is never the thing to lose.
    """
    by_key = {normalise_alias(requirement.text): requirement for requirement in ordered}
    groups: list[RequirementGroup] = []
    dropped: set[str] = set()
    member_of: dict[str, str] = {}

    for compound, parts in disjunctions.items():
        members = [by_key.get(normalise_alias(part)) for part in parts]
        present = [
            member
            for member in members
            if member is not None and normalise_alias(member.text) != normalise_alias(compound)
        ]
        if len(present) < 2:
            continue

        # An alternative already spoken for stays where it is. Two overlapping
        # disjunctions in one posting is rare and ambiguous, and the honest
        # reading of "A or B" plus "B or C" is not a four-way choice.
        if any(member.id in member_of for member in present):
            continue

        match = requirement_pattern(compound).search(text)
        groups.append(
            RequirementGroup(
                id=f"G-{len(groups) + 1}",
                requirement_ids=[member.id for member in present],
                text=compound,
                span=SourceSpan(start=match.start(), end=match.end(), text=match.group(0))
                if match
                else None,
            )
        )
        for member in present:
            member_of[member.id] = groups[-1].id

        stale = by_key.get(normalise_alias(compound))
        if stale is not None:
            dropped.add(stale.id)

    kept = [
        requirement.model_copy(update={"group_id": member_of.get(requirement.id)})
        for requirement in ordered
        if requirement.id not in dropped
    ]
    return kept, groups


# ---------------------------------------------------------------------------
#  Eligibility (FR-2.4) — the half that was being thrown away
# ---------------------------------------------------------------------------
#
# `_ELIGIBILITY` above is a REJECT filter: `_acceptable` uses it to keep "7.0
# CGPA", "2+ years" and "B.Tech" out of the requirement list. That is right —
# §3.2.2 is explicit that eligibility is a hard filter and not an interview
# topic, and filing a CGPA cutoff under skills would put a number the ontology
# can never resolve into the unmapped queue for ever.
#
# What was wrong is that the match was then DISCARDED. The comment beside the
# regex says these "belong in a structured eligibility field", and the field did
# not exist — so the module recognised the most consequential line in a job
# posting and dropped it.
#
# The cost is FR-2.15's whole sentence: *"you have 7.2, cutoff is 7.5"*. A
# student cannot be told they are ineligible for a drive by a module that never
# kept the cutoff. §2.3 puts that banner at the top of the JD screen, and
# students waste weeks preparing for drives they cannot sit.
#
# Every field is `None` when the posting does not say. Not zero, not a
# permissive default: "this JD does not state a CGPA cutoff" and "this JD has no
# cutoff" are different facts, and a `min_cgpa: 0.0` would tell a student they
# are eligible for a drive nobody has checked them against.

#: "CGPA of 7.5", "7.5 CGPA", "minimum 7.5 CGPA", "70%" — the shapes an Indian
#: campus posting actually writes a cutoff in.
_CGPA = re.compile(
    r"(?:(?:min(?:imum)?|above|at\s+least|not\s+below)\s*)?"
    r"(?:cgpa|gpa)\s*(?:of\s*|:\s*|-\s*|>=?\s*)?(?P<value>\d{1,2}(?:\.\d{1,2})?)"
    r"|(?P<value2>\d{1,2}(?:\.\d{1,2})?)\s*(?:\+\s*)?(?:cgpa|gpa)",
    re.IGNORECASE,
)

#: "no active backlogs", "zero backlogs", "at most 1 backlog".
_BACKLOGS = re.compile(
    r"(?P<none>no|zero|nil)\s+(?:active\s+|current\s+|standing\s+)?(?:backlog|arrear)s?"
    r"|(?:at\s+most|maximum|max|up\s+to)\s*(?P<count>\d+)\s*(?:active\s+)?(?:backlog|arrear)s?"
    # "Students with standing arrears are NOT eligible to apply." The bar is
    # stated as a disqualification rather than as a limit, which is the usual
    # phrasing on a campus brochure and matched nothing at all.
    r"|with\s+(?:standing|active|current|any)\s+(?P<none2>backlog|arrear)s?\s+"
    r"(?:are\s+)?(?:not|non)[\s-]*eligible",
    re.IGNORECASE,
)

#: "2026 batch", "batch of 2026", "year of passing 2026".
_BATCH = re.compile(
    r"(?:batch\s+of\s+|year\s+of\s+passing\s*:?\s*|passing\s+out\s+in\s+)?(?P<year>20\d{2})\s*batch"
    r"|batch\s+of\s+(?P<year2>20\d{2})"
    r"|year\s+of\s+passing\s*:?\s*(?P<year3>20\d{2})"
    # "Students graduating in 2027" is how a brochure writes it, and neither
    # "batch" nor "year of passing" appears anywhere near it.
    r"|graduat\w*\s+(?:in|by)\s+(?P<year4>20\d{2})"
    r"|class\s+of\s+(?P<year5>20\d{2})",
    re.IGNORECASE,
)

#: "2 year bond", "service agreement of 18 months".
#: A colon is how a posting labels a field, and this pattern required a space.
#: "Bond: 18 months" — on this module's own sample JD, on the paste screen —
#: read as no bond at all, which is the difference between a student signing an
#: eighteen-month commitment knowingly and finding out at the offer letter.
_BOND = re.compile(
    r"(?P<years>\d{1,2})\s*[- ]?\s*years?\s+(?:bond|service\s+agreement)"
    r"|(?:bond|service\s+agreement)\s*[:\-]?\s*(?:of\s+|period\s+)?(?P<months>\d{1,3})\s*months?"
    r"|(?:bond|service\s+agreement)\s*[:\-]?\s*(?:of\s+)?(?P<years3>\d{1,2})\s*[- ]?\s*years?"
    r"|(?P<years2>\d{1,2})\s*[- ]?\s*years?\s+commitment",
    re.IGNORECASE,
)


#: "CSE/IT/ECE", "Computer Science, IT and ECE only", "B.Tech CSE/IS".
#:
#: The slash IS split here, unlike everywhere else in this file — `_DELIMITERS`
#: refuses it because "CI/CD" is one name. A branch list is the one context
#: where a slash reliably means "or": nobody writes a single degree called
#: "CSE/IT". The pattern is anchored on a branch vocabulary rather than on the
#: punctuation, which is what keeps that narrow.
_BRANCHES = {
    "cse": "CSE",
    "cs": "CSE",
    "computer science": "CSE",
    "computer science and engineering": "CSE",
    "it": "IT",
    "information technology": "IT",
    "ise": "ISE",
    "is": "ISE",
    "information science": "ISE",
    "ece": "ECE",
    "electronics and communication": "ECE",
    "eee": "EEE",
    "electrical": "EEE",
    "eie": "EIE",
    "mech": "MECH",
    "mechanical": "MECH",
    "civil": "CIVIL",
    "aids": "AIDS",
    "aiml": "AIML",
    "ai": "AIML",
    "csbs": "CSBS",
    "chemical": "CHEMICAL",
    "biotech": "BIOTECH",
}

#: Only read inside a branch-shaped context, never from the whole document.
#: "IT" and "AI" and "IS" are ordinary English fragments, and scanning a JD for
#: them produces a branch list off the word "it".
#: Only read inside a branch-shaped context, or from a run of REAL branch
#: codes. The original second alternative was any run of capitals joined by
#: slashes, which on a real brochure matched "CI/CD", "AI/ML" and "LPA / INR" —
#: producing `allowed_branches: ["AIML"]` on a posting with no branch
#: restriction at all. That is not noise: it tells a student they are
#: ineligible for a drive that never excluded them.
_BRANCH_CODES = "|".join(
    sorted((re.escape(k) for k in _BRANCHES if len(k) <= 5), key=len, reverse=True)
)
_BRANCH_CONTEXT = re.compile(
    r"(?:branch(?:es)?|discipline|stream|circuit|eligibility|eligible|"
    r"only\s+for|open\s+to|qualification)"
    r"\s*[:\-]?\s*(?P<list>[A-Za-z&,/ .]{2,120})"
    r"|(?P<list2>(?:" + _BRANCH_CODES + r")(?:\s*[/,]\s*(?:" + _BRANCH_CODES + r")){1,6})",
    re.IGNORECASE,
)

#: "6.5 LPA", "₹6.5 LPA", "CTC 6.5 LPA", "4.5 fixed + 2 variable".
_PACKAGE = re.compile(
    r"(?:ctc|package|salary|compensation)?\s*[:\-]?\s*"
    r"(?:₹|rs\.?|inr)?\s*(?P<value>\d{1,3}(?:\.\d{1,2})?)\s*(?:lpa|lakhs?\s*(?:per\s*annum)?|l\b)",
    re.IGNORECASE,
)
_FIXED = re.compile(
    r"(?:₹|rs\.?|inr)?\s*(?P<value>\d{1,3}(?:\.\d{1,2})?)\s*(?:lpa|l\b)?\s*(?:fixed|base)",
    re.IGNORECASE,
)

#: "Bangalore", "based in Chennai", "Location: Hyderabad / Pune".
_LOCATION = re.compile(
    r"(?:location|based\s+(?:in|out\s+of)|posting|work\s+location|office)\s*[:\-]?\s*"
    r"(?P<list>[A-Za-z,/&\- ]{3,80})",
    re.IGNORECASE,
)

#: "no backlogs in the entire academic career", "no history of backlogs".
_HISTORY_BACKLOGS = re.compile(
    r"(?:no|zero|nil)\s+(?:backlog|arrear)s?\s+(?:in\s+)?"
    r"(?:the\s+)?(?:entire\s+|whole\s+)?(?:academic\s+)?(?:career|history|history\s+of\s+study)"
    r"|no\s+history\s+of\s+(?:backlog|arrear)s?"
    r"|(?:no|zero|nil)\s+(?:standing|past|historical)\s+(?:backlog|arrear)s?",
    re.IGNORECASE,
)


def _read_branches(text: str) -> list[str]:
    """Branch codes the posting allows, normalised and deduplicated.

    Returns `[]` when the posting does not name any, which is different from
    "all branches welcome" and is treated as such: an empty list means we did
    not find a restriction, not that we verified there is none.
    """
    found: list[str] = []
    for match in _BRANCH_CONTEXT.finditer(text):
        raw = match.group("list") or match.group("list2") or ""
        for token in re.split(r"[,/&]|\band\b|\bor\b", raw):
            key = " ".join(token.lower().split()).strip(". ")
            code = _BRANCHES.get(key)
            if code and code not in found:
                found.append(code)
    return found


def _read_location(text: str) -> list[str]:
    match = _LOCATION.search(text)
    if not match:
        return []
    places: list[str] = []
    for token in re.split(r"[,/&]|\band\b", match.group("list")):
        name = " ".join(token.split()).strip(". ")
        # Two characters is not a city, and a whole clause is not one either.
        if 2 < len(name) <= 30 and name[0].isupper() and name not in places:
            places.append(name)
    return places[:6]


class EligibilityCriteria(BaseModel):
    """The hard filters on who may sit this drive (§5, FR-2.4).

    §5's `EligibilityCriteria`, complete as of 2026-08-27.

    Every field is `None` or empty when the posting does not say. Not zero and
    not a permissive default: "this JD states no CGPA cutoff" and "this JD has
    no cutoff" are different facts, and a `min_cgpa: 0.0` would tell a student
    they are eligible for a drive nobody has checked them against. An empty
    `allowed_branches` means we found no restriction, NOT that we verified
    there is none.

    `stated` is the field a screen branches on. Every value being `None` and
    the posting genuinely having no cutoff look identical otherwise, and only
    one of them means "we checked".
    """

    min_cgpa: float | None = None
    max_backlogs_active: int | None = None
    year_of_passing: list[int] = Field(default_factory=list)
    bond_months: int | None = None
    #: "no backlogs in the entire academic career" is a stricter bar than "no
    #: ACTIVE backlogs", and a student who cleared an old arrear passes one and
    #: fails the other. Two fields because they are two rules.
    max_backlogs_history: int | None = None
    #: Normalised branch codes: CSE, IT, ECE. Empty when none are named.
    allowed_branches: list[str] = Field(default_factory=list)
    #: Cities named as the posting or work location.
    location: list[str] = Field(default_factory=list)
    #: What the posting advertises. `total` is the headline number and `fixed`
    #: the part that is not variable — a 6.5 LPA offer with 2 LPA of variable
    #: is a 4.5 LPA salary, and students compare the wrong one constantly.
    package_lpa_total: float | None = None
    package_lpa_fixed: float | None = None
    #: The lines these were read from, so a student can check the cutoff we are
    #: about to tell them they miss.
    raw_spans: list[SourceSpan] = Field(default_factory=list)

    # `computed_field`, not a bare `@property`: pydantic does not serialise a
    # plain property, so the frontend declared `stated: boolean` and would have
    # received `undefined` — and `if (!eligibility.stated)` on undefined reads
    # as "this drive states no cutoff", which is the one wrong answer this
    # field exists to prevent.
    @computed_field  # type: ignore[prop-decorator]
    @property
    def stated(self) -> bool:
        return bool(
            self.min_cgpa is not None
            or self.max_backlogs_active is not None
            or self.year_of_passing
            or self.bond_months is not None
            or self.max_backlogs_history is not None
            or self.allowed_branches
            or self.location
            or self.package_lpa_total is not None
        )


def _span_at(text: str, match: re.Match[str]) -> SourceSpan:
    return SourceSpan(start=match.start(), end=match.end(), text=match.group(0))


def extract_eligibility(text: str) -> EligibilityCriteria:
    """The eligibility block, kept instead of filtered out (FR-2.4).

    Every span is recorded. A student told "you have 7.2, the cutoff is 7.5"
    is being told something with real consequences, and the only honest version
    of that sentence points at the line it came from.
    """
    criteria = EligibilityCriteria()
    spans: list[SourceSpan] = []

    match = _CGPA.search(text)
    if match:
        raw = match.group("value") or match.group("value2")
        value = float(raw)
        # A percentage cutoff written as "70%" is not a CGPA. Above 10 it is
        # one or the other, and storing 70.0 in `min_cgpa` would tell every
        # student on a 10-point scale that they are ineligible.
        if value <= 10:
            criteria.min_cgpa = value
            spans.append(_span_at(text, match))

    match = _BACKLOGS.search(text)
    if match:
        no_backlogs = match.group("none") or match.group("none2")
        criteria.max_backlogs_active = 0 if no_backlogs else int(match.group("count"))
        spans.append(_span_at(text, match))

    years = {
        int(year)
        for match in _BATCH.finditer(text)
        for year in (
            match.group("year"),
            match.group("year2"),
            match.group("year3"),
            match.group("year4"),
            match.group("year5"),
        )
        if year
    }
    if years:
        criteria.year_of_passing = sorted(years)
        spans.extend(_span_at(text, m) for m in _BATCH.finditer(text))

    match = _HISTORY_BACKLOGS.search(text)
    if match:
        # The stricter bar, and it implies the looser one: a posting that wants
        # no backlogs EVER certainly does not want current ones. `_BACKLOGS`
        # above will usually have set `max_backlogs_active` from the same
        # sentence; this makes that true even when the phrasing dodges it.
        criteria.max_backlogs_history = 0
        criteria.max_backlogs_active = 0
        spans.append(_span_at(text, match))

    branches = _read_branches(text)
    if branches:
        criteria.allowed_branches = branches

    places = _read_location(text)
    if places:
        criteria.location = places

    match = _PACKAGE.search(text)
    if match:
        criteria.package_lpa_total = float(match.group("value"))
        spans.append(_span_at(text, match))
    fixed = _FIXED.search(text)
    if fixed:
        criteria.package_lpa_fixed = float(fixed.group("value"))

    match = _BOND.search(text)
    if match:
        if match.group("months"):
            criteria.bond_months = int(match.group("months"))
        else:
            years = match.group("years") or match.group("years2") or match.group("years3")
            criteria.bond_months = int(years) * 12
        spans.append(_span_at(text, match))

    criteria.raw_spans = sorted(spans, key=lambda span: span.start)
    return criteria
