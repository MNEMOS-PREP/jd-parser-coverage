"""Reading a responsibilities block by its objects rather than its verbs.

The TODO carried this for weeks as *"needs a label-level test of does this name
a thing rather than an action"*, and the section stayed unread. On the real
Cognizant brochure that was the most technology-dense part of the posting —
multi-agent systems, RAG pipelines, vector stores, knowledge bases — discarded
to avoid four verbs.

These tests are about the two things that make the split work without a verb
list: the run is found positionally, and ambiguity is settled by the document
rather than by a vocabulary of ambiguous words.
"""

from __future__ import annotations

from backend_M02_JD_Parser.extract import (
    _list_lines,
    known_things,
    object_of,
    resolve_action_block,
)

# The four bullets from the real brochure, verbatim.
BROCHURE = """What you will do

• Build and orchestrate multi-agent AI systems.
• Specify intent prompts for AI coding agents.
• Validate AI-generated code for quality and correctness.
• Design and build RAG pipelines, vector stores, and knowledge bases
"""


# ---------------------------------------------------------------------------
#  The positional split
# ---------------------------------------------------------------------------


def test_the_verb_run_is_found_without_a_verb_list():
    """ "orchestrate" is not on any list, and would not have been.

    In an action clause the verb comes first and English conjoins verbs with a
    bare and/or before the object begins, so the split is positional. That is
    the whole reason this works on a posting written after the code.
    """
    assert object_of("• Build and orchestrate multi-agent AI systems.") == (
        "multi-agent AI systems"
    )
    assert object_of("• Specify intent prompts for AI coding agents.") == (
        "intent prompts for AI coding agents"
    )


def test_a_bullet_opening_on_a_real_skill_is_left_alone():
    """ "Python and SQL development" is a requirement, not a job.

    Both words are things the module knows, and a conjunction joins like with
    like, so the run is a noun phrase.
    """
    line = "• Python and SQL development"
    assert object_of(line) == line


def test_a_conjunction_of_a_thing_and_a_non_thing_reads_as_verbs():
    """ "Design" is in the vocabulary because "System Design" is an archetype
    requirement, so a first-word test left this line untouched and lost the
    densest line in the posting.

    "build" is not a thing. A conjunction joins like with like, so the pair
    resolves in favour of the verb reading — and the sentence disambiguates
    itself without anybody listing "design" as ambiguous.
    """
    assert object_of("• Design and build RAG pipelines, vector stores") == (
        "RAG pipelines, vector stores"
    )


def test_a_particle_is_not_an_object():
    """ "Build out" is a verb, and one word after it is not a requirement."""
    assert object_of("• Roll out") == "• Roll out"


def test_a_sentence_is_not_split():
    """Past a few words the leading run is not a verb phrase and the split
    would be a guess."""
    line = "• We are very much looking for people who thrive in ambiguity"
    assert object_of(line) == line


# ---------------------------------------------------------------------------
#  The block settles its own ties
# ---------------------------------------------------------------------------


def test_an_ambiguous_bullet_is_resolved_by_its_siblings():
    """ "Design AI-native solutions" has no conjunction to disambiguate it.

    Its siblings do. A block of jobs is written in one voice, so if the
    unambiguous bullets opened on verbs, this one did too. The alternative is a
    list of every noun-verb in the language — architect, engineer, test,
    monitor, scale, partner — which would still be wrong for the posting that
    used one the other way.
    """
    block = [
        "• Build and orchestrate multi-agent AI systems.",
        "• Specify intent prompts for AI coding agents.",
        "• Design AI-native solutions, agentic workflows, and AI architectures.",
    ]

    resolved = resolve_action_block(block)

    assert resolved[-1] == "AI-native solutions, agentic workflows, and AI architectures"


def test_a_block_of_things_leaves_its_ambiguous_bullet_alone():
    """The rule has to run both ways or it is not a rule.

    A block whose siblings are noun phrases says the ambiguous one is a noun
    phrase too, and stripping it would invent a requirement out of a modifier.
    """
    block = [
        "• Python and SQL development",
        "• Java and Spring experience",
        "• Design patterns and architecture",
    ]

    assert resolve_action_block(block) == block


def test_no_majority_leaves_the_line_alone():
    """The same refusal the archetype matcher makes when two roles are too
    close: with nothing to settle the tie, do not guess."""
    block = ["• Design patterns and architecture"]

    assert resolve_action_block(block) == block


# ---------------------------------------------------------------------------
#  End to end through `_list_lines`
# ---------------------------------------------------------------------------


def test_the_responsibilities_block_yields_its_objects():
    lines = _list_lines(BROCHURE)

    assert "multi-agent AI systems" in lines
    assert "intent prompts for AI coding agents" in lines
    assert "RAG pipelines, vector stores, and knowledge bases" in lines
    assert not any(line.strip().startswith("Build") for line in lines), (
        "a verb reached the requirement list"
    )


def test_a_requirements_block_is_untouched_by_any_of_this():
    """The strip runs under an ACTION heading and nowhere else.

    An ordinary requirements list must parse exactly as it did before this
    existed, which is most of what the 271 tests around this one are checking.
    """
    lines = _list_lines(
        "Requirements:\n• Strong DBMS and SQL fundamentals\n• Object Oriented Programming\n"
    )

    assert any("Strong DBMS" in line for line in lines)


def test_an_ordinary_heading_closes_the_action_block():
    """Otherwise the verb strip runs on the requirements that follow it."""
    lines = _list_lines(
        "What you will do\n"
        "• Build and orchestrate multi-agent AI systems.\n"
        "Requirements:\n"
        "• Strong DBMS fundamentals\n"
    )

    assert "multi-agent AI systems" in lines
    assert any("Strong DBMS" in line for line in lines)


# ---------------------------------------------------------------------------
#  The vocabulary is derived, not written
# ---------------------------------------------------------------------------


def test_the_thing_vocabulary_comes_from_the_archetypes():
    """A second list of "words that are things" would need maintaining beside
    the first, and the day somebody added a requirement to an archetype without
    also adding it here, the strip would start eating it."""
    things = known_things()

    assert "python" in things
    assert "design" in things, "from 'System Design' — the ambiguity is real"
    assert "orchestrate" not in things
    assert len(things) > 50, "the archetype requirement sets did not load"
