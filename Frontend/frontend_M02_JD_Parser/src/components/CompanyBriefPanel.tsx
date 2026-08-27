/**
 * What this company actually does at a drive (FR-2.13).
 *
 * Every other panel on this page reads the posting. This one reads the people
 * who sat the interview.
 *
 * ── What a student is actually looking for here ─────────────────────────────
 *
 * Not "Cognizant is an IT services company". They know. Three things they
 * cannot get from the PDF in front of them:
 *
 *   1. Is the number real? The posting advertises a package; the reports say
 *      what was offered. A 6.5 LPA headline against 4.2 reported is the single
 *      most useful line on this page and it takes one row to say.
 *   2. Is there a bond? Postings leave it out constantly. The reports do not.
 *   3. What do they ask? Not a syllabus — the topics that keep coming up.
 *
 * So the panel leads with the disagreements, then the silences, and puts the
 * topic distribution last. That is the reverse of how the data arrives and the
 * order somebody reads it in.
 *
 * ── Rule 2 ──────────────────────────────────────────────────────────────────
 *
 * M15 down and M15 not knowing the company are both `null` from the endpoint
 * and both ordinary. `/deps` already tells them apart on this page, so the
 * empty state here says which of the two it is instead of rendering a shrug.
 */

import { useCompanyBrief, useDeps } from "../api";
import type { CompanyBrief, DriveFact } from "../types";
import { Panel, Section } from "../ui/primitives";

/** The reports and the posting disagree. Read first, because it is the row
 *  that changes a decision. */
function Disagreement({ fact }: { fact: DriveFact }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 py-2.5">
      <span className="text-sm text-ink">
        The posting says <strong className="font-medium">{fact.stated}</strong>
      </span>
      <span className="flex shrink-0 items-center gap-2">
        <span className="text-sm text-ink">{fact.observed}</span>
        <span className="provenance">reported by students</span>
      </span>
    </div>
  );
}

/** The posting is silent and the reports are not. */
function Addition({ fact }: { fact: DriveFact }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 py-2">
      <span className="text-sm text-ink-soft">
        {fact.field === "bond"
          ? "The posting does not mention a bond"
          : `The posting does not state the ${fact.field}`}
      </span>
      <span className="flex shrink-0 items-center gap-2">
        <span className="text-sm text-ink">{fact.observed}</span>
        <span className="provenance">reported</span>
      </span>
    </div>
  );
}

function TopicBars({ brief }: { brief: CompanyBrief }) {
  const topics = Object.entries(brief.observed_topics)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8);
  if (topics.length === 0) return null;

  // Scaled against the largest so the shortest bar is still visible. The
  // NUMBER is the share of reported questions; the bar is only its shape, and
  // labelling both would say the same thing twice.
  const top = topics[0][1] || 1;

  return (
    <Section
      label={
        brief.topics_scope === "drive"
          ? "What this drive asks about"
          : "What this company asks about"
      }
      meta={`from ${brief.report_count} report${brief.report_count === 1 ? "" : "s"}`}
    >
      <Panel className="px-4 py-3">
        <div className="space-y-2">
          {topics.map(([topic, share]) => (
            <div key={topic} className="flex items-center gap-3">
              <span className="w-40 shrink-0 truncate text-sm text-ink">
                {topic}
              </span>
              <span className="h-1.5 min-w-0 flex-1 rounded-full bg-line">
                <span
                  className="block h-full rounded-full bg-brand"
                  style={{ width: `${Math.max(6, (share / top) * 100)}%` }}
                />
              </span>
              <span className="provenance w-10 shrink-0 text-right">
                {Math.round(share * 100)}%
              </span>
            </div>
          ))}
        </div>
        <p className="mt-3 text-xs text-ink-faint">
          The share of reported topics, weighted by how many students
          independently agreed. A topic missing here is one no report mentioned
          &mdash; not one they do not ask about.
          {brief.topics_scope === "company" && brief.drive_variant_name ? (
            <>
              {" "}
              These are reports from across the company rather than from{" "}
              {brief.drive_variant_name} specifically &mdash; nobody who
              reported named which drive they sat.
            </>
          ) : null}
        </p>
      </Panel>
    </Section>
  );
}

export function CompanyBriefPanel({
  jdId,
  candidateId,
}: {
  jdId: string | undefined;
  candidateId: string | undefined;
}) {
  const brief = useCompanyBrief(jdId, candidateId);
  const deps = useDeps();

  // Loading is silent. This panel is an enrichment: a skeleton would claim the
  // page is incomplete without it, and the page is complete without it.
  if (brief.isLoading || brief.isError) return null;

  const data = brief.data;

  if (!data) {
    const m15 = deps.data?.find((d) => d.module_id === "M15");
    if (m15 && !m15.available) {
      return (
        <Section label="This company at a drive">
          <Panel className="px-4 py-3">
            <p className="text-sm text-ink-soft">{m15.on_missing}</p>
          </Panel>
        </Section>
      );
    }
    // M15 is up and does not know this company. Not an outage and not worth a
    // panel — the page says everything it can already.
    return null;
  }

  const differs = data.facts.filter((f) => f.relation === "differs");
  const absent = data.facts.filter((f) => f.relation === "absent");

  return (
    <Section
      label="This company at a drive"
      meta={
        data.report_count > 0
          ? `${data.report_count} report${data.report_count === 1 ? "" : "s"}`
          : "no reports yet"
      }
    >
      <Panel className="px-4 py-3">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <span className="text-sm text-ink">
            {data.company_name}
            {data.drive_variant_name ? (
              <span className="text-ink-soft">
                {" "}
                &middot; {data.drive_variant_name}
              </span>
            ) : null}
          </span>
          {data.aliases.length > 0 && (
            <span className="provenance">
              also written {data.aliases.slice(0, 3).join(", ")}
            </span>
          )}
        </div>
        {data.variant_reason && (
          <p className="mt-1 text-xs text-ink-faint">{data.variant_reason}</p>
        )}

        {data.report_count === 0 && (
          <p className="mt-2 text-sm text-ink-soft">
            Nobody has reported sitting this drive yet, so there is nothing to
            check the posting against. If you sit it, the next student reading
            this page gets what you did not.
          </p>
        )}
      </Panel>

      {differs.length > 0 && (
        <Panel className="mt-3 px-4 py-1">
          <div className="divide-y divide-line">
            {differs.map((fact) => (
              <Disagreement key={fact.field} fact={fact} />
            ))}
          </div>
        </Panel>
      )}

      {absent.length > 0 && (
        <Panel className="mt-3 px-4 py-1">
          <div className="divide-y divide-line">
            {absent.map((fact) => (
              <Addition key={fact.field} fact={fact} />
            ))}
          </div>
        </Panel>
      )}

      <TopicBars brief={data} />

      {Object.keys(data.evidence_boost).length > 0 && (
        <p className="mt-3 text-xs text-ink-faint">
          Your question plan below is weighted slightly toward the topics this
          drive is reported to ask about. Slightly on purpose &mdash; what the
          company wrote in the posting still decides the order, and{" "}
          {data.report_count} report{data.report_count === 1 ? "" : "s"} is a
          sample, not a syllabus.
        </p>
      )}
    </Section>
  );
}
