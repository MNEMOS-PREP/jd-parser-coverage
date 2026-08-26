# M02 — TODO · JD Parser & Coverage Planner

Running list for **M02 JD Parser & Coverage Planner**.
Spec: [M02_JD_Parser.md](M02_JD_Parser.md)

> **Read this first when starting a session on M02.** It is the running state
> of the module: what is done, what is next, and what is deliberately deferred.
> Update it as things land — a stale list is worse than no list, because the
> next session trusts it.

- **Phase:** 1 · **Owner:** E3 · **Ports:** API `8102`, web `5202`
- **Repo:** `jd-parser-coverage`

Legend: ✅ done · 🟡 partly done · ⬜ not started

---

## 0. Ideas and scouting

Things worth building that did not come from the spec — usually from reading
somebody else's implementation. **New ideas go at the top of this section.**

The rule we keep arriving at: borrow a **technique**, not a **component**. The
platform's contracts — character offsets, per-fact provenance, permanent
evidence — are more demanding than general-purpose tools assume, so integration
usually costs more than reimplementing the one idea we actually wanted.

_Nothing scouted for this module yet._

---

## 1. Where the module stands

| | |
|---|---|
| Status | **The parser half exists. The coverage planner does not.** |
| Backend tests passing | **32** |
| Release gates (`-m gate`) | **6** |
| Route decorators | **7** |
| Frontend | present — `JdPage`, `ParsePage`, `CoveragePanel`, `DepsPage` |

*Audited 2026-08-25 in code, not from this file. This row replaced "Not
started", which was written before the module was.*

---

### 1.1 What is built, and one part of it is the hard part

- ✅ **FR-2.5** — every requirement resolved to a `concept_id` or kept as
      unmapped, with `concept_source` recording whether M04 confirmed the id or
      an offline table guessed it.
- ✅ **FR-2.7, and it is the one worth having.** `GET /jds/{id}/coverage/{cid}`
      treats **"not measured" as a distinct state**, and `coverage_score` is a
      fraction of the requirements that could actually be checked — never of
      all of them — so an unmeasured requirement can never depress it. That is
      the trap this endpoint exists to avoid and it is avoided.

### 1.2 What is missing — §5's contracts, almost entirely

The spec declares seven types. **None of them exist in `models.py`**, which is
one table whose requirements are a flat `list[str]`:

    Requirement · RequirementGroup · EligibilityCriteria
    RequirementSet · Gap · CoverageAllocation · CoveragePlan

| FR | | |
|---|---|---|
| FR-2.1 | 🟡 | Pasted text only. `JdParseIn` requires `raw_text`; no PDF/DOCX, no company+role |
| FR-2.2 | 🟡 | **Spans landed 2026-08-25** — every requirement carries a `SourceSpan` that resolves verbatim, and the JD screen quotes the line each one came from. Still no `kind`, `necessity` or `weight`: omitted rather than defaulted, because a `necessity: "must"` on every row would look derived and would be what the coverage plan allocates on |
| FR-2.3 | ⬜ | No disjunctive `any_of` groups |
| FR-2.4 | ⬜ | Eligibility is **actively discarded** — see below |
| FR-2.6 | ⬜ | No role archetype inference |
| FR-2.8 | ⬜ | No `CoveragePlan`, no question budget. This is the module's name |
| FR-2.9 | ⬜ | Nothing guarantees a probe per `must` |
| FR-2.10 | ⬜ | Requirements are not editable |
| FR-2.11 | ⬜ | No live coverage, no post-session report |
| FR-2.12 | ✅ | **Landed 2026-08-25.** Normalised (company, role, text) hash, looked up globally — the parse is shared, the gap is per-student. A hit answers 200 rather than 201 |
| FR-2.13 | ⬜ | No M15 enrichment |
| FR-2.14 | ⬜ | **P0.** Role-only mode does not exist |
| FR-2.15 | ⬜ | Eligibility mismatch cannot be surfaced; it is not extracted |
| FR-2.16 | ? | p95 never measured |

### 1.3 Three findings worth acting on before the FR list

- ⬜ **Eligibility is thrown away, not extracted.** `_ELIGIBILITY` in
      `extract.py` FILTERS OUT "7.0 CGPA", "2+ years", "B.Tech" — the exact
      opposite of FR-2.4, and it makes FR-2.15 impossible. Its own comment says
      these "belong in a structured eligibility field", so the intent is
      recorded and the field is not built.
- ✅ **Spans (2026-08-25).** Every requirement carries an offset into
      `raw_text`, asserted at `-m gate` to resolve verbatim — a span that points
      at the wrong words is worse than no span, because it is a citation.
- ⬜ **A requirements line longer than five words is read as prose.**
      `- Experience with Docker and Kubernetes` yields nothing: `_list_lines`
      only trusts a line under an enumerating heading if it has a delimiter or
      is at most five words, and that one is six with no comma. Inherited from
      M01's extractor, where a resume bullet genuinely is prose — a JD
      requirement written as a sentence is not. Real, and costs whole
      requirements.
- ⬜ **`extract.py` is a copy of M01's.** Same functions, same
      `_COMMON_ENGLISH` guard, same `_split_conjunctions`. It is untracked, so
      it was copied in recently — and M01's hyphen-wrap fix of 2026-08-25 is
      NOT in it. This is the drift `Platform_Core` exists to prevent; the
      shared half belongs there or in one module that owns it.

### 1.3b Landed 2026-08-25

- ✅ **Identity.** `/coverage/{candidate_id}` took the id from the caller and
      trusted it — any student's gap analysis to anyone who guessed a UUID.
      Router-level `enforce_access` on `ai_core.identity`; the JD routes stay
      open on purpose, because a posting is the company's and FR-2.12 shares
      one parse across students.
- ✅ **Contract gate.** Every route has a client, every hook has a screen,
      every raw `fetch` sends identity. M02 was already in the good state; this
      is what keeps it there while the module grows.
- ✅ **FR-2.12**, and **FR-2.2's span half** — see the table above.

### 1.4 Honest summary

M02 today is **M01's skill extractor pointed at a job description, plus a good
gap calculation**. The parsing half is real. The half the module is named after
— allocating a question budget across weighted requirements under a time
constraint — has not been started.

---

## 2. Next

_To fill in._ The spec's §4 functional requirements and §13 acceptance
gates are the natural first pass — copy them in as a checklist, then mark what
already exists.

---

## 3. Deferred — inter-module

Not gaps in M02. Each needs a module that is not built or not wired yet, and
each is listed so it is not mistaken for an oversight.

_To fill in._
