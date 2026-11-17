/**
 * The three ways to work on one job description, one click apart (2026-11-17).
 *
 * The same tab row M01 puts over a resume (`ResumeTabs`), so the two modules
 * read as one product: a resume has "Review & fix · What they'll ask · Job
 * match", a job has "Tailor your resume · The posting & interview · Can you sit it".
 */
import { Link } from "react-router-dom";

const TABS = [
  { key: "tailor", label: "Tailor your resume", path: "/tailor" },
  { key: "posting", label: "The posting & interview plan", path: "" },
  { key: "eligibility", label: "Can you sit it", path: "/match" },
] as const;

export type JdTab = (typeof TABS)[number]["key"];

export function JdTabs({ jdId, active }: { jdId: string; active: JdTab }) {
  return (
    <nav
      aria-label="Ways to work on this job"
      className="flex gap-1 overflow-x-auto border-b border-line [scrollbar-width:none]"
    >
      {TABS.map((tab) => {
        const on = tab.key === active;
        return (
          <Link
            key={tab.key}
            to={`/jds/${jdId}${tab.path}`}
            aria-current={on ? "page" : undefined}
            className={`-mb-px shrink-0 border-b-2 px-3 py-2 text-sm font-medium ${
              on ? "border-brand text-ink" : "border-transparent text-ink-soft hover:text-ink"
            }`}
          >
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}
