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
| Backend tests passing | **37** |
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
| FR-2.1 | 🟡 | **PDF/DOCX/TXT landed 2026-08-27.** `POST /v1/jds/upload` sniffs by magic bytes (a renamed `.docx` is still read as one), converts to text, and calls `parse_jd` — no parsing logic of its own, so a pasted and an uploaded JD are byte-identical and the second comes back 200 from the cache. DOCX tables flatten to `key: value`, which is how campus postings write the eligibility block. No OCR: a scan is refused with a sentence rather than parsed into an empty JD, which would render as a clean screen saying the job asks for nothing. Still missing: the company picker and the drives feed (doors 1 and 3) |
| FR-2.2 | ✅ | **Complete 2026-08-27.** Spans, `necessity`, `weight`, `mentions`, and now `kind`, `measured_by` and `seniority_signal`. §3.2.1 trap 3 is closed in all three tiers: "communication" → `[communication]`, "team player" → `[behavioural]`, "go-getter attitude" → `[]` and said out loud. Derived from a lexicon rather than §6.2's LLM call — deterministic, auditable, and the fallback that call needs behind it anyway. Everything defaults to the CHEAPEST round, because overpricing under-fills a session and underpricing breaks a promise |
| FR-2.3 | 🟡 | **Landed 2026-08-27.** "Docker or Kubernetes" is one `RequirementGroup` with `satisfaction: any_of` over two requirements, not three requirements. The alternatives share one requirement's weight. A slash splits only when the ontology recognises ≥2 of its parts — `Java/Python/C++` does, `CI/CD` does not — so with M04 down nothing splits and slashed requirements stay whole rather than being invented into three. `n_of` is not emitted because no posting seen writes "at least two of" |
| FR-2.4 | 🟡 | **Landed 2026-08-25.** CGPA, backlogs, batch and bond extracted with spans, stored beside the requirements rather than among them. `allowed_branches`, `location` and the package figures are still absent — omitted, not guessed |
| FR-2.6 | ⬜ | No role archetype inference |
| FR-2.8 | 🟡 | **Landed 2026-08-27, round pricing same day.** §6.5's solver: priority `weight × (1 − mastery)`, a guaranteed question per measurable must-have (FR-2.9), the rest by marginal value per minute under `log(1 + q)`, capped at 4. Questions are now priced by `measured_by` — 3.5 min verbal, 12 coding, 20 design — and a requirement measured several ways is priced at the dearest. §10's differentiation test passes. Missing: `rounds` as a structured list, and the ILP fallback §6.5 names for infeasible must-have sets (`uncovered` + `suggestion` carry that case today) |
| FR-2.9 | ✅ | **Landed 2026-08-27** with FR-2.8. The must-have floor is seeded before any second question is allocated, in severity order, so when the budget runs out it is the least severe must that goes `uncovered` rather than whichever the posting wrote last |
| FR-2.10 | ⬜ | Requirements are not editable |
| FR-2.11 | ⬜ | No live coverage, no post-session report |
| FR-2.12 | ✅ | **Landed 2026-08-25.** Normalised (company, role, text) hash, looked up globally — the parse is shared, the gap is per-student. A hit answers 200 rather than 201 |
| FR-2.13 | ⬜ | No M15 enrichment |
| FR-2.14 | ⬜ | **P0.** Role-only mode does not exist |
| FR-2.15 | ✅ | **Landed 2026-08-27.** M02 reads M01. `GET /v1/jds/{id}/match/{candidate}` says *"you have 7.2, cutoff is 7.5"* — and refuses to say it whenever the scales differ: a percentage or a 4-point GPA against a 10-point cutoff is `scale_mismatch`, not a conversion, because the factor differs per university and being wrong tells a student the opposite of the truth about a drive they can or cannot sit. No grade at all is `unknown`, never `fails`. Identity is forwarded to M01 rather than a service token, so M02 can only read resumes its own caller was already allowed to see |
| FR-2.16 | ? | p95 never measured |

### 1.3 Three findings worth acting on before the FR list

- ✅ **Eligibility (2026-08-25).** The field its own comment promised now
      exists. Keeping these OUT of the requirement list was always right; the
      bug was keeping them nowhere.
- ⬜ **The comparison, FR-2.15.** "You have 7.2, cutoff is 7.5" needs the
      student's CGPA. M01 already extracts it (`entities.education.grade`) and
      M02 does not read M01. Asserting a student falls short on a number this
      module does not hold would be the worst thing here to be wrong about, so
      the banner states the bar and stops.
- ✅ **Spans (2026-08-25).** Every requirement carries an offset into
      `raw_text`, asserted at `-m gate` to resolve verbatim — a span that points
      at the wrong words is worse than no span, because it is a citation.
- ✅ **A requirements line longer than five words is read as prose
      (fixed 2026-08-27).** `- Experience with Docker and Kubernetes` yielded
      nothing: `_list_lines` only trusted a line under an enumerating heading if
      it had a delimiter or was at most five words, and that one is six with no
      comma. Inherited from M01's extractor, where a resume bullet genuinely is
      prose — a JD requirement written as a sentence is not. A bullet glyph is
      now an enumeration signal whatever the line's length; the word cap moved
      from the LINE to the LABEL, where `_acceptable` was already applying it,
      so a genuinely prose bullet still yields nothing.
- ⬜ **The heading vocabulary is a fixed list of 30 phrases, and a JD that
      words its heading differently extracts NOTHING.** `_list_lines` only
      enters list mode under a `_HEADINGS` match, so `Responsibilities:`,
      `What you will do:` and `Your day to day:` — all common, and all places
      a posting names its stack — produce zero requirements from the bullets
      beneath them. Found 2026-08-27 while writing necessity tests: two test
      JDs that looked entirely ordinary parsed to an empty list.
      Not fixed here, because it is not a vocabulary problem. Adding
      `responsibilities` pulls in `- Design scalable systems`, which survives
      `_acceptable` at five words and becomes a fabricated requirement. The
      real fix is a label-level test of *does this name a thing rather than an
      action*, which is the same judgement `_COMMON_ENGLISH` is a crude
      stand-in for. Own change, own tests.
- ⬜ **`extract.py` is a copy of M01's.** Same functions, same
      `_COMMON_ENGLISH` guard, same `_split_conjunctions`. It is untracked, so
      it was copied in recently — and M01's hyphen-wrap fix of 2026-08-25 is
      NOT in it. This is the drift `Platform_Core` exists to prevent; the
      shared half belongs there or in one module that owns it.

### 1.3c Landed 2026-08-27

- ✅ **The phantom compound.** `- Experience with Docker or Kubernetes`
      produced THREE requirements: both alternatives plus a "Docker or
      Kubernetes" compound that no ontology resolves, so it sat in the unmapped
      queue permanently — and once weights existed it was drawing a full
      requirement's worth. The disjunction is recorded before `drop_redundant`
      deletes the compound, which is the only window in which it still exists.
- ✅ **`drop_redundant` was comparing aliases with a raw substring test.**
      `normalise_alias` strips punctuation, so "C++" becomes the single letter
      `c`, and `"c" in "ci cd pipelines"` is True — resolving C++ deleted
      every unresolved requirement containing the letter. "SQL" likewise
      deleted "NoSQL". Nothing had caught it because the offline table holds
      five multi-word concepts and nothing short had ever resolved; splitting
      `Java/Python/C++` put a one-letter alias into `resolved` for the first
      time. Whole-word containment now. **The same line was in M01** — same
      function, copied — where it was live against M04 and silently removing
      skills from students' own resumes. Fixed in both, tested in both.
- ✅ **The choice reaches the score.** Groups existed in the parse but
      coverage still counted each alternative as its own demand, so a student
      strong in Python was marked weak on Java and had their coverage score
      lowered for an alternative the posting never required them to take —
      §3.2.1's "33% qualified", arriving at the one number the student reads.
      The best-placed alternative now represents the group; the others are
      `met_by_alternative`, which is neither a gap nor silence, and the screen
      says "not needed — the posting accepted Python" rather than dropping the
      row. Two weak answers are still a gap, reported once.
- ✅ **`- Strong programming skills in Java or Python` extracted nothing.**
      Found by parsing an ordinary campus posting and reading the output: the
      most important line on it was simply absent. `_clean` leaves six words,
      `_acceptable` refuses that for the word cap, and extraction bailed on the
      fragment before trying its conjunction parts — so both alternatives went
      with it. The same shape as the bullet-length bug, one level further in.
      Parts are now tried on over-long fragments, but only those that look like
      a NAME: the first attempt at this invented a skill called "enjoys
      mentoring juniors", and recovering a real requirement is not worth
      inventing one.
- ✅ **"Familiarity with Git" was a nice-to-have.** `_COULD` matched
      "familiarity with", "exposure to" and "awareness of", which describe
      DEPTH rather than optionality. A requirement stated under a Requirements
      heading landed in the could band and earned a third of the interview time
      the posting asked for. The heading decides now; under "Nice to have:" the
      same words are still a `could`.
- ✅ **A field-level contract gate.** The route↔client and hook↔screen
      gates do not notice the drift that happens most: the backend grows a
      field and no frontend type mentions it, so nothing renders it and every
      test is green. `requirement_groups` would have been invisible exactly
      that way — the parser folding the choice and the screen drawing two
      demands anyway. Every `JobDescription` and `Requirement` field must now
      be declared in `types.ts`.

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
