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
          <Panel className="px-4 py-3">
            <div className="flex flex-wrap gap-1.5">
              {data.required_skills.map((skill) => (
                <Pill
                  key={skill}
                  tone={data.concept_source[skill] === "m04" ? "confirmed" : "reported"}
                  title={
                    data.resolved_concepts[skill]
                      ? `${data.resolved_concepts[skill]} · ${
                          data.concept_source[skill] === "m04"
                            ? "resolved by M04"
                            : "guessed offline, unconfirmed"
                        }`
                      : "no concept id"
                  }
                >
                  {skill}
                </Pill>
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
              any-of group. The backend returns none of that &mdash; no{" "}
              <code className="provenance">necessity</code>,{" "}
              <code className="provenance">weight</code>,{" "}
              <code className="provenance">span</code> or group &mdash; so ordering them here would
              be an ordering this module invented.
            </p>
            <p>
              Eligibility (CGPA cutoff, backlogs, bond) is also not extracted, so the banner §2.3
              puts at the top of this screen is absent. That one has a real cost: students waste
              weeks preparing for drives they are not eligible to sit.
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
