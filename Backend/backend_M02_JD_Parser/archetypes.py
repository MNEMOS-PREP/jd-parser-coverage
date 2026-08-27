"""The role archetype library, and what it fills in (FR-2.6, §6.3).

§3.2.1 trap 1: *"Assuming the JD contains enough information. The 40-word campus
JD is the MEDIAN, not the edge case. A parser tuned on LinkedIn-style JDs will
emit three requirements and a useless plan."*

That is this module's central risk and the archetype library is the counter. A
posting reading "Looking for SDE trainees. Good knowledge of DSA and OOPs."
yields two requirements, and a coverage plan over two requirements is not a mock
interview — it is two questions and a shrug.

── The honesty rule, which is the whole design ─────────────────────────────────

§6.3: *"if the JD yields < 5 measurable requirements, add archetype requirements
up to 8, each marked `source=archetype`. The UI shows these in a lighter style
with a tooltip: 'This wasn't in the JD, but it's standard for this role.'
Honesty here costs nothing and buys credibility."*

Every backfilled requirement carries `source="archetype"` and `span=None`,
because there is no span — nothing in the document said it. That combination is
what makes the addition auditable: a requirement with no span and
`source="jd"` would be a bug, and a screen can tell the two apart without
asking.

§6.4's weighting already discounts them at `source_w = 0.75`. That line has been
in `_raw_weight` since weights landed and has never had anything to apply to,
because every requirement came from the JD. It applies now: an inferred
requirement is worth three quarters of a stated one, so a backfilled set never
outvotes what the company actually wrote.

── Matched deterministically, not by embedding ─────────────────────────────────

§6.3 asks for cosine similarity over embeddings of the title and requirement
texts. There is no embedding model in this module and adding one for a
24-way classification would be the tail wagging the dog — so the match is token
overlap against a title vocabulary, weighted toward the title because that is
where the signal is: a posting titled "Data Analyst" is a data analyst whatever
its bullets say.

`confidence` is the top-1 score with §6.3's margin check against top-2 folded
in, and a weak or ambiguous match returns NO archetype rather than the best of a
bad set. Backfilling eight data-science requirements onto a posting we did not
actually recognise would produce a plan for a job nobody advertised — worse than
the thin plan it was trying to fix, because it looks complete.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#: §6.3 wants ~24. These are the ones an Indian campus placement season actually
#: produces, which is not the same list a general job board would give: the
#: support, testing and analyst roles are here because they are a large share of
#: mass-recruiter drives, and a student sitting one still needs a real mock.
#:
#: `requirements` is the canonical set a mock for this role should cover when
#: the posting says nothing. Ordered by how central each is, because the backfill
#: takes a prefix of the list.


@dataclass(frozen=True)
class Archetype:
    id: str
    name: str
    #: Words that appear in a title for this role. Matched whole, so "qa" does
    #: not fire on "quality" and "ml" does not fire on "html".
    titles: tuple[str, ...]
    #: What a mock for this role covers when the JD does not say.
    requirements: tuple[str, ...]
    #: §6.3's "typical duration". What the plan screen should default to.
    default_minutes: int = 45
    #: Terms in the BODY that support this archetype. Weaker evidence than the
    #: title and used only to break ties.
    signals: tuple[str, ...] = field(default_factory=tuple)


ARCHETYPES: tuple[Archetype, ...] = (
    Archetype(
        "sde_1",
        "Software Engineer",
        (
            "software engineer",
            "sde",
            "software developer",
            "programmer analyst",
            "swe",
            "member technical staff",
            "software engineering",
        ),
        (
            "Data Structures",
            "Algorithms",
            "OOPs",
            "DBMS",
            "Operating Systems",
            "Computer Networks",
            "Problem Solving",
            "SQL",
        ),
        60,
        ("coding round", "technical interview"),
    ),
    Archetype(
        "backend_engineer",
        "Backend Engineer",
        ("backend", "back end", "server side", "api engineer"),
        (
            "Data Structures",
            "Algorithms",
            "DBMS",
            "SQL",
            "REST APIs",
            "System design",
            "OOPs",
            "Operating Systems",
        ),
        60,
        ("microservices", "api", "database"),
    ),
    Archetype(
        "frontend_engineer",
        "Frontend Engineer",
        ("frontend", "front end", "ui engineer", "ui developer", "web developer"),
        (
            "JavaScript",
            "HTML",
            "CSS",
            "React",
            "Browser rendering",
            "Responsive design",
            "Accessibility",
            "Problem Solving",
        ),
        45,
        ("react", "angular", "vue", "css"),
    ),
    Archetype(
        "fullstack_engineer",
        "Full Stack Engineer",
        ("full stack", "fullstack", "mern", "mean stack"),
        (
            "JavaScript",
            "React",
            "REST APIs",
            "DBMS",
            "SQL",
            "Data Structures",
            "Algorithms",
            "System design",
        ),
        60,
    ),
    Archetype(
        "data_analyst",
        "Data Analyst",
        ("data analyst", "business intelligence", "bi analyst", "reporting analyst"),
        (
            "SQL",
            "Excel",
            "Data visualisation",
            "Statistics",
            "Python",
            "Business communication",
            "Dashboarding",
        ),
        45,
        ("tableau", "power bi", "dashboards"),
    ),
    Archetype(
        "data_scientist",
        "Data Scientist",
        ("data scientist", "data science"),
        (
            "Statistics",
            "Probability",
            "Machine Learning",
            "Python",
            "SQL",
            "Feature engineering",
            "Model evaluation",
            "Data visualisation",
        ),
        60,
        ("modelling", "regression", "hypothesis"),
    ),
    Archetype(
        "ml_engineer",
        "Machine Learning Engineer",
        ("machine learning engineer", "ml engineer", "ai engineer", "deep learning"),
        (
            "Machine Learning",
            "Deep Learning",
            "Python",
            "Model evaluation",
            "Data Structures",
            "Linear Algebra",
            "MLOps",
            "Statistics",
        ),
        60,
        ("pytorch", "tensorflow", "neural network"),
    ),
    Archetype(
        "data_engineer",
        "Data Engineer",
        ("data engineer", "etl developer", "big data"),
        (
            "SQL",
            "Python",
            "ETL",
            "Data modelling",
            "Spark",
            "Data warehousing",
            "Airflow",
            "Distributed systems",
        ),
        60,
        ("pipeline", "warehouse", "hadoop"),
    ),
    Archetype(
        "qa_engineer",
        "QA / Test Engineer",
        (
            "qa engineer",
            "quality assurance",
            "test engineer",
            "sdet",
            "automation engineer",
            "quality engineer",
        ),
        (
            "Testing fundamentals",
            "Test case design",
            "Selenium",
            "Automation",
            "SQL",
            "Debugging",
            "Problem Solving",
            "API testing",
        ),
        45,
        ("test cases", "regression testing"),
    ),
    Archetype(
        "devops_engineer",
        "DevOps Engineer",
        ("devops", "site reliability", "sre", "platform engineer", "build engineer"),
        (
            "Linux",
            "CI/CD",
            "Docker",
            "Kubernetes",
            "Scripting",
            "Networking",
            "Cloud platforms",
            "Monitoring",
        ),
        45,
        ("jenkins", "terraform", "ansible"),
    ),
    Archetype(
        "cloud_engineer",
        "Cloud Engineer",
        ("cloud engineer", "aws engineer", "azure engineer", "cloud consultant"),
        (
            "Cloud platforms",
            "Linux",
            "Networking",
            "Virtualisation",
            "Security basics",
            "Scripting",
            "Containers",
        ),
        45,
        ("aws", "azure", "gcp"),
    ),
    Archetype(
        "mobile_engineer",
        "Mobile Engineer",
        (
            "android developer",
            "ios developer",
            "mobile developer",
            "app developer",
            "flutter",
            "react native",
        ),
        (
            "Mobile app lifecycle",
            "Java",
            "Kotlin",
            "UI design",
            "REST APIs",
            "Data Structures",
            "Debugging",
        ),
        45,
    ),
    Archetype(
        "embedded_engineer",
        "Embedded Engineer",
        ("embedded", "firmware", "vlsi", "hardware engineer"),
        (
            "C programming",
            "Microcontrollers",
            "Operating Systems",
            "Digital electronics",
            "Communication protocols",
            "Debugging",
            "Data Structures",
        ),
        45,
        ("rtos", "arm", "verilog"),
    ),
    Archetype(
        "security_analyst",
        "Security Analyst",
        (
            "security analyst",
            "cyber security",
            "cybersecurity",
            "information security",
            "soc analyst",
            "penetration tester",
        ),
        (
            "Networking",
            "Operating Systems",
            "Cryptography basics",
            "Vulnerability assessment",
            "Security tools",
            "Incident response",
            "Linux",
        ),
        45,
        ("siem", "owasp", "threat"),
    ),
    Archetype(
        "network_engineer",
        "Network Engineer",
        ("network engineer", "network administrator", "noc engineer"),
        (
            "Computer Networks",
            "TCP/IP",
            "Routing and switching",
            "Linux",
            "Troubleshooting",
            "Network security",
        ),
        45,
        ("cisco", "ccna", "firewall"),
    ),
    Archetype(
        "dba",
        "Database Administrator",
        ("database administrator", "dba", "database engineer"),
        (
            "SQL",
            "DBMS",
            "Query optimisation",
            "Backup and recovery",
            "Transactions",
            "Indexing",
            "Database security",
        ),
        45,
        ("oracle", "postgres", "mysql"),
    ),
    Archetype(
        "support_engineer",
        "Support / Production Engineer",
        (
            "support engineer",
            "technical support",
            "production support",
            "application support",
            "service desk",
            "helpdesk",
        ),
        (
            "Troubleshooting",
            "SQL",
            "Linux",
            "Communication",
            "Incident management",
            "Customer handling",
            "Debugging",
        ),
        30,
        ("ticket", "sla", "escalation"),
    ),
    Archetype(
        "business_analyst",
        "Business Analyst",
        ("business analyst", "functional consultant", "process analyst"),
        (
            "Requirement gathering",
            "SQL",
            "Excel",
            "Business communication",
            "Stakeholder management",
            "Documentation",
            "Process modelling",
        ),
        45,
        ("stakeholder", "requirements", "user stories"),
    ),
    Archetype(
        "product_manager",
        "Associate Product Manager",
        ("product manager", "apm", "product analyst", "associate product"),
        (
            "Product sense",
            "Prioritisation",
            "Metrics and analytics",
            "Business communication",
            "SQL",
            "User research",
            "Case analysis",
        ),
        45,
        ("roadmap", "user stories", "product"),
    ),
    Archetype(
        "consultant",
        "Analyst / Consultant",
        ("consultant", "associate consultant", "analyst", "technology analyst", "systems engineer"),
        (
            "Aptitude",
            "Logical reasoning",
            "Business communication",
            "Case analysis",
            "Basic programming",
            "SQL",
            "Teamwork",
        ),
        45,
        ("client", "engagement", "case study"),
    ),
    Archetype(
        "ui_ux_designer",
        "UI/UX Designer",
        ("ux designer", "ui ux", "product designer", "interaction designer"),
        (
            "Design fundamentals",
            "Wireframing",
            "Figma",
            "User research",
            "Usability testing",
            "Visual communication",
            "Accessibility",
        ),
        45,
        ("figma", "prototype", "usability"),
    ),
    Archetype(
        "sales_bd",
        "Sales / Business Development",
        (
            "sales",
            "business development",
            "inside sales",
            "account manager",
            "pre sales",
            "presales",
        ),
        (
            "Communication",
            "Negotiation",
            "Product knowledge",
            "Objection handling",
            "Market awareness",
            "Teamwork",
            "Target orientation",
        ),
        30,
        ("crm", "pipeline", "quota"),
    ),
    Archetype(
        "hr_recruiter",
        "HR / Talent Acquisition",
        ("human resources", "hr executive", "talent acquisition", "recruiter", "hr generalist"),
        (
            "Communication",
            "Interviewing skills",
            "HR fundamentals",
            "Stakeholder management",
            "Documentation",
            "Conflict resolution",
        ),
        30,
        ("sourcing", "onboarding", "payroll"),
    ),
    Archetype(
        "research_intern",
        "Research Intern",
        ("research intern", "research associate", "research engineer", "phd intern"),
        (
            "Research methodology",
            "Machine Learning",
            "Statistics",
            "Paper reading",
            "Python",
            "Experimental design",
            "Technical writing",
        ),
        60,
        ("publication", "paper", "literature"),
    ),
)

BY_ID = {archetype.id: archetype for archetype in ARCHETYPES}

#: Below this the match is a guess, and a guess backfills eight requirements for
#: a job nobody advertised — which is worse than the thin plan it was fixing,
#: because it looks complete.
MIN_CONFIDENCE = 0.30

#: §6.3's margin check. Two archetypes within this of each other is an ambiguous
#: posting ("Software / Data Engineer"), and picking the higher one by a hair is
#: a coin toss the student cannot see.
MIN_MARGIN = 0.08

#: §6.3's backfill trigger and ceiling.
BACKFILL_BELOW = 5
BACKFILL_UP_TO = 8


def _token_set(text: str) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9+#.]+", text.lower()) if len(word) > 1}


def _phrase_hits(phrases: tuple[str, ...], text: str) -> int:
    """How many of these phrases appear in the text as whole words."""
    lowered = f" {' '.join(text.lower().split())} "
    return sum(1 for phrase in phrases if f" {phrase} " in lowered)


def _score(archetype: Archetype, title: str, body: str) -> float:
    """How well this archetype fits, in [0, 1].

    The title dominates deliberately. A posting titled "Data Analyst" is a data
    analyst whatever its bullets say, and the bullets on a campus posting are
    frequently boilerplate shared across every role the company is hiring for.
    """
    title_lowered = f" {' '.join(title.lower().split())} "
    title_score = 0.0
    for phrase in archetype.titles:
        if f" {phrase} " in title_lowered:
            # Longer phrases are more specific, and the gap between lengths has
            # to EXCEED `MIN_MARGIN` or the specific match and the generic one
            # cancel each other out as "ambiguous".
            #
            # That is not hypothetical: `consultant` carries a bare "analyst",
            # and at a shallower bonus "Data Analyst" scored 0.68 against its
            # 0.64 — a margin of 0.04, below the threshold, so a completely
            # unambiguous title matched NOTHING. One word of difference now
            # moves the score by 0.12.
            title_score = max(title_score, 0.45 + 0.12 * len(phrase.split()))

    requirement_tokens = _token_set(" ".join(archetype.requirements))
    body_tokens = _token_set(body)
    overlap = len(requirement_tokens & body_tokens) / max(len(requirement_tokens), 1)

    signal_score = 0.05 * _phrase_hits(archetype.signals, f"{title} {body}")

    return min(1.0, title_score + 0.35 * overlap + signal_score)


def match(title: str, body: str = "") -> tuple[Archetype | None, float]:
    """The archetype this posting is for, and how sure we are.

    Returns `(None, confidence)` when nothing scores high enough or when the top
    two are too close to separate. The confidence is still reported in that
    case, because "we looked and were not sure" is a different answer from "we
    did not look" and the screen says so.
    """
    scored = sorted(
        ((archetype, _score(archetype, title, body)) for archetype in ARCHETYPES),
        key=lambda pair: pair[1],
        reverse=True,
    )
    if not scored:
        return None, 0.0

    best, best_score = scored[0]
    runner_up = scored[1][1] if len(scored) > 1 else 0.0

    if best_score < MIN_CONFIDENCE:
        return None, round(best_score, 3)
    if best_score - runner_up < MIN_MARGIN:
        # "Software / Data Engineer" matches two archetypes almost equally.
        # Picking the higher by a hair is a coin toss the student cannot see.
        return None, round(best_score, 3)

    return best, round(best_score, 3)


def backfill_labels(archetype: Archetype, existing: list[str]) -> list[str]:
    """Archetype requirements to ADD, given what the posting already stated.

    §6.3: *"if the JD yields < 5 measurable requirements, add archetype
    requirements up to 8."* Below the trigger, nothing is added — a posting with
    six real requirements does not need help, and adding to it would dilute what
    the company actually wrote.

    Case-insensitive against what is already there, so a JD that says "SQL" does
    not get a second "SQL" from the archetype.
    """
    if len(existing) >= BACKFILL_BELOW:
        return []

    have = {" ".join(label.lower().split()) for label in existing}
    additions: list[str] = []
    for label in archetype.requirements:
        if len(existing) + len(additions) >= BACKFILL_UP_TO:
            break
        if " ".join(label.lower().split()) not in have:
            additions.append(label)
    return additions
