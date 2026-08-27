/**
 * M02 — JD Parser & Coverage Planner · the shapes the backend actually sends.
 *
 * Hand-written against `router.py` rather than generated, and deliberately
 * narrow: there is no type here for a field the API does not return. The spec
 * (§5) describes `Requirement`, `RequirementGroup`, `EligibilityCriteria`,
 * `CoveragePlan` and more — none of which exist yet — and declaring them now
 * would let a screen be written against a shape nothing serves.
 */

import type { DegradedFeature, DependencyStatus } from "@ai/core";

/** Where a concept_id came from. The whole reason the field exists. */
export type ConceptSource = "m04" | "offline_fallback";

/** Which ontology the JD was scanned against. */
export type ScannedAgainst = "m04" | "offline_lexicon";

/**
 * Where in the JD a requirement is written. Offsets into `raw_text`.
 *
 * The platform's one contract above the others: a fact points at the
 * characters it came from. `text` is verbatim, so a client can check the span
 * still resolves rather than trusting the offsets.
 */
export interface SourceSpan {
  start: number;
  end: number;
  text: string;
}

/**
 * One thing the posting asks for, and where it says so.
 *
 * A PARTIAL §5 `Requirement`. `kind`, `necessity`, `weight`, `measured_by` and
 * `seniority_signal` are not here because nothing derives them yet — absent
 * rather than defaulted, since a `necessity: "must"` on every row would look
 * derived and would be what the coverage plan allocates questions on.
 */
/**
 * §6.4's three levels. Ordered here the way they are ranked, so a `Necessity[]`
 * literal reads down from strongest.
 */
export type Necessity = "must" | "should" | "could";

/**
 * §5's `RequirementGroup`. Only `any_of` is ever emitted: `all_of` is the
 * default and would carry no information, and no posting seen so far writes
 * "at least two of".
 */
export interface RequirementGroup {
  id: string;
  satisfaction: "any_of" | "all_of" | "n_of";
  /** `Requirement.id`s. Two or more — a group of one is not a choice. */
  requirement_ids: string[];
  /** The words the disjunction was written as, e.g. "Docker or Kubernetes". */
  text: string;
  span: SourceSpan | null;
}

export interface Requirement {
  id: string;
  text: string;
  /** `null` when the label could not be located — an inferred requirement. */
  span: SourceSpan | null;
  /**
   * How badly the posting wants it, read from modal language and the heading
   * it sits under. `should` is the default and means the JD did not say —
   * not that it is optional.
   */
  necessity: Necessity;
  /** 0-1, normalised across the set. The share of interview time it earns. */
  weight: number;
  /** How many times the posting names it. Repetition is emphasis (§6.4). */
  mentions: number;
  /**
   * The `RequirementGroup` this is one alternative of, or `null` — which is
   * most requirements. A member is one acceptable answer, not a demand.
   */
  group_id: string | null;
  /** `hard_skill` | `soft_skill` | `tool` | `domain` | `qualification`. */
  kind: string;
  /**
   * How this platform could produce evidence about it.
   *
   * EMPTY is a real answer, not a gap in a lexicon (§3.2.1 trap 3):
   * "go-getter attitude" is something the posting asked for and nothing here
   * can test, and saying so beats faking a score for it.
   */
  measured_by: string[];
  /** `null` because the posting did not say — never defaulted to `fresher`. */
  seniority_signal: string | null;
  concept_ids: string[];
  /**
   * A concept id exists, so M04 can supply mastery, prerequisites and an
   * adaptive ladder.
   *
   * The rarer case, by design: M04's ontology is 120 INTERVIEW concepts — DSA,
   * CS core, communication — and two of them are technology-shaped. A modern
   * stack grounds almost nowhere, and that is not a gap in the ontology.
   */
  grounded: boolean;
  /**
   * A question can be put in front of the student at all.
   *
   * Grounded, or the posting states it at a real offset and `measured_by`
   * names a round that could carry it — in which case M05 generates a question
   * citing the line the company wrote. Weaker than grounded (no mastery prior,
   * no adaptive ladder) and completely different from nothing.
   *
   * Reading "no concept id" as "unaskable" is what reported 72 of 73
   * requirements untestable on a posting where 72 are perfectly askable.
   */
  testable: boolean;
  /** `m04` or `offline_fallback`; `null` when it mapped to nothing. */
  concept_source: ConceptSource | null;
  source: string;
}

/**
 * The hard filters on who may sit this drive (FR-2.4).
 *
 * Every field is `null` when the posting does not say — not zero, not a
 * permissive default. "This JD does not state a cutoff" and "this JD has no
 * cutoff" are different facts, and a `min_cgpa: 0` would tell a student they
 * are eligible for a drive nobody checked them against.
 *
 * `stated` is the field to branch on: all-nulls and a genuinely open drive look
 * identical otherwise, and only one of them means we looked.
 *
 * PARTIAL against §5: `allowed_branches`, `location` and the package figures
 * are not extracted yet and are absent rather than guessed.
 */
export interface EligibilityCriteria {
  min_cgpa: number | null;
  max_backlogs_active: number | null;
  year_of_passing: number[];
  bond_months: number | null;
  /**
   * "No backlogs in the entire academic career" is a stricter bar than "no
   * ACTIVE backlogs": a student who cleared an old arrear passes one and fails
   * the other, so they are two fields rather than one.
   */
  max_backlogs_history: number | null;
  /** Normalised branch codes. Empty means we found no restriction — NOT that
   *  we verified there is none. */
  allowed_branches: string[];
  location: string[];
  /** The headline number. */
  package_lpa_total: number | null;
  /** The part that is not variable. A 6.5 LPA offer with 2 LPA variable is a
   *  4.5 LPA salary, and students compare the wrong one constantly. */
  package_lpa_fixed: number | null;
  /** The lines these were read from, so a student can check the cutoff. */
  raw_spans: SourceSpan[];
  stated: boolean;
}

export interface JobDescription {
  id: string;
  company_name: string;
  role_title: string;
  raw_text: string;
  /**
   * SHA-256 of the normalised (company, role, text) — FR-2.12.
   *
   * The parse is shared across every student who pastes the same posting;
   * only the gap analysis is per-student. Two students on the same drive are
   * looking at one `id`, and this is why.
   */
  content_sha256: string;
  /** The same labels as `requirements`, without the provenance. */
  required_skills: string[];
  /** §5's contract: each requirement with the span it was written at. */
  requirements: Requirement[];
  /** The places the posting offered a CHOICE rather than making a demand. */
  requirement_groups: RequirementGroup[];
  /** The hard filters — CGPA, backlogs, batch, bond. Never interview topics. */
  eligibility: EligibilityCriteria;
  /** skill label -> concept_id. Only labels that resolved to something. */
  resolved_concepts: Record<string, string>;
  concept_source: Record<string, ConceptSource>;
  /** Found in the JD, mapped to no concept. Kept, never dropped. */
  unresolved_skills: string[];
  /**
   * §5's `role_archetype`. `null` when nothing matched well enough, or when the
   * top two were too close to separate — both are answers, and different from
   * each other.
   */
  role_archetype: string | null;
  /** Recorded even when the match was rejected, because "we looked and were
   *  not sure" is not the same as "we did not look". */
  archetype_confidence: number;
  /** How many requirements came from the archetype rather than the posting. */
  inferred_count: number;
  /**
   * Which extraction passes actually ran: `lexicon`, `lexicon+model`,
   * `lexicon (model: <reason>)`, or `archetype` for a role-only set.
   *
   * Recorded per posting rather than inferred from config, because §6.2 runs
   * both passes and Rule 2 means either can be absent without an error — and
   * two students comparing thin lists need to see that one parse had a model
   * and the other did not.
   */
  extracted_by: string;
  /**
   * Instruction-shaped spans neutralised in this posting (EC-2.13). Almost
   * always zero.
   *
   * Shown, unlike M01's equivalent, and for the opposite reason: M01 hides it
   * because a resume's author IS the person the filter is aimed at, and
   * telling them turns it into an oracle. A posting's author is not the person
   * reading this screen — the student pasted a document somebody else wrote.
   */
  injections_removed: number;
  scanned_against: ScannedAgainst;
  created_at: string;
}

/** One entry in §2.3's door-3 role picker. */
export interface ArchetypeOut {
  id: string;
  name: string;
  /** Shown before the student commits: "just pick a role" is only trustworthy
   *  if they can see what they are picking. */
  requirements: string[];
  default_minutes: number;
}

/**
 * The six gap states.
 *
 * `not_measured` is M02's spec word (§6.5) for what the platform's MasteryBar
 * calls `not_tested`. Same fact, two vocabularies, and the mapping lives in
 * one place — `CoverageRow` — rather than being re-derived per screen.
 */
export type GapState =
  | "strong"
  | "adequate"
  | "weak"
  | "not_measured"
  | "unmeasurable"
  /**
   * The posting offered a choice and another answer met it (FR-2.3). Not a
   * gap and not silence: "Java or Python" is satisfied by Python, and the
   * student needs to see that Java was asked about and is accounted for.
   */
  | "met_by_alternative";

export interface Coverage {
  jd_id: string;
  candidate_id: string;
  /** null whenever there was nothing to average. NEVER 0 for "we don't know". */
  coverage_score: number | null;
  /** "M04" when a live upstream answered, null when nobody was asked. */
  measured_against: string | null;
  measured_count: number;
  requirement_count: number;
  covered: string[];
  weak: string[];
  not_measured: string[];
  unmeasurable: string[];
  states: Record<string, GapState>;
  mastery: Record<string, number | null>;
  gap_severity: Record<string, number>;
  /** label -> the alternative that met the same requirement. */
  met_by_alternative: Record<string, string>;
  /** skill label -> concept_id, for the labels that resolved. */
  resolved_concepts: Record<string, string>;
  concept_source: Record<string, ConceptSource>;
  scanned_against: ScannedAgainst;
  degraded: DegradedFeature[];
}

export interface Health {
  status: string;
  module: string;
}

/** `ai_core.modules_meta.ModuleStatus`, as served by GET /status. */
export interface ModuleStatus {
  id: string;
  name: string;
  slug: string;
  phase: string;
  owner: string;
  implemented: boolean;
  spec: string;
  reserved_port: number;
  detail: string;
}

export type Deps = DependencyStatus[];

export interface JdParseIn {
  company_name: string;
  role_title: string;
  raw_text: string;
}

/* ------------------------------------------------------------------ */
/*  The coverage plan (FR-2.8)                                        */
/* ------------------------------------------------------------------ */

/**
 * One requirement's share of the interview.
 *
 * `rationale` is a sentence rather than a code because the spec marks it
 * "shown in the UI": a student looking at four questions on one topic and none
 * on another is owed the reason in words they can argue with.
 */
export interface CoverageAllocation {
  requirement_id: string;
  requirement_text: string;
  question_budget: number;
  /** Always "verbal" today — `measured_by` does not exist, so nothing can say
   *  a requirement needs a coding or design round. */
  round_type: string;
  /** `weight × (1 − mastery)`, discounted when we are guessing. */
  priority: number;
  rationale: string;
  minutes: number;
}

export interface CoveragePlan {
  jd_id: string;
  candidate_id: string;
  total_minutes: number;
  /** What the allocation actually consumes — lower than `total_minutes` when
   *  the remaining time cannot buy another whole question. */
  allocated_minutes: number;
  allocations: CoverageAllocation[];
  /** Must-haves that did not fit. Stated openly, never quietly dropped. */
  uncovered: string[];
  /** Requirements no question can probe — a different problem from not fitting. */
  unmeasurable: string[];
  /** EC-2.11 requires the suggestion, not just the omission. */
  suggestion: string | null;
  /**
   * Every requirement is at its four-question cap with minutes left over.
   *
   * At that point the plan genuinely IS the same for every student, because
   * there is nothing left to differentiate with. Not a bug — a 90-minute
   * session against a five-requirement posting has more time than the posting
   * has content — but a plan that looks tailored and is not is exactly what
   * §3.2.1's trap 4 warns about, so it is said out loud.
   */
  saturated: boolean;
  plan_version: string;
}

/* ------------------------------------------------------------------ */
/*  The resume against the posting (FR-2.15)                          */
/* ------------------------------------------------------------------ */

/**
 * Four states, not two.
 *
 * Collapsing `unknown` and `scale_mismatch` into `fails` turns "we could not
 * read your grade" into "you are not eligible" — a different sentence with
 * very different consequences for somebody deciding whether to prepare.
 */
export type VerdictState = "meets" | "fails" | "unknown" | "scale_mismatch";

export interface Verdict {
  criterion: string;
  state: VerdictState;
  /** The sentence already written, so no screen re-phrases a cutoff. */
  detail: string;
  /** What the posting demands, verbatim. */
  required: string | null;
  /** What the resume says, verbatim. */
  yours: string | null;
}

/**
 * `blocking` is reserved for eligibility.
 *
 * A skill gap is something to prepare for; a CGPA cutoff is something to be
 * turned away by. Ranking them together would tell a student to study for a
 * drive they cannot sit.
 */
export type RiskSeverity = "blocking" | "high" | "medium" | "low";

export interface Risk {
  severity: RiskSeverity;
  title: string;
  detail: string;
  requirements: string[];
}

/** `ok`, `no_resume`, or `m01_unreachable` — never conflated. */
export type ResumeStatus = "ok" | "no_resume" | "m01_unreachable";

export interface MatchReport {
  jd_id: string;
  candidate_id: string;
  resume_id: string | null;
  resume_status: ResumeStatus;
  verdicts: Verdict[];
  evidenced: string[];
  unevidenced: string[];
  /**
   * label -> the alternative that met the same requirement.
   *
   * A posting saying "Python or Java" is met by Python, and listing Java as
   * missing is §3.2.1's "33% qualified" reading arriving at the resume screen.
   */
  met_by_alternative: Record<string, string>;
  /** `null` when the posting states no must-haves — not 0, which reads as
   *  total failure rather than as a question nobody asked. */
  must_have_evidence: number | null;
  risks: Risk[];
}

/* ------------------------------------------------------------------ */
/*  The student's corrections (FR-2.10)                               */
/* ------------------------------------------------------------------ */

/** What a student can know better than the parser. Three things, not a form. */
export type EditAction = "remove" | "add" | "necessity";

export interface RequirementEditIn {
  action: EditAction;
  /** The requirement's LABEL, not its id — ids are positional and move. */
  target: string;
  /** Only read for `necessity`. */
  value?: string;
}

/**
 * One student's view of a SHARED parse.
 *
 * `GET /jds/{id}` returns the parse itself, cached by content hash across every
 * student who pasted the same posting (FR-2.12). This is that parse with one
 * student's corrections laid over it — two students on one drive can disagree
 * about what the posting says and both be served correctly.
 */
export interface EffectiveRequirements {
  jd_id: string;
  candidate_id: string;
  requirements: Requirement[];
  requirement_groups: RequirementGroup[];
  edit_count: number;
}
