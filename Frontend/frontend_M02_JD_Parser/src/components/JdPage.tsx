/**
 * The requirement read-back, and the gap.
 *
 * Spec: plan_in_depth/M02_JD_Parser.md §2.3 (Screen 2)
 *
 * The spec's Screen 2 groups requirements into MUST / SHOULD, weights them,
 * resolves disjunctions, banners the eligibility criteria, highlights ONE gap
 * with a time-to-close estimate, and offers an edit control.
 *
 * Grouping and weighting are real now — the backend reads necessity from the
 * posting's own modal language, so §3.2.1's trap ("Good knowledge of DSA" and
 * "Bonus: familiarity with Docker" are not equal) is no longer flattened here.
 * Disjunctive any-of groups are still missing, and this screen says so rather
 * than letting three alternatives read as three separate demands.
 *
 * What it still does not do is pick a "biggest gap" out of severities that are
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
import {
  Empty,
  ErrorNote,
  Panel,
  Pill,
  Section,
  SkeletonRows,
} from "../ui/primitives";
import type { EligibilityCriteria, Necessity, Requirement } from "../types";

export function JdPage() {
  const { jdId } = useParams<{ jdId: string }>();
  const candidateId = useCandidateId();
  const jd = useJd(jdId);
  const coverage = useCoverage(jdId, candidateId);

  if (jd.isLoading) return <SkeletonRows rows={6} />;

  if (jd.isError || !jd.data) {
    return (
      <Empty title="No such job description">
        The id in the URL does not match a stored JD. Paste one and it gets a
        fresh id.
        <div className="mt-3">
          <Link
            to="/"
            className="text-sm font-medium text-brand hover:text-brand-hover"
          >
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
        <h1 className="mt-0.5 text-display font-semibold text-ink">
          {data.role_title}
        </h1>
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
            Nothing in this text matched a concept we know about. With M04 down
            the scan only looks for five concepts, so this is more likely an
            outage than an empty JD &mdash; check{" "}
            <Link
              to="/deps"
              className="font-medium text-brand hover:text-brand-hover"
            >
              dependencies
            </Link>
            .
          </Empty>
        ) : (
          <div className="space-y-4">
            {NECESSITY_ORDER.map((necessity) => {
              const group = data.requirements.filter(
                (r) => r.necessity === necessity,
              );
              if (group.length === 0) return null;
              return (
                <NecessityGroup
                  key={necessity}
                  necessity={necessity}
                  requirements={group}
                  rawText={data.raw_text}
                />
              );
            })}
          </div>
        )}

        {/* The spec's §5 structure, and why none of it is on screen. Kept
            visible rather than in a backlog: a reader of this screen should
            not have to guess whether "flat list" is the design or the state. */}
        <details className="mt-3 text-sm">
          <summary className="cursor-pointer text-xs text-ink-faint hover:text-ink-soft">
            What is still missing here
          </summary>
          <div className="mt-2 space-y-1.5 border-l-2 border-line pl-3 text-xs text-ink-soft">
            <p>
              <code className="provenance">necessity</code> and{" "}
              <code className="provenance">weight</code> are read from the
              posting now &mdash; from its modal language (&ldquo;strong&rdquo;,
              &ldquo;a plus&rdquo;) and the heading each line sits under &mdash;
              so the groups above are the JD&rsquo;s ordering and not one this
              module invented. Where the posting says nothing, the requirement
              is a <strong>should</strong>: that means unstated, not optional.
            </p>
            <p>
              Still missing: any-of groups. A posting asking for
              &ldquo;Java/Python/C++&rdquo; is making <em>one</em> requirement
              with three acceptable answers, and it currently reads as three, so
              a student who knows only Python looks a third qualified instead of
              fully. Also absent are <code className="provenance">kind</code>,{" "}
              <code className="provenance">measured_by</code> and{" "}
              <code className="provenance">seniority_signal</code>.
            </p>
            <p>
              Eligibility (CGPA cutoff, backlogs, batch, bond) IS extracted now
              and shows above. What is still missing there is the comparison
              &mdash; FR-2.15&rsquo;s &ldquo;you have 7.2, cutoff is 7.5&rdquo;
              needs the student&rsquo;s own CGPA, which lives in M01, so the
              banner states the bar rather than whether you clear it.
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
          The posting exactly as it was pasted. Every requirement above quotes
          its own line out of this text, so anything the parser claims can be
          checked against what the company actually wrote &mdash; including what
          it left out.
        </p>
      </Section>
    </>
  );
}

/**
 * Strongest first. A student reading top-down reads the things that will
 * actually get asked before the things that might.
 */
const NECESSITY_ORDER: Necessity[] = ["must", "should", "could"];

/**
 * What each level means in the student's terms, not the spec's.
 *
 * `should` is the one worth being careful about: it is the DEFAULT, assigned
 * when the posting used no modal language at all. Labelling it "optional" would
 * turn silence into permission to skip — so it says the posting did not say.
 */
const NECESSITY_COPY: Record<Necessity, { title: string; note: string }> = {
  must: {
    title: "Must have",
    note: "Stated as required, or listed under a requirements heading.",
  },
  should: {
    title: "Asked for",
    note: "Named without a qualifier. The posting did not say how firm this is.",
  },
  could: {
    title: "Nice to have",
    note: "Explicitly a bonus, a plus, or under a nice-to-have heading.",
  },
};

/**
 * One necessity band, with its requirements under it.
 *
 * The band header carries its share of the total weight, which is the number
 * that matters downstream: FR-2.8 allocates the interview's question budget
 * across these, so "nice-to-have is 6% of this posting" is the difference
 * between one throwaway question about Kubernetes and four.
 */
function NecessityGroup({
  necessity,
  requirements,
  rawText,
}: {
  necessity: Necessity;
  requirements: Requirement[];
  rawText: string;
}) {
  const copy = NECESSITY_COPY[necessity];
  const share = requirements.reduce((sum, r) => sum + r.weight, 0);

  return (
    <div>
      {/* The separator IS the group label — a rule with the name sitting in it,
          so the stack reads as bands rather than as one list with headings. */}
      <div className="flex items-center gap-3">
        <span className="rule-label shrink-0">{copy.title}</span>
        <span className="h-px flex-1 bg-line" />
        <span
          className="provenance shrink-0"
          title="Share of this posting's total weight — what fraction of the interview these should earn"
        >
          {Math.round(share * 100)}% of the ask
        </span>
      </div>
      <p className="mt-1 text-xs text-ink-faint">{copy.note}</p>

      <Panel className="mt-2 px-4 py-1">
        {/* One row per requirement, each quoting the words it came from.
            The span is the reason this is a list rather than a row of chips:
            "we found Python" is a claim about the posting, and a student can
            only check it against the line it was read from. */}
        <div className="divide-y divide-line">
          {requirements.map((requirement) => (
            <div
              key={requirement.id}
              className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 py-2"
            >
              <span className="min-w-0">
                <span className="text-sm text-ink">{requirement.text}</span>
                {requirement.mentions > 1 && (
                  <span
                    className="provenance ml-2"
                    title="Repetition is emphasis — a posting that says it three times means it"
                  >
                    &times;{requirement.mentions}
                  </span>
                )}
                {requirement.span && (
                  <span className="provenance ml-2 break-words">
                    &ldquo;{quote(rawText, requirement.span)}&rdquo;
                  </span>
                )}
              </span>
              <Pill
                tone={
                  requirement.concept_source === "m04"
                    ? "confirmed"
                    : "reported"
                }
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
    </div>
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
function EligibilityBanner({
  eligibility,
}: {
  eligibility: EligibilityCriteria;
}) {
  // `stated` rather than checking the fields: "the posting says nothing about
  // eligibility" and "we found nothing" look identical from the values alone,
  // and only one of them means we looked.
  if (!eligibility?.stated) return null;

  const bars: string[] = [];
  if (eligibility.min_cgpa !== null)
    bars.push(`CGPA ${eligibility.min_cgpa} or above`);
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
    <div
      className="mb-7 rounded-md border border-reported-line bg-reported-soft px-4 py-3"
      role="note"
    >
      <p className="text-sm font-medium text-reported">
        Who can sit this drive
      </p>
      <p className="mt-1 text-sm text-ink">{bars.join(" · ")}</p>
      <p className="mt-2 text-xs text-ink-soft">
        Read off the posting, not checked against you &mdash; your CGPA is not
        something this screen holds. Check these before you spend a fortnight
        preparing.
      </p>
      {eligibility.raw_spans.length > 0 && (
        <p className="provenance mt-1.5 break-words">
          {eligibility.raw_spans.map((span) => `“${span.text}”`).join(" · ")}
        </p>
      )}
    </div>
  );
}
