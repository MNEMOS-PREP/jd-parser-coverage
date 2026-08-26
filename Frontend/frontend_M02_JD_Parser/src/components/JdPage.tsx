/**
 * The requirement read-back, and the gap.
 *
 * Spec: plan_in_depth/M02_JD_Parser.md §2.3 (Screen 2)
 *
 * The spec's Screen 2 groups requirements into MUST / SHOULD, weights them,
 * resolves disjunctions, banners the eligibility criteria, highlights ONE gap
 * with a time-to-close estimate, and offers an edit control. None of that data
 * exists: the backend returns a flat list of matched skill labels, so this
 * screen renders a flat list. What it does not do is invent an ordering and
 * present it as necessity, or pick a "biggest gap" out of severities that are
 * all the same number.
 *
 * What it does carry is the part the spec is most emphatic about, which is also
 * the part that costs nothing to get right: every requirement shows where its
 * concept id came from, and an unmeasured requirement never looks like a bad
 * score. `CoveragePanel` owns that.
 */

import { Link, useParams } from "react-router-dom";

import { useCoverage, useJd } from "../api";
import { useCandidateId } from "./candidate-hook";
import { CoveragePanel } from "./CoveragePanel";
import { ScanSourceNote } from "./ConceptSourceChip";
import { Empty, ErrorNote, Panel, Pill, Section, SkeletonRows } from "../ui/primitives";
import type { EligibilityCriteria } from "../types";

export function JdPage() {
  const { jdId } = useParams<{ jdId: string }>();
  const candidateId = useCandidateId();
  const jd = useJd(jdId);
  const coverage = useCoverage(jdId, candidateId);

  if (jd.isLoading) return <SkeletonRows rows={6} />;

  if (jd.isError || !jd.data) {
    return (
      <Empty title="No such job description">
        The id in the URL does not match a stored JD. Paste one and it gets a fresh id.
        <div className="mt-3">
          <Link to="/" className="text-sm font-medium text-brand hover:text-brand-hover">
            Paste a JD &rarr;
          </Link>
        </div>
      </Empty>
    );
  }

  const data = jd.data;
  const skillCount = data.required_skills.length;

  return (
    <>
      <header className="mb-8">
        <p className="rule-label">{data.company_name}</p>
        <h1 className="mt-0.5 text-display font-semibold text-ink">{data.role_title}</h1>
        <div className="mt-2.5 max-w-2xl">
          <ScanSourceNote scannedAgainst={data.scanned_against} />
        </div>
      </header>

      <EligibilityBanner eligibility={data.eligibility} />

      <Section
        label="What this job asks for"
        meta={`${skillCount} matched · ${data.unresolved_skills.length} unmapped`}
      >
        {skillCount === 0 ? (
          <Empty title="No requirements matched">
            Nothing in this text matched a concept we know about. With M04 down the scan only looks
            for five concepts, so this is more likely an outage than an empty JD &mdash; check{" "}
            <Link to="/deps" className="font-medium text-brand hover:text-brand-hover">
              dependencies
            </Link>
            .
          </Empty>
        ) : (
          <Panel className="px-4 py-1">
            {/* One row per requirement, each quoting the words it came from.
                The span is the reason this is a list rather than a row of
                chips: "we found Python" is a claim about the posting, and a
                student can only check it against the line it was read from. */}
            <div className="divide-y divide-line">
              {data.requirements.map((requirement) => (
                <div
                  key={requirement.id}
                  className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 py-2"
                >
                  <span className="min-w-0">
                    <span className="text-sm text-ink">{requirement.text}</span>
                    {requirement.span && (
                      <span className="provenance ml-2 break-words">
                        &ldquo;{quote(data.raw_text, requirement.span)}&rdquo;
                      </span>
                    )}
                  </span>
                  <Pill
                    tone={requirement.concept_source === "m04" ? "confirmed" : "reported"}
                    title={
                      requirement.concept_ids[0]
                        ? `${requirement.concept_ids[0]} · ${
                            requirement.concept_source === "m04"
                              ? "resolved by M04"
                              : "guessed offline, unconfirmed"
                          }`
                        : "no concept id — nothing downstream can test this"
                    }
                  >
                    {requirement.measurable
                      ? requirement.concept_source === "m04"
                        ? "ontology"
                        : "guessed offline"
                      : "no concept yet"}
                  </Pill>
                </div>
              ))}
            </div>
          </Panel>
        )}

        {/* The spec's §5 structure, and why none of it is on screen. Kept
            visible rather than in a backlog: a reader of this screen should
            not have to guess whether "flat list" is the design or the state. */}
        <details className="mt-3 text-sm">
          <summary className="cursor-pointer text-xs text-ink-faint hover:text-ink-soft">
            Why this is a flat list
          </summary>
          <div className="mt-2 space-y-1.5 border-l-2 border-line pl-3 text-xs text-ink-soft">
            <p>
              The spec groups these by necessity (must / should / could), weights each one by
              emphasis and repetition, and resolves &ldquo;Java/Python/C++&rdquo; into one
              any-of group. The backend now returns a{" "}
              <code className="provenance">span</code> for each one &mdash; which is why every row
              can quote the words it came from &mdash; but still no{" "}
              <code className="provenance">necessity</code>,{" "}
              <code className="provenance">weight</code> or group. Ordering them by importance
              here would be an ordering this module invented, so they are in the order the posting
              writes them.
            </p>
            <p>
              Eligibility (CGPA cutoff, backlogs, batch, bond) IS extracted now and shows above.
              What is still missing there is the comparison &mdash; FR-2.15&rsquo;s &ldquo;you have
              7.2, cutoff is 7.5&rdquo; needs the student&rsquo;s own CGPA, which lives in M01,
              so the banner states the bar rather than whether you clear it.
            </p>
          </div>
        </details>
      </Section>

      {coverage.isLoading && <SkeletonRows rows={4} />}
      {coverage.isError && (
        <ErrorNote>
          Could not load the gap for this candidate.{" "}
          {coverage.error instanceof Error ? coverage.error.message : ""}
        </ErrorNote>
      )}
      {coverage.data && <CoveragePanel coverage={coverage.data} />}

      <Section label="The pasted text">
        <Panel tone="sunken" className="px-4 py-3">
          <pre className="text-source whitespace-pre-wrap break-words font-mono text-ink-soft">
            {data.raw_text}
          </pre>
        </Panel>
        <p className="mt-2 text-xs text-ink-faint">
          Shown verbatim because there are no source spans yet (§6.2): we cannot point at the
          words a requirement came from, so the whole text stands in for the citation.
        </p>
      </Section>
    </>
  );
}

/**
 * The line a requirement was read from, trimmed to something quotable.
 *
 * Widened past the matched word on both sides, because "Python" on its own
 * proves nothing — the whole question a student is checking is whether it
 * appeared in the requirements or in "no Python required".
 */
function quote(text: string, span: { start: number; end: number }): string {
  const from = Math.max(0, text.lastIndexOf("\n", span.start) + 1);
  const to = text.indexOf("\n", span.end);
  const line = text.slice(from, to === -1 ? undefined : to).trim();
  return line.length > 90 ? `${line.slice(0, 90)}…` : line;
}

/**
 * The bar for sitting this drive, at the top of the screen (§2.3, FR-2.4).
 *
 * §2.3 puts this above the requirements for a reason a student feels directly:
 * they waste weeks preparing for drives they are not eligible to sit. The
 * module recognised these lines and threw them away, so the banner could not
 * exist.
 *
 * It states the bar and does NOT say whether the student clears it. FR-2.15's
 * sentence — "you have 7.2, cutoff is 7.5" — needs their CGPA, which is M01's
 * (`entities.education.grade`), and asserting they fall short on a number this
 * module does not hold would be the worst possible thing to be wrong about.
 */
function EligibilityBanner({ eligibility }: { eligibility: EligibilityCriteria }) {
  // `stated` rather than checking the fields: "the posting says nothing about
  // eligibility" and "we found nothing" look identical from the values alone,
  // and only one of them means we looked.
  if (!eligibility?.stated) return null;

  const bars: string[] = [];
  if (eligibility.min_cgpa !== null) bars.push(`CGPA ${eligibility.min_cgpa} or above`);
  if (eligibility.max_backlogs_active !== null) {
    bars.push(
      eligibility.max_backlogs_active === 0
        ? "no active backlogs"
        : `at most ${eligibility.max_backlogs_active} active backlog${
            eligibility.max_backlogs_active === 1 ? "" : "s"
          }`,
    );
  }
  if (eligibility.year_of_passing.length > 0) {
    bars.push(`${eligibility.year_of_passing.join(", ")} batch`);
  }
  if (eligibility.bond_months !== null) {
    bars.push(
      eligibility.bond_months % 12 === 0
        ? `${eligibility.bond_months / 12}-year bond`
        : `${eligibility.bond_months}-month bond`,
    );
  }

  return (
    <div className="mb-7 rounded-md border border-reported-line bg-reported-soft px-4 py-3" role="note">
      <p className="text-sm font-medium text-reported">Who can sit this drive</p>
      <p className="mt-1 text-sm text-ink">{bars.join(" · ")}</p>
      <p className="mt-2 text-xs text-ink-soft">
        Read off the posting, not checked against you &mdash; your CGPA is not something this
        screen holds. Check these before you spend a fortnight preparing.
      </p>
      {eligibility.raw_spans.length > 0 && (
        <p className="provenance mt-1.5 break-words">
          {eligibility.raw_spans.map((span) => `“${span.text}”`).join(" · ")}
        </p>
      )}
    </div>
  );
}
