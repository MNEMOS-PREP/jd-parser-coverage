# M02 — TODO · JD Parser & Coverage Planner


> **Completion: 91%** — 13 of 16 functional requirements met, 3 partially. From this module's own audited FR table. Functional requirements are not the whole spec: the acceptance gates, edge cases and screens are tracked separately below, and the remaining work is not spread evenly across them.
>
> _Method: `(met + ½ × partial) ÷ total`, from the FR table below, 2026-08-28. One measure applied the same way to all nineteen modules so they compare; it counts requirements, not screens or gates._

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

### 2026-10-03 — one session for the page (Platform_Core v0.12.0)

- ✅ **`components/candidate.ts` is `@ai/core`'s session in this module's words.** It kept its
  own id under its own localStorage key and set the page's identity headers
  itself, as three other modules did, so in Platform_Shell the student was
  whoever's module loaded last. The shell's sign-in screen sets the session
  now; standalone signs in as the seeded student only when nobody is. The old
  key is migrated, so no browser loses its student.
- ✅ Pinned to v0.12.0 on both halves; the lockfile resolves `9ee259c`.

### 2026-10-02 — asks from M06, found running the full chain live

- ⬜ **The first plan for a posting took 4.7 s.** `POST /v1/jds/{id}/plan/{candidate}`,
  measured from M06 on the first live run of M02 → M06 → M05 → M13 → M04. M06
  waited 3 s — its budget for a call made on a turn — so every session planned
  on the even split and told the student *"the planner is offline"* while M02
  was up. M06 now gives plan-time calls 20 s, but a student is watching that
  spinner: precompute what the plan needs at parse time, or publish the
  expected latency in `/v1/deps` so a caller can budget for it.
- ⬜ **Link "practise for this role" to `/mock?jd={id}`.** M06's setup honours
  `?jd=` since its day 13 and tailors the session to the posting.
- ✅ The coverage ledger's docstring now says M06 is the writer of `asked`,
  `answered` and `skipped`, and M13 of `scored` (2026-10-02).

### 2026-10-02 — the shell, the guard, the pin

- ✅ **Platform_Core v0.9.1 → v0.11.0**, on both halves.
- ✅ **The router guard is Platform_Core's** `candidate_guard`, replacing
  M02's hand-written copy, so copies cannot drift. Since v0.11.0 it also reads
  a student named in the query. A gate runs the shared stranger check.
- ✅ **Every /v1 noun M02 serves is routed to M02 by the shell.**
  - The company picker moved from `/v1/companies` (M15's noun) to
    `/v1/doors/companies…`.
  - The ledger moved from `/v1/sessions/{s}/coverage/{c}…` (M05's noun) to
    `/v1/coverage/{s}/{c}…`. M06 and M13 call the new paths.
  - The shell's table gained `archetypes`, `coverage`, `doors` and
    `performance`. Three of those were served by M02 and routed by nobody.
  - `tests/test_shell_nouns.py` reads the shell's live table, and fails on
    a noun in either direction.

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

**The placement-cell CALENDAR.** All three doors of Screen 1 work as of
2026-08-28 — door 1 is built against M15, which owns companies, aliases and
drive variants. What M15 knows is which drives a company runs, not which are
scheduled this month, and §2.3's claim that pre-loading them means *"most
students never type anything at all"* needs the calendar to be true. `/v1/doors`
now measures whether it is (AC-2.7).

**Everything downstream of the plan.** The ledger exists and is read back —
`build_plan` re-prioritises against it — but M05 and M13 are the writers and
neither is built. So the table is correct and empty, and `/sessions/{id}` says
which module has not arrived rather than looking broken.

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
| FR-2.7 | ✅ | **Complete 2026-08-27.** §6.5's confidence discount, which was recorded here as blocked on *"M04 publishes no standard error"* — **that was wrong**. M04's `MasteryOut` has carried `se`, `se_effective`, `n_direct` and `stale` since it was written; nobody checked the payload. `confidence = 1 - se_effective/SE_PRIOR` (imported from `ai_core.mastery`, not written down), `not_measured` below 0.25, and `severity × confidence`. Reads `se_effective` not `se`, so evidence widened by age is probed again. An upstream that states NO uncertainty gets discount 1.0 rather than 0 — `None` is not zero |
| FR-2.8 | ✅ | **Complete 2026-08-27.** §6.5's solver, round pricing from `measured_by`, and §5's `rounds` — one `PlannedRound` per modality, ordered cheapest first so a session warms up rather than opening on 20 minutes of design. `PlannedRound` is declared at §5:252 and never defined, so its fields are chosen here. The ILP fallback is still not built: for an infeasible must-have set there is nothing to optimise, and `uncovered` + `suggestion` carry that case honestly |
| FR-2.9 | ✅ | **Landed 2026-08-27.** The must-have floor is seeded before any second question is allocated, in severity order, so a budget that runs out drops the *least* severe must rather than whichever the posting wrote last. Gate: `test_every_measurable_must_have_gets_at_least_one_question`. |
| FR-2.10 | ✅ | **Landed 2026-08-27.** Three corrections a student can make — remove, add, change necessity — stored as their OWN rows keyed by `(candidate_id, jd_id)`. The shared parse is never written to: FR-2.12 caches one parse across sixty students, so a `PATCH` on `jd.requirements` would let any student silently rewrite what fifty-nine others see. Edits re-run `locate`, so weights renormalise rather than being patched, and an added label carries `source="user"` — §5's enum has held that value since the spec was written and nothing had ever produced it |
| FR-2.11 | ✅ | **Landed 2026-08-27.** `coverage_ledger` is M02's table even though M05 and M13 do the writing — M02 made the promise, so the endpoints are the contract they will be written against rather than a client of theirs. Append-only against §6.6's wording: a row does not "move to scored", a second row is appended and the FURTHEST-THROUGH state wins, because M05 and M13 are separate services whose clocks are not ordered and a late `answered` must not un-score a scored turn. The planner reads it — `build_plan` seeds its counts so a topic already asked twice sees the diminishing return of a third question, and FR-2.9's floor is not re-paid for a must the session already satisfied. `question_budget` is now what is LEFT to ask: a plan is what remains to be done. `/sessions/{id}` renders it live and as the report, because they are the same question at different times. |
| FR-2.12 | ✅ | **Landed 2026-08-25.** Normalised (company, role, text) hash, looked up globally — the parse is shared, the gap is per-student. A hit answers 200 rather than 201. |
| FR-2.13 | ✅ | **Landed 2026-08-27.** A JD says what a company WANTS; M15 holds what it ASKED. Three enrichments: alias resolution (§3.2 hard part 5 — M15 owns that table and M02 asks rather than keeping a second one), the drive variant, and a cross-check of the posting's package, bond and locations against the reports. The last is the row that changes a decision — the seeded TCS Digital posting advertises 9.0 LPA and the reports say 7.0. Topics come from the CLAIMS, weighted by `corroboration_count`, because M15 has already decided what a report is worth. `evidence_boost` is a bounded ×0.85–1.25 nudge to §6.4's weights, floored at 8 units of corroborated evidence, and said out loud in the rationale. M15 absent removes the panel and nothing else. |
| FR-2.14 | ✅ | **Landed 2026-08-27.** `GET /v1/archetypes` and `POST /v1/jds/from-role`. §2.3's door 3 is real: a student with no drive scheduled picks a role and gets a requirement set and a coverage plan. `raw_text` is EMPTY rather than a synthesised posting — storing a plausible JD would make the read-back quote sentences no company ever published. Cached like a pasted JD, because two students picking "SDE" share one set |
| FR-2.15 | ✅ | **Landed 2026-08-27.** M02 reads M01. `GET /v1/jds/{id}/match/{candidate}` says *"you have 7.2, cutoff is 7.5"* — and refuses to say it whenever the scales differ: a percentage or a 4-point GPA against a 10-point cutoff is `scale_mismatch`, not a conversion. No grade at all is `unknown`, never `fails`. Identity is forwarded to M01 rather than held as a service token, so M02 can only read resumes its own caller was already allowed to see. |
| FR-2.16 | ✅ | **Landed 2026-08-27.** Every parse records `parse_ms` and a per-stage `stage_ms`, and `GET /v1/performance` reports p95 per stage against §11's budget. Measured over STORED ROWS rather than a benchmark script — a benchmark measures the machine it ran on, and §11's budget is a claim about what a student waits for. Empty until something is parsed, which is the honest answer before there is one |

---

## 3. Acceptance gates

Spec §13. A gate is release-blocking; the rest are tracked.

| AC | | |
|---|---|---|
| AC-2.1 **[GATE]** | ✅ | Every measurable must-have gets ≥1 probe. Enforced in `build_plan` as a floor seeded before any second question, and asserted. |
| AC-2.2 **[GATE]** | ✅ | **Gated 2026-08-27.** §13 says "verified in UI tests" and this repo has no frontend runner — a toolchain and a network install for one assertion. Gated the STRONGER version: a screen cannot render a number that was never sent, so `mastery[label]` is `None` for every `not_measured` row and `coverage_score` is `null` not `0.0`. Plus a source gate keeping `unmeasurable` and `met_by_alternative` out of `TO_MASTERY_STATE` |
| AC-2.3 | 🟡 | **0.857 on 2026-08-27** (precision 0.891, recall 0.826), past §13's 0.85 — but the target is a claim about REAL postings and 11 of the 12 documents are synthetic, so `MEASURES_REAL_WORLD` stays False. What is true: the parser scores 0.857 on the shapes the spec names. The floor went 0.55 → 0.72 → 0.82 in one day as the corpus named bugs and the fixes landed. 7 of 12 documents score 1.000, including the real one. §10 asks for 25 documents; there are 12 |
| AC-2.4 | 🟡 | **Measured 2026-08-27: 0.90** over §10's 30 strings. Half are NEGATIVE cases — "CI/CD", "TCP/IP", "A/B testing", "24/7 support" — because splitting one fabricates a skill |
| AC-2.5 | 🟡 | **Measurable 2026-08-27** — `GET /v1/performance`, p95 per stage with the sample count beside it. Whether the 8 s budget is MET is a question about production traffic; on the golden documents every stage is far inside it, and a p95 over a handful of parses is not a p95 |
| AC-2.6 | ✅ | Plans differ ≥ 30% between students on one JD. `test_two_students_on_one_posting_get_different_plans` asserts it directionally: the student weak on SQL is asked about SQL more, and the reverse for DP. |
| AC-2.7 | ✅ | **Measurable 2026-08-28.** `GET /v1/doors`, and there are chips now. Derived from `extracted_by` rather than from a counter of its own — a second record of one event is a second thing to keep correct, and the first time they disagreed nobody could say which was right. Pasting and uploading count as ONE door, because §2.3 counts "bring me the posting" as a single way in. It is the number that says whether door 1 earned its place: if the paste share does not move now the chips exist, the calendar behind it is not worth building either |
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
| EC-2.5 | ✅ | Non-technical archetypes now DROP the coding and design rounds rather than merely not allocating to them. An HR interview does not open a twelve-minute coding round because the JD mentioned SQL in passing. Asserted both ways so the drop cannot widen to engineering roles |
| EC-2.6 | 🟡 | **Detection landed 2026-08-28.** `language.py` counts letters by Unicode block — ten scripts, no wheel to install, exact. A posting is non-Latin at 20% of its LETTERS, not a majority, because a real Hindi posting still writes "Java" and the company name in Latin. Verified live: a Devanagari posting reports `devanagari` at 0.879 and still extracts Java, SQL and eight archetype requirements. **Translation is deliberately NOT done** and this stays 🟡 for it: every requirement carries a span into `raw_text`, and offsets into a translation point at text no company published. The §6.2 model pass already reads Hindi, so the extraction that matters works on the original — which is exactly why the spans must stay on it. The screen names the script and says the English lexicon may have missed some |
| EC-2.7 | ✅ | Unknown company → `POST /v1/jds/from-role` with the default `company_name`. Nothing about the company is fabricated, and `raw_text` stays empty. |
| EC-2.8 | ✅ | Requirement maps to no concept → `measurable=false`, and the UI says "can't be tested here" with a hatched mark rather than a zero score. |
| EC-2.9 | ✅ | All-strong → `difficulty: final_boss` and copy about finding a ceiling rather than a gap. Derived from the mastery behind the allocations, not passed in — the point is that the plan NOTICES |
| EC-2.10 | ✅ | Zero history → `difficulty: diagnostic` and the copy §12 asks for. `diagnostic` beats `final_boss` on a tie deliberately: "you're ready" said to somebody nobody has tested is a guess dressed as praise, and it stops a student preparing |
| EC-2.11 | ✅ | Time budget too small → `uncovered` populated AND an explicit suggestion. Also the reverse: a session longer than the posting needs reports `saturated` and says so, because a saturated plan is identical for every student and looks exactly like the template §3.2.1 warns about. |
| EC-2.12 | ✅ | Same JD twice → hash hit, 200, instant. |
| EC-2.13 | ✅ | **Landed 2026-08-27, deliberately BEFORE §6.2's model call.** M01's `safety.py` ported: homoglyph folding, five injection patterns, masked in place with `█` so every span offset survives. `injections_removed` is SHOWN, which is the opposite of M01's rule and right for the opposite reason — a resume's author is the person the filter is aimed at, a posting's author is not the person reading the screen. `persona_switch` is tighter than M01's: "Ability to act as a technical lead" is real posting prose and M01's pattern flagged it |
| EC-2.14 | ✅ | **Landed 2026-08-27.** `match` already refused an ambiguous title — two archetypes inside `MIN_MARGIN`, returns nothing rather than tossing a coin — and that refusal was SILENT. `role_candidates` names them best-first, so "default to the first" is the caller doing nothing. Empty when unambiguous, and empty is the signal there was nothing to ask |

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
| 1 — Input, three doors | ✅ | **All three land 2026-08-28.** Door 1 is `CompanyDoor`: search a company through M15's alias table, then pick the drive. The chips carry their own figures — TCS Digital reports 7.0 LPA against NQT and Ninja at 3.6 — because a chip reading only "Digital" makes the student click to find out what they are picking. Built against M15 rather than a company table of M02's own: §3.2's fifth hard part is that a second copy of that table is how two modules drift. M15 down leaves the other two doors untouched and names the module. |
| 2 — Requirement read-back | ✅ | Grouped by necessity with each band's share of the total ask, weights, disjunctions rendered as one row, eligibility banner, per-requirement provenance, and the coverage plan beneath it. |
| 3 — The gap | 🟡 | `CoveragePanel` shows every requirement's state and never renders `not_measured` as a number. **The spec's "your biggest gap: DBMS — specifically normalisation and indexing, you broke on both in your last session" needs M04 evidence links**, which do not exist. |
| Match — resume vs posting | ✅ | Not in the spec, added 2026-08-27. Confirmation page then analysis: eligibility verdicts first and alone (§3.2.2 — a hard filter, not a topic), then risks ranked with `blocking` reserved for eligibility, then what the resume evidences. |

---

## 7. Deferred — inter-module

Not gaps in M02. Each needs a module that is not built or not wired yet, and
each is listed so it is not mistaken for an oversight.

- **The ledger's WRITERS** — M05 writes `asked`, M13 moves it to `scored`.
  The table, the endpoints and the re-prioritisation are built (FR-2.11); what
  is missing is anything to put a row in it. §6.6 calls the ledger *"the
  mechanism that makes coverage a guarantee rather than an intention"*, and
  that is the half of the promise M02 cannot keep alone.
- **`Gap.evidence_session_ids` and `closable_hours_estimate`** — M04 publishes a
  mastery scalar and no provenance behind it, so "you broke on both in your last
  session" cannot be said.
- ~~**FR-2.7's confidence discount**~~ — **this entry was wrong, and it is
  left here rather than deleted.** It claimed M04 publishes no standard error.
  M04's `MasteryOut` has carried `se`, `se_effective`, `n_direct` and `stale`
  since it was written; nobody had called the endpoint. Landed 2026-08-27.
  Being blocked on an upstream was asserted here for a fortnight without anyone
  checking the payload, which is worth remembering the next time a line in this
  section says blocked.
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
- ~~**The offline concept table holds five entries.**~~ **Closed 2026-08-28** —
  110 now, derived from the archetypes' requirement sets rather than written
  out. The IDs deliberately did NOT grow: `FALLBACK_RESOLUTIONS` still holds
  exactly five, because an id invented from a label looks exactly like a real
  one and matches nothing in M04, so every mastery lookup returns nothing and
  "no score" becomes indistinguishable from "not measured yet". Wide vocabulary,
  five honest ids.

  Checking those five against M04's actual ontology — the first time anyone
  had — found `concept:sql_basics`, which **M04 has never had**. It is
  `concept:sql_queries`. The damage was not limited to a degraded parse:
  FR-2.12 shares one parse across every student on a drive, so a posting parsed
  while M04 happened to be down stored a dead id for all sixty of them.
  `test_the_offline_ids_are_ids_m04_actually_has` is now a gate.
- ~~**The heading vocabulary is 30 fixed phrases.**~~ **Closed 2026-08-28.**
  The label-level test this asked for exists, and it needed no verb list. In an
  action clause the verb comes first and English conjoins verbs with a bare
  and/or before the object begins, so the split is POSITIONAL — "Build and
  orchestrate | multi-agent AI systems". Two guards keep it honest, and both
  are derived rather than listed: the leading run is checked against the
  archetypes' own ~190 requirement labels, and where every word of the run is a
  known thing the line is left alone. Where that is ambiguous — "Design" is a
  thing because "System Design" is an archetype requirement — the DOCUMENT
  settles it: a conjunction joins like with like, so "Design and build" pairs a
  thing with a non-thing and reads as verbs, and a bullet with no conjunction
  is resolved by the majority of its siblings in the same block.

  On the real brochure this recovered the most technology-dense section of the
  posting: multi-agent AI systems, intent prompts for AI coding agents, RAG
  pipelines, vector stores and knowledge bases — all previously discarded to
  avoid four verbs.
- ~~**No golden corpus.**~~ This line was stale and is left struck through
  rather than deleted: the corpus landed on 2026-08-27 and AC-2.3 has been
  measured at 0.857 since. A debt entry that outlives its debt is worse than no
  entry, because the next session reads it and re-plans work already done.

- **No migrations.** The dev database has now been rotated twice in one session
  — once for the FR-2.13 columns and once for `script`/`script_share` — because
  a schema change makes every existing row unreadable and every request 500s
  with a SQL error rather than a sentence. `*.db.*` is gitignored so the
  rotation is cheap, and that is a workaround, not a fix.

- **The `for_requirements` pipeline rejoins twice.** `normalise` rejoins before
  stripping and `for_requirements` rejoins again after it, because stripping
  DELETES lines and deleting a line makes its neighbours adjacent. Correct, and
  it means the layout repair is not a single pass anybody can point at. Found
  on the real brochure, where a table artefact sat between "Design and build RAG
  pipelines, vector stores, and" and "knowledge bases" and kept them apart for
  the whole pipeline.

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
