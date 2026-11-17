/**
 * One line of the resume, traced to the line of the posting it answers
 * (2026-11-17).
 *
 * Opened from a tag on a line, a row of the requirement matrix, or a flag. It
 * shows both sides in their own words — the resume's sentence with the matched
 * words marked, the posting's line with the requirement marked, the heading it
 * sits under — and says in one sentence why they were connected and how
 * strongly. Nothing here is a model's opinion: every word is quoted from one
 * of the two documents, and the "why" is how the match was made.
 */
import type { TailorFlag, TailorHit, TailorRequirement } from "../types";

const SUPPORT: Record<string, { label: string; className: string }> = {
  direct: { label: "Directly supported", className: "bg-confirmed-soft text-ink border-confirmed-line" },
  partial: { label: "Partially supported", className: "bg-reported-soft text-ink border-reported-line" },
  unsupported: { label: "Unsupported", className: "bg-contested-soft text-ink border-contested-line" },
};

function support(hit: TailorHit, confirmed: boolean): keyof typeof SUPPORT {
  if (!hit.natural && !confirmed) return "unsupported";
  return hit.level === "direct" && hit.how === "named" ? "direct" : "partial";
}

function why(req: TailorRequirement, hit: TailorHit, confirmed: boolean): string {
  if (!hit.natural && !confirmed) {
    return `“${hit.term}” is only in a line you edited or added — the resume you uploaded never says it. It does not count until you confirm it is true.`;
  }
  if (!hit.natural && confirmed) {
    return `You added “${hit.term}” and said it is true of you. It counts — be ready to explain it.`;
  }
  switch (hit.how) {
    case "named":
      return `This line names “${hit.term}” in something you did — the evidence a recruiter looks for.`;
    case "listed":
      return `“${hit.term}” is in your skills list: named, but not shown in use anywhere.`;
    case "summary":
      return `“${hit.term}” is in your summary: a claim about yourself, not a thing you did.`;
    default:
      return `This line says “${hit.term}”; the posting says “${req.text}”. Your resume's own reading maps both to one skill, but an exact keyword screen will not.`;
  }
}

function Marked({ text, start, end }: { text: string; start: number; end: number }) {
  if (start < 0 || end > text.length || start >= end) return <>{text}</>;
  return (
    <>
      {text.slice(0, start)}
      <mark className="rounded-sm bg-reported-soft px-0.5 font-medium text-ink">{text.slice(start, end)}</mark>
      {text.slice(end)}
    </>
  );
}

/** The sentence of `text` that holds [start, end), re-based — not the whole paragraph. */
function sentenceOf(text: string, start: number, end: number): { text: string; start: number; end: number } {
  const before = text.slice(0, start);
  const cut = Math.max(before.lastIndexOf(". "), before.lastIndexOf("; "));
  let from = cut >= 0 ? cut + 2 : 0;
  const after = text.slice(end).search(/[.;](\s|$)/);
  let to = after >= 0 ? end + after + 1 : text.length;
  if (start - from > 140) from = start - 120;
  if (to - end > 160) to = end + 140;
  const lead = from > 0 ? "…" : "";
  const tail = to < text.length ? "…" : "";
  return {
    text: lead + text.slice(from, to).trim() + tail,
    start: start - from + lead.length,
    end: end - from + lead.length,
  };
}

function PostingLine({ req }: { req: TailorRequirement }) {
  if (!req.jd_line) {
    return <p className="text-xs text-ink-faint">Implied by the role — not quoted from the posting.</p>;
  }
  const quote = req.quote ?? req.text;
  const at = req.jd_line.toLowerCase().indexOf(quote.toLowerCase());
  return (
    <blockquote className="rounded-md border-l-2 border-brand-line bg-surface-sunken px-2.5 py-1.5 text-xs leading-relaxed text-ink">
      {at >= 0 ? <Marked text={req.jd_line} start={at} end={at + quote.length} /> : req.jd_line}
    </blockquote>
  );
}

export function TracePopup({
  requirement,
  hit,
  line,
  confirmed,
  onClose,
}: {
  requirement: TailorRequirement;
  hit: TailorHit;
  /** The resume line's text as it reads now. */
  line: string;
  confirmed: boolean;
  onClose: () => void;
}) {
  const level = support(hit, confirmed);
  const tone = SUPPORT[level];
  return (
    <div className="rounded-xl border border-line-strong bg-surface p-3.5 text-left shadow-[0_12px_32px_-12px_oklch(0_0_0/0.35)]">
      <div className="flex items-start justify-between gap-2">
        <p className="text-[0.6875rem] font-semibold tracking-wide text-ink-faint uppercase">Claim check</p>
        <span className={`rounded-full border px-2 py-0.5 text-[0.6875rem] font-semibold ${tone.className}`}>
          {tone.label}
        </span>
      </div>

      <p className="mt-2 text-[0.6875rem] font-medium text-ink-faint">Your resume says</p>
      <p className="mt-0.5 text-xs leading-relaxed text-ink">
        <Marked {...sentenceOf(line, hit.start, hit.end)} />
      </p>

      <p className="mt-2.5 text-[0.6875rem] font-medium text-ink-faint">
        The posting asks for <span className="text-ink">{requirement.text}</span>
        <span className="ml-1.5 rounded-full border border-line px-1.5 text-[0.625rem]">
          {requirement.necessity === "must" ? "must-have" : requirement.necessity === "could" ? "nice to have" : "expected"}
        </span>
        {requirement.jd_heading && <span> · under “{requirement.jd_heading}”</span>}
      </p>
      <div className="mt-1">
        <PostingLine req={requirement} />
      </div>

      <p className="mt-2.5 text-[0.6875rem] font-medium text-ink-faint">Why they are connected</p>
      <p className="mt-0.5 text-xs leading-relaxed text-ink-soft">{why(requirement, hit, confirmed)}</p>

      <div className="mt-3 flex justify-end">
        <button type="button" onClick={onClose} className="text-xs font-medium text-ink-soft hover:text-ink">
          Close
        </button>
      </div>
    </div>
  );
}

/** The same card for a line that says something the uploaded resume never did. */
export function FlagPopup({ flag, line, onClose }: { flag: TailorFlag; line: string; onClose: () => void }) {
  return (
    <div className="rounded-xl border border-contested-line bg-surface p-3.5 text-left shadow-[0_12px_32px_-12px_oklch(0_0_0/0.35)]">
      <div className="flex items-start justify-between gap-2">
        <p className="text-[0.6875rem] font-semibold tracking-wide text-ink-faint uppercase">Check before you send</p>
        <span className="rounded-full border border-contested-line bg-contested-soft px-2 py-0.5 text-[0.6875rem] font-semibold text-ink">
          {flag.terms.length ? "Not in your uploaded resume" : "Confirmed by you"}
        </span>
      </div>
      <p className="mt-2 text-xs leading-relaxed text-ink">{line}</p>
      <p className="mt-2 text-xs leading-relaxed text-ink-soft">{flag.message}</p>
      <div className="mt-3 flex justify-end">
        <button type="button" onClick={onClose} className="text-xs font-medium text-ink-soft hover:text-ink">
          Close
        </button>
      </div>
    </div>
  );
}
