"""Every requirement is quoted, and every choice is read (2026-11-17).

Two parser gaps found by holding a real posting against a real resume:

- "REST APIs with FastAPI or Flask" gave FastAPI and Flask as two must-haves,
  so a student with FastAPI read as missing one. The choice is written
  BETWEEN the requirements, not inside one label, and only compound labels
  were read for choices.
- A concept found through an alias ("AWS") was added under its ontology NAME
  ("Amazon Web Services"), which the posting never wrote: a requirement with
  no span, claiming to come from the JD, beside a duplicate of itself.
"""

from __future__ import annotations

from backend_M02_JD_Parser.extract import locate, prose_surfaces


def _groups(text: str, labels: list[str]) -> list[list[str]]:
    result = locate(text, labels, resolved={}, sources={})
    by_id = {r.id: r.text for r in result.requirements}
    return [[by_id[i] for i in g.requirement_ids] for g in result.groups]


def test_a_choice_written_between_two_requirements_is_one_group():
    text = "Requirements:\n- Experience building REST APIs with FastAPI or Flask.\n"
    assert _groups(text, ["FastAPI", "Flask"]) == [["FastAPI", "Flask"]]


def test_a_comma_list_ending_in_or_is_one_choice():
    # A slash ("PyTorch/TensorFlow") is read by `find_disjunctions`, which asks
    # the ontology first so "CI/CD" stays whole; this is the English list.
    assert _groups("Any of Java, Python or C++.", ["Java", "Python", "C++"]) == [
        ["Java", "Python", "C++"]
    ]


def test_and_is_two_demands_and_a_new_line_is_never_a_choice():
    assert _groups("Strong Python and SQL.", ["Python", "SQL"]) == []
    assert _groups("- Python\nor anything else\n- SQL", ["Python", "SQL"]) == []
    assert _groups("Python, SQL, Docker.", ["Python", "SQL", "Docker"]) == []


def test_a_choice_keeps_its_weight_shared_not_doubled():
    result = locate(
        "Use FastAPI or Flask. Use Docker.", ["FastAPI", "Flask", "Docker"], resolved={}, sources={}
    )
    weights = {r.text: r.weight for r in result.requirements}
    assert weights["FastAPI"] == weights["Flask"]
    assert weights["FastAPI"] < weights["Docker"]


def test_an_alias_is_kept_in_the_postings_own_words():
    concepts = [
        {"name": "Amazon Web Services", "aliases": ["AWS"]},
        {"name": "Large Language Models", "aliases": ["LLMs", "LLM"]},
        {"name": "Recursion", "aliases": ["recursion"]},
    ]
    found = prose_surfaces("Experience with AWS, LLMs and recursion.", concepts)
    assert found == {
        "Amazon Web Services": "AWS",
        "Large Language Models": "LLMs",
        # The name itself, in another case, keeps the name's spelling.
        "Recursion": "Recursion",
    }


def test_a_parsed_posting_quotes_every_requirement(client, m04_mastery):
    m04_mastery(
        {"measured": []},
        extra_concepts=[
            {"name": "Amazon Web Services", "aliases": ["AWS"]},
            {"name": "Retrieval-Augmented Generation", "aliases": ["RAG"]},
        ],
        extra_resolutions={
            "AWS": "concept:aws",
            "RAG pipelines": "concept:rag",
            "RAG": "concept:rag",
        },
    )
    res = client.post(
        "/v1/jds/parse",
        json={
            "company_name": "Nimbus",
            "role_title": "ML Engineer",
            "raw_text": (
                "Requirements:\n"
                "- Experience building REST APIs with FastAPI or Flask.\n"
                "- Deploying on AWS.\n"
                "- Building RAG pipelines.\n"
            ),
        },
    )
    assert res.status_code == 201, res.text
    jd = res.json()
    texts = [r["text"] for r in jd["requirements"]]
    # The ontology's names never stand in for the posting's words...
    assert "Amazon Web Services" not in texts
    assert "Retrieval-Augmented Generation" not in texts
    # ...so every requirement the posting stated points at where it says so.
    assert all(r["span"] for r in jd["requirements"] if r["source"] == "jd")
    # "RAG" is inside a stated line already: the same requirement, not a second.
    assert "RAG" not in texts
    # And a choice is grouped whenever both of its answers were read.
    if "FastAPI" in texts and "Flask" in texts:
        by_id = {r["id"]: r["text"] for r in jd["requirements"]}
        groups = [sorted(by_id[i] for i in g["requirement_ids"]) for g in jd["requirement_groups"]]
        assert ["FastAPI", "Flask"] in groups
