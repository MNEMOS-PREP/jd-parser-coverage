/**
 * The left of the tailoring workspace: what the posting asks for, where the
 * resume stands against it, and what to change (2026-11-17).
 *
 * Three views of one analysis (`tailoring.py`):
 *
 *   Suggestions   ranked by what they are worth to THIS posting, each with its
 *                 reason — what changes, why, which line of the posting it
 *                 answers, what it improves, and what kind of change it is.
 *                 Applying one is an edit of the tailored copy, recorded with
 *                 where it came from; turning one down is remembered.
 *   Requirements  the coverage matrix: every requirement, how strongly the
 *                 resume evidences it, and the line that does — one click
 *                 traces it onto the editor and the PDF.
 *   Keywords      the posting's skills, split into on the resume as uploaded,
 *                 added while tailoring, and missing.
 *
 * Nothing on this panel adds a fact. A requirement the resume does not show is
 * asked about — "is this true of you?" — and only the student's answer, or the
 * student's own words, ever reaches the resume.
 */
import { useMemo, useState } from "react";

import {
  FixDiff,
  TailoredRewrite,
  apiProblem,
  useAddTailoredBlock,
  useEditTailoredBlock,
  useMoveTailoredBlock,
  type TailoredResume,
} from "@ai/m01";

import { useDecide } from "../api";
import type {
  TailorFlag,
  TailorHit,
  TailorReport,
  TailorRequirement,
  TailorSuggestion,
} from "../types";

const CATEGORY_LABEL: Record<TailorSuggestion["category"], string> = {
  keywords: "Missing keywords",
  skills: "Skills to add or highlight",
  experience: "Experience to improve",
  projects: "Projects to emphasise",
  structure: "Format and structure",
};
const CATEGORY_ORDER: TailorSuggestion["category"][] = [
  "keywords",
  "skills",
  "experience",
  "projects",
  "structure",
];

const IMPACT: Record<TailorSuggestion["impact"], { label: string; dot: string }> = {
  high: { label: "High impact", dot: "bg-contested" },
  medium: { label: "Medium", dot: "bg-reported" },
  low: { label: "Low", dot: "bg-ink-faint" },
};

const STATUS: Record<string, { label: string; className: string }> = {
  direct: { label: "Shown in work", className: "border-confirmed-line bg-confirmed-soft" },
  partial: { label: "Listed / other words", className: "border-reported-line bg-reported-soft" },
  missing: { label: "Missing", className: "border-line bg-surface-sunken text-ink-soft" },
  unsupported: { label: "Typed in, unsupported", className: "border-contested-line bg-contested-soft" },
  alternative: { label: "Met by a choice", className: "border-line bg-surface" },
};

const NECESSITY: Record<string, string> = { must: "must", should: "expected", could: "nice" };

function pct(value: number | null | undefined): string {
  return typeof value === "number" ? `${Math.round(value * 100)}%` : "—";
}

function clip(text: string, limit = 110): string {
  return text.length <= limit ? text : `${text.slice(0, limit - 1).trimEnd()}…`;
}

/* ── the match, counted ─────────────────────────────────────────────────── */

function MatchHeader({ report, onShowMatrix }: { report: TailorReport; onShowMatrix: () => void }) {
  const c = report.coverage;
  const moved = c.score !== null && c.baseline !== null && Math.round(c.score * 100) !== Math.round(c.baseline * 100);
  return (
    <div className="border-b border-line px-4 py-3">
      <div className="flex items-end justify-between gap-3">
        <div>
          <p className="text-[0.6875rem] font-medium text-ink-faint">Match with this posting</p>
          <p className="mt-0.5 text-2xl font-semibold tracking-tight text-ink" data-numeric>
            {pct(c.score)}
            {moved && (
              <span className="ml-2 text-xs font-medium text-confirmed">
                from {pct(c.baseline)} as uploaded
              </span>
            )}
          </p>
        </div>
        <button type="button" onClick={onShowMatrix} className="text-xs font-medium text-brand hover:underline">
          How it's counted
        </button>
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5 text-[0.6875rem]" data-numeric>
        {c.musts > 0 && (
          <span className="rounded-full border border-line px-2 py-0.5 text-ink-soft">
            {c.musts_direct}/{c.musts} must-haves shown in work
          </span>
        )}
        <span className="rounded-full border border-line px-2 py-0.5 text-ink-soft">
          {c.direct} shown · {c.partial} listed · {c.missing} missing
        </span>
        {c.unsupported > 0 && (
          <span className="rounded-full border border-contested-line bg-contested-soft px-2 py-0.5 text-ink">
            {c.unsupported} typed in, unsupported
          </span>
        )}
      </div>
      <div className="mt-2.5 space-y-1">
        {report.sections
          .filter((s) => s.direct.length + s.partial.length > 0)
          .map((section) => {
            const total = Math.max(1, c.requirements);
            return (
              <div key={section.section} className="flex items-center gap-2 text-[0.6875rem]">
                <span className="w-24 shrink-0 truncate text-ink-soft">{section.label}</span>
                <span className="flex h-1.5 flex-1 overflow-hidden rounded-full bg-surface-sunken" aria-hidden>
                  <span className="bg-confirmed" style={{ width: `${(section.direct.length / total) * 100}%` }} />
                  <span className="bg-reported/70" style={{ width: `${(section.partial.length / total) * 100}%` }} />
                </span>
                <span className="w-16 shrink-0 text-right text-ink-faint" data-numeric>
                  {section.direct.length + section.partial.length} of {c.requirements}
                </span>
              </div>
            );
          })}
      </div>
    </div>
  );
}

/* ── the reason, always shown with the change ───────────────────────────── */

function ReasonBox({ s }: { s: TailorSuggestion }) {
  const rows: [string, string][] = [
    ["What should change", s.reason.what],
    ["Why", s.reason.why],
    ["What in the posting it answers", s.reason.addresses],
    ["How it improves the match", s.reason.improves],
  ];
  return (
    <div className="rounded-lg border border-line bg-surface-sunken px-3 py-2.5">
      <p className="text-[0.6875rem] font-semibold tracking-wide text-ink-faint uppercase">Reason for suggestion</p>
      <dl className="mt-1.5 space-y-1.5">
        {rows.map(([label, text]) => (
          <div key={label}>
            <dt className="text-[0.6875rem] font-medium text-ink-faint">{label}</dt>
            <dd className="text-xs leading-relaxed text-ink">{text}</dd>
          </div>
        ))}
        <div>
          <dt className="text-[0.6875rem] font-medium text-ink-faint">Kind of change</dt>
          <dd className="text-xs text-ink">{s.reason.type_label}</dd>
        </div>
      </dl>
    </div>
  );
}

/* ── "is this true of you?" ─────────────────────────────────────────────── */

function Confirm({
  s,
  copy,
  report,
  decide,
  source,
}: {
  s: TailorSuggestion;
  copy: TailoredResume;
  report: TailorReport;
  decide: ReturnType<typeof useDecide>;
  source: string;
}) {
  const requirement = report.requirements.find((r) => r.id === s.requirement_id);
  const options = requirement?.choice.length ? requirement.choice : [requirement?.term ?? s.requirement ?? ""];
  const [term, setTerm] = useState(options[0]);
  const [step, setStep] = useState<"ask" | "where">(s.state === "confirmed" ? "where" : "ask");
  const [line, setLine] = useState<string | null>(null);
  const [mode, setMode] = useState<"draft" | "write">("draft");
  const [draft, setDraft] = useState("");
  const edit = useEditTailoredBlock(copy.resume_id, copy.id);
  const add = useAddTailoredBlock(copy.resume_id, copy.id);
  const note = `${s.reason.why} (you confirmed ${term} is true of you)`;
  const blocks = new Map(copy.blocks.map((b) => [b.id, b]));
  const skillsLine = s.insert_after ? blocks.get(s.insert_after) : undefined;
  const error = edit.error ?? add.error ?? decide.error;

  if (step === "ask") {
    return (
      <div className="space-y-2">
        <p className="text-xs font-medium text-ink">
          {options.length > 1 ? "Do you have one of these?" : `Is “${term}” true of you?`}
        </p>
        {options.length > 1 && (
          <div className="flex flex-wrap gap-1.5">
            {options.map((option) => (
              <button
                key={option}
                type="button"
                aria-pressed={term === option}
                onClick={() => setTerm(option)}
                className={`rounded-full border px-2.5 py-0.5 text-xs ${term === option ? "border-brand bg-brand-soft text-ink" : "border-line text-ink-soft"}`}
              >
                {option}
              </button>
            ))}
          </div>
        )}
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={decide.isPending}
            onClick={() =>
              decide.mutate({ key: s.key, state: "confirmed", term }, { onSuccess: () => setStep("where") })
            }
            className="rounded-md bg-brand px-2.5 py-1 text-xs font-medium text-white hover:bg-brand-hover disabled:opacity-50"
          >
            Yes — I've used it
          </button>
          <button
            type="button"
            disabled={decide.isPending}
            onClick={() => decide.mutate({ key: s.key, state: "rejected" })}
            className="rounded-md border border-line px-2.5 py-1 text-xs font-medium text-ink-soft hover:text-ink"
          >
            No — leave it out
          </button>
        </div>
        <p className="text-[0.6875rem] text-ink-faint">
          If not, nothing is added. Expect the panel to ask about it, and prepare an honest answer.
        </p>
      </div>
    );
  }

  const chosen = line ? blocks.get(line) : undefined;
  return (
    <div className="space-y-2">
      <p className="text-xs font-medium text-ink">Where did you use {term}?</p>
      <ul className="space-y-1">
        {s.candidates.map((id) => {
          const block = blocks.get(id);
          if (!block) return null;
          return (
            <li key={id}>
              <button
                type="button"
                aria-pressed={line === id}
                onClick={() => {
                  setLine(id);
                  setDraft(block.text);
                }}
                className={`w-full rounded-md border px-2.5 py-1.5 text-left text-xs leading-relaxed ${
                  line === id ? "border-brand bg-brand-soft text-ink" : "border-line text-ink-soft hover:border-line-strong"
                }`}
              >
                {clip(block.text, 140)}
              </button>
            </li>
          );
        })}
      </ul>
      {skillsLine && !line && (
        <button
          type="button"
          disabled={edit.isPending}
          onClick={() =>
            edit.mutate({
              blockId: skillsLine.id,
              patch: { text: `${skillsLine.text.replace(/[\s,.;]+$/, "")}, ${term}`, source, note },
            })
          }
          className="text-xs font-medium text-brand hover:underline"
        >
          Just add {term} to “{clip(skillsLine.text, 40)}”
        </button>
      )}
      {chosen && (
        <div className="space-y-2 rounded-md border border-line p-2">
          <div className="flex gap-3 text-xs">
            <button type="button" aria-pressed={mode === "draft"} onClick={() => setMode("draft")} className={mode === "draft" ? "font-semibold text-ink" : "text-ink-soft"}>
              Draft it from my line
            </button>
            <button type="button" aria-pressed={mode === "write"} onClick={() => setMode("write")} className={mode === "write" ? "font-semibold text-ink" : "text-ink-soft"}>
              Write it myself
            </button>
          </div>
          {mode === "draft" ? (
            <TailoredRewrite
              key={chosen.id}
              copy={copy}
              blockId={chosen.id}
              requirement={term}
              jdLine={s.jd_line}
              allowedTerms={[term]}
              source={source}
              note={note}
            />
          ) : (
            <div>
              <textarea
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                rows={3}
                aria-label="Your line"
                className="w-full rounded-md border border-line bg-surface px-2.5 py-1.5 text-xs leading-relaxed text-ink outline-none focus:border-brand"
              />
              <div className="mt-1 flex gap-2">
                <button
                  type="button"
                  disabled={edit.isPending || !draft.trim() || draft.trim() === chosen.text}
                  onClick={() => edit.mutate({ blockId: chosen.id, patch: { text: draft.trim(), source, note } })}
                  className="rounded-md bg-brand px-2.5 py-1 text-xs font-medium text-white disabled:opacity-50"
                >
                  Save this line
                </button>
                <button
                  type="button"
                  disabled={add.isPending || !draft.trim() || draft.trim() === chosen.text}
                  onClick={() => add.mutate({ after: chosen.id, text: draft.trim(), source, note })}
                  className="rounded-md border border-line px-2.5 py-1 text-xs font-medium text-ink-soft disabled:opacity-50"
                >
                  Add as a new line instead
                </button>
              </div>
            </div>
          )}
        </div>
      )}
      <button
        type="button"
        onClick={() => decide.mutate({ key: s.key, state: "open" }, { onSuccess: () => setStep("ask") })}
        className="text-[0.6875rem] text-ink-faint hover:text-ink"
      >
        I'm not sure after all
      </button>
      {error && <p className="text-xs text-contested">{apiProblem(error)}</p>}
    </div>
  );
}

/* ── one suggestion ─────────────────────────────────────────────────────── */

function SuggestionCard({
  s,
  copy,
  report,
  decide,
  open,
  onToggle,
  onFocusBlock,
}: {
  s: TailorSuggestion;
  copy: TailoredResume;
  report: TailorReport;
  decide: ReturnType<typeof useDecide>;
  open: boolean;
  onToggle: () => void;
  onFocusBlock: (blockId: string) => void;
}) {
  const edit = useEditTailoredBlock(copy.resume_id, copy.id);
  const move = useMoveTailoredBlock(copy.resume_id, copy.id);
  const source = `jd:${s.key}`;
  const note = s.reason.why;
  const impact = IMPACT[s.impact];
  const target = s.block_id ? copy.blocks.find((b) => b.id === s.block_id) : undefined;
  const anchor = s.move_before ? copy.blocks.find((b) => b.id === s.move_before) : undefined;
  const busy = edit.isPending || move.isPending;
  const error = edit.error ?? move.error;
  const rejected = s.state === "rejected";

  const apply = () => {
    if (s.action === "replace" && s.block_id && s.after) {
      edit.mutate({ blockId: s.block_id, patch: { text: s.after, source, note, expect_revision: copy.revision } });
    } else if (s.action === "hide" && s.block_id) {
      edit.mutate({ blockId: s.block_id, patch: { hidden: true, source, note } });
    } else if (s.action === "move" && s.block_id) {
      move.mutate({ block_id: s.block_id, before: s.move_before, source, note });
    }
  };

  return (
    <article className={`rounded-lg border bg-surface ${open ? "border-brand-line" : "border-line"} ${rejected ? "opacity-70" : ""}`}>
      <button
        type="button"
        onClick={() => {
          onToggle();
          if (s.block_id) onFocusBlock(s.block_id);
          else if (s.candidates[0]) onFocusBlock(s.candidates[0]);
        }}
        aria-expanded={open}
        className="w-full px-3 py-2.5 text-left"
      >
        <div className="flex items-center gap-1.5 text-[0.6875rem] text-ink-faint">
          <span aria-hidden className={`size-1.5 rounded-full ${impact.dot}`} />
          <span>{impact.label}</span>
          <span>·</span>
          <span>{s.reason.type_label}</span>
          {s.state === "confirmed" && <span className="ml-auto font-medium text-confirmed">you said yes</span>}
          {rejected && <span className="ml-auto font-medium">dismissed</span>}
        </div>
        <p className="mt-0.5 text-sm font-medium text-ink">{s.title}</p>
        {!open && <p className="mt-0.5 line-clamp-2 text-xs text-ink-soft">{s.reason.what}</p>}
      </button>

      {open && (
        <div className="space-y-2.5 border-t border-line px-3 py-2.5">
          {s.action === "replace" && s.before && s.after && <FixDiff original={s.before} suggestion={s.after} compact />}
          {s.action === "hide" && target && (
            <FixDiff original={target.text} suggestion="(hidden from this version — kept in your resume)" compact />
          )}
          {s.action === "move" && target && anchor && (
            <p className="rounded-md border border-line bg-surface-sunken px-2.5 py-1.5 text-xs text-ink">
              <span className="font-medium">{clip(target.text.split("|")[0], 60)}</span> moves above{" "}
              <span className="font-medium">{clip(anchor.text.split("|")[0], 60)}</span>, with its bullets.
            </p>
          )}

          <ReasonBox s={s} />

          {!rejected && s.action === "draft" && s.block_id && (
            <TailoredRewrite
              copy={copy}
              blockId={s.block_id}
              requirement={s.requirement ?? ""}
              jdLine={s.jd_line}
              source={source}
              note={note}
            />
          )}
          {!rejected && s.action === "confirm" && (
            <Confirm s={s} copy={copy} report={report} decide={decide} source={source} />
          )}

          <div className="flex flex-wrap items-center gap-2">
            {!rejected && ["replace", "hide", "move"].includes(s.action) && (
              <button
                type="button"
                disabled={busy}
                onClick={apply}
                className="rounded-md bg-brand px-2.5 py-1 text-xs font-medium text-white hover:bg-brand-hover disabled:opacity-50"
              >
                {busy ? "Applying…" : "Accept"}
              </button>
            )}
            {!rejected && s.action !== "confirm" && (
              <button
                type="button"
                disabled={decide.isPending}
                onClick={() => decide.mutate({ key: s.key, state: "rejected" })}
                className="rounded-md border border-line px-2.5 py-1 text-xs font-medium text-ink-soft hover:text-ink"
              >
                Reject
              </button>
            )}
            {rejected && (
              <button
                type="button"
                onClick={() => decide.mutate({ key: s.key, state: "open" })}
                className="text-xs font-medium text-brand hover:underline"
              >
                Bring it back
              </button>
            )}
            {s.block_id && (
              <span className="ml-auto text-[0.6875rem] text-ink-faint">You can edit any line by hand in the middle.</span>
            )}
          </div>
          {error && <p className="text-xs text-contested">{apiProblem(error)}</p>}
        </div>
      )}
    </article>
  );
}

/* ── the coverage matrix ────────────────────────────────────────────────── */

function Matrix({
  report,
  copy,
  onTrace,
}: {
  report: TailorReport;
  copy: TailoredResume;
  onTrace: (req: TailorRequirement, hit?: TailorHit) => void;
}) {
  const blocks = new Map(copy.blocks.map((b) => [b.id, b]));
  const quoted = report.requirements.filter((r) => !r.inferred);
  const implied = report.requirements.filter((r) => r.inferred);
  const order = { must: 0, should: 1, could: 2 } as Record<string, number>;
  const rows = [...quoted].sort((a, b) => (order[a.necessity] ?? 3) - (order[b.necessity] ?? 3) || b.weight - a.weight);
  const [showImplied, setShowImplied] = useState(false);

  const row = (req: TailorRequirement) => {
    const status = STATUS[req.status] ?? STATUS.missing;
    const best =
      req.hits.find((h) => h.level === "direct" && h.how === "named") ?? req.hits.find((h) => h.natural) ?? req.hits[0];
    const where = [...new Set(req.hits.map((h) => blocks.get(h.block_id)?.section ?? h.section))];
    return (
      <tr key={req.id} className="border-t border-line align-top">
        <td className="py-1.5 pr-2">
          <button
            type="button"
            onClick={() => onTrace(req, best)}
            className="text-left text-xs font-medium text-ink hover:text-brand"
            title={req.jd_line ?? undefined}
          >
            {req.term}
          </button>
          <span className="ml-1 text-[0.625rem] text-ink-faint">{NECESSITY[req.necessity] ?? req.necessity}</span>
        </td>
        <td className="py-1.5 pr-2">
          <span className={`inline-block rounded-full border px-1.5 text-[0.625rem] font-medium whitespace-nowrap text-ink ${status.className}`}>
            {req.status === "alternative" && req.met_by ? `Met by ${req.met_by}` : status.label}
          </span>
        </td>
        <td className="py-1.5 text-[0.6875rem] text-ink-soft">
          {where.length ? (
            <button type="button" onClick={() => onTrace(req, best)} className="text-left hover:text-brand">
              {where.join(", ")}
            </button>
          ) : (
            "—"
          )}
        </td>
      </tr>
    );
  };

  return (
    <div className="px-4 py-3">
      <p className="text-xs text-ink-soft">
        Every requirement the posting states, how strongly your resume evidences it, and where. Click one to see the
        line on the page next to the posting's own words.
      </p>
      <table className="mt-2 w-full border-collapse">
        <thead>
          <tr className="text-left text-[0.625rem] tracking-wide text-ink-faint uppercase">
            <th className="pb-1 font-medium">Requirement</th>
            <th className="pb-1 font-medium">Evidence</th>
            <th className="pb-1 font-medium">Where</th>
          </tr>
        </thead>
        <tbody>{rows.map(row)}</tbody>
      </table>
      <p className="mt-3 text-[0.6875rem] leading-relaxed text-ink-faint">
        The match counts each requirement by its weight in the posting: 1 when a line of work names it, ½ when only
        the skills list or summary does (or says it in other words), 0 otherwise. A word you typed in that your
        uploaded resume never had counts for nothing until you confirm it is true.
      </p>
      {implied.length > 0 && (
        <div className="mt-3">
          <button type="button" onClick={() => setShowImplied((on) => !on)} className="text-xs font-medium text-ink-soft hover:text-ink">
            {showImplied ? "Hide" : "Show"} {implied.length} implied by the role, not quoted
          </button>
          {showImplied && (
            <table className="mt-1 w-full border-collapse opacity-75">
              <tbody>{implied.map(row)}</tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}

/* ── keyword coverage ───────────────────────────────────────────────────── */

function Keywords({ report, onTrace }: { report: TailorReport; onTrace: (req: TailorRequirement) => void }) {
  const byId = new Map(report.requirements.map((r) => [r.id, r]));
  const groups: [string, string, string, typeof report.keywords][] = [
    ["natural", "On your resume as uploaded", "border-confirmed-line bg-confirmed-soft", report.keywords.filter((k) => k.state === "natural")],
    ["inserted", "Added while tailoring", "border-reported-line bg-reported-soft", report.keywords.filter((k) => k.state === "inserted")],
    ["missing", "Missing", "border-line bg-surface-sunken text-ink-soft", report.keywords.filter((k) => k.state === "missing")],
  ];
  return (
    <div className="space-y-3 px-4 py-3">
      {groups.map(([key, label, tone, items]) => (
        <div key={key}>
          <p className="text-[0.6875rem] font-medium text-ink-faint">
            {label} <span data-numeric>· {items.length}</span>
          </p>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {items.length === 0 && <span className="text-xs text-ink-faint">None</span>}
            {items.map((k) => {
              const req = byId.get(k.requirement_id);
              return (
                <button
                  key={k.requirement_id}
                  type="button"
                  onClick={() => req && onTrace(req)}
                  className={`rounded-full border px-2 py-0.5 text-xs text-ink ${tone}`}
                >
                  {req?.term ?? k.term}
                  {key === "inserted" && req?.status === "unsupported" && " · unsupported"}
                </button>
              );
            })}
          </div>
        </div>
      ))}
      <p className="text-[0.6875rem] leading-relaxed text-ink-faint">
        “Added while tailoring” means the word is only in a line you edited or added. It is fine when it is true —
        and it is flagged in red when your uploaded resume gives it no support.
      </p>
    </div>
  );
}

/* ── the panel ──────────────────────────────────────────────────────────── */

export function TailorIntel({
  report,
  copy,
  jdId,
  candidateId,
  updating,
  onTrace,
  onFlag,
  onFocusBlock,
  onCollapse,
}: {
  report: TailorReport;
  copy: TailoredResume;
  jdId: string;
  candidateId: string;
  updating: boolean;
  onTrace: (req: TailorRequirement, hit?: TailorHit) => void;
  onFlag: (flag: TailorFlag) => void;
  onFocusBlock: (blockId: string) => void;
  onCollapse?: () => void;
}) {
  const decide = useDecide(jdId, candidateId);
  const [tab, setTab] = useState<"suggestions" | "requirements" | "keywords">("suggestions");
  const [openKey, setOpenKey] = useState<string | null>(null);
  const [showRejected, setShowRejected] = useState(false);

  const active = report.suggestions.filter((s) => s.state !== "rejected");
  const rejected = report.suggestions.filter((s) => s.state === "rejected");
  const grouped = useMemo(
    () =>
      CATEGORY_ORDER.map((category) => [category, active.filter((s) => s.category === category)] as const).filter(
        ([, items]) => items.length > 0,
      ),
    [active],
  );
  const flagged = report.flags.filter((f) => f.terms.length > 0);

  return (
    <section aria-label="What this posting asks for" className="panel flex min-h-0 flex-col overflow-hidden bg-surface">
      <div className="flex items-center gap-2 border-b border-line px-4 py-2.5">
        <p className="text-sm font-semibold text-ink">Job match</p>
        {updating && <span className="text-xs text-ink-faint">re-checking…</span>}
        {onCollapse && (
          <button type="button" onClick={onCollapse} className="ml-auto text-xs font-medium text-ink-soft hover:text-ink" title="Hide this panel">
            Hide
          </button>
        )}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        <MatchHeader report={report} onShowMatrix={() => setTab("requirements")} />

        {flagged.length > 0 && (
          <div className="border-b border-line bg-contested-soft/60 px-4 py-2.5">
            <p className="text-xs font-semibold text-ink">Check before you send</p>
            <ul className="mt-1 space-y-1">
              {flagged.map((flag) => (
                <li key={flag.block_id}>
                  <button type="button" onClick={() => onFlag(flag)} className="text-left text-xs text-ink hover:underline">
                    {flag.terms.join(", ")} — not in the resume you uploaded
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div role="tablist" className="flex gap-1 border-b border-line px-3">
          {(
            [
              ["suggestions", `Suggestions · ${active.length}`],
              ["requirements", `Requirements · ${report.coverage.requirements}`],
              ["keywords", "Keywords"],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              role="tab"
              type="button"
              aria-selected={tab === key}
              onClick={() => setTab(key)}
              className={`-mb-px border-b-2 px-2 py-2 text-xs font-medium ${tab === key ? "border-brand text-ink" : "border-transparent text-ink-soft hover:text-ink"}`}
            >
              {label}
            </button>
          ))}
        </div>

        {tab === "suggestions" && (
          <div className="space-y-4 px-3 py-3">
            {active.length === 0 && (
              <p className="px-1 text-sm text-ink-soft">
                Nothing left to suggest for this posting. Read the PDF through once more, then download it.
              </p>
            )}
            {grouped.map(([category, items]) => (
              <div key={category}>
                <p className="px-1 text-[0.6875rem] font-semibold tracking-wide text-ink-faint uppercase">
                  {CATEGORY_LABEL[category]} <span data-numeric>· {items.length}</span>
                </p>
                <div className="mt-1.5 space-y-2">
                  {items.map((s) => (
                    <SuggestionCard
                      key={s.key}
                      s={s}
                      copy={copy}
                      report={report}
                      decide={decide}
                      open={openKey === s.key}
                      onToggle={() => setOpenKey((key) => (key === s.key ? null : s.key))}
                      onFocusBlock={onFocusBlock}
                    />
                  ))}
                </div>
              </div>
            ))}
            {rejected.length > 0 && (
              <div>
                <button type="button" onClick={() => setShowRejected((on) => !on)} className="px-1 text-xs font-medium text-ink-soft hover:text-ink">
                  {showRejected ? "Hide" : "Show"} {rejected.length} dismissed
                </button>
                {showRejected && (
                  <div className="mt-1.5 space-y-2">
                    {rejected.map((s) => (
                      <SuggestionCard
                        key={s.key}
                        s={s}
                        copy={copy}
                        report={report}
                        decide={decide}
                        open={openKey === s.key}
                        onToggle={() => setOpenKey((key) => (key === s.key ? null : s.key))}
                        onFocusBlock={onFocusBlock}
                      />
                    ))}
                  </div>
                )}
              </div>
            )}
            {decide.error && <p className="px-1 text-xs text-contested">{apiProblem(decide.error)}</p>}
          </div>
        )}
        {tab === "requirements" && <Matrix report={report} copy={copy} onTrace={onTrace} />}
        {tab === "keywords" && <Keywords report={report} onTrace={(req) => onTrace(req)} />}
      </div>
    </section>
  );
}
