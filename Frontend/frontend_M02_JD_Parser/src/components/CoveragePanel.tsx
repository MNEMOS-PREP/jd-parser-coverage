/**
 * The gap: one row per requirement, and an honest headline.
 *
 * Spec: plan_in_depth/M02_JD_Parser.md §2.3 (Screen 2), §6.5, §8, EC-2.8
 *
 * ── The one thing this file exists to get right ──────────────────────────────
 *
 * **"Not measured" must not look like a bad score.** §8 states it as a visual
 * rule and calls it a fairness property: weak is a filled amber bar, not
 * measured is a dashed grey outline carrying the literal words. A student with
 * no session history has EVERY requirement unmeasured, so if the two ever
 * collapse into one treatment, the first screen that student sees reads as a
 * wall of failures — and it is the most common first-run state there is.
 *
 * So the bars are `MasteryBar` from `@ai/core`, not a local component. That is
 * the platform's single definition of the distinction, it enforces "a
 * non-displayable state can never render a number", and a nineteenth copy is
 * how the promise stops being true in whichever repo falls behind.
 *
 * The headline follows the same rule one level up. `coverage_score` is `null`
 * whenever nothing could be checked, and null renders as a sentence about what
 * is missing — never as 0%.
 */

import { DependencyAlert, MasteryBar } from "@ai/core";
import type { MasteryState, MasteryValue } from "@ai/core";

import type { Coverage, GapState } from "../types";
import { Panel, Pill, Section } from "../ui/primitives";
import { ConceptSourceChip } from "./ConceptSourceChip";

/**
 * M02's spec word (§6.5) to the platform's (M04 §5.3). Same fact, two
 * vocabularies — settled here, once, rather than per screen. `unmeasurable`
 * has no counterpart: it is outside the scale, not a point on it, so it never
 * reaches `MasteryBar`.
 */
const TO_MASTERY_STATE: Record<
  Exclude<GapState, "unmeasurable" | "met_by_alternative">,
  MasteryState
> = {
  strong: "strong",
  adequate: "adequate",
  weak: "weak",
  not_measured: "not_tested",
};

function CoverageRow({
  label,
  coverage,
}: {
  label: string;
  coverage: Coverage;
}) {
  const state = coverage.states[label];
  const conceptId = coverage.resolved_concepts[label];

  /* A requirement nothing can score. Hatched, colourless, no bar at all — it
     is not at the bottom of the scale, it is off it. Spec EC-2.8. */
  /* One answer to a question that accepted several. No bar: the student is
     not at some point on this scale, the requirement is simply already met. */
  if (state === "met_by_alternative") {
    const by = coverage.met_by_alternative[label];
    return (
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1.5 py-2.5">
        <div className="flex min-w-0 items-center gap-2">
          <span
            className="inline-block h-2.5 w-10 shrink-0 rounded-sm bg-line"
            aria-hidden
          />
          <span className="truncate text-sm text-ink-soft">{label}</span>
        </div>
        <span className="text-xs text-ink-faint">
          not needed &mdash; the posting accepted {by}
        </span>
      </div>
    );
  }

  if (state === "unmeasurable") {
    return (
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1.5 py-2.5">
        <div className="flex min-w-0 items-center gap-2">
          <span
            className="untestable-mark inline-block h-2.5 w-10 shrink-0"
            aria-hidden
          />
          <span className="truncate text-sm text-ink">{label}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-ink-faint">
            can&rsquo;t be tested here
          </span>
          <Pill
            tone="neutral"
            title="This requirement maps to no concept in the ontology, so no question can probe it and no score can be earned against it."
          >
            unmapped
          </Pill>
        </div>
      </div>
    );
  }

  const value: MasteryValue = {
    concept_id: conceptId ?? label,
    name: label,
    state: TO_MASTERY_STATE[state],
    // Passed straight through. The backend already sends null for anything M04
    // would not claim, and MasteryBar ignores it for a non-displayable state
    // anyway — two independent guards on the same lie.
    mastery_p: coverage.mastery[label] ?? null,
    // No n_direct: M02 reads a coverage summary, not M04's evidence ledger.
    // Since v0.6.0 the field is optional and the "tested N×" suffix is omitted
    // rather than fabricated.
  };

  return (
    <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1.5 py-2.5">
      <div className="flex min-w-0 items-center gap-2">
        <span className="truncate text-sm text-ink">{label}</span>
        <ConceptSourceChip
          source={coverage.concept_source[label]}
          conceptId={conceptId}
        />
      </div>
      <div className="flex items-center gap-3">
        <MasteryBar value={value} width="w-32" />
      </div>
    </div>
  );
}

/**
 * The headline.
 *
 * Three genuinely different situations, three different sentences. Collapsing
 * any pair of them into a percentage is how this screen starts lying:
 *
 *   nobody asked        M04 is down. We know nothing about the student.
 *   asked, no answer    M04 is up and holds no measurement for these concepts.
 *   measured            a real fraction, over what could actually be checked.
 */
function Headline({ coverage }: { coverage: Coverage }) {
  const {
    coverage_score,
    measured_against,
    measured_count,
    requirement_count,
  } = coverage;

  if (coverage_score === null) {
    const reason =
      measured_against === null
        ? "M04 Skill Graph isn't running, so nothing has been compared yet."
        : "M04 is running, but it holds no measurement for any of these topics yet.";
    return (
      <div className="rounded-panel border border-dashed border-line-strong px-4 py-3.5">
        <p className="text-sm font-medium text-ink">Not measured yet</p>
        <p className="mt-1 max-w-xl text-sm text-ink-soft">
          {reason} The {requirement_count} requirement
          {requirement_count === 1 ? "" : "s"} below came out of the job
          description and are correct; what is missing is where <em>you</em>{" "}
          stand against them.
        </p>
        <p className="mt-1.5 text-xs text-ink-faint">
          This is not a score of zero. A first session maps your baseline and
          every row below fills in.
        </p>
      </div>
    );
  }

  const pct = Math.round(coverage_score * 100);
  const unmeasured = requirement_count - measured_count;
  return (
    <div className="rounded-panel border border-line bg-surface px-4 py-3.5">
      <p className="text-title font-semibold text-ink" data-numeric>
        {pct}%
        <span className="ml-2 align-middle text-sm font-normal text-ink-soft">
          of what could be checked
        </span>
      </p>
      <p className="mt-1 max-w-xl text-sm text-ink-soft">
        Measured against {measured_count} of {requirement_count} requirement
        {requirement_count === 1 ? "" : "s"}.
        {unmeasured > 0 && (
          <>
            {" "}
            The other {unmeasured} {unmeasured === 1 ? "is" : "are"} not
            measured and{" "}
            <strong className="font-medium text-ink">
              not counted against you
            </strong>{" "}
            &mdash; they are topics to probe, not gaps.
          </>
        )}
      </p>
    </div>
  );
}

export function CoveragePanel({ coverage }: { coverage: Coverage }) {
  /* Order: what needs work first, then what is unmeasured, then what is fine,
     then what cannot be tested. A student reads this to decide what to study,
     so the actionable rows are at the top and the reference rows at the
     bottom. */
  const ordered = [
    ...coverage.weak,
    ...coverage.not_measured,
    ...coverage.covered,
    ...coverage.unmeasurable,
    /* Alternatives another answer already met. They belong at the bottom
       because they need no work — but they belong ON the page, because the
       backend removes them from every gap bucket and a requirement that
       simply stops appearing is indistinguishable from one we forgot. */
    ...Object.keys(coverage.met_by_alternative),
  ];

  return (
    <>
      {/* Renders nothing when nothing is degraded, so it is always safe to
          include - and when M04 is down it names it. */}
      <div className="mb-6 empty:mb-0">
        <DependencyAlert degraded={coverage.degraded} />
      </div>

      <Section
        label="Where you stand"
        meta={
          coverage.measured_against
            ? `measured against ${coverage.measured_against}`
            : "not measured"
        }
      >
        <Headline coverage={coverage} />

        <Panel className="mt-4 px-4 py-1">
          <div className="divide-y divide-line">
            {ordered.map((label) => (
              <CoverageRow key={label} label={label} coverage={coverage} />
            ))}
          </div>
        </Panel>

        {coverage.unmeasurable.length > 0 && (
          <p className="mt-2.5 text-xs text-ink-soft">
            {coverage.unmeasurable.length} requirement
            {coverage.unmeasurable.length === 1 ? "" : "s"} map to no concept in
            the ontology, so no question can probe{" "}
            {coverage.unmeasurable.length === 1 ? "it" : "them"}. They are
            listed rather than dropped, because a requirement we cannot test is
            still one the job asks for.
          </p>
        )}
      </Section>
    </>
  );
}
