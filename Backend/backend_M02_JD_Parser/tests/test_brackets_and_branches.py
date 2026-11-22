"""Three misreads of one real campus posting (good_and_bads #11, 2026-11-22).

The Razorpay SDE-1 posting from the 29 Oct walkthrough: branch codes shown as
must-have skills, a bracketed list cut into "algorithms (arrays", and "CSE, IT
or ECE" read as two branches. Each line here is from that posting.
"""

from __future__ import annotations

from backend_M02_JD_Parser.extract import extract_eligibility, extract_surface_forms

POSTING = """Requirements
- B.Tech/B.E. in CSE, IT or ECE, graduating in 2026, CGPA 7.0 or above
- Strong data structures and algorithms (arrays, hashing, trees, graphs, dynamic programming)
- Good understanding of operating systems (processes, threads, concurrency) and DBMS (normalisation, SQL, ACID)
- Basic understanding of computer networks (HTTP, TCP/IP)

Good to have
- Experience with caching (Redis), message queues (Kafka) or cloud (AWS)
- Familiarity with message brokers (e.g. RabbitMQ)
"""


def labels() -> list[str]:
    return extract_surface_forms(POSTING)


def test_a_branch_code_is_not_a_skill():
    got = labels()
    for code in ("CSE", "IT", "ECE"):
        assert code not in got, f"{code} read as a skill"


def test_a_bracketed_list_belongs_to_its_phrase():
    got = labels()
    assert not any("(" in label or ")" in label for label in got), got
    for want in (
        "data structures",
        "algorithms",
        "arrays",
        "hashing",
        "dynamic programming",
        "operating systems",
        "threads",
        "DBMS",
        "SQL",
        "ACID",
        "HTTP",
        "TCP/IP",
        "caching",
        "Redis",
        "Kafka",
        "AWS",
    ):
        assert want in got, f"{want} missing from {got}"


def test_an_aside_in_brackets_is_not_a_requirement():
    got = labels()
    assert "RabbitMQ" in got
    assert not any(label.lower().startswith(("e.g", "eg ")) for label in got), got


def test_the_last_branch_after_or_is_eligible_too():
    assert extract_eligibility(POSTING).allowed_branches == ["CSE", "IT", "ECE"]


def test_it_in_a_sentence_is_not_a_branch():
    got = extract_surface_forms("Requirements\n- Experience with it, Python and SQL\n")
    assert "Python" in got and "SQL" in got
