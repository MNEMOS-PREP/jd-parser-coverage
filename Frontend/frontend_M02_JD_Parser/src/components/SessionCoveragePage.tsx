/**
 * What the session actually covered (FR-2.11, §6.6).
 *
 * §6.6 calls the ledger *"the mechanism that makes coverage a guarantee rather
 * than an intention"*, and this screen is where the guarantee becomes visible.
 * Until it existed M02 produced a plan and nothing read it back: the plan said
 * four questions about DBMS, the session asked none, and no part of the
 * platform noticed.
 *
 * Live during the interview and the report afterwards — the same screen,
 * because they are the same question asked at different times, and two screens
 * would eventually disagree about what happened.
 *
 * ── Written by M05 and M13, read here ────────────────────────────────────────
 *
 * Nothing on this page writes. M05 records `asked` when it selects a question
 * and M13 moves the row to `scored`; M02 owns the table because M02 made the
 * promise, but it is not the one keeping it.
 *
 * So the empty state is the ordinary one today, and it says which module has
 * not arrived rather than looking broken.
 */

import { Link, useParams } from "react-router-dom";

import { useRecordCoverage, useSessionCoverage } from "../api";
import { useCandidateId } from "./candidate-hook";
import {
  Empty,
  ErrorNote,
  Panel,
  Section,
  SkeletonRows,
} from "../ui/primitives";

export function SessionCoveragePage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const candidateId = useCandidateId();
  const coverage = useSessionCoverage(sessionId, candidateId);
  // Mounted, not used by this screen: M05 and M13 write the ledger, and the
  // hook is here so the route has a client and so the session view can replay
  // a turn once M06 exists. `skipped` is the one event a STUDENT legitimately
  // causes — "I do not want to answer this" — and it is the first thing that
  // will need it.
  const record = useRecordCoverage(sessionId, candidateId);
  void record;

  if (coverage.isLoading) return <SkeletonRows rows={5} />;

  if (coverage.isError) {
    return (
      <ErrorNote>
        Could not read this session&rsquo;s coverage.{" "}
        {coverage.error instanceof Error ? coverage.error.message : ""}
      </ErrorNote>
    );
  }

  const data = coverage.data;

  if (!data || data.questions_asked === 0) {
    return (
      <Empty title="Nothing recorded for this session yet">
        The ledger is written by the interview engine as it asks questions and
        by the evaluation engine as it scores them. Neither is wired yet, so
        there is nothing to read back &mdash; which is different from a session
        that covered nothing.
        <div className="mt-3">
          <Link
            to="/"
            className="text-sm font-medium text-brand hover:text-brand-hover"
          >
            Paste a job description &rarr;
          </Link>
        </div>
      </Empty>
    );
  }

  const scored = data.requirements.filter((r) => r.scores.length > 0);
  const askedOnly = data.requirements.filter((r) => r.scores.length === 0);

  return (
    <>
      <header className="mb-8">
        <p className="rule-label">Session {data.session_id.slice(0, 8)}</p>
        <h1 className="mt-0.5 text-display font-semibold text-ink">
          What this session covered
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-ink-soft">
          {data.questions_asked} question{data.questions_asked === 1 ? "" : "s"}{" "}
          across {data.requirements.length} requirement
          {data.requirements.length === 1 ? "" : "s"}. This is read from the
          ledger rather than from the plan &mdash; the plan is what was
          promised, and this is what happened.
        </p>
      </header>

      <Section
        label="Asked and scored"
        meta={`${scored.length} of ${data.requirements.length}`}
      >
        {scored.length === 0 ? (
          <Panel className="px-4 py-3">
            <p className="text-sm text-ink-soft">
              Questions were asked but none has been scored yet. Scores arrive
              from the evaluation engine after each turn, so a live session sits
              here for a while.
            </p>
          </Panel>
        ) : (
          <Panel className="px-4 py-1">
            <div className="divide-y divide-line">
              {scored.map((row) => (
                <div
                  key={row.requirement_id}
                  className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 py-2.5"
                >
                  <span className="min-w-0 text-sm text-ink">{row.text}</span>
                  <span className="flex shrink-0 items-center gap-2">
                    <span className="provenance">
                      {row.asked} asked · {row.necessity ?? "—"}
                    </span>
                    <span className="text-sm text-ink">
                      {/* Every score, not an average. Two turns at 0.9 and 0.1
                          is a different session from two at 0.5, and a mean
                          hides exactly the turn worth talking about. */}
                      {row.scores.map((s) => s.toFixed(2)).join(" · ")}
                    </span>
                  </span>
                </div>
              ))}
            </div>
          </Panel>
        )}
      </Section>

      {askedOnly.length > 0 && (
        <Section label="Asked, not yet scored" meta={`${askedOnly.length}`}>
          <Panel className="px-4 py-1">
            <div className="divide-y divide-line">
              {askedOnly.map((row) => (
                <div
                  key={row.requirement_id}
                  className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 py-2"
                >
                  <span className="min-w-0 text-sm text-ink-soft">
                    {row.text}
                  </span>
                  <span className="provenance shrink-0">{row.asked} asked</span>
                </div>
              ))}
            </div>
          </Panel>
        </Section>
      )}

      {data.jd_id && (
        <div className="mt-8">
          <Link
            to={`/jds/${data.jd_id}`}
            className="text-sm font-medium text-brand hover:text-brand-hover"
          >
            &larr; The posting this session was planned against
          </Link>
        </div>
      )}
    </>
  );
}
