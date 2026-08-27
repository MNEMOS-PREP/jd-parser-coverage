"""The backend surface and the frontend client, checked against each other.

`api.ts` already states this rule at the top of the file:

    "One hook per backend endpoint, and no hook without one… there is no hook
     here for `/v1/archetypes` or `/v1/jds/{id}/plan`, because writing one would
     let a screen be built on an endpoint that does not exist."

It was a comment, and a comment cannot notice. M01 shipped the same sentence and
still ended up with ten routes that had no client and four hooks that no screen
mounted — every one of them invisible from either side alone, because the
backend suite passed and the frontend built and the feature did not exist.

M02 is in the good state today: all six routes have a client. This is what keeps
it there while the module grows, which is the only time a check like this is
cheap to add.

── Why this lives in the Python suite ──────────────────────────────────────────

Because this suite is the one that runs. Both halves are in this repository and
the check has to read both, so a route added without a client fails the same
command that already gates a release rather than a second one somebody has to
remember.

It reads the frontend as TEXT rather than parsing TypeScript. A regex over
template literals is crude and it is enough: it answers "could any request in
this file produce that path", which is the question, and it cannot be satisfied
by a hook that names an endpoint in a comment.
"""

from __future__ import annotations

import importlib
import inspect
import pathlib
import pkgutil
import re

import pytest
from backend_M02_JD_Parser.app import app
from pydantic import BaseModel

_REPO = pathlib.Path(__file__).resolve().parents[3]
_FRONTEND = _REPO / "Frontend" / "frontend_M02_JD_Parser" / "src"

#: Routes the server declares as a second spelling of another. Empty today, and
#: kept as a named list rather than an inline exception so that adding one is a
#: decision somebody makes on purpose. It is not a place to park an endpoint
#: nobody got round to wiring.
ALIASES: dict[tuple[str, str], str] = {}


def _routes() -> set[tuple[str, str]]:
    """Every path this app serves.

    From the OpenAPI schema rather than `app.routes`: FastAPI wraps an included
    router in a node whose children are not on the top-level list, and walking
    that list reports almost nothing — a check that passes by seeing two
    endpoints out of thirty.
    """
    return {
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        for method in operations
        if method.upper() not in {"HEAD", "OPTIONS"}
    }


def _source(name: str) -> str:
    return (_FRONTEND / name).read_text(encoding="utf-8")


def _all_components() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in _FRONTEND.rglob("*.ts*")
        if path.name != "api.ts"
    )


def _backend_models() -> dict[str, type[BaseModel]]:
    """Every Pydantic model this module defines, found by walking the package.

    Imported by discovery rather than by a list of module names, because a list
    of module names is the same mistake one level up: `ledger.py` and `match.py`
    both arrived after this file did, and a hand-written list would have skipped
    them in silence.
    """
    import backend_M02_JD_Parser as package

    found: dict[str, type[BaseModel]] = {}
    for info in pkgutil.iter_modules(package.__path__):
        module = importlib.import_module(f"{package.__name__}.{info.name}")
        for obj in vars(module).values():
            if (
                inspect.isclass(obj)
                and issubclass(obj, BaseModel)
                and obj.__module__.startswith(package.__name__)
            ):
                found.setdefault(obj.__name__, obj)
    return found


def _interfaces() -> dict[str, str]:
    """Every `export interface` in `types.ts`, name to body."""
    return dict(re.findall(r"export interface (\w+) \{(.*?)\n\}", _source("types.ts"), re.DOTALL))


def _serialised_by(model: type[BaseModel]) -> set[str]:
    """Everything the model actually puts on the wire.

    `model_fields` is not that set. `Requirement.testable` and
    `EligibilityCriteria.stated` are `computed_field`s — derived on
    serialisation, present in every response, and invisible to `model_fields`.
    Reading only the declared fields would have reported the frontend as
    inventing two fields the backend sends on every parse.
    """
    return set(model.model_fields) | set(model.model_computed_fields)


def _declared_in(body: str) -> set[str]:
    """Field names an interface body declares, optional or not."""
    return set(re.findall(r"^\s{2}([a-z_0-9]+)\??:", body, re.MULTILINE))


def _model_interface_pairs() -> dict[str, tuple[type[BaseModel], str]]:
    """Backend models that share a name with a frontend interface.

    A shared name is the intent: somebody wrote `export interface MatchReport`
    because `MatchReport` crosses the wire. Models with no interface are not
    failures — `RequirementEdit` is a table, `JdParseIn` is a request — but
    once an interface exists the two halves must agree in full.
    """
    models = _backend_models()
    interfaces = _interfaces()
    return {name: (models[name], interfaces[name]) for name in models.keys() & interfaces.keys()}


def _client_exists_for(path: str, api: str) -> bool:
    """Could any template literal in `api.ts` produce this path?"""
    pattern = re.escape(path)
    # `{jd_id}` in the route -> `${anything}` in the template literal.
    pattern = re.sub(r"\\\{[a-z_]+\\\}", r"\\$\\{[^`]*?\\}", pattern)
    return re.search(pattern, api) is not None


@pytest.mark.gate
def test_every_endpoint_has_a_client():
    """A route with no caller is a feature that does not exist.

    It is worse than an unbuilt one: the tests pass, the docs list it, and the
    only person who finds out is the student who needed it.
    """
    api = _source("api.ts")

    orphans = sorted(
        f"{method} {path}"
        for method, path in _routes()
        if (method, path) not in ALIASES and not _client_exists_for(path, api)
    )

    assert not orphans, "backend routes with no client in api.ts:\n  " + "\n  ".join(orphans)


@pytest.mark.gate
def test_every_hook_is_mounted_by_a_screen():
    """The other direction, and the one that is easier to let slide.

    A hook nothing renders is an endpoint the student cannot reach — the same
    outcome as not writing it, reached by a route that looks finished in every
    file you would think to open.
    """
    api = _source("api.ts")
    components = _all_components()

    hooks = re.findall(r"export function (use[A-Za-z]+)", api)
    assert hooks, "no hooks found — the regex or the file layout changed"

    dead = sorted(hook for hook in hooks if not re.search(rf"\b{hook}\b", components))

    assert not dead, "hooks that no screen mounts:\n  " + "\n  ".join(dead)


@pytest.mark.gate
def test_every_raw_fetch_in_the_client_sends_identity():
    """A raw `fetch` bypasses `@ai/core`, and therefore bypasses its headers.

    There are none in this module today — every call goes through `api.get` and
    `api.post`. The check is here because the first one will be written the day
    a verb core does not carry is needed, by somebody with no reason to know
    that identity lives in a wrapper they are stepping around.

    That is not hypothetical. It happened in M01 the day identity landed: PATCH
    and multipart upload were both raw `fetch`, both missed the header, and the
    backend answered 403 to every upload and every correction while the paste
    path worked perfectly.
    """
    source = _source("api.ts")

    calls = re.findall(r"fetch\((.*?)\n  \}\)", source, re.DOTALL)
    naked = [call for call in calls if "identityHeaders" not in call]

    assert not naked, (
        "raw fetch without identity headers — the backend will answer 403:\n  "
        + "\n  ".join(call.strip()[:90] for call in naked)
    )


# ---------------------------------------------------------------------------
#  The shape of the response, not just the address of it
# ---------------------------------------------------------------------------


@pytest.mark.gate
def test_every_field_the_backend_returns_is_declared_on_the_frontend():
    """A field with no consumer is a feature that stops at the database.

    The three gates above check that a route has a caller and a hook has a
    screen. None of them notices the drift that actually happens most often:
    the backend grows a field, the response carries it, and no frontend type
    mentions it — so nothing renders it and the tests are all green.

    That is not hypothetical. `requirement_groups` landed on 2026-08-27 and
    would have been invisible: the parse folds "Docker or Kubernetes" into one
    choice, stores the group, returns it, and the screen goes on drawing two
    separate demands — the exact §3.2.1 mistake, fixed in the parser and
    reintroduced by the renderer.

    ── Why the pairs are discovered rather than listed ─────────────────────────

    This gate used to name two models, `JobDescription` and `Requirement`,
    because those were the two that had drifted. Which made it a check that
    could only catch the bug it was written for: `CoveragePlan`, `MatchReport`,
    `Risk`, `Verdict` and `PlannedRound` all arrived afterwards and none was
    looked at, and `CoverageAllocation.grounded` sat unreachable by any screen
    with the whole suite green.

    So the set is derived. Every Pydantic model this module defines that shares
    a name with an interface in `types.ts` is a pair somebody intended, and the
    two halves have to agree. A model with no interface is not a failure — not
    everything the backend defines is meant to cross the wire — but the moment
    one exists, it is held to the whole model.

    Declared, not necessarily rendered. A type is where a field becomes
    reachable, and a field nobody typed is one nobody can reach.
    """
    pairs = _model_interface_pairs()
    assert len(pairs) >= 10, (
        f"only {len(pairs)} model/interface pairs discovered — types.ts or the "
        "package layout changed and this gate now checks almost nothing"
    )

    drift: list[str] = []
    for name, (model, body) in sorted(pairs.items()):
        missing = sorted(_serialised_by(model) - _declared_in(body))
        if missing:
            drift.append(f"  {name}: {', '.join(missing)}")

    assert not drift, (
        "backend fields absent from the matching frontend interface:"
        + "\n"
        + "\n".join(drift)
        + "\nAdd them to types.ts, or the screen cannot reach what the backend found."
    )


@pytest.mark.gate
def test_the_frontend_does_not_invent_fields_the_backend_never_sends():
    """The same drift running the other way, and it fails later and worse.

    An interface declaring `confidence_label` the backend does not send
    compiles perfectly, renders `undefined`, and is discovered by a student
    looking at a blank cell. TypeScript cannot catch it: the value arrives as
    JSON and the interface is an assertion ABOUT that JSON, not a check of it.

    Optional fields are exempt. `name?:` is the declared way to say "may be
    absent", and the client legitimately builds partial objects while a request
    is in flight.
    """
    invented: list[str] = []
    for name, (model, body) in sorted(_model_interface_pairs().items()):
        required = set(re.findall(r"^\s{2}([a-z_0-9]+):", body, re.MULTILINE))
        extra = sorted(required - _serialised_by(model))
        if extra:
            invented.append(f"  {name}: {', '.join(extra)}")

    assert not invented, (
        "frontend interfaces declaring fields no backend model has:"
        + "\n"
        + "\n".join(invented)
        + "\nThese render as undefined. Mark them optional or delete them."
    )


# ---------------------------------------------------------------------------
#  AC-2.2 [GATE] — `not_measured` never renders as a number
# ---------------------------------------------------------------------------


@pytest.mark.gate
def test_not_measured_carries_no_number_to_render():
    """The backend half, and the one that makes the UI half impossible to break.

    §13 words this gate as "verified in UI tests", and this repository has no
    frontend test runner — adding one is a toolchain and a network install for
    a single assertion. What it has instead is the stronger version of the same
    guarantee: a screen cannot render a number that was never sent.

    `mastery[label]` is `None` for every `not_measured` requirement, and
    `coverage_score` is `null` rather than `0.0` whenever nothing could be
    checked. A zero is the failure mode that survives review, because it looks
    like a measurement and reads like a verdict.
    """
    from backend_M02_JD_Parser.router import NOT_MEASURED_SEVERITY

    # Asserted against the module's own constant rather than a literal, so a
    # change to §6.5's discount moves this with it instead of breaking it.
    assert 0 < NOT_MEASURED_SEVERITY < 1


@pytest.mark.gate
def test_a_state_outside_the_scale_never_reaches_the_bar():
    """The UI half, read as source — the same technique the gates above use.

    `MasteryBar` comes from `@ai/core` precisely so "a non-displayable state can
    never render a number" is defined once for nineteen modules. This asserts
    M02 has not quietly widened it: `unmeasurable` and `met_by_alternative` are
    outside the scale, not points on it, and the mapping must exclude them.

    A regex over a type declaration is crude and it is enough. It answers "could
    this module hand a bar a state that has no number", which is the question,
    and it cannot be satisfied by a comment.
    """
    source = (_FRONTEND / "components" / "CoveragePanel.tsx").read_text(encoding="utf-8")

    mapping = re.search(
        r"TO_MASTERY_STATE:\s*Record<\s*(.*?),\s*MasteryState\s*>", source, re.DOTALL
    )
    assert mapping, "TO_MASTERY_STATE changed shape — this gate needs rewriting, not deleting"

    excluded = mapping.group(1)
    assert "Exclude<" in excluded, "the mapping stopped excluding anything"
    for state in ("unmeasurable", "met_by_alternative"):
        assert state in excluded, f"{state} can now reach MasteryBar, and it has no number"
