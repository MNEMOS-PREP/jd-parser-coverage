/**
 * "Shall we check this posting against your resume?" — the confirmation step.
 *
 * Spec: plan_in_depth/M02_JD_Parser.md FR-2.15
 *
 * A separate screen before the analysis, rather than the analysis appearing on
 * its own, for one reason: this is the first thing in the platform that reads a
 * student's RESUME in order to say something about their chances. Producing
 * "you miss the CGPA cutoff" as a side effect of parsing a job posting would be
 * the right sentence at a moment nobody asked for it.
 *
 * So the student is told what will be read, from where, and what it will be
 * compared against — and then chooses. The three ways this can go all get an
 * honest screen:
 *
 *   · a resume exists      → what it is, when, and a button
 *   · no resume            → where to make one, and that the JD screen still works
 *   · M01 unreachable      → that it is our outage, not their missing upload
 *
 * The third matters most. "You have no resume" when the truth is "we cannot
 * reach the resume service" sends a student off to re-upload a file they
 * already uploaded.
 */

import { Link, useNavigate, useParams } from "react-router-dom";

import { useJd, useMatch } from "../api";
import { useCandidateId } from "./candidate-hook";
import {
  Btn,
  Empty,
  ErrorNote,
  Panel,
  Section,
  SkeletonRows,
} from "../ui/primitives";
import { M01_URL } from "../links";

export function MatchConfirmPage() {
  const { jdId } = useParams<{ jdId: string }>();
  const candidateId = useCandidateId();
  const navigate = useNavigate();
  const jd = useJd(jdId);
  const match = useMatch(jdId, candidateId);

  if (jd.isLoading || match.isLoading) return <SkeletonRows rows={5} />;

  if (jd.isError || !jd.data) {
    return (
      <Empty title="No such job description">
        The id in the URL does not match a stored JD.
        <div className="mt-3">
          <Link
            to="/jd"
            className="text-sm font-medium text-brand hover:text-brand-hover"
          >
            Paste one &rarr;
          </Link>
        </div>
      </Empty>
    );
  }

  const status = match.data?.resume_status;

  return (
    <>
      <header className="mb-8">
        <p className="rule-label">
          {jd.data.company_name} &middot; {jd.data.role_title}
        </p>
        <h1 className="mt-0.5 text-display font-semibold text-ink">
          Check this against your resume?
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-ink-soft">
          We read the posting already. This step reads your <em>resume</em> too,
          and compares the two: whether you clear the eligibility bar, and which
          of the requirements your resume actually mentions. Nothing is stored
          and nothing is sent anywhere &mdash; the comparison happens when you
          ask for it and is thrown away when you leave.
        </p>
      </header>

      {match.isError && (
        <ErrorNote>
          Could not reach the match service.{" "}
          {match.error instanceof Error ? match.error.message : ""}
        </ErrorNote>
      )}

      <Section label="What will be compared">
        <Panel className="px-4 py-3">
          <dl className="space-y-2.5 text-sm">
            <div className="flex flex-wrap justify-between gap-x-4">
              <dt className="text-ink-soft">This posting</dt>
              <dd className="text-ink">
                {jd.data.requirements.length} requirement
                {jd.data.requirements.length === 1 ? "" : "s"}
                {jd.data.eligibility?.stated
                  ? " · an eligibility block we could read"
                  : " · no eligibility block stated"}
              </dd>
            </div>
            <div className="flex flex-wrap justify-between gap-x-4">
              <dt className="text-ink-soft">Your resume</dt>
              <dd className="text-ink">
                {status === "ok" && (
                  <span>
                    the active one on file
                    {match.data?.resume_id && (
                      <span className="provenance ml-2">
                        {match.data.resume_id.slice(0, 8)}
                      </span>
                    )}
                  </span>
                )}
                {status === "no_resume" && (
                  <span className="text-ink-faint">none uploaded yet</span>
                )}
                {status === "m01_unreachable" && (
                  <span className="text-contested">
                    the resume service is not answering
                  </span>
                )}
              </dd>
            </div>
          </dl>
        </Panel>
      </Section>

      {status === "ok" && (
        <div className="mt-6 flex flex-wrap items-center gap-3">
          <Btn onClick={() => navigate(`/jds/${jdId}/match`)}>Compare them</Btn>
          <Link
            to={`/jds/${jdId}`}
            className="text-sm text-ink-soft hover:text-ink"
          >
            Skip &mdash; just show me the posting
          </Link>
        </div>
      )}

      {status === "no_resume" && (
        <Section label="You have not uploaded a resume">
          <Panel className="px-4 py-3">
            <p className="text-sm text-ink-soft">
              The eligibility check needs your CGPA and the evidence check needs
              your skills, and both live on your resume. Neither is something we
              can guess &mdash; asserting that a student misses a cutoff on a
              number we do not hold is the worst thing on this screen to be
              wrong about.
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <a
                href={M01_URL}
                target="_blank"
                rel="noreferrer"
                className="text-sm font-medium text-brand hover:text-brand-hover"
              >
                Upload one in Resume Ingestion &rarr;
              </a>
              <Link
                to={`/jds/${jdId}`}
                className="text-sm text-ink-soft hover:text-ink"
              >
                Or carry on without it
              </Link>
            </div>
          </Panel>
        </Section>
      )}

      {status === "m01_unreachable" && (
        <Section label="The resume service is not answering">
          <Panel className="px-4 py-3">
            <p className="text-sm text-ink-soft">
              This is our outage, not a missing upload &mdash; if you have a
              resume on file, it is still there. Everything else about this
              posting works: the requirements, the weights, the gap against your
              Skill Graph and the coverage plan.
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <Link
                to={`/jds/${jdId}`}
                className="text-sm font-medium text-brand hover:text-brand-hover"
              >
                Carry on without it &rarr;
              </Link>
              <Link to="/deps" className="text-sm text-ink-soft hover:text-ink">
                What is down
              </Link>
            </div>
          </Panel>
        </Section>
      )}
    </>
  );
}
