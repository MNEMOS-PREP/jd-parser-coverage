# M02 — JD Parser & Coverage Planner

> **What is this job actually asking for, and where do you stand against it.**
> A pasted JD becomes the configuration for everything downstream: the
> requirements, the student's gap against them, and the question budget the
> mock spends closing it.
>
> Spec: [plan_in_depth/M02_JD_Parser.md](plan_in_depth/M02_JD_Parser.md) · Ports: API `8102`, web `5202` ([PORTS.txt](PORTS.txt))

```bash
git clone https://github.com/MNEMOS-PREP/jd-parser-coverage
cd jd-parser-coverage
python -m venv Backend/.venv && Backend/.venv/Scripts/python -m pip install -e ".[dev]"
Backend/.venv/Scripts/python -m pytest       # 13 passed, no network, no API key
cd Frontend && npm install && cd ..
start_jd.bat                                  # API :8102 · web :5202
```

No API key needed, and **no model is called anywhere in this milestone.** The
scan is a word-boundary match over an ontology; the gap is arithmetic. The
spec's extraction stage (§6.2) is where a model arrives, and it has not.

---

## What is built

A thin spine, and one property held properly.

| Endpoint | What it does |
|---|---|
| `POST /v1/jds/parse` | Word-boundary scan of the JD text against M04's ontology; resolves each hit to a `concept_id` |
| `GET /v1/jds/{id}` | The stored JD |
| `GET /v1/jds/{id}/coverage/{candidate_id}` | Per-requirement state and gap severity against M04's mastery |
| `GET /v1/deps` | Which upstreams are up and what breaks when they are not |
| `GET /health` | |

**The property worth the code: this module never fabricates.** Both halves of
that are tested rather than asserted in a comment.

**1. A missing measurement is `null`, never `0.0`.** [`router.py`](Backend/backend_M02_JD_Parser/router.py) ·
With M04 unreachable the first version returned `coverage_score: 0.0`, every
requirement in `missing`, and `gap_severity: 1.0`. That is a confident,
specific statement that the student meets none of this job's requirements —
produced by a service nobody asked, on the default path, because a missing
`base_url` in the manifest meant M04 was never called even when it was
running. Now the score is `null`, the state is `not_measured`, severity is
`0.6` (spec §6.5: we do not know, so we should probe), and `degraded` names
M04 on the response. The mirror case is fixed too: a JD with no mappable
requirements returned `1.0`, fabricated full coverage; unmappable
requirements are now `unmeasurable` (EC-2.8) and sit outside the score.

**2. A guessed `concept_id` is labelled as a guess.** An id is a licence for
M05 to build questions on and for M13 to score against. With M04 down this
module falls back to a five-entry table — useful, and now carrying
`concept_source: "offline_fallback"` per label, plus `scanned_against` for the
lexicon itself. Nothing from the offline table is presented as ontology.

### What is deliberately not built

Everything else, and it is **absent, not stubbed** — an endpoint that returns
a placeholder is worse than one that does not, because a caller writes against
it and finds out later.

Measured against [§4](plan_in_depth/M02_JD_Parser.md), **2 of 16 functional
requirements are met**: FR-2.5 (concept mapping, with `unmeasurable` marked)
and FR-2.7 (a per-requirement gap with `not_measured` as a distinct state).
FR-2.1 is partly met — pasted text only, no PDF/DOCX, no company picker, no
role picker.

The fourteen that are not, roughly in the order they block something:

| Missing | What it blocks |
|---|---|
| **Role archetype** (§6.3, FR-2.6) | M15 already declares M02 and names "role archetype" as what it takes. There is no archetype, no `/v1/archetypes`, no backfill. M15's role matching is still on its fallback path — this is the single highest-value thing to build here. |
| **`CoveragePlan`** (§6.5, FR-2.8/2.9) | M06 has nothing to configure a mock with. There is no question budget, no round mix, no `uncovered` list. Coverage today reports a *state*, not a *plan*. |
| **Requirement structure** (§5, FR-2.2) | No `kind`, `necessity`, `weight`, or `span`. Every requirement is equally important, which §3.1 Trap 2 names as the specific way this module fails: "Good knowledge of DSA" and "Bonus: Docker" are not equal, and a flat list makes them equal. |
| **Disjunction groups** (FR-2.3) | "Java/Python/C++" is three requirements here, so a Python-only student looks 33% qualified. §3.2 calls this out by name. |
| **Eligibility** (FR-2.4, FR-2.15) | CGPA cutoffs, backlogs, bond, package. §2.3 puts these at the top of the read-back screen because students waste weeks preparing for drives they cannot sit. |
| **Coverage ledger** (§6.6, FR-2.11) | M19 has no coverage report. §6.6 is explicit that the ledger is written at selection time, not reconstructed after. |
| **JD hash cache** (FR-2.12) | Sixty students paste the same campus JD and we parse it sixty times. |
| **Role-only mode** (FR-2.14) | A student with no drive scheduled cannot use the module at all. Spec calls Door 3 "mandatory". |

The scan itself is also not the spec's pipeline: §6.1 normalisation
(boilerplate stripping, admin/role block separation) and §6.2 structured
extraction do not exist, so a 40-word campus JD — which §2.1 says is the
*median* case, not the edge case — yields whatever of five concepts happen to
appear literally in it.

### Contract note

The spec's §7 surface is `POST /v1/jds` and `GET /v1/jds/{id}/gap`; this code
serves `POST /v1/jds/parse` and `GET /v1/jds/{id}/coverage/{candidate_id}`.
Nothing consumes either yet, so the divergence is free to resolve in whichever
direction — but it should be resolved before M05 or M06 writes against it.

---

## The frontend

Two screens on `:5202`, and the reason they are only two is that the backend
fills only two. `src/api.ts` has one hook per endpoint and none without one —
the same rule the router keeps, applied on the other side of the wire.

**The coverage rows use `MasteryBar` from `@ai/core`, not a local component.**
Spec §8 makes "not measured must look different from weak" a *fairness*
property: a student with no session history has every requirement unmeasured,
so if the two treatments ever collapse, the most common first-run state on the
platform reads as a wall of failures. `@ai/core` holds the single definition of
that distinction, and it enforces "a non-displayable state can never render a
number" in code rather than in a comment. A nineteenth copy is how the promise
stops being true in whichever repo falls behind while its own tests pass.

Building this surfaced one thing worth fixing upstream: `MasteryValue.n_direct`
was required, and M02 has no evidence count to put in it — it reads a coverage
summary, not M04's ledger. Passing `0` rendered "tested 0×" under a strong bar,
a fabricated fact produced by the type signature of the component built to
prevent fabricated facts. Platform_Core v0.6.0 makes it optional.

What the screens deliberately do **not** do:

- **Invent an ordering.** With no `necessity` or `weight`, requirements are a
  flat list and the page says so in an expandable note rather than implying a
  priority the backend never sent.
- **Pick a "biggest gap".** §2.3 highlights one. Every severity here is either
  `0.6` (not measured) or `1 − mastery`, so a single highlighted gap would be an
  artefact of list order.
- **Render dead controls.** The company picker, role picker and campus-drive
  chips are named on the page as not built. A greyed-out button that does
  nothing reads as a broken product; a named gap reads as an unfinished one.

---

## Layout

```
module.json                     manifest: ports, upstreams, feeds. Read at
                                request time to probe M04.
dependencies.txt                the same thing for humans, plus what breaks
PORTS.txt                       platform-wide port allocation
Backend/
  backend_M02_JD_Parser/
    app.py                      FastAPI app, SQLite engine, /health
    router.py                   every endpoint, and the M04 client
    models.py                   JobDescription — the whole data model today
    tests/                      13 tests, no socket opened
  seed.py                       two JDs, provenance-marked as seeded
Frontend/
  frontend_M02_JD_Parser/
    src/api.ts                  one hook per endpoint, and none without one
    src/types.ts                only fields the API actually sends
    src/components/             ParsePage, JdPage, CoveragePanel, DepsPage
    src/ui/                     shell, primitives, design tokens
scripts/                        launcher engine (shared, identical across repos)
start_jd.bat                    this module            (:8102 · :5202)
start_all.bat                   plus any sibling repo checked out next door
```

## Conventions worth knowing before you edit

- **`module.json` and `dependencies.txt` are one fact in two files.** Edit one,
  edit the other. The backend reads the first at startup.
- **Every declared upstream carries a `base_url`.** `from_manifest` defaults it
  to `""`, and an empty base_url disables the upstream *silently* — the module
  runs in fallback with M04 healthy on :8104 and says nothing. That was this
  repo's first bug.
- **The sibling folder name comes from the repo URL's last path segment.**
  On-disk folder and GitHub repo name must agree or `start_all.bat` skips a
  running module in silence.
- **`not_measured` is a state, not a zero.** If you add a number to a response,
  say where it came from and what it means when the input is missing.
- `ruff check .` before committing; the config is in `pyproject.toml`.
