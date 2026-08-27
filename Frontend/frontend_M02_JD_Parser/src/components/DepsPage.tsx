/**
 * Which upstreams are up, and what is switched off without them.
 *
 * `DependencyTable` comes from `@ai/core` so every module answers "why is this
 * page thin?" the same way. The rows are what `GET /v1/deps` returns, which is
 * what `module.json` declares — so a dependency missing a `base_url` shows up
 * here as "no base_url configured" rather than as an upstream that mysteriously
 * never gets called. That was this repo's first bug and this page is where it
 * would now be visible in one request.
 */

import { DependencyTable } from "@ai/core";

import { useDeps, useHealth, useModuleStatus, usePerformance } from "../api";
import {
  Field,
  Panel,
  Pill,
  Rows,
  Section,
  SkeletonRows,
} from "../ui/primitives";

export function DepsPage() {
  const deps = useDeps();
  const perf = usePerformance();
  const health = useHealth();
  const status = useModuleStatus();

  if (deps.isLoading) return <SkeletonRows rows={4} />;

  const m04 = deps.data?.find((d) => d.module_id === "M04");

  return (
    <>
      <header className="mb-8">
        <h1 className="text-title font-semibold text-ink">Dependencies</h1>
        <p className="mt-1 max-w-2xl text-sm text-ink-soft">
          M02 starts and runs with none of these present. What changes is the
          scope of what it can say &mdash; never the quality of what it does
          say, and never silently.
        </p>
      </header>

      <Section label="This module">
        <Panel className="px-4 py-3">
          <Rows>
            <Field label="status">{health.data?.status ?? "unreachable"}</Field>
            {/* From the platform registry rather than from this module's own
                opinion of itself - the two disagreeing is worth seeing. */}
            <Field label="registry">
              {status.data
                ? `${status.data.id} · phase ${status.data.phase} · ${status.data.detail}`
                : "unreachable"}
            </Field>
            <Field label="spec">{status.data?.spec ?? "—"}</Field>
            <Field label="reserved port">
              {status.data?.reserved_port ?? "—"}
            </Field>
          </Rows>
        </Panel>
      </Section>

      <Section label="Upstream">
        <Panel className="overflow-x-auto px-4 py-3">
          <DependencyTable statuses={deps.data ?? []} />
        </Panel>

        {m04 && !m04.available && (
          <Panel tone="sunken" className="mt-3 px-4 py-3">
            <div className="flex flex-wrap items-center gap-2">
              <Pill tone="reported">running on the offline lexicon</Pill>
              <span className="provenance">{m04.detail}</span>
            </div>
            <p className="mt-2 text-sm text-ink-soft">
              Three things are narrowed while M04 is down, and they fail
              separately:
            </p>
            <ul className="mt-1.5 space-y-1 text-sm text-ink-soft">
              <li>
                <strong className="font-medium text-ink">The scan</strong> looks
                for five concepts instead of the ontology, so most requirements
                in a real JD are not found at all.
              </li>
              <li>
                <strong className="font-medium text-ink">Resolution</strong>{" "}
                falls back to a five-entry table. Those ids are usable and are
                labelled <em>guessed offline</em> everywhere they appear.
              </li>
              <li>
                <strong className="font-medium text-ink">The gap</strong> cannot
                be computed at all. Coverage returns null, not zero.
              </li>
            </ul>
            <p className="mt-2 text-xs text-ink-faint">
              Point at a running instance without editing the manifest:{" "}
              <code className="provenance">
                M04_BASE_URL=http://127.0.0.1:8104
              </code>
            </p>
          </Panel>
        )}
      </Section>

      {/* AC-2.5. §11 budgets a cold parse at 8 s and none of it was ever timed,
          so the number was UNKNOWN — which is worse than missed. A missed
          budget is a bug report; an unknown one is a blank space where
          everybody assumes it is fine.

          Measured over stored rows rather than a benchmark, because a
          benchmark measures the machine it ran on and §11's budget is a claim
          about what a student waits for. */}
      <Section
        label="How long a parse takes"
        meta={
          perf.data?.length
            ? `p95 over ${perf.data[0].samples} parses`
            : undefined
        }
      >
        {perf.data && perf.data.length === 0 && (
          <Panel className="px-4 py-3">
            <p className="text-sm text-ink-soft">
              Nothing parsed yet, so there is no p95. That is different from a
              zero, and it is why this says so rather than showing one.
            </p>
          </Panel>
        )}
        {perf.data && perf.data.length > 0 && (
          <Panel className="px-4 py-1">
            <div className="divide-y divide-line">
              {perf.data.map((stage) => (
                <div
                  key={stage.stage}
                  className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 py-2"
                >
                  <span className="text-sm text-ink">{stage.stage}</span>
                  <span className="flex items-center gap-2">
                    <span
                      className={
                        stage.within_budget
                          ? "text-sm text-confirmed"
                          : "text-sm text-contested"
                      }
                    >
                      {stage.p95_ms} ms
                    </span>
                    <span className="provenance">
                      budget {stage.budget_ms} ms · {stage.samples}{" "}
                      {stage.samples === 1 ? "parse" : "parses"}
                    </span>
                  </span>
                </div>
              ))}
            </div>
          </Panel>
        )}
        <p className="mt-2 text-xs text-ink-faint">
          A p95 over a handful of parses is not a p95. The sample count is shown
          for every row so the number can be read with the weight it has earned.
        </p>
      </Section>
    </>
  );
}
