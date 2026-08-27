/**
 * The analysis: your resume against this posting.
 *
 * Spec: plan_in_depth/M02_JD_Parser.md FR-2.15, §3.2.2
 *
 * Ordered by what actually stops you. Eligibility first and alone, because
 * §3.2.2 makes it a hard filter rather than an interview topic: no amount of
 * preparation gets you into a drive whose CGPA bar you miss, and a page that
 * listed "you miss the cutoff" as the seventh bullet under six skill gaps would
 * have thrown that separation away at the last possible step.
 *
 * Then risk, then evidence. A student reading this is deciding two things —
 * whether to apply at all, and what to fix first — and they are different
 * decisions that want different halves of the page.
 *
 * ── What this screen refuses to say ─────────────────────────────────────────
 *
 * It does not convert between grade scales. A resume saying "82%" against a
 * "7.5 CGPA" cutoff gets `scale_mismatch` and a sentence telling the student to
 * check that one themselves, because the conversion factor differs per
 * university and being wrong here tells somebody the opposite of the truth
 * about a drive they can or cannot sit.
 */

import { Link, useParams } from "react-router-dom";

import { useJd, useMatch } from "../api";
import { useCandidateId } from "./candidate-hook";
import {
  Empty,
  ErrorNote,
  Panel,
  Pill,
  Section,
  SkeletonRows,
} from "../ui/primitives";
import type { Risk, Verdict } from "../types";

/** Copy per verdict state. Written once so no screen re-phrases a cutoff. */
const VERDICT_TONE: Record<
  Verdict["state"],
  { label: string; className: string }
> = {
  meets: { label: "you clear this", className: "text-confirmed" },
  fails: { label: "you do not clear this", className: "text-contested" },
  unknown: { label: "we could not check", className: "text-ink-faint" },
  scale_mismatch: { label: "check this yourself", className: "text-ink-faint" },
};

const RISK_TONE: Record<Risk["severity"], string> = {
  blocking: "border-contested-line bg-contested-soft",
  high: "border-line-strong bg-surface-sunken",
  medium: "border-line bg-surface-sunken",
  low: "border-line bg-surface",
};

const RISK_LABEL: Record<Risk["severity"], string> = {
  blocking: "blocks you",
  high: "costs you the screen",
  medium: "worth fixing",
  low: "worth knowing",
};

export function MatchPage() {
  const { jdId } = useParams<{ jdId: string }>();
  const candidateId = useCandidateId();
  const jd = useJd(jdId);
  const match = useMatch(jdId, candidateId);

  if (jd.isLoading || match.isLoading) return <SkeletonRows rows={6} />;

  if (match.isError || !match.data || !jd.data) {
    return (
      <ErrorNote>
        Could not build the analysis.{" "}
        {match.error instanceof Error ? match.error.message : ""}
      </ErrorNote>
    );
  }

  const report = match.data;

  if (report.resume_status !== "ok") {
    return (
      <Empty title="Nothing to compare against">
        {report.resume_status === "no_resume"
          ? "There is no resume on file for you yet, so there is nothing to hold this posting up against."
          : "The resume service is not answering, so we cannot read your resume. This is our outage, not a missing upload."}
        <div className="mt-3">
          <Link
            to={`/jds/${jdId}/compare`}
            className="text-sm font-medium text-brand hover:text-brand-hover"
          >
            Back &rarr;
          </Link>
        </div>
      </Empty>
    );
  }

  const blocking = report.risks.filter((risk) => risk.severity === "blocking");

  return (
    <>
      <header className="mb-8">
        <p className="rule-label">
          {jd.data.company_name} &middot; {jd.data.role_title}
        </p>
        <h1 className="mt-0.5 text-display font-semibold text-ink">
          Your resume against this job
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-ink-soft">
          This is not the same question as &ldquo;where you stand&rdquo; on the
          posting screen. That one asks the Skill Graph what you can do across
          every session you have run; this asks your <em>resume</em> what a
          recruiter will read about you next week. They disagree often, and the
          difference is usually the thing worth fixing.
        </p>
      </header>

      {/* Eligibility first and alone. §3.2.2: a hard filter, not a topic. */}
      {report.verdicts.length > 0 && (
        <Section
          label="Can you sit this drive"
          meta={
            blocking.length > 0 ? "one or more hard filters missed" : undefined
          }
        >
          <Panel className="px-4 py-1">
            <div className="divide-y divide-line">
              {report.verdicts.map((verdict) => {
                const tone = VERDICT_TONE[verdict.state];
                return (
                  <div key={verdict.criterion} className="py-2.5">
                    <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                      <span className="text-sm font-medium text-ink">
                        {verdict.criterion.replace(/_/g, " ")}
                      </span>
                      <span className={`text-xs font-medium ${tone.className}`}>
                        {tone.label}
                      </span>
                    </div>
                    <p className="mt-0.5 text-sm text-ink-soft">
                      {verdict.detail}
                    </p>
                    {(verdict.required || verdict.yours) && (
                      <p className="provenance mt-1">
                        posting: {verdict.required ?? "—"} · your resume:{" "}
                        {verdict.yours ?? "not stated"}
                      </p>
                    )}
                  </div>
                );
              })}
            </div>
          </Panel>
        </Section>
      )}

      {report.verdicts.length === 0 && (
        <Section label="Can you sit this drive">
          <Panel className="px-4 py-3">
            <p className="text-sm text-ink-soft">
              This posting states no eligibility criteria we could read &mdash;
              no CGPA cutoff, no batch, no backlog rule. That means there is
              nothing to check, not that you passed a check.
            </p>
          </Panel>
        </Section>
      )}

      <Section
        label="What will cost you"
        meta={
          report.risks.length === 0
            ? "nothing we can see"
            : `${report.risks.length} to read`
        }
      >
        {report.risks.length === 0 ? (
          <Panel className="px-4 py-3">
            <p className="text-sm text-ink-soft">
              Nothing on your resume stands out against this posting. That is a
              statement about what we could check &mdash; the eligibility bar
              and whether your resume mentions each requirement &mdash; and not
              a prediction about the interview.
            </p>
          </Panel>
        ) : (
          <div className="space-y-2">
            {report.risks.map((risk, index) => (
              <div
                key={`${risk.severity}-${index}`}
                className={`rounded-md border px-3.5 py-2.5 ${RISK_TONE[risk.severity]}`}
              >
                <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                  <span className="text-sm font-medium text-ink">
                    {risk.title}
                  </span>
                  <Pill
                    tone={
                      risk.severity === "blocking" ? "contested" : "neutral"
                    }
                  >
                    {RISK_LABEL[risk.severity]}
                  </Pill>
                </div>
                <p className="mt-1 text-sm text-ink-soft">{risk.detail}</p>
                {risk.requirements.length > 0 && (
                  <p className="provenance mt-1.5">
                    {risk.requirements.join(" · ")}
                  </p>
                )}
              </div>
            ))}
          </div>
        )}
      </Section>

      <Section
        label="What your resume evidences"
        meta={
          report.must_have_evidence === null
            ? "no must-haves stated"
            : `${Math.round(report.must_have_evidence * 100)}% of the must-haves`
        }
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <Panel className="px-4 py-3">
            <p className="rule-label">On your resume</p>
            {report.evidenced.length === 0 ? (
              <p className="mt-2 text-sm text-ink-faint">Nothing matched.</p>
            ) : (
              <ul className="mt-2 space-y-1">
                {report.evidenced.map((label) => (
                  <li key={label} className="text-sm text-ink">
                    {label}
                  </li>
                ))}
              </ul>
            )}
          </Panel>
          <Panel className="px-4 py-3">
            <p className="rule-label">Asked for, not mentioned</p>
            {report.unevidenced.length === 0 ? (
              <p className="mt-2 text-sm text-ink-faint">Nothing missing.</p>
            ) : (
              <ul className="mt-2 space-y-1">
                {report.unevidenced.map((label) => (
                  <li key={label} className="text-sm text-ink-soft">
                    {label}
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </div>
        <p className="mt-2 text-xs text-ink-faint">
          Matched on concept id where both sides resolved, and on the plain
          label otherwise. &ldquo;Not mentioned&rdquo; means your resume does
          not say it &mdash; not that you cannot do it. That distinction is the
          entire value of this screen: a recruiter screening on keywords sees
          the resume, not you.
        </p>
      </Section>

      <div className="mt-8 flex flex-wrap items-center gap-4">
        <Link
          to={`/jds/${jdId}`}
          className="text-sm font-medium text-brand hover:text-brand-hover"
        >
          &larr; The posting, and your coverage plan
        </Link>
      </div>
    </>
  );
}
