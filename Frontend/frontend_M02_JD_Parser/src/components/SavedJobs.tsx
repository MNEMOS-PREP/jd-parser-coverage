/**
 * "Your job descriptions" — every posting this student has read, kept
 * (2026-11-17).
 *
 * Until now a posting lived only in the URL: leave the page and it was gone,
 * paste it again to get it back. The parse is still shared across students
 * (FR-2.12); this list is the student's own — renamable, deletable, and each
 * one reopens where they left it: same resume, same edits, same decisions.
 */
import { useState } from "react";
import { Link } from "react-router-dom";

import { deleteTailored } from "@ai/m01";

import { useForgetJob, useSaveWorkspace, useSavedJobs } from "../api";
import type { WorkspaceOut } from "../types";
import { useCandidateId } from "./candidate-hook";
import { Panel, Section, SkeletonRows } from "../ui/primitives";

/** A server time, read as UTC: SQLite drops the zone, so a bare ISO string is UTC. */
function utc(iso: string): number {
  return new Date(/[zZ]$|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`).getTime();
}

function when(iso: string): string {
  const minutes = Math.round((Date.now() - utc(iso)) / 60_000);
  if (minutes < 2) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  if (minutes < 60 * 24) return `${Math.round(minutes / 60)} h ago`;
  const days = Math.round(minutes / (60 * 24));
  return days === 1 ? "yesterday" : `${days} days ago`;
}

function Row({ job, candidateId }: { job: WorkspaceOut; candidateId: string }) {
  const save = useSaveWorkspace(job.jd_id, candidateId);
  const forget = useForgetJob(candidateId);
  const [renaming, setRenaming] = useState(false);
  const [title, setTitle] = useState(job.title);
  const [confirming, setConfirming] = useState(false);
  const summary = job.summary ?? {};
  const score = typeof summary.score === "number" ? Math.round(summary.score * 100) : null;

  const remove = async () => {
    // The tailored copies are M01's; they go first, then the job.
    await Promise.allSettled(
      Object.entries(job.tailored ?? {}).map(([resumeId, copyId]) => deleteTailored(resumeId, copyId)),
    );
    forget.mutate(job.jd_id);
  };

  return (
    <li className="flex flex-wrap items-center gap-x-4 gap-y-2 py-3">
      {/* Full width on a phone, so the name is never squeezed to "Pho…". */}
      <div className="w-full min-w-0 sm:w-auto sm:flex-1">
        {renaming ? (
          <form
            onSubmit={(event) => {
              event.preventDefault();
              save.mutate({ title, touch: false }, { onSuccess: () => setRenaming(false) });
            }}
            className="flex items-center gap-2"
          >
            <input
              autoFocus
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              onKeyDown={(event) => event.key === "Escape" && setRenaming(false)}
              aria-label="Name this job"
              className="w-full max-w-sm rounded-md border border-line bg-surface px-2.5 py-1 text-sm text-ink outline-none focus:border-brand"
            />
            <button type="submit" className="text-xs font-medium text-brand">
              Save
            </button>
            <button type="button" onClick={() => setRenaming(false)} className="text-xs text-ink-soft">
              Cancel
            </button>
          </form>
        ) : (
          <Link to={`/jds/${job.jd_id}/tailor`} className="group block">
            <span className="block truncate text-sm font-medium text-ink group-hover:text-brand">
              {job.title}
            </span>
            <span className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-ink-faint">
              {job.title !== `${job.company_name} · ${job.role_title}` && (
                <span>
                  {job.company_name} · {job.role_title} ·
                </span>
              )}
              <span data-numeric>{job.requirement_count} requirements</span>
              <span>· opened {when(job.opened_at)}</span>
            </span>
          </Link>
        )}
      </div>
      <div className="flex shrink-0 flex-wrap items-center gap-1.5 text-xs">
        {score !== null ? (
          <span className="rounded-full bg-brand-soft px-2 py-0.5 font-medium text-brand" data-numeric>
            {score}% match
          </span>
        ) : (
          <span className="rounded-full border border-line px-2 py-0.5 text-ink-faint">
            {job.resume_id ? "not checked yet" : "no resume yet"}
          </span>
        )}
        {summary.musts ? (
          <span className="rounded-full border border-line px-2 py-0.5 text-ink-soft" data-numeric>
            {summary.musts_direct}/{summary.musts} must-haves shown
          </span>
        ) : null}
        {summary.open ? (
          <span className="rounded-full border border-line px-2 py-0.5 text-ink-soft" data-numeric>
            {summary.open} suggestion{summary.open === 1 ? "" : "s"}
          </span>
        ) : null}
      </div>
      <div className="flex shrink-0 items-center gap-2 text-xs">
        {confirming ? (
          <>
            <span className="text-ink-soft">Forget this job and its tailored copies?</span>
            <button type="button" onClick={() => void remove()} className="font-medium text-contested">
              Delete
            </button>
            <button type="button" onClick={() => setConfirming(false)} className="text-ink-soft">
              Keep
            </button>
          </>
        ) : (
          <>
            <Link
              to={`/jds/${job.jd_id}/tailor`}
              className="rounded-md bg-brand px-2.5 py-1 font-medium text-white hover:bg-brand-hover"
            >
              Open
            </Link>
            <button type="button" onClick={() => setRenaming(true)} className="text-ink-soft hover:text-ink">
              Rename
            </button>
            <button type="button" onClick={() => setConfirming(true)} className="text-ink-soft hover:text-contested">
              Delete
            </button>
          </>
        )}
      </div>
    </li>
  );
}

export function SavedJobs() {
  const candidateId = useCandidateId();
  const jobs = useSavedJobs(candidateId);
  if (jobs.isLoading) {
    return (
      <Section label="Your job descriptions">
        <SkeletonRows rows={2} />
      </Section>
    );
  }
  if (!jobs.data?.length) return null;
  return (
    <Section label="Your job descriptions" meta={`${jobs.data.length} saved`}>
      <Panel className="px-4 py-0">
        <ul className="divide-y divide-line">
          {jobs.data.map((job) => (
            <Row key={job.id} job={job} candidateId={candidateId} />
          ))}
        </ul>
      </Panel>
      <p className="mt-2 text-xs text-ink-faint">
        Each keeps its own resume, edits and decisions. The posting itself is shared with anyone who
        pasted the same one; this list is yours.
      </p>
    </Section>
  );
}
