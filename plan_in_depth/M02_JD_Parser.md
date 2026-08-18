# M2 — JD Parser & Coverage Planner

> **Master plan reference:** §28 · **Phase:** 1 · **Owner:** E3 · **Depends on:** M4 (ontology), M1 (claims) · **Feeds:** M5, M6, M15, M16, M19

---

## 1. In one paragraph

The student pastes a job description — usually a badly formatted blob from a placement-portal email — and it becomes the **configuration for everything that follows**. We extract what the role actually requires, weight each requirement by how much the JD emphasises it, compare it against what we know the student can do, and produce a **coverage plan**: an allocation of interview question budget across requirements. The Mock Interview Engine consumes that plan directly. One paste configures the panel, the round list, the difficulty band, the study plan, and the readiness target. This is the module that turns "a mock interview" into "a mock interview *for this job*".

---

## 2. Reverse-thinking: the user

### 2.1 What actually arrives

Campus JDs are not LinkedIn JDs. Real specimens from an Indian placement cell:

```
Company: XYZ Technologies
Role: Software Engineer Trainee
Package: 6.5 LPA (4.5 fixed + 2 variable)
Eligibility: 7.5 CGPA, no active backlogs, CSE/IT/ECE
JD: Good knowledge of DSA, OOPs, DBMS. Should be a team player with
excellent communication. Knowledge of any one of Java/Python/C++.
Bond: 18 months
```

That is 40 words of actual requirement. Meanwhile a product-company JD runs 600 words with a "what you'll do / what we're looking for / bonus points" structure. **The parser must handle both, and the thin one is the common case.** A system that needs a rich JD to work is useless on campus.

### 2.2 The emotional arc

```
BEFORE   "I have an interview Thursday. I don't know what to study."   (undirected anxiety)
   ↓
DURING   "Oh — it's mostly DSA and DBMS, and I'm weak on DBMS."        (orientation)
   ↓
AFTER    "I know exactly what to work on and I have 3 days."            (targeted readiness)
   ↓
NEXT     "Start the mock configured for this."                          (action)
```

The competitor failure here is generic: every tool says "practise DSA". The thing that lands is *"this JD mentions DBMS three times and normalisation twice — and your last two sessions broke on normalisation."*

### 2.3 The journey

#### Screen 1 — Input, with three doors

```
┌─────────────────────────────────────────────────────────────┐
│  What are you preparing for?                                │
│                                                             │
│  ┌───────────────┐  ┌───────────────┐  ┌────────────────┐   │
│  │ 🔍 Pick a     │  │ 📋 Paste a    │  │ 🎯 Just pick   │   │
│  │   company     │  │   JD          │  │   a role       │   │
│  │               │  │               │  │                │   │
│  │ TCS, Infosys, │  │ Any format.   │  │ SDE, Data      │   │
│  │ Amazon…       │  │ Even messy.   │  │ Analyst, ML…   │   │
│  └───────────────┘  └───────────────┘  └────────────────┘   │
│                                                             │
│  Upcoming at your campus:                                   │
│  [ Zoho · 14 Aug ] [ TCS NQT · 22 Aug ] [ Cognizant · 2 Sep ]│
└─────────────────────────────────────────────────────────────┘
```

**The campus-drive chips are the highest-value element on this screen.** The placement cell already publishes the calendar; pre-loading it means most students never type anything. This is a one-day integration that removes the largest friction point in the product.

**Door 3 ("just pick a role") is mandatory.** A student in September with no drive scheduled still needs to practise. Requiring a JD to use the product would be a self-inflicted wound.

#### Screen 2 — The requirement read-back

```
┌────────────────────────────────────────────────────────────────┐
│  XYZ Technologies · Software Engineer Trainee                  │
│  6.5 LPA · 18-month bond · 7.5 CGPA cutoff                     │
│                                                                │
│  MUST HAVE                                        You          │
│  ● Data Structures & Algorithms       ▓▓▓▓▓▓▓░░░  strong       │
│  ● Object-Oriented Programming        ▓▓▓▓▓░░░░░  ok           │
│  ● DBMS  ⚠                            ▓▓░░░░░░░░  weak    ←    │
│  ● One of Java / Python / C++         ▓▓▓▓▓▓▓▓░░  Python ✓     │
│                                                                │
│  SHOULD HAVE                                                   │
│  ○ Communication                      ▓▓▓▓░░░░░░  ok           │
│  ○ Teamwork                           —           not measured │
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Your biggest gap: DBMS — specifically normalisation      │  │
│  │  and indexing. You broke on both in your last session.    │  │
│  │  About 4 hours of focused work closes it.                 │  │
│  │                        [ Show me the plan ]               │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                │
│  [ ✎ Something wrong? Edit requirements ]                      │
│  [ Start the mock configured for this →  ~45 min ]             │
└────────────────────────────────────────────────────────────────┘
```

**Design decisions:**
- **"not measured" is written out, never shown as 0 or as an empty bar.** (README Rule 2.) A student seeing `Teamwork: 0` when we simply haven't tested it is a trust-destroying lie.
- The eligibility line (CGPA, backlogs, bond) is surfaced prominently because students genuinely miss these and waste a week preparing for a drive they can't sit.
- One highlighted gap, not five. Five gaps is a wall; one gap is a task.
- The mock button carries a **time estimate**. Students budget in evenings, not in features.

#### Screen 3 — Coverage transparency (before the interview, not after)

A small expandable panel showing *what the interview will actually cover*, because a mock that surprises you feels random and a mock you understand feels designed:

```
This 45-minute mock will cover:
  DSA          ████████████  4 questions   (your gap: medium)
  DBMS         ████████      3 questions   (your gap: large)  ← focus
  OOP          ████          2 questions
  Projects     ████          2 questions
  HR           ████          2 questions

  Not covered: system design (not in this JD)
  [ Adjust ]
```

The `[Adjust]` control is real: the student can drag a slider to add or remove emphasis. A student who says "actually I want more DBMS" is telling us something valuable, and we log it.

### 2.4 What makes a user quit

| Quit trigger | Counter |
|---|---|
| Asked to paste a JD they don't have | Company picker + role picker + campus-drive chips |
| Parse produces obvious nonsense on a 40-word JD | Role-archetype fallback fills the gaps; read-back screen is editable |
| Wall of 25 requirements | Group by MUST/SHOULD, cap the visible list at 8, "show all" behind a link |
| Gap analysis says "you're weak at everything" | Show one gap; frame as time-to-close, not as deficiency |
| No idea what the mock will do | Screen 3 coverage transparency |

---

## 3. Reverse-thinking: the developer

### 3.1 The five traps

**Trap 1 — Assuming the JD contains enough information.** The 40-word campus JD is the *median*, not the edge case. A parser tuned on LinkedIn-style JDs will emit three requirements and a useless plan. *Counter: the role-archetype library (§6.3) supplies everything the JD doesn't say, and we mark which requirements came from the JD vs the archetype so the UI can be honest about it.*

**Trap 2 — Extracting requirements without weighting them.** "Good knowledge of DSA, OOPs, DBMS" and "Bonus: familiarity with Docker" are not equal, and a flat list makes them equal. *Counter: necessity extraction from modal language + repetition counting + position weighting (§6.4).*

**Trap 3 — Treating the JD as trusted text.** Same injection surface as M1, and worse — students paste from anywhere. *Counter: identical untrusted-input handling (M1 §6.7).*

**Trap 4 — Coverage planning as a fixed template.** "Every SDE mock = 4 DSA + 2 OOP + 2 HR" is not planning, it is a constant. The entire value is that the plan changes based on *this student's* gaps against *this JD*. *Counter: the budget allocation in §6.5 is a real optimisation, and it must visibly differ between two students on the same JD. Test that explicitly.*

**Trap 5 — Losing the requirement→turn linkage.** If you can't say "this question probed requirement R-3", you can't produce a coverage report, and coverage is half the value. *Counter: `CoverageLedger` is written at question-selection time, not reconstructed afterwards (§6.6).*

### 3.2 The non-obvious hard parts

1. **"Java/Python/C++" is a disjunction**, not three requirements. Missing this makes a Python-only student look 33% qualified. Parse `/`, `or`, `any one of`, `either` into a `RequirementGroup` with `satisfaction: any_of`.
2. **Eligibility ≠ requirement.** CGPA cutoffs and bonds are hard filters, not interview topics. They belong in a separate `EligibilityCriteria` object and must never enter the coverage plan.
3. **Soft skills are requirements we can partially measure.** "Communication" maps to real measured constructs (M12/M17). "Team player" maps to behavioural probes (M6 HR round). "Go-getter attitude" maps to nothing — mark it `unmeasurable` and say so rather than faking a score.
4. **The same JD is pasted by 60 students.** Normalise and cache by content hash; the parse is shared, the gap analysis is per-student.
5. **Company aliasing.** "TCS", "Tata Consultancy Services", "TCS Digital", "TCS NQT" are one company and four different drives. The alias + drive-variant table matters more than it sounds.

---

## 4. Functional requirements

| ID | Requirement | Priority |
|---|---|---|
| FR-2.1 | Accept pasted text, uploaded PDF/DOCX, company+role selection, or role-only selection | P0 |
| FR-2.2 | Extract requirements with `kind`, `necessity`, `weight`, and a source span | P0 |
| FR-2.3 | Handle disjunctive requirements as a group with `any_of` satisfaction | P0 |
| FR-2.4 | Extract eligibility criteria separately from requirements | P0 |
| FR-2.5 | Map each requirement to `concept_id`s where possible; mark `unmeasurable` where not | P0 |
| FR-2.6 | Infer a role archetype and fill missing requirements from it, marked as inferred | P0 |
| FR-2.7 | Produce a per-requirement gap using the Skill Graph, with "not measured" as a distinct state | P0 |
| FR-2.8 | Produce a `CoveragePlan` allocating question budget under a time constraint | P0 |
| FR-2.9 | Guarantee ≥1 probe for every `must` requirement that is measurable | P0 |
| FR-2.10 | Allow the student to edit requirements and re-plan | P1 |
| FR-2.11 | Track live coverage during a session and expose a coverage report after | P0 |
| FR-2.12 | Cache parses by JD content hash across students | P1 |
| FR-2.13 | Enrich with company drive data from M15 when available | P1 |
| FR-2.14 | Work with zero JD (role-only mode) at full functionality | P0 |
| FR-2.15 | Surface eligibility mismatches prominently ("you have 7.2, cutoff is 7.5") | P1 |
| FR-2.16 | Complete p95 in ≤ 8 s | P0 |

---

## 5. Data contracts

```python
class Requirement(BaseModel):
    id: str                       # "R-3", stable within a JD
    text: str
    span: SourceSpan | None       # None when inferred from archetype
    kind: Literal["hard_skill","soft_skill","tool","domain","responsibility",
                  "qualification","nice_to_have"]
    necessity: Literal["must","should","could"]
    concept_ids: list[str]
    measurable: bool              # False for "go-getter attitude"
    measured_by: list[Literal["technical","coding","design","behavioural",
                              "communication","aptitude"]]
    weight: float                 # 0–1, normalised across the set
    source: Literal["jd","archetype","company_profile","user"]
    seniority_signal: Literal["intern","fresher","junior","mid","senior"] | None

class RequirementGroup(BaseModel):
    id: str
    satisfaction: Literal["all_of","any_of","n_of"]
    n: int | None
    requirement_ids: list[str]
    # "Java / Python / C++" → any_of

class EligibilityCriteria(BaseModel):
    min_cgpa: float | None
    max_backlogs_active: int | None
    max_backlogs_history: int | None
    allowed_branches: list[str]
    year_of_passing: list[int]
    bond_months: int | None
    location: list[str]
    package_lpa_fixed: float | None
    package_lpa_total: float | None
    raw_spans: list[SourceSpan]

class RequirementSet(BaseModel):
    id: UUID
    jd_id: UUID | None
    company_id: UUID | None
    role_archetype: str           # "sde_1", "data_analyst", ...
    archetype_confidence: float
    requirements: list[Requirement]
    groups: list[RequirementGroup]
    eligibility: EligibilityCriteria
    inferred_count: int           # how much came from the archetype, for honesty in UI

class Gap(BaseModel):
    requirement_id: str
    state: Literal["strong","adequate","weak","not_measured","unmeasurable"]
    mastery: float | None         # None when not_measured
    confidence: float | None
    severity: float               # weight × (1 - mastery); 0 when not measurable
    evidence_session_ids: list[UUID]
    closable_hours_estimate: float | None

class CoverageAllocation(BaseModel):
    requirement_id: str
    question_budget: int
    round_type: str
    priority: float
    rationale: str                # "must-have + large gap" — shown in the UI

class CoveragePlan(BaseModel):
    id: UUID
    requirement_set_id: UUID
    candidate_id: UUID
    total_minutes: int
    allocations: list[CoverageAllocation]
    rounds: list[PlannedRound]
    uncovered: list[str]          # requirement_ids we can't fit — stated openly
    generated_at: datetime
    plan_version: str
```

```sql
CREATE TABLE job_descriptions (
  id UUID PRIMARY KEY,
  content_sha256 TEXT UNIQUE NOT NULL,   -- shared across students
  raw_text TEXT NOT NULL,
  source TEXT,                            -- paste|upload|company_picker|role_picker
  company_id UUID REFERENCES companies(id),
  title TEXT,
  parsed JSONB,                           -- RequirementSet
  parser_version TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE coverage_ledger (
  session_id UUID NOT NULL,
  requirement_id TEXT NOT NULL,
  turn_id UUID,
  state TEXT NOT NULL,                    -- planned|asked|answered|scored|skipped
  score REAL,
  updated_at TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (session_id, requirement_id, turn_id)
);
```

---

## 6. The pipeline in minute detail

### 6.1 Stage 1 — Normalise the input
Strip boilerplate (email signatures, "Regards, Placement Cell", forwarded-message headers, disclaimers) with a rule list built from 50 real campus emails. Detect and separate the *administrative* block (dates, venue, registration link) from the *role* block. Hash the role block for the cache key.

### 6.2 Stage 2 — Extract
Single mid-tier structured-output call over the cleaned text, returning requirements, groups, eligibility, and title. Prompt includes 4 few-shot examples deliberately chosen as: one 40-word campus JD, one 600-word product JD, one with a disjunction, one with an embedded eligibility table.

Post-checks:
- Every `span` must verbatim-resolve (same rule as M1). Non-resolving requirements are kept but marked `source=jd, span=None` and logged.
- Disjunction detection is **also** run as a deterministic regex pass (`/(\w+)\s*[/|]\s*(\w+)/`, `any one of`, `either .* or`) and merged with the LLM's groups — belt and braces, because getting this wrong is visible and embarrassing.

### 6.3 Stage 3 — Role archetype & backfill
Embed the title + requirement texts, cosine-match against an archetype library (~24 archetypes, each with a canonical requirement set, default round template, default difficulty band, and typical duration). Confidence = top-1 similarity, with a margin check against top-2.

**Backfill rule:** if the JD yields < 5 measurable requirements, add archetype requirements up to 8, each marked `source=archetype`. The UI shows these in a lighter style with a tooltip: *"This wasn't in the JD, but it's standard for this role."* Honesty here costs nothing and buys credibility.

### 6.4 Stage 4 — Weighting

```python
necessity_mult = {"must": 1.0, "should": 0.6, "could": 0.3}[r.necessity]
position_w     = 1.0 - 0.4 * (first_mention_index / total_length)   # earlier = heavier
repetition_w   = min(1.0, 0.6 + 0.2 * (mention_count - 1))
emphasis_w     = 1.2 if in_bold_or_bulleted_must_section else 1.0
source_w       = 1.0 if r.source == "jd" else 0.75                  # inferred counts less

raw = necessity_mult * position_w * repetition_w * emphasis_w * source_w
weight = raw / sum(all_raw)                                          # normalise to 1.0
```

### 6.5 Stage 5 — Gap analysis and budget allocation

Gap state per requirement:
```
mastery = skill_graph.mastery(concept_ids)   # posterior mean, weighted by concept centrality
confidence = 1 - mean(standard_error)

state = "not_measured"  if confidence < 0.25
        "unmeasurable"  if not r.measurable
        "weak"          if mastery < 0.45
        "adequate"      if mastery < 0.70
        "strong"        otherwise

severity = r.weight * (1 - mastery) * confidence_discount
# not_measured requirements get severity = r.weight * 0.6 — we don't know, so we should probe
```

**Budget allocation.** Total question budget `Q = f(total_minutes, round_mix)` — roughly one question per 3.5 minutes for verbal, one per 12 minutes for coding, one per 20 for design.

```
maximise   Σ_i severity_i · log(1 + q_i)        # diminishing returns per requirement
subject to Σ_i q_i · time_i ≤ total_minutes
           q_i ≥ 1  for all measurable must-haves          # FR-2.9 hard constraint
           q_i ≤ 4                                          # nobody wants 7 DBMS questions
           round feasibility (a coding requirement needs a coding round)
```
Solved greedily by marginal value per minute; falls back to a small ILP (`pulp`) when the must-have constraints alone exceed the time budget — in which case the plan honestly reports `uncovered` and suggests a longer session.

**The log-utility matters:** without it the optimiser dumps the entire budget on the single worst gap, producing a mock that is 9 DBMS questions. Diminishing returns is what makes the plan feel like a human designed it.

### 6.6 Stage 6 — Live coverage tracking
When M5 selects a question, it writes `coverage_ledger(session, requirement_id, turn_id, state='asked')`. When M13 scores that turn, the row moves to `scored` with the score. The planner reads the ledger at each round boundary and re-prioritises remaining budget toward the least-covered high-weight requirements. **This is the mechanism that makes coverage a guarantee rather than an intention.**

### 6.7 Stage 7 — Company enrichment
If `company_id` resolves and M15 has a brief, override archetype defaults with observed reality: real round structure, real difficulty band, real topic-frequency distribution. A JD saying "good problem solving" becomes a plan saying "2 medium DP, 1 graph, 1 SQL" because that's what this company actually asked last season.

---

## 7. API surface

```
POST /v1/jds                          {text|file|company_id+role|archetype} → RequirementSet
GET  /v1/jds/{id}
PATCH /v1/jds/{id}/requirements/{rid} user edit
POST /v1/jds/{id}/plan                {minutes, modalities, focus_overrides} → CoveragePlan
GET  /v1/jds/{id}/gap                 → Gap[] for the current user
GET  /v1/sessions/{id}/coverage       → live coverage ledger view
GET  /v1/campus/drives                → upcoming drives with prefilled JDs
GET  /v1/archetypes                   → the role picker list
```

---

## 8. UI specification

**Components:** `JDInputTabs` · `DriveChips` · `RequirementList` (grouped, MUST/SHOULD, inferred styling) · `GapBar` (with a distinct "not measured" treatment) · `CoveragePreview` (with adjust sliders) · `EligibilityBanner` · `RequirementEditor`

**States:**

| Component | Loading | Empty | Error | Partial |
|---|---|---|---|---|
| RequirementList | 6 skeleton rows | "Couldn't find requirements — pick a role instead" | Retry + role fallback | "Read 4 requirements; filled 4 more from the standard SDE profile" |
| GapBar | shimmer | "not measured yet" label | — | greyed with a "?" for unknown |
| CoveragePreview | — | — | — | shows `uncovered` list with "extend to 60 min to include these" |

**Critical visual rules:**
- **"Not measured" must look different from "weak".** Weak = filled bar, amber. Not measured = dashed outline, grey, with the literal words "not measured yet". If a designer ever unifies these, the fairness property breaks.
- Inferred requirements: 70% opacity + a dotted underline + tooltip.
- Eligibility mismatch: a top banner, amber, non-blocking: *"This drive needs 7.5 CGPA. You've told us 7.2 — double-check with your placement cell before spending time here."* Never block; sometimes the cell relaxes cutoffs and we should not be the reason a student didn't try.

**Mobile:** the requirement list collapses to MUST-only by default with a "show 6 more"; the coverage preview becomes a horizontal bar chart.

---

## 9. Edge cases

| ID | Case | Behaviour |
|---|---|---|
| EC-2.1 | 40-word JD | Archetype backfill to 8 requirements, clearly marked |
| EC-2.2 | 3,000-word JD with 40 requirements | Cap displayed at 8 by weight; all stored; plan uses top 12 |
| EC-2.3 | "Java/Python/C++" disjunction | `RequirementGroup(any_of)`; satisfied if any one is strong |
| EC-2.4 | JD is actually an email thread | Boilerplate stripper; if < 30 words survive, prompt for a paste of just the JD |
| EC-2.5 | Non-technical role (HR, Sales) | Archetype exists; technical rounds dropped; behavioural + aptitude emphasised |
| EC-2.6 | JD in Hindi/Tamil | Detect, translate for parsing, keep original for display |
| EC-2.7 | Company unknown | Archetype-only path; brief unavailable; no fabricated company detail |
| EC-2.8 | Requirement maps to no concept | `measurable=false`; stated in UI as "we can't test this here" |
| EC-2.9 | All requirements already strong | Plan shifts to Final Boss difficulty + stretch items; copy: "you're ready — let's find your ceiling" |
| EC-2.10 | Student has zero session history | All gaps `not_measured`; plan is broad-coverage diagnostic; copy explains why |
| EC-2.11 | Time budget too small for must-haves | `uncovered` populated + explicit suggestion to extend |
| EC-2.12 | Same JD pasted twice | Hash hit, instant |
| EC-2.13 | Prompt injection in JD | Stripped + logged (M1 §6.7) |
| EC-2.14 | Two roles in one JD ("SDE or QA") | Detect, ask the student which, default to the first |
| EC-2.15 | JD demands 5 years' experience (mis-posted) | Seniority signal flagged; note shown: "this looks like an experienced-hire JD" |

---

## 10. Failure modes & fallbacks

| Failure | Fallback | User sees |
|---|---|---|
| LLM extraction fails | Regex + keyword extraction against the ontology | Fewer requirements + "add anything I missed" |
| Archetype match ambiguous | Ask the user to pick from top 3 | A 1-click chooser |
| Skill Graph empty | All gaps `not_measured` | "First session will map your baseline" |
| ILP infeasible | Greedy allocation + `uncovered` list | Honest "these won't fit in 30 minutes" |
| Company enrichment down | Archetype defaults | No visible change; enrichment is additive |

---

## 11. Performance & cost budget

| Stage | p95 | Cost |
|---|---|---|
| Normalise + hash | 0.1 s | — |
| Extraction (mid tier, cached across students) | 4 s | ₹0.35 (amortised ~₹0.01 at 40 students/JD) |
| Archetype match | 0.2 s | — |
| Gap analysis | 0.3 s | — |
| Plan optimisation | 0.2 s | — |
| **Total (cold)** | **≤ 8 s** | **≈ ₹0.35** |
| **Total (cached JD)** | **≤ 1 s** | **≈ 0** |

---

## 12. Test plan

**Unit** — disjunction parser on 30 real strings · weighting monotonicity (a repeated requirement never gets less weight) · allocation respects the must-have constraint under 20 random time budgets · `not_measured` never becomes 0.

**Integration** — 60 real campus JDs (collect from the placement cell in week 1) → assert every one produces ≥5 requirements and a feasible plan.

**Golden set** — 25 JDs with hand-annotated requirements + necessity. Track F1 in CI.

**The differentiation test [important]** — two students with different Skill Graphs, same JD → assert the plans differ materially (≥30% different budget allocation). If they don't, the planner is a template and the module has failed its purpose.

**Adversarial** — injection; a JD that is just "TBD"; a JD with 200 bullet points; a JD that is an image.

**Manual QA** (8 min): paste a real campus JD → check requirements → check the gap screen reads honestly → start a mock → confirm the first three questions actually target the highlighted gap → finish → confirm the coverage report matches the plan.

---

## 13. Metrics & acceptance gates

| ID | Metric | Target |
|---|---|---|
| AC-2.1 **[GATE]** | Every measurable must-have gets ≥1 probe in a full session | 100% |
| AC-2.2 **[GATE]** | `not_measured` never rendered as a numeric score | verified in UI tests |
| AC-2.3 | Requirement extraction F1 on golden set | ≥ 0.85 |
| AC-2.4 | Disjunction detection accuracy | ≥ 0.95 |
| AC-2.5 | p95 cold parse | ≤ 8 s |
| AC-2.6 | Plans differ between students on the same JD | ≥ 30% allocation divergence |
| AC-2.7 | % of sessions started from a drive chip vs manual paste | tracked; higher is better UX |
| AC-2.8 | Post-session: student agrees "the interview matched the JD" | ≥ 80% |

---

## 14. Build order

| Day | Task |
|---|---|
| 1 | JD table, hashing, cache, input endpoints |
| 2 | Boilerplate stripper on 50 real placement emails |
| 3 | LLM extraction + span verification + structured output |
| 4 | Deterministic disjunction pass + group merge |
| 5 | Eligibility extraction (separate object) |
| 6 | Archetype library (24 archetypes) + matcher + backfill |
| 7 | Weighting function + unit tests |
| 8 | Gap analysis against Skill Graph, incl. `not_measured` semantics |
| 9 | Budget allocation (greedy + ILP fallback) |
| 10 | Coverage ledger + live tracking hooks into M5/M13 |
| 11 | Screens 1–2 UI |
| 12 | Coverage preview + adjust sliders |
| 13 | Campus drive chips + placement-cell calendar import |
| 14 | Golden set, differentiation test, QA pass |

---

## 15. Open decisions

1. **Where does the campus drive calendar come from?** Options: (a) placement cell shares a sheet weekly, (b) we build a tiny admin UI for them, (c) portal integration. Recommendation: **(b)** — 1 day of work, no dependency on their IT, and it makes the cell a daily user of our product, which is worth more than the feature.
2. **Do we show package/bond info?** It's the first thing students look at. Recommendation: yes, but sourced from the cell's own data only — never scraped and never guessed.
3. **Should students see other students' gap distribution for the same JD?** ("62% of your batch is weak on DBMS too.") Genuinely reassuring, but needs cell approval and k-anonymity ≥ 20. Recommendation: yes, Phase 4, aggregate-only.
4. **Archetype library ownership** — who curates the 24 archetypes and reviews them each season? Proposal: E3 + one faculty reviewer, once per semester.
