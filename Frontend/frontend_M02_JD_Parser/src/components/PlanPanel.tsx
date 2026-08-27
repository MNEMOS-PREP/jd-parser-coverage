/**
 * The coverage plan: what the interview should actually spend its time on.
 *
 * Spec: plan_in_depth/M02_JD_Parser.md §6.5 (FR-2.8)
 *
 * This is the screen for the thing the module is named after. §1: *"an
 * allocation of interview question budget across requirements. The Mock
 * Interview Engine consumes that plan directly."*
 *
 * The bar per row is deliberately not a mastery bar. `CoveragePanel` above it
 * shows where the student stands; this shows where their TIME goes, and the two
 * are different numbers that would be confused instantly if they shared a
 * visual language. A requirement can be strong and still earn questions,
 * because the posting leans on it.
 */

import { useState } from "react";

import { usePlan } from "../api";
import {
  Empty,
  ErrorNote,
  Panel,
  Pill,
  Section,
  SkeletonRows,
} from "../ui/primitives";

/** Session lengths a student actually picks. §2.3: they budget in evenings. */
const LENGTHS = [20, 30, 45, 60, 90];

export function PlanPanel({
  jdId,
  candidateId,
}: {
  jdId: string | undefined;
  candidateId: string | undefined;
}) {
  const [minutes, setMinutes] = useState(45);
  const plan = usePlan(jdId, candidateId, minutes);

  return (
    <Section
      label="If you had this long"
      meta={
        plan.data
          ? `${plan.data.allocations.reduce((n, a) => n + a.question_budget, 0)} questions · ${plan.data.allocated_minutes} min used`
          : undefined
      }
    >
      {/* The control comes first because it is the input, and because a plan
          that cannot be re-asked at a different length is a template. */}
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className="rule-label">Session</span>
        {LENGTHS.map((length) => (
          <button
            key={length}
            type="button"
            onClick={() => setMinutes(length)}
            className={
              length === minutes
                ? "rounded-md border border-brand bg-brand/10 px-2.5 py-1 text-xs font-medium text-brand"
                : "rounded-md border border-line px-2.5 py-1 text-xs text-ink-soft hover:border-ink-faint hover:text-ink"
            }
          >
            {length} min
          </button>
        ))}
      </div>

      {plan.isLoading && <SkeletonRows rows={4} />}
      {plan.isError && (
        <ErrorNote>
          Could not build a plan.{" "}
          {plan.error instanceof Error ? plan.error.message : ""}
        </ErrorNote>
      )}

      {plan.data && plan.data.allocations.length === 0 && (
        <Empty title="Nothing to allocate">
          Every requirement on this posting is either unmeasurable or already
          met by an alternative, so there is no question budget to spend. That
          is a statement about the parse, not about the student.
        </Empty>
      )}

      {plan.data && plan.data.allocations.length > 0 && (
        <Panel className="px-4 py-1">
          <div className="divide-y divide-line">
            {plan.data.allocations.map((allocation) => (
              <div key={allocation.requirement_id} className="py-2.5">
                <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                  <span className="min-w-0 text-sm text-ink">
                    {allocation.requirement_text}
                  </span>
                  <span className="flex shrink-0 items-center gap-2">
                    {/* One pip per question. A count this small is read faster
                        as marks than as a numeral, and it makes the shape of
                        the allocation visible down the column. */}
                    <span className="flex gap-0.5" aria-hidden>
                      {Array.from({ length: allocation.question_budget }).map(
                        (_, index) => (
                          <span
                            key={index}
                            className="h-2.5 w-2.5 rounded-sm bg-brand"
                          />
                        ),
                      )}
                    </span>
                    <span className="provenance">
                      {allocation.question_budget} Q · {allocation.minutes} min
                    </span>
                  </span>
                </div>
                <p className="mt-0.5 text-xs text-ink-faint">
                  {allocation.rationale}
                </p>
              </div>
            ))}
          </div>
        </Panel>
      )}

      {/* EC-2.11: the omission AND the suggestion. A plan that silently drops a
          must-have is worse than one that says the session is too short. */}
      {plan.data?.suggestion && (
        <div
          className={
            plan.data.uncovered.length > 0
              ? "mt-3 rounded-md border border-contested-line bg-contested-soft px-3 py-2"
              : "mt-3 rounded-md border border-line bg-surface-sunken px-3 py-2"
          }
        >
          <p
            className={
              plan.data.uncovered.length > 0
                ? "text-sm text-contested"
                : "text-sm text-ink-soft"
            }
          >
            {plan.data.suggestion}
          </p>
          {plan.data.uncovered.length > 0 && (
            <p className="mt-1 text-xs text-ink-soft">
              Not fitted in: {plan.data.uncovered.join(", ")}
            </p>
          )}
        </div>
      )}

      {plan.data && plan.data.unmeasurable.length > 0 && (
        <p className="mt-2.5 text-xs text-ink-soft">
          {plan.data.unmeasurable.length} requirement
          {plan.data.unmeasurable.length === 1 ? "" : "s"} got no questions
          because nothing in the ontology can test{" "}
          {plan.data.unmeasurable.length === 1 ? "it" : "them"}. They are not
          uncovered &mdash; they are untestable, which is a different problem
          and has a different fix.
        </p>
      )}

      <details className="mt-3 text-sm">
        <summary className="cursor-pointer text-xs text-ink-faint hover:text-ink-soft">
          How this was decided
        </summary>
        <div className="mt-2 space-y-1.5 border-l-2 border-line pl-3 text-xs text-ink-soft">
          <p>
            Each requirement gets a priority of{" "}
            <code className="provenance">weight × (1 − mastery)</code>. Every
            measurable must-have is guaranteed one question before anything gets
            a second (FR-2.9), and the rest of the time goes wherever the next
            question is worth most &mdash; where value grows as{" "}
            <code className="provenance">log(1 + questions)</code>, so the
            fourth question on a topic is worth much less than the first.
            Without that, the whole session collapses onto the single worst gap.
          </p>
          <p>
            Every question is costed at 3.5 minutes, because nothing yet says
            which requirements need a coding or design round &mdash; that is{" "}
            <code className="provenance">measured_by</code>, still unbuilt. So
            the priorities here are real and the <em>shape</em> of the session
            is not: treat the minutes as a rough floor.
          </p>
          <Pill tone="neutral">
            {plan.data?.plan_version ?? "greedy-log-v1"}
          </Pill>
        </div>
      </details>
    </Section>
  );
}
