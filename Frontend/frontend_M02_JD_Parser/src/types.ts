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
  concept_ids: string[];
  /** False when nothing in the ontology corresponds to it. */
  measurable: boolean;
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
  /** The hard filters — CGPA, backlogs, batch, bond. Never interview topics. */
  eligibility: EligibilityCriteria;
  /** skill label -> concept_id. Only labels that resolved to something. */
  resolved_concepts: Record<string, string>;
  concept_source: Record<string, ConceptSource>;
  /** Found in the JD, mapped to no concept. Kept, never dropped. */
  unresolved_skills: string[];
  scanned_against: ScannedAgainst;
  created_at: string;
}

/**
 * The five gap states.
 *
 * `not_measured` is M02's spec word (§6.5) for what the platform's MasteryBar
 * calls `not_tested`. Same fact, two vocabularies, and the mapping lives in
 * one place — `CoverageRow` — rather than being re-derived per screen.
 */
export type GapState =
  "strong" | "adequate" | "weak" | "not_measured" | "unmeasurable";

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
