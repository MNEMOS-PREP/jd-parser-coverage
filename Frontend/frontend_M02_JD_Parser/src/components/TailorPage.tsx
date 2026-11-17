/**
 * Tailor your resume to this job — the whole job, without leaving it
 * (2026-11-17).
 *
 *   1. The job is saved for this student the moment they arrive.
 *   2. They pick one of their resumes (M01's own list), or keep the one they
 *      picked last time. Each resume gets its own tailored COPY for this job;
 *      the uploaded resume is never written, and switching back finds the
 *      edits made the first time.
 *   3. Three panels: what the posting asks for and what to change (this
 *      module), the copy line by line (M01's editor), and the real PDF of it
 *      (M01's renderer) — every accepted change is in the PDF at once.
 *   4. A tag on a line, a row of the matrix or a flag traces a claim: the line
 *      is marked in the editor, boxed on its page, and the posting's own words
 *      sit beside it. "Back" returns the page to where it was.
 *   5. A final check, then the file — generated from the latest version, under
 *      the name typed at the top.
 *
 * The resume module owns the resume: its editor, its PDF, its rewording with
 * fact checks. This page orchestrates them with the job description.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import {
  DownloadPdf,
  PhotoToggle,
  ResumeList,
  TailoredEditor,
  TailoredPreview,
  apiProblem,
  suggestFilename,
  useCandidateResumes,
  useCreateTailored,
  useResume,
  useTailored,
  useTailoredLayout,
  type BlockAnnotation,
  type BlockMark,
  type PreviewFocus,
  type TailoredResume,
} from "@ai/m01";

import { useJd, useSaveWorkspace, useTailorReport, useWorkspace } from "../api";
import { m01Href } from "../links";
import type { TailorFlag, TailorHit, TailorIn, TailorReport, TailorRequirement } from "../types";
import { useCandidateId } from "./candidate-hook";
import { JdTabs } from "./JdTabs";
import { TailorIntel } from "./TailorIntel";
import { FlagPopup, TracePopup } from "./TracePopup";
import { Empty, ErrorNote, Panel, SkeletonRows } from "../ui/primitives";

type Trace =
  | { kind: "claim"; requirement: TailorRequirement; hit: TailorHit }
  | { kind: "flag"; flag: TailorFlag };

/** The copy, as the analysis reads it. */
function bodyOf(copy: TailoredResume, resume: { id: string; resolved_concepts: Record<string, string>; canonical_skills: Record<string, string> }, pages: number | null): TailorIn {
  return {
    resume: { id: resume.id, resolved_concepts: resume.resolved_concepts, canonical_skills: resume.canonical_skills },
    tailored_id: copy.id,
    revision: copy.revision,
    pages,
    blocks: copy.blocks.map((b) => ({
      id: b.id,
      kind: b.kind,
      section: b.section,
      group: b.group,
      text: b.text,
      original: b.original,
      hidden: b.hidden,
      added: b.added,
      masked: b.masked,
    })),
  };
}

/** Tags for every line: what it evidences, and what it says that the upload never did. */
function annotate(report: TailorReport | undefined, confirmed: Set<string>) {
  const tags: Record<string, (BlockAnnotation & { weight: number })[]> = {};
  if (!report) return {} as Record<string, BlockAnnotation[]>;
  for (const req of report.requirements) {
    if (req.inferred || req.status === "alternative") continue;
    for (const hit of req.hits) {
      const ok = hit.natural || confirmed.has(hit.term.toLowerCase()) || confirmed.has(req.term.toLowerCase());
      const tone: BlockAnnotation["tone"] = !ok
        ? "unsupported"
        : hit.level === "direct" && hit.how === "named"
          ? "direct"
          : "partial";
      const list = (tags[hit.block_id] ??= []);
      if (list.some((t) => t.key === `req:${req.id}`)) continue;
      list.push({
        key: `req:${req.id}`,
        label: req.term,
        tone,
        weight: req.weight,
        title: `${req.text} — ${tone === "direct" ? "shown here" : tone === "partial" ? "named, not shown in work" : "not in your uploaded resume"}. Click to trace it to the posting.`,
      });
    }
  }
  for (const flag of report.flags) {
    if (!flag.terms.length) continue;
    (tags[flag.block_id] ??= []).unshift({
      key: "flag",
      label: "not in your upload",
      tone: "unsupported",
      weight: 99,
      title: flag.message,
    });
  }
  const out: Record<string, BlockAnnotation[]> = {};
  for (const [id, list] of Object.entries(tags)) {
    const sorted = [...list].sort((a, b) => b.weight - a.weight);
    out[id] = sorted.slice(0, 4).map(({ weight: _weight, ...rest }) => rest);
    if (sorted.length > 4) out[id].push({ key: "more", label: `+${sorted.length - 4}`, tone: "info" });
  }
  return out;
}

/* ── step 2: which resume ───────────────────────────────────────────────── */

function PickResume({
  candidateId,
  current,
  busy,
  error,
  missing,
  onPick,
  onCancel,
}: {
  candidateId: string;
  current: string | null;
  busy: boolean;
  error: unknown;
  missing: boolean;
  onPick: (resumeId: string) => void;
  onCancel?: () => void;
}) {
  const resumes = useCandidateResumes(candidateId);
  const upload = m01Href("/resume", candidateId);
  const usable = (resumes.data ?? []).filter((r) => r.parse_status === "ready" || r.parse_status === "needs_review");
  const [chosen, setChosen] = useState<string | null>(current ?? usable.find((r) => r.is_active)?.id ?? null);
  const [everything, setEverything] = useState(false);
  // The active resume first, then the newest few; older versions on request —
  // a student with fifteen uploads came for one of the last two.
  const ordered = [...usable].sort((a, b) => Number(b.is_active) - Number(a.is_active));
  const shown = everything ? ordered : ordered.filter((r, i) => i < 3 || r.id === chosen);
  useEffect(() => {
    if (!chosen && usable.length) setChosen(usable.find((r) => r.is_active)?.id ?? usable[0].id);
  }, [chosen, usable]);

  return (
    <section className="mx-auto mt-6 max-w-3xl">
      <h2 className="text-title font-semibold tracking-tight text-ink">Which resume should we tailor?</h2>
      <p className="mt-1 text-sm text-ink-soft">
        Your resumes, as the Resume page lists them. We make a copy of the one you pick for this job — the
        resume itself stays exactly as you uploaded it, and every other job keeps its own copy.
      </p>
      {missing && (
        <p className="mt-3 rounded-md border border-reported-line bg-reported-soft px-3 py-2 text-sm text-ink">
          The resume you used for this job last time has been removed. Pick another — your notes on this job are kept.
        </p>
      )}
      <div className="mt-5">
        {resumes.isLoading && <SkeletonRows rows={3} />}
        {resumes.isError && <ErrorNote>The resume service is not answering — your resumes are still there.</ErrorNote>}
        {resumes.data && usable.length === 0 && (
          <Empty title="No resume yet">
            Upload one once, on the Resume page, and every job can use it.
            <div className="mt-3">
              {upload.external ? (
                <a href={upload.href} className="text-sm font-medium text-brand">
                  Add your resume →
                </a>
              ) : (
                <Link to={upload.href} className="text-sm font-medium text-brand">
                  Add your resume →
                </Link>
              )}
            </div>
          </Empty>
        )}
        {usable.length > 0 && (
          <>
            <ResumeList resumes={shown} selectedId={chosen} actionLabel="Use this" onOpen={(resume) => setChosen(resume.id)} />
            {ordered.length > shown.length && (
              <button type="button" onClick={() => setEverything(true)} className="mt-2 text-xs font-medium text-ink-soft hover:text-ink">
                Show {ordered.length - shown.length} older version{ordered.length - shown.length === 1 ? "" : "s"}
              </button>
            )}
          </>
        )}
      </div>
      {usable.length > 0 && (
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <button
            type="button"
            disabled={!chosen || busy}
            onClick={() => chosen && onPick(chosen)}
            className="rounded-md bg-brand px-3.5 py-2 text-sm font-medium text-white hover:bg-brand-hover disabled:opacity-50"
          >
            {busy ? "Making your copy…" : "Tailor this resume"}
          </button>
          {onCancel && (
            <button type="button" onClick={onCancel} className="text-sm text-ink-soft hover:text-ink">
              Keep the current one
            </button>
          )}
          {upload.external ? (
            <a href={upload.href} className="ml-auto text-xs text-ink-soft hover:text-ink">
              Upload a different resume
            </a>
          ) : (
            <Link to={upload.href} className="ml-auto text-xs text-ink-soft hover:text-ink">
              Upload a different resume
            </Link>
          )}
        </div>
      )}
      {Boolean(error) && <p className="mt-2 text-sm text-contested">{apiProblem(error)}</p>}
    </section>
  );
}

/* ── step 5: the final check ────────────────────────────────────────────── */

function FinalCheck({
  report,
  copy,
  pages,
  onBack,
  onTraceFlag,
  download,
}: {
  report: TailorReport | undefined;
  copy: TailoredResume;
  pages: number | null;
  onBack: () => void;
  onTraceFlag: (flag: TailorFlag) => void;
  download: React.ReactNode;
}) {
  const open = report?.suggestions.filter((s) => s.state === "open") ?? [];
  const high = open.filter((s) => s.impact === "high");
  const flags = report?.flags.filter((f) => f.terms.length) ?? [];
  const c = report?.coverage;
  const item = (ok: boolean | null, text: React.ReactNode, key: string) => (
    <li key={key} className="flex gap-2 text-sm">
      <span aria-hidden className={ok === null ? "text-ink-faint" : ok ? "text-confirmed" : "text-reported"}>
        {ok === null ? "·" : ok ? "✓" : "!"}
      </span>
      <span className="text-ink">{text}</span>
    </li>
  );
  return (
    <Panel className="flex flex-col gap-4 p-5">
      <div>
        <p className="text-[0.6875rem] font-semibold tracking-wide text-ink-faint uppercase">Final check</p>
        <h2 className="mt-1 text-title font-semibold tracking-tight text-ink">Before you send it</h2>
      </div>
      <ul className="space-y-2">
        {c &&
          item(
            null,
            <>
              Matches <strong data-numeric>{Math.round((c.score ?? 0) * 100)}%</strong> of this posting
              {c.baseline !== null && c.score !== c.baseline && <> (was {Math.round((c.baseline ?? 0) * 100)}% as uploaded)</>}
              {c.musts > 0 && (
                <>
                  , {c.musts_direct} of {c.musts} must-haves shown in your work
                </>
              )}
            </>,
            "match",
          )}
        {item(flags.length === 0, flags.length === 0 ? "Every line is backed by the resume you uploaded, or by you" : `${flags.length} line${flags.length === 1 ? "" : "s"} say something your uploaded resume never did`, "flags")}
        {item(high.length === 0, high.length === 0 ? "No high-impact suggestion left open" : `${high.length} high-impact suggestion${high.length === 1 ? "" : "s"} still open`, "open")}
        {item((pages ?? 1) <= 1, pages ? `${pages} page${pages === 1 ? "" : "s"}` : "Page count not known yet", "pages")}
        {item(true, `${copy.edited} change${copy.edited === 1 ? "" : "s"} from your uploaded resume, every one in the version history`, "edits")}
      </ul>
      {flags.length > 0 && (
        <ul className="space-y-1 rounded-md border border-contested-line bg-contested-soft/60 px-3 py-2">
          {flags.map((flag) => (
            <li key={flag.block_id}>
              <button type="button" onClick={() => onTraceFlag(flag)} className="text-left text-xs text-ink hover:underline">
                {flag.terms.join(", ")} — show me the line
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="border-t border-line pt-4">
        <PhotoToggle copy={copy} />
        <p className="mt-3 text-xs font-medium text-ink-faint">File name</p>
        <div className="mt-1">{download}</div>
        <p className="mt-2 text-xs text-ink-faint">
          Made now from the latest version — exactly the pages on the right, with your contact details printed.
        </p>
      </div>
      <button type="button" onClick={onBack} className="self-start text-sm font-medium text-brand hover:underline">
        ← Back to editing
      </button>
    </Panel>
  );
}

/* ── the page ───────────────────────────────────────────────────────────── */

export function TailorPage() {
  const { jdId = "" } = useParams<{ jdId: string }>();
  const candidateId = useCandidateId();
  const [params, setParams] = useSearchParams();
  const view = params.get("view") === "final" ? "final" : "edit";

  const jd = useJd(jdId);
  const workspace = useWorkspace(jdId, candidateId);
  const save = useSaveWorkspace(jdId, candidateId);
  const create = useCreateTailored();
  const resumes = useCandidateResumes(candidateId);

  // 1. Saved the moment the student arrives, so the job is there tomorrow.
  const savedOnce = useRef(false);
  useEffect(() => {
    if (workspace.isSuccess && !savedOnce.current) {
      savedOnce.current = true;
      save.mutate({ touch: true });
    }
  }, [workspace.isSuccess, save]);

  const row = workspace.data ?? null;
  const resumeId = row?.resume_id ?? null;
  const tailoredId = resumeId ? row?.tailored?.[resumeId] : undefined;
  const resumeGone = Boolean(resumeId && resumes.data && !resumes.data.some((r) => r.id === resumeId));
  const [picking, setPicking] = useState(false);

  const copy = useTailored(resumeGone ? undefined : (resumeId ?? undefined), tailoredId);
  const resume = useResume(resumeGone ? undefined : (resumeId ?? undefined));
  const layout = useTailoredLayout(resumeId ?? "", tailoredId ?? "", copy.data?.revision);
  const pages = layout.data ? layout.data.pages.length : null;

  // A copy deleted from the resume page is made again (the server finds or makes it).
  const remade = useRef(false);
  useEffect(() => {
    if (copy.isError && resumeId && jd.data && !remade.current) {
      remade.current = true;
      create.mutate(
        { resumeId, targetRef: jdId, label: row?.title ?? jd.data.role_title },
        { onSuccess: (made) => save.mutate({ resume_id: resumeId, tailored: { [resumeId]: made.id }, touch: false }) },
      );
    }
  }, [copy.isError, resumeId, jd.data, jdId, row?.title, create, save]);

  const pick = useCallback(
    (chosen: string) => {
      const existing = row?.tailored?.[chosen];
      if (existing) {
        save.mutate({ resume_id: chosen, touch: false }, { onSuccess: () => setPicking(false) });
        return;
      }
      create.mutate(
        { resumeId: chosen, targetRef: jdId, label: row?.title || `${jd.data?.company_name} · ${jd.data?.role_title}` },
        {
          onSuccess: (made) =>
            save.mutate(
              { resume_id: chosen, tailored: { [chosen]: made.id }, touch: false },
              { onSuccess: () => setPicking(false) },
            ),
        },
      );
    },
    [row, jdId, jd.data, create, save],
  );

  const body = useMemo(
    () => (copy.data && resume.data ? bodyOf(copy.data, resume.data, pages) : null),
    [copy.data, resume.data, pages],
  );
  const report = useTailorReport(jdId, candidateId, body);

  // Panels in step.
  const [focusId, setFocusId] = useState<string | null>(null);
  const [previewFocus, setPreviewFocus] = useState<PreviewFocus | null>(null);
  const [trace, setTrace] = useState<Trace | null>(null);
  const [leftOpen, setLeftOpen] = useState(true);

  const confirmed = useMemo(
    () =>
      new Set(
        Object.values(row?.decisions ?? {})
          .filter((d) => d.state === "confirmed" && d.term)
          .map((d) => String(d.term).toLowerCase()),
      ),
    [row?.decisions],
  );
  const annotations = useMemo(() => annotate(report.data, confirmed), [report.data, confirmed]);
  const marks = useMemo(() => {
    const out: Record<string, BlockMark[]> = {};
    if (trace?.kind === "claim") {
      for (const hit of trace.requirement.hits) {
        (out[hit.block_id] ??= []).push({
          start: hit.start,
          end: hit.end,
          tone: hit === trace.hit ? "focus" : hit.level === "direct" ? "direct" : "partial",
        });
      }
    }
    return out;
  }, [trace]);

  const focusBlock = useCallback((blockId: string) => {
    setFocusId(blockId);
    setPreviewFocus({ blockId, nonce: Date.now() });
    setTrace(null);
  }, []);

  const traceClaim = useCallback((requirement: TailorRequirement, hit?: TailorHit) => {
    const chosen = hit ?? requirement.hits[0];
    if (!chosen) {
      // Nothing on the resume evidences it: show the requirement, no line.
      setTrace(null);
      setFocusId(null);
      setLeftOpen(true);
      return;
    }
    setFocusId(chosen.block_id);
    setPreviewFocus({ blockId: chosen.block_id, start: chosen.start, end: chosen.end, nonce: Date.now() });
    setTrace({ kind: "claim", requirement, hit: chosen });
  }, []);

  const traceFlag = useCallback((flag: TailorFlag) => {
    setFocusId(flag.block_id);
    setPreviewFocus({ blockId: flag.block_id, nonce: Date.now() });
    setTrace({ kind: "flag", flag });
  }, []);

  const onAnnotation = useCallback(
    (blockId: string, annotation: BlockAnnotation) => {
      if (!report.data) return;
      if (annotation.key === "flag") {
        const flag = report.data.flags.find((f) => f.block_id === blockId);
        if (flag) traceFlag(flag);
        return;
      }
      const requirement = report.data.requirements.find((r) => `req:${r.id}` === annotation.key);
      const hit = requirement?.hits.find((h) => h.block_id === blockId);
      if (requirement && hit) traceClaim(requirement, hit);
    },
    [report.data, traceClaim, traceFlag],
  );

  // File name: what the student typed, kept with the job.
  const [filename, setFilename] = useState<string | null>(null);
  useEffect(() => {
    if (filename === null && row) setFilename(row.filename ?? "");
  }, [filename, row]);
  const saveName = useRef<number | undefined>(undefined);
  const onFilename = (value: string) => {
    setFilename(value);
    window.clearTimeout(saveName.current);
    saveName.current = window.setTimeout(() => save.mutate({ filename: value, touch: false }), 600);
  };

  // Title, renamable in place.
  const [renaming, setRenaming] = useState(false);
  const [title, setTitle] = useState("");

  if (jd.isLoading || workspace.isLoading) {
    return <SkeletonRows rows={8} />;
  }
  if (jd.isError || !jd.data) {
    return (
      <Empty title="No such job description">
        It may have been removed. Your saved jobs are on the job description page.
        <div className="mt-3">
          <Link to="/jd" className="text-sm font-medium text-brand">
            Your job descriptions →
          </Link>
        </div>
      </Empty>
    );
  }

  const posting = jd.data;
  const shownTitle = row?.title || `${posting.company_name} · ${posting.role_title}`;
  const copyData = copy.data;
  const needsResume = !resumeId || resumeGone || picking || (!tailoredId && !create.isPending);
  const suggested = suggestFilename(copyData?.name, posting.company_name);

  const popup =
    trace?.kind === "claim" && copyData ? (
      <TracePopup
        requirement={trace.requirement}
        hit={trace.hit}
        line={copyData.blocks.find((b) => b.id === trace.hit.block_id)?.text ?? ""}
        confirmed={confirmed.has(trace.hit.term.toLowerCase()) || confirmed.has(trace.requirement.term.toLowerCase())}
        onClose={() => setTrace(null)}
      />
    ) : trace?.kind === "flag" && copyData ? (
      <FlagPopup
        flag={trace.flag}
        line={copyData.blocks.find((b) => b.id === trace.flag.block_id)?.text ?? ""}
        onClose={() => setTrace(null)}
      />
    ) : undefined;

  const download = copyData ? (
    <DownloadPdf copy={copyData} filename={filename ?? ""} onFilename={onFilename} suggested={suggested} compact />
  ) : null;
  const currentResume = resumes.data?.find((r) => r.id === resumeId);

  return (
    <div className="lg:-mx-4 xl:-mx-10">
      <header className="mb-3">
        <Link to="/jd" className="text-xs font-medium text-ink-soft hover:text-ink">
          ← Your job descriptions
        </Link>
        <div className="mt-1 flex flex-wrap items-end justify-between gap-x-4 gap-y-2">
          <div className="min-w-0">
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
                  className="w-80 rounded-md border border-line bg-surface px-2.5 py-1 text-lg font-semibold text-ink outline-none focus:border-brand"
                />
                <button type="submit" className="text-sm font-medium text-brand">
                  Save
                </button>
              </form>
            ) : (
              <h1 className="flex flex-wrap items-baseline gap-x-2 text-title font-semibold tracking-tight break-words text-ink sm:flex-nowrap sm:truncate">
                {shownTitle}
                <button
                  type="button"
                  onClick={() => {
                    setTitle(shownTitle);
                    setRenaming(true);
                  }}
                  className="text-xs font-medium text-ink-faint hover:text-ink"
                >
                  Rename
                </button>
              </h1>
            )}
            <p className="mt-0.5 text-xs text-ink-faint">
              {posting.company_name} · {posting.role_title} · saved for you
              {currentResume && !needsResume && (
                <>
                  {" "}· tailoring <span className="text-ink-soft">{currentResume.filename ?? "your pasted resume"}</span>{" "}
                  <button type="button" onClick={() => setPicking(true)} className="font-medium text-brand hover:underline">
                    change
                  </button>
                </>
              )}
            </p>
          </div>
          {!needsResume && copyData && view === "edit" && (
            <div className="flex flex-col items-start gap-1.5 sm:items-end">
              <div className="flex flex-wrap items-center gap-2">
                {download}
                <button
                  type="button"
                  onClick={() => setParams({ view: "final" })}
                  className="rounded-md border border-line bg-surface px-3 py-1.5 text-sm font-medium text-ink hover:border-line-strong"
                >
                  Final check →
                </button>
              </div>
              <PhotoToggle copy={copyData} />
            </div>
          )}
        </div>
        <div className="mt-3">
          <JdTabs jdId={jdId} active="tailor" />
        </div>
      </header>

      {needsResume ? (
        <PickResume
          candidateId={candidateId}
          current={resumeGone ? null : resumeId}
          busy={create.isPending || save.isPending}
          error={create.error ?? save.error}
          missing={resumeGone}
          onPick={pick}
          onCancel={picking && !resumeGone && tailoredId ? () => setPicking(false) : undefined}
        />
      ) : !copyData ? (
        copy.isError && !create.isPending ? (
          <ErrorNote>Your tailored copy could not be loaded: {apiProblem(copy.error)}</ErrorNote>
        ) : (
          <SkeletonRows rows={10} />
        )
      ) : view === "final" ? (
        <div className="grid gap-3 xl:h-[calc(100dvh-14rem)] xl:grid-cols-[minmax(20rem,26rem)_minmax(0,1fr)]">
          <FinalCheck
            report={report.data}
            copy={copyData}
            pages={pages}
            onBack={() => setParams({})}
            onTraceFlag={(flag) => {
              setParams({});
              traceFlag(flag);
            }}
            download={download}
          />
          <TailoredPreview copy={copyData} />
        </div>
      ) : (
        <div
          className={`grid gap-3 xl:h-[calc(100dvh-14rem)] xl:min-h-[34rem] ${
            leftOpen
              ? "xl:grid-cols-[minmax(17rem,24rem)_minmax(0,1fr)_minmax(0,1fr)]"
              : "xl:grid-cols-[2.25rem_minmax(0,1fr)_minmax(0,1fr)]"
          } [&>*]:max-xl:h-[78vh]`}
        >
          {leftOpen ? (
            report.data ? (
              <TailorIntel
                report={report.data}
                copy={copyData}
                jdId={jdId}
                candidateId={candidateId}
                updating={report.isFetching}
                onTrace={traceClaim}
                onFlag={traceFlag}
                onFocusBlock={focusBlock}
                onCollapse={() => setLeftOpen(false)}
              />
            ) : (
              <Panel className="p-4">
                {report.isError ? (
                  <ErrorNote>The match could not be worked out: {apiProblem(report.error)}</ErrorNote>
                ) : (
                  <SkeletonRows rows={8} />
                )}
              </Panel>
            )
          ) : (
            <button
              type="button"
              onClick={() => setLeftOpen(true)}
              className="panel flex items-start justify-center bg-surface pt-4 text-xs font-medium text-ink-soft [writing-mode:vertical-rl] hover:text-ink"
            >
              Job match · {report.data ? `${Math.round((report.data.coverage.score ?? 0) * 100)}%` : "…"}
            </button>
          )}
          <TailoredEditor
            copy={copyData}
            focusId={focusId}
            onFocus={focusBlock}
            annotations={annotations}
            onAnnotation={onAnnotation}
            marks={marks}
          />
          <TailoredPreview
            copy={copyData}
            focus={previewFocus}
            popup={popup}
            onPick={(blockId) => setFocusId(blockId)}
            onBack={() => setTrace(null)}
          />
        </div>
      )}
    </div>
  );
}
