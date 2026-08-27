# M02 — TODO · JD Parser & Coverage Planner

Task list for taking **M02 JD Parser & Coverage Planner** to 100% of
[M02_JD_Parser.md](M02_JD_Parser.md).

> **This is a copy.** The one that moves lives in the module's own repo at
> `jd-parser-coverage/plan_in_depth/M02_JD_Parser_TODO.md`, next to the code it
> describes. Sync it here when something lands, so this directory holds one view
> of all nineteen modules.

> **Read this first when starting a session on M02.** It is the running state of
> the module: what is done, what is next, and what is deliberately deferred.
> Update it as things land — a stale list is worse than no list, because the
> next session trusts it.

- **Phase:** 1 · **Owner:** E3 · **Repo:** `jd-parser-coverage`
- **Ports:** API `8102`, web `5202`
- **Run the suite:** `Backend/.venv/Scripts/python -m pytest`
- **Run the gates only:** `Backend/.venv/Scripts/python -m pytest -m gate`
- **Lint:** `Backend/.venv/Scripts/python -m ruff check Backend/`
- **Frontend:** `cd Frontend/frontend_M02_JD_Parser && npx tsc --noEmit && npx vite build`

Legend: ✅ done · 🟡 partly done · ⬜ not started

---

## 0. Ideas and scouting

Things worth building that did not come from the spec — usually from reading
somebody else's implementation. **New ideas go at the top of this section.**

The rule we keep arriving at: borrow a **technique**, not a **component**. The
platform's contracts — character offsets, per-fact provenance, permanent
evidence — are more demanding than general-purpose tools assume, so integration
usually costs more than reimplementing the one idea we actually wanted.

### ⬜ The placement-cell calendar is a one-day integration and the largest win

§2.3 says it outright: *"The campus-drive chips are the highest-value element on
this screen. The placement cell already publishes the calendar; pre-loading it
means most students never type anything. This is a one-day integration that
removes the largest friction point in the product."*

Nothing about it is built. It is not an FR of its own, which is why it keeps
falling off the list — it lives inside FR-2.1's "company+role selection" and
reads like a UI detail. It is not a UI detail: it is the difference between a
student pasting a badly formatted email and a student clicking a chip.

### ⬜ A JD diff between two drives at the same company

TCS NQT and TCS Digital are two drives and one company (§3.2.5). A student
preparing for both currently parses two postings and gets two unrelated screens.
The requirement sets overlap heavily and the interesting part is the delta.
Cheap once `content_sha256` and `requirements` exist, which they do.

---

## 1. Where the module stands

| | |
|---|---|
| Status | **Phase 1 substantially built.** 135 backend tests, ruff and tsc clean, frontend builds. |
| Suite | `135 passed` · gates green |
| Identity | Router-level `enforce_access` on `ai_core.identity`. JD routes deliberately open; `candidate_id` routes gated. |
| Upstreams | M04 (ontology, mastery) and M01 (resume) — both optional, both declared in `module.json` with an `on_missing` a student can act on. |

### What exists end to end

A student pastes or uploads a posting; it is normalised, hashed and cached
across students; requirements come out with source spans, necessity, weight,
kind, `measured_by` and disjunctive groups; eligibility is read whole; the gap
is computed against M04's Skill Graph; a coverage plan allocates question budget
under a time constraint; and — as of 2026-08-27 — the whole thing can be held up
against the student's own resume from M01.

### What is conspicuously absent

**Doors 1 and 3 of Screen 1.** No company picker, no drive chips, no role
archetype. Door 3 is marked *mandatory* in the spec and is FR-2.14, a P0. A
student in September with no drive scheduled cannot use this module at all.

**Everything downstream of the plan.** FR-2.11's live coverage ledger needs M05
and M13. The plan is produced and nothing consumes it yet.

---

## 2. Functional requirements

Spec §4. This is the authoritative list; §3 below is only the inter-module half.

| FR | | |
|---|---|---|
| FR-2.1 | 🟡 | **PDF/DOCX/TXT landed 2026-08-27.** `POST /v1/jds/upload` sniffs by magic bytes (a renamed `.docx` is still read as one), converts to text, and calls `parse_jd` — no parsing logic of its own, so pasted and uploaded produce the same row and the second answers 200 from the cache. DOCX tables flatten to `key: value`, which is how campus postings write the eligibility block. No OCR: a scan is refused with a sentence rather than parsed into an empty JD, which would render as a clean screen saying the job asks for nothing. **Still missing: the company picker and the drives feed (doors 1 and 3).** |
| FR-2.2 | ✅ | **Complete 2026-08-27.** `SourceSpan`, `necessity`, `weight`, `mentions`, `kind`, `measured_by`, `seniority_signal`. §3.2.1 trap 3 closed in all three tiers: "communication" → `[communication]`, "team player" → `[behavioural]`, "go-getter attitude" → `[]` and said out loud. Lexicon-derived rather than §6.2's LLM call — deterministic, auditable, and the fallback that call needs behind it anyway. Everything defaults to the CHEAPEST round: overpricing under-fills a session, underpricing breaks a promise. |
| FR-2.3 | 🟡 | **Landed 2026-08-27.** "Docker or Kubernetes" is one `RequirementGroup` with `satisfaction: any_of` over two requirements, not three. Alternatives share one requirement's weight, and an answered choice is excluded from the gap, the plan and the resume match. A slash splits only when the ontology recognises ≥2 parts — `Java/Python/C++` does, `CI/CD` does not — so with M04 down nothing splits rather than being invented into three. **Missing: `n_of`**, deliberately — no posting seen writes "at least two of". |
| FR-2.4 | ✅ | **Complete 2026-08-27.** CGPA, active AND history backlogs, batch, bond, `allowed_branches`, `location`, both package figures. `package_lpa_fixed` is separate because a 6.5 LPA headline with 2 LPA variable is a 4.5 LPA salary and students compare the wrong one. The slash IS split for branches and nowhere else. |
| FR-2.5 | 🟡 | **Reframed 2026-08-27.** `grounded` (a concept id exists → M04 can drive adaptive questioning) is now separate from `testable` (a question can be put in front of the student at all). One boolean was answering both and reported *72 of 73 untestable* on a posting where 72 are perfectly askable. **This is not an M04 outage**: M04's ontology is 120 interview concepts — 55 DSA, 50 CS-core, 15 communication — and exactly two are technology-shaped. A modern stack grounds almost nowhere BY DESIGN. The plan now allocates to testable-but-ungrounded requirements, marked `grounded: false` so M05 knows to generate rather than draw from the graph |
| FR-2.6 | ✅ | **Landed 2026-08-27.** A 24-archetype library, matched on title phrases with §6.3's margin check against top-2. Under five requirements, the posting is topped up to eight, each marked `source="archetype"` with `span=None` — the pair that makes the addition auditable. §6.4's `source_w = 0.75` finally has something to apply to. A suggested label that TURNS OUT to be in the document is `jd`, not `archetype`: the archetype found it, the company still said it. Matched deterministically rather than by embedding, and a weak or ambiguous title matches NOTHING |
| FR-2.7 | 🟡 | Per-requirement gap with `not_measured` as a distinct state, `unmeasurable` as another, and `met_by_alternative` as a third. **Missing: the confidence discount** — §6.5 wants `confidence < 0.25 → not_measured`, and M04 publishes no standard error yet. |
| FR-2.8 | 🟡 | **Landed 2026-08-27.** §6.5's solver: priority `weight × (1 − mastery)`, a guaranteed question per measurable must-have, the rest by marginal value per minute under `log(1 + q)`, capped at 4. Questions are priced by `measured_by` — 3.5 min verbal, 12 coding, 20 design — and a requirement measured several ways is priced at the dearest. **Missing: `rounds` as a structured list**, and the ILP fallback §6.5 names for infeasible must-have sets (`uncovered` + `suggestion` carry that case today). |
| FR-2.9 | ✅ | **Landed 2026-08-27.** The must-have floor is seeded before any second question is allocated, in severity order, so a budget that runs out drops the *least* severe must rather than whichever the posting wrote last. Gate: `test_every_measurable_must_have_gets_at_least_one_question`. |
| FR-2.10 | ✅ | **Landed 2026-08-27.** Three corrections a student can make — remove, add, change necessity — stored as their OWN rows keyed by `(candidate_id, jd_id)`. The shared parse is never written to: FR-2.12 caches one parse across sixty students, so a `PATCH` on `jd.requirements` would let any student silently rewrite what fifty-nine others see. Edits re-run `locate`, so weights renormalise rather than being patched, and an added label carries `source="user"` — §5's enum has held that value since the spec was written and nothing had ever produced it |
| FR-2.11 | ⬜ | No live coverage ledger, no post-session report. **Blocked** — needs M05 to write `asked` rows and M13 to move them to `scored`. |
| FR-2.12 | ✅ | **Landed 2026-08-25.** Normalised (company, role, text) hash, looked up globally — the parse is shared, the gap is per-student. A hit answers 200 rather than 201. |
| FR-2.13 | ⬜ | No M15 company-brief enrichment. **Blocked** — M15 not wired. |
| FR-2.14 | ✅ | **Landed 2026-08-27.** `GET /v1/archetypes` and `POST /v1/jds/from-role`. §2.3's door 3 is real: a student with no drive scheduled picks a role and gets a requirement set and a coverage plan. `raw_text` is EMPTY rather than a synthesised posting — storing a plausible JD would make the read-back quote sentences no company ever published. Cached like a pasted JD, because two students picking "SDE" share one set |
| FR-2.15 | ✅ | **Landed 2026-08-27.** M02 reads M01. `GET /v1/jds/{id}/match/{candidate}` says *"you have 7.2, cutoff is 7.5"* — and refuses to say it whenever the scales differ: a percentage or a 4-point GPA against a 10-point cutoff is `scale_mismatch`, not a conversion. No grade at all is `unknown`, never `fails`. Identity is forwarded to M01 rather than held as a service token, so M02 can only read resumes its own caller was already allowed to see. |
| FR-2.16 | ⬜ | **p95 never measured.** §11 budgets ≤ 8 s cold and ≤ 1 s cached. Nothing is timed, so the number is unknown rather than met or missed. |

---

## 3. Acceptance gates

Spec §13. A gate is release-blocking; the rest are tracked.

| AC | | |
|---|---|---|
| AC-2.1 **[GATE]** | ✅ | Every measurable must-have gets ≥1 probe. Enforced in `build_plan` as a floor seeded before any second question, and asserted. |
| AC-2.2 **[GATE]** | 🟡 | `not_measured` never renders as a number — `MasteryBar` has no bar for it and `coverage_score` is `null`, never `0.0`, when nothing was measured. **The UI test the gate names does not exist**; this is asserted on the backend only. |
| AC-2.3 | 🟡 | **0.857 on 2026-08-27** (precision 0.891, recall 0.826), past §13's 0.85 — but the target is a claim about REAL postings and 11 of the 12 documents are synthetic, so `MEASURES_REAL_WORLD` stays False. What is true: the parser scores 0.857 on the shapes the spec names. The floor went 0.55 → 0.72 → 0.82 in one day as the corpus named bugs and the fixes landed. 7 of 12 documents score 1.000, including the real one. §10 asks for 25 documents; there are 12 |
| AC-2.4 | 🟡 | **Measured 2026-08-27: 0.90** over §10's 30 strings. Half are NEGATIVE cases — "CI/CD", "TCP/IP", "A/B testing", "24/7 support" — because splitting one fabricates a skill |
| AC-2.5 | ⬜ | p95 cold parse ≤ 8 s. Never measured — see FR-2.16. |
| AC-2.6 | ✅ | Plans differ ≥ 30% between students on one JD. `test_two_students_on_one_posting_get_different_plans` asserts it directionally: the student weak on SQL is asked about SQL more, and the reverse for DP. |
| AC-2.7 | ⬜ | Drive-chip vs manual-paste ratio. Nothing to track — no chips. |
| AC-2.8 | ⬜ | "The interview matched the JD" ≥ 80%. Needs a post-session survey and a session to survey. |

---

## 4. Edge cases

Spec §12. Listed in full because several are one afternoon each and are the
difference between a demo and a product.

| EC | | |
|---|---|---|
| EC-2.1 | ✅ | 40-word JD → topped up to 8, each marked. Verified on the spec's own example: "Looking for SDE trainees. Good knowledge of DSA and OOPs." went from one requirement to eight, with the one the posting stated weighing 0.180 against 0.117 for the inferred. |
| EC-2.2 | ✅ | **Landed 2026-08-27.** The top 8 by weight per band, everything else one click away and counted in the band header. Capped per BAND rather than overall, because the bands are already an ordering that means something. Found by reading the real brochure's output as a student: 73 rows in one flat stack, weights between 0.006 and 0.028, no shape — and a list nobody reads may as well hold three |
| EC-2.3 | ✅ | "Java/Python/C++" → `RequirementGroup(any_of)`, satisfied if any one is strong. |
| EC-2.4 | ✅ | **Landed 2026-08-27.** §6.1's stripper, written against a real brochure (`Testing/JD_Testing/`, Cognizant 2027 Ace Team, 12,446 chars). A rule list for what campus emails have in common, PLUS a structural rule that needs no list — a line appearing 3× in one document is furniture. The structural half is what survives the 51st email. `too_thin` fires on the RATIO, not the length: a 40-word posting is the median (§3.2.1 trap 1), an email that lost 65% of itself to the stripper was mostly not a job description |
| EC-2.5 | 🟡 | Non-technical archetypes exist (HR, Sales, Support, Consultant) and their requirement sets are behavioural and aptitude-led, so `measured_by` prices them as verbal rounds. **Missing: an explicit rule that DROPS technical rounds** rather than just not allocating to them. |
| EC-2.6 | ⬜ | JD in Hindi/Tamil → detect, translate for parsing, keep the original for display. Nothing detects language — but the model pass landed 2026-08-27 and a multilingual model reads Hindi without being told to, so this is now mostly a question of what the SPANS point at |
| EC-2.7 | ✅ | Unknown company → `POST /v1/jds/from-role` with the default `company_name`. Nothing about the company is fabricated, and `raw_text` stays empty. |
| EC-2.8 | ✅ | Requirement maps to no concept → `measurable=false`, and the UI says "can't be tested here" with a hatched mark rather than a zero score. |
| EC-2.9 | ⬜ | All requirements already strong → Final Boss difficulty and stretch items. The plan currently allocates normally and says nothing. |
| EC-2.10 | 🟡 | Zero session history → all gaps `not_measured` and the plan is a broad diagnostic. The state is right; **the copy explaining why is not written**. |
| EC-2.11 | ✅ | Time budget too small → `uncovered` populated AND an explicit suggestion. Also the reverse: a session longer than the posting needs reports `saturated` and says so, because a saturated plan is identical for every student and looks exactly like the template §3.2.1 warns about. |
| EC-2.12 | ✅ | Same JD twice → hash hit, 200, instant. |
| EC-2.13 | ✅ | **Landed 2026-08-27, deliberately BEFORE §6.2's model call.** M01's `safety.py` ported: homoglyph folding, five injection patterns, masked in place with `█` so every span offset survives. `injections_removed` is SHOWN, which is the opposite of M01's rule and right for the opposite reason — a resume's author is the person the filter is aimed at, a posting's author is not the person reading the screen. `persona_switch` is tighter than M01's: "Ability to act as a technical lead" is real posting prose and M01's pattern flagged it |
| EC-2.14 | ⬜ | Two roles in one JD ("SDE or QA") → detect and ask. Not detected. |

---

## 5. Data model

Spec §5 declares seven types.

| Type | | |
|---|---|---|
| `Requirement` | ✅ | Every field. |
| `RequirementGroup` | 🟡 | `any_of` only; `all_of` is the default and carries no information, `n_of` is unwritten by real postings. |
| `EligibilityCriteria` | ✅ | Every field. |
| `RequirementSet` | 🟡 | Exists as a return type from `locate`, not as a persisted row with an id. FR-2.10's editing needs the persisted version. |
| `Gap` | 🟡 | Computed and returned; `evidence_session_ids` and `closable_hours_estimate` are absent — both need M04 to publish more than a mastery scalar. |
| `CoverageAllocation` | ✅ | Including `rationale` as a sentence, which §5 marks "shown in the UI". |
| `CoveragePlan` | 🟡 | No `id`, no `requirement_set_id`, no `rounds`. The first two need a persisted plan; `rounds` needs a round-packing pass over the allocations, which is now possible since `measured_by` landed. |

---

## 6. Screens

Spec §2.3.

| Screen | | |
|---|---|---|
| 1 — Input, three doors | 🟡 | Doors 2 and 3 work: paste, upload, or pick from 24 roles with the requirement set shown before you commit. **Door 1 (company picker) absent**, and the drive chips — "the highest-value element on this screen" — do not exist. |
| 2 — Requirement read-back | ✅ | Grouped by necessity with each band's share of the total ask, weights, disjunctions rendered as one row, eligibility banner, per-requirement provenance, and the coverage plan beneath it. |
| 3 — The gap | 🟡 | `CoveragePanel` shows every requirement's state and never renders `not_measured` as a number. **The spec's "your biggest gap: DBMS — specifically normalisation and indexing, you broke on both in your last session" needs M04 evidence links**, which do not exist. |
| Match — resume vs posting | ✅ | Not in the spec, added 2026-08-27. Confirmation page then analysis: eligibility verdicts first and alone (§3.2.2 — a hard filter, not a topic), then risks ranked with `blocking` reserved for eligibility, then what the resume evidences. |

---

## 7. Deferred — inter-module

Not gaps in M02. Each needs a module that is not built or not wired yet, and
each is listed so it is not mistaken for an oversight.

- **FR-2.11 live coverage ledger** — M05 writes `asked`, M13 moves it to
  `scored`. §6.6 calls this *"the mechanism that makes coverage a guarantee
  rather than an intention"*, and it is the one part of the module's promise
  that cannot be kept alone.
- **FR-2.13 company brief** — M15. §6.7.
- **`Gap.evidence_session_ids` and `closable_hours_estimate`** — M04 publishes a
  mastery scalar and no provenance behind it, so "you broke on both in your last
  session" cannot be said.
- **FR-2.7's confidence discount** — M04 publishes no standard error, so
  §6.5's `confidence < 0.25 → not_measured` is approximated by "M04 returned
  `None`", which is a coarser signal.
- **M12/M17 for `measured_by: communication`** — the classification is made and
  nothing consumes it yet.

---

## 7b. The grounding gap — the module's real ceiling

Established 2026-08-27 by reading M04's `concepts.yaml` rather than assuming.

**M04 holds 120 concepts: 55 dsa, 50 cs_core, 15 communication.** Two are
technology-shaped (`SQL Queries`, `NoSQL and When to Use It`). That is not a
small ontology waiting to be grown into a large one — it is a deliberate
catalogue of what an INTERVIEW TESTS. M02's own `extract.py` docstring has said
so since it was written: *"the ontology holds interview concepts — binary
search, normalisation, asking clarifying questions — not technologies."*

So a JD's technology list will never ground, however long M04 runs, and three
responses are available. They are not equally good:

- ⬜ **Build a technology catalogue in M02.** 500–2,000 concepts with aliases,
      parents, prerequisites. Directly attacks the gap — and it would be a
      SECOND ontology, owned by the wrong module, diverging from M04's the way
      `extract.py` and `safety.py` already diverge. This platform has measured
      that cost twice in one day. **Not M02's to build.**
- ⬜ **Map technology → competency.** "Kubernetes" is evidence of container
      orchestration, distributed systems and networking — all of which are
      already in M04's `cs_core`. This grounds a modern stack against the
      ontology that exists, ages far better than a framework list, and is
      testable in a way rote API knowledge is not. **The strongest option, and
      it belongs to M04** as ontology edges, with M02 supplying the candidate
      pairs it observes.
- ✅ **Generate questions for the ungrounded (2026-08-27).** Done, to the
      boundary of what M02 owns: a requirement the posting STATES, with a
      `measured_by` round that could carry it, is `testable` and gets plan
      budget with `grounded: false`. M05 generates from the requirement and the
      line it was written on. Weaker than the graph — no mastery prior, no
      adaptive ladder — and a real question about a real requirement.

On the Cognizant brochure this moved the plan from **1 allocation / 14 minutes**
to **16 allocations / 59.5 of 60 minutes, 0 untestable**.

What M02 must NOT do, and the reason is ownership rather than difficulty: hold
an ontology (M04), generate questions (M05), or build scoring rubrics (M13).
What it CAN add next is the candidate-mining half — harvest requirement labels
across parsed JDs, cluster them, and propose them to M04 with the postings that
evidence each one. That is M02 feeding the ontology rather than forking it.

---

## 8. Known debt

- **The `ai_core` promotion, now measured rather than asserted.** `extract.py`
  is no longer "a copy of M01's" — M01's is 419 lines and M02's is 1,563.
  Compared function by function, ignoring docstrings:

      IDENTICAL (6)   `_clean`, `_split_conjunctions`, `drop_redundant`,
                      `_contains_phrase`, `prose_safe_alias`, `scan_prose`
      DIVERGED  (3)   `_acceptable`, `_list_lines`, `extract_surface_forms`
      M02 ONLY  (22)  the §5 types, weighting, disjunction folding, …

  The divergence is deliberate: M02 treats a bullet as an enumeration signal
  whatever the line's length and M01 does not, because a long undelimited line
  under a resume's SKILLS heading usually IS prose. Forcing them to share
  `_list_lines` would make one of them wrong.

  So the promotion is **those six functions, about a hundred lines** — pure text
  handling with no module-specific judgement — and not the file. `safety.py` is
  the same shape of case: near-identical, with one deliberate difference
  (`persona_switch` is tighter here, because a JD says "act as" in earnest).

  The cost of waiting is measured: `drop_redundant`'s substring bug and
  `_split_conjunctions`' length cap were both fixed twice, in two repositories,
  on 2026-08-27. **Not attempted in that session** — a core release retags a
  dependency pinned across six modules and has a four-site version-parity test
  behind it, which deserves its own session rather than the tail of another.
- **The offline concept table holds five entries.** With M04 down the module is
  honest and nearly useless. Not wrong, but the degraded path is much thinner
  than "degraded" suggests.
- **The heading vocabulary is 30 fixed phrases.** A posting that writes
  `Responsibilities:` or `What you will do:` extracts *nothing* from the bullets
  beneath it. Not a vocabulary problem: adding `responsibilities` pulls in
  "- Design scalable systems" as a fabricated requirement. The real fix is a
  label-level test of *does this name a thing rather than an action*.
- **No golden corpus.** AC-2.3 and AC-2.4 cannot be measured, so every
  extraction change is verified by reading output on one or two examples.
  Today alone that method found four real bugs — which is the argument both for
  and against it.

---

## 9. Findings log

Kept because the reasoning is the useful part: each of these was found by
running the module rather than by reading it, and the ones still open are open
for a stated reason.

### Findings, and what happened to them

- ✅ **Eligibility (2026-08-25).** The field its own comment promised now
      exists. Keeping these OUT of the requirement list was always right; the
      bug was keeping them nowhere.
- ✅ **The comparison, FR-2.15 (2026-08-27).** "You have 7.2, cutoff is 7.5" needed the
      student's CGPA. M01 already extracts it (`entities.education.grade`) and
      M02 did not read M01. M02 reads it now, and refuses the comparison
      wherever the scales differ — a percentage or a 4-point GPA against a
      10-point cutoff is `scale_mismatch`, not a conversion, because asserting
      that a student falls short is the worst thing here to be wrong about.
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
      `_COMMON_ENGLISH` guard, same `_split_conjunctions`. On 2026-08-27 two
      bugs had to be fixed twice, in two repos, on the same day: the
      `drop_redundant` substring test and the conjunction-part length cap.
      That is the cost, it is now measured rather than predicted, and it will
      recur. The shared half belongs in `ai_core.concepts`, whose own docstring
      already names both callers.

### Landed 2026-08-27

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

### Landed 2026-08-25

- ✅ **Identity.** `/coverage/{candidate_id}` took the id from the caller and
      trusted it — any student's gap analysis to anyone who guessed a UUID.
      Router-level `enforce_access` on `ai_core.identity`; the JD routes stay
      open on purpose, because a posting is the company's and FR-2.12 shares
      one parse across students.
- ✅ **Contract gate.** Every route has a client, every hook has a screen,
      every raw `fetch` sends identity. M02 was already in the good state; this
      is what keeps it there while the module grows.
- ✅ **FR-2.12**, and **FR-2.2's span half** — see the table above.
