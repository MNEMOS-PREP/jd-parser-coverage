"""Scoring the golden set (§10, AC-2.3, AC-2.4).

── Read this before quoting a number from it ───────────────────────────────────

§10 asks for *"25 JDs with hand-annotated requirements + necessity"* and
*"disjunction parser on 30 real strings"*. What is in
`research/data/golden/jds.json` is 12 JDs and 30 strings, and eleven of the
twelve are **synthetic** — written to cover the shapes the spec names rather
than sampled from what a placement cell actually mails out. The twelfth is real
(Cognizant's 2027 Ace Team brochure, trimmed to its requirement-bearing
sections), and it is the only one that is.

That difference matters in one direction: the documents and the parser were
written by the same hand, so an F1 measured here is an OPTIMISTIC estimate of
an F1 on postings nobody wrote for it, and adding more synthetic fixtures does
not fix that. It makes the number look better while measuring the same thing.

So there are two jobs and only one is being done:

  **A regression gate — done.** A change that makes extraction worse fails the
  build. This works whatever the documents' provenance, because it compares the
  parser against a fixed annotation rather than against reality. Until today
  every extraction change in this module was verified by reading output on one
  or two examples; that method found four real bugs on 2026-08-27 and would
  have caught none of them twice.

  **The acceptance measurement — not done.** AC-2.3 ≥ 0.85 and AC-2.4 ≥ 0.95
  are claims about real postings. They stay UNMEASURED until real ones land.
  `MEASURES_REAL_WORLD` is the flag that says so, and it is False. Flipping it
  is a deliberate act that goes with replacing the corpus.

Stating that here rather than in a commit message is the point. A synthetic
golden set quietly relabelled as acceptance evidence is exactly how a project
ends up believing it met a bar it never tested.

── Why the annotation disagrees with the parser on purpose ─────────────────────

`requirements` in the fixture is what a careful reader would list, in the
posting's own words — not what the parser returns. Several entries are things it
currently misses. A golden set that agrees with the implementation measures the
implementation against itself and always scores 1.0.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass

from ai_core.concepts import normalise_alias

#: False, and it is a claim about the CORPUS rather than about the code.
#:
#: Eleven of twelve documents are synthetic. Until that is the other way round,
#: the numbers below are a regression signal and not acceptance evidence.
MEASURES_REAL_WORLD = False

#: §13's targets, recorded here so the gap between them and the measurement is
#: visible in one place rather than only in the spec.
AC_2_3_TARGET = 0.85
AC_2_4_TARGET = 0.95

_ROOT = pathlib.Path(__file__).resolve().parents[2] / "research" / "data" / "golden"


@dataclass(frozen=True)
class GoldenJd:
    id: str
    role: str
    text: str
    #: What a careful reader would list. Deliberately not the parser's output.
    requirements: tuple[str, ...]
    note: str = ""


@dataclass(frozen=True)
class GoldenDisjunction:
    text: str
    #: Empty where the string is NOT a disjunction. Half the value of the set:
    #: splitting "CI/CD" fabricates a skill, and fabricating is worse than
    #: missing, so the negatives carry more weight than the positives.
    parts: tuple[str, ...]


def _load() -> dict:
    return json.loads((_ROOT / "jds.json").read_text(encoding="utf-8"))


def load_jds() -> list[GoldenJd]:
    return [
        GoldenJd(
            id=case["id"],
            role=case["role"],
            text=case["text"],
            requirements=tuple(case["requirements"]),
            note=case.get("note", ""),
        )
        for case in _load()["cases"]
    ]


def load_disjunctions() -> list[GoldenDisjunction]:
    return [
        GoldenDisjunction(text=case["text"], parts=tuple(case["parts"]))
        for case in _load()["disjunctions"]
    ]


@dataclass
class Score:
    """Set-valued precision and recall over normalised labels.

    Normalised because "REST APIs" and "REST API" are the same requirement and
    a golden set that punished the difference would measure spelling. Set-valued
    because a posting listing a requirement twice is making it once — which is
    the same rule `locate` follows.
    """

    matched: int = 0
    predicted: int = 0
    expected: int = 0

    @property
    def precision(self) -> float:
        return self.matched / self.predicted if self.predicted else 1.0

    @property
    def recall(self) -> float:
        return self.matched / self.expected if self.expected else 1.0

    @property
    def f1(self) -> float:
        if not (self.precision + self.recall):
            return 0.0
        return 2 * self.precision * self.recall / (self.precision + self.recall)

    def add(self, predicted: set[str], expected: set[str]) -> None:
        self.matched += len(predicted & expected)
        self.predicted += len(predicted)
        self.expected += len(expected)

    def __str__(self) -> str:
        return (
            f"precision {self.precision:.3f}  "
            f"recall {self.recall:.3f}  "
            f"F1 {self.f1:.3f}  "
            f"({self.matched} matched / {self.predicted} predicted / {self.expected} expected)"
        )


def keys(labels) -> set[str]:
    """Normalised, non-empty, deduplicated."""
    return {key for label in labels if (key := normalise_alias(label))}
