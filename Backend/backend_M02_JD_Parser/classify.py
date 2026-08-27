"""What kind of requirement is this, and what could test it (FR-2.2, §3.2.1).

Three of §5's `Requirement` fields land here: `kind`, `measured_by` and
`seniority_signal`. `measured_by` is the one with teeth — it is what lets the
coverage plan cost a coding question at twelve minutes and a verbal one at
three and a half, which until now it could not, so every plan priced every
question the same and said so on screen.

── Trap 3, which is most of this file ──────────────────────────────────────────

§3.2.1: *"Soft skills are requirements we can partially measure. 'Communication'
maps to real measured constructs (M12/M17). 'Team player' maps to behavioural
probes (M6 HR round). 'Go-getter attitude' maps to nothing — mark it
`unmeasurable` and say so rather than faking a score."*

Three tiers, and the trap is treating them as one. Collapse them upward and the
platform invents a score for "go-getter attitude"; collapse them downward and it
throws away "communication", which M12 and M17 genuinely measure. So:

    "excellent communication"   -> measured_by ["communication"]
    "team player"               -> measured_by ["behavioural"]
    "go-getter attitude"        -> measured_by []           and said out loud

An empty `measured_by` is a real answer here, not a gap in the lexicon. It means
no round in this platform can produce evidence about this requirement, which is
a fact the student should see next to it rather than a silence.

── Why a lexicon and not a model ───────────────────────────────────────────────

§6.2 puts requirement extraction behind a structured-output LLM call, and that
is still the plan. This is not it. It is deterministic, auditable and runs in
microseconds, and — more to the point — it is the fallback that has to exist
anyway: §6.2's post-checks assume a classification to check, and Rule 2 says a
missing dependency narrows scope rather than quality. A lexicon that defaults
safely is what "narrowed scope" looks like here.

Everything defaults to `technical`, which costs a verbal question — the CHEAPEST
option. A wrong default that overprices makes the planner fit fewer questions
into a session than it should; a wrong default that underprices makes it promise
a 45-minute mock that takes two hours. Between an under-full session and a
broken promise, the first is recoverable.
"""

from __future__ import annotations

import re

#: §5's `kind`. `nice_to_have` from the spec's list is deliberately absent: it
#: is a NECESSITY, not a kind, and `necessity` already carries it. A field that
#: can say "this is a tool" and "this is optional" in the same slot forces a
#: choice between two facts that are both true.
HARD_SKILL = "hard_skill"
SOFT_SKILL = "soft_skill"
TOOL = "tool"
DOMAIN = "domain"
QUALIFICATION = "qualification"

#: §5's `measured_by`, verbatim.
TECHNICAL = "technical"
CODING = "coding"
DESIGN = "design"
BEHAVIOURAL = "behavioural"
COMMUNICATION = "communication"
APTITUDE = "aptitude"


def _words(*terms: str) -> re.Pattern[str]:
    """A whole-word alternation. Never a substring test.

    `"c" in "ci cd pipelines"` was a real bug in this repository on 2026-08-27,
    and it deleted requirements. Every lexicon here is anchored.
    """
    joined = "|".join(term.replace(" ", r"\s+") for term in terms)
    return re.compile(rf"(?<![\w-])(?:{joined})(?![\w-])", re.IGNORECASE)


# ---------------------------------------------------------------------------
#  measured_by
# ---------------------------------------------------------------------------

#: A whiteboard or an editor. These are the twelve-minute questions.
_CODING = _words(
    "dsa",
    "data structures",
    "algorithms?",
    "algorithmic",
    "dynamic programming",
    "recursion",
    "greedy",
    "backtracking",
    "graph theory",
    "sorting",
    "searching",
    "binary search",
    "trees?",
    "linked lists?",
    "hashing",
    "competitive programming",
    "problem solving",
    "coding",
    "leetcode",
    "time complexity",
    "space complexity",
)

#: Twenty-minute questions. A design requirement cannot be probed in three and a
#: half minutes and pretending otherwise is how a plan overpromises.
_DESIGN = _words(
    "system design",
    "high level design",
    "hld",
    "low level design",
    "lld",
    "architecture",
    "architectural",
    "scalability",
    "scalable systems",
    "distributed systems",
    "design patterns",
    "microservices",
    "api design",
    "database design",
    "schema design",
    "load balancing",
    "caching strategy",
)

_COMMUNICATION = _words(
    "communication",
    "communicator",
    "verbal",
    "written",
    "presentation",
    "articulate",
    "stakeholder management",
    "client facing",
    "documentation skills",
)

_BEHAVIOURAL = _words(
    "team player",
    "teamwork",
    "collaborat\\w*",
    "leadership",
    "ownership",
    "adaptability",
    "adaptable",
    "flexible",
    "work ethic",
    "time management",
    "conflict resolution",
    "mentoring",
    "cross functional",
    "interpersonal",
)

_APTITUDE = _words(
    "aptitude",
    "quantitative",
    "logical reasoning",
    "analytical reasoning",
    "numerical ability",
    "verbal ability",
    "puzzles?",
)

#: §3.2.1's third tier: language that describes a PERSON rather than a skill.
#:
#: Nothing in this platform produces evidence about these. They are kept as
#: requirements — the posting asked for them and dropping them would hide what
#: the company said — and marked so no screen can render a score beside one.
_UNMEASURABLE = _words(
    "go.getter",
    "self.starter",
    "passionate",
    "passion",
    "attitude",
    "enthusiastic",
    "hard.working",
    "dynamic personality",
    "go getter",
    "energetic",
    "motivated",
    "willingness to learn",
    "eager to learn",
    "positive mindset",
    "can.do",
    "detail.oriented",
    "result.oriented",
    "results.driven",
)


# ---------------------------------------------------------------------------
#  kind
# ---------------------------------------------------------------------------

_TOOL = _words(
    "docker",
    "kubernetes",
    "git",
    "jenkins",
    "jira",
    "maven",
    "gradle",
    "npm",
    "webpack",
    "terraform",
    "ansible",
    "postman",
    "figma",
    "tableau",
    "excel",
    "linux",
    "bash",
    "ci.cd",
    "aws",
    "azure",
    "gcp",
    "kafka",
    "redis",
    "nginx",
)

_DOMAIN = _words(
    "fintech",
    "healthcare",
    "e.commerce",
    "banking",
    "insurance",
    "retail",
    "telecom",
    "manufacturing",
    "logistics",
    "edtech",
    "payments",
    "capital markets",
)

#: A degree abbreviation needs the punctuation that makes it one.
#:
#: `b.?e` matched the word "be", so "Must be a team player" classified as a
#: QUALIFICATION — wrong, and the kind of wrong that looks deliberate on screen
#: rather than like a regex accident. Two-letter abbreviations only count with
#: their dots; the spelled-out forms do not need them.
_QUALIFICATION = _words(
    r"b\.?tech",
    r"b\.e\.?",
    r"m\.?tech",
    "mca",
    "bca",
    "degree",
    "graduates?",
    "graduation",
    "certifications?",
    "certified",
    "diploma",
)


# ---------------------------------------------------------------------------
#  seniority_signal
# ---------------------------------------------------------------------------

#: Read only where the posting SAYS it. A requirement with no seniority language
#: gets `None`, not `fresher` — this platform's users are overwhelmingly
#: freshers and defaulting to that would make the field always agree and
#: therefore never inform anything.
#: Plurals matter more than they look. A posting says "we are hiring FRESHERS",
#: never "we are hiring fresher", and `_words` anchors on both sides — so the
#: singular form matched nothing at all in the sentence postings actually write.
_SENIORITY = (
    ("intern", _words("interns?", "internships?", "trainees?")),
    (
        "fresher",
        _words("freshers?", "fresh graduates?", "entry.level", "no experience", "0.1 years?"),
    ),
    ("junior", _words("junior", "1.3 years?", r"1\+ years?", r"2\+ years?")),
    ("mid", _words("mid.level", "3.5 years?", r"3\+ years?", r"4\+ years?", r"5\+ years?")),
    (
        "senior",
        _words("senior", "lead", "principal", "staff engineer", r"6\+ years?", r"7\+ years?"),
    ),
)


def measured_by(label: str, *, context: str = "") -> list[str]:
    """How this platform could produce evidence about this requirement.

    `context` is the line the requirement was written on. It matters: a bare
    "communication" is one word and the line around it — "excellent written and
    verbal communication" — is where the signal usually is.

    Returns a LIST because a requirement can be several things at once. "System
    design and scalability" is a design question; "DSA and problem solving under
    time pressure" is coding and aptitude both.
    """
    haystack = f"{label} {context}"

    if _UNMEASURABLE.search(label):
        # Checked against the LABEL only. A bullet that happens to contain
        # "passionate about distributed systems" is a design requirement with an
        # adjective in front of it, not an unmeasurable one.
        return []

    found: list[str] = []
    for name, pattern in (
        (CODING, _CODING),
        (DESIGN, _DESIGN),
        (COMMUNICATION, _COMMUNICATION),
        (BEHAVIOURAL, _BEHAVIOURAL),
        (APTITUDE, _APTITUDE),
    ):
        if pattern.search(haystack):
            found.append(name)

    # A named technology with no other signal is asked about verbally: "tell me
    # how you used Docker" is a three-minute question, not a twelve-minute one.
    return found or [TECHNICAL]


def kind_of(label: str, *, measured: list[str]) -> str:
    """`hard_skill`, `soft_skill`, `tool`, `domain` or `qualification`."""
    if _QUALIFICATION.search(label):
        return QUALIFICATION
    if _TOOL.search(label):
        return TOOL
    if _DOMAIN.search(label):
        return DOMAIN
    if not measured or {COMMUNICATION, BEHAVIOURAL} & set(measured):
        # Including the empty case: "go-getter attitude" is a soft skill that
        # nothing can measure, and both halves of that are true at once.
        return SOFT_SKILL
    return HARD_SKILL


def seniority_of(text: str) -> str | None:
    """The seniority the posting states, or `None` because it did not.

    Scanned over the WHOLE document rather than per requirement: a posting says
    "we are hiring freshers" once, at the top, and every requirement under it
    inherits that. Per-requirement scanning would find it on one row and leave
    the rest silent, which reads as disagreement rather than as one statement.

    First match wins in list order, so an explicit "senior" beats an incidental
    "trainee" further down.
    """
    for name, pattern in reversed(_SENIORITY):
        if pattern.search(text):
            return name
    return None
