/**
 * §2.3 door 1 — pick a company, then the drive you are actually sitting.
 *
 * The spec calls the drive chips "the highest-value element on this screen",
 * and this page carried a note for weeks saying they did not exist because
 * there was no company table. There still is not one, and there should not be:
 * M15 owns companies, aliases and drive variants, and §3.2's fifth hard part is
 * that keeping a second copy is exactly how the two drift. M15 is running now,
 * so the door is built against it.
 *
 * ── Why the chip and not just the company ───────────────────────────────────
 *
 * "TCS" is not an interview. TCS NQT, TCS Digital and TCS Ninja are three, with
 * different packages, different bars and different questions. A student who
 * picks the company and not the drive gets an average of three interviews, two
 * of which they are not sitting.
 *
 * So the chip carries its figures — package, bond, locations — and the student
 * sees them before committing. That is the same rule door 3 follows by showing
 * the requirement list before you pick a role: a button that produces an
 * interview about something unspecified is not a door, it is a surprise.
 *
 * ── Rule 2 ─────────────────────────────────────────────────────────────────
 *
 * M15 down means no companies come back, and this renders as a named absence
 * rather than an empty box or a spinner that never resolves. The other two
 * doors are untouched, which is the whole point of the rule.
 */

import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { useCompanies, useDeps, useDrives, useParseFromDrive } from "../api";
import type { DriveOption } from "../types";
import { ErrorNote, Panel, Section } from "../ui/primitives";

function figures(drive: DriveOption): string {
  const parts: string[] = [];
  if (drive.typical_package_lpa !== null)
    parts.push(`${drive.typical_package_lpa.toFixed(1)} LPA reported`);
  if (drive.bond_months !== null) parts.push(`${drive.bond_months}-month bond`);
  if (drive.typical_locations.length > 0)
    parts.push(drive.typical_locations.slice(0, 3).join(", "));
  return parts.join(" · ");
}

export function CompanyDoor() {
  const [query, setQuery] = useState("");
  const [companyId, setCompanyId] = useState<string | null>(null);
  const navigate = useNavigate();

  const companies = useCompanies(query);
  const drives = useDrives(companyId ?? undefined);
  const fromDrive = useParseFromDrive();
  const deps = useDeps();

  const m15 = deps.data?.find((d) => d.module_id === "M15");
  const chosen = companies.data?.find((c) => c.id === companyId);

  if (m15 && !m15.available) {
    return (
      <Section label="Pick a company">
        <Panel tone="sunken" className="px-4 py-3.5">
          <p className="text-sm text-ink-soft">{m15.on_missing}</p>
          <p className="mt-2 text-xs text-ink-faint">
            The other two doors are unaffected &mdash; paste the posting or pick
            a role below.
          </p>
        </Panel>
      </Section>
    );
  }

  return (
    <Section
      label="Pick a company"
      meta={companies.data ? `${companies.data.length} known` : undefined}
    >
      <Panel className="p-5">
        <p className="text-sm text-ink-soft">
          For a drive that is already on the calendar. We use what students who
          sat it reported &mdash; the package, the bond, and the topics that
          keep coming up &mdash; so you do not need the posting.
        </p>

        <label className="mt-4 block">
          <span className="rule-label">Company</span>
          <input
            type="search"
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setCompanyId(null);
            }}
            placeholder="TCS, Cognizant, Zoho…"
            className="mt-1.5 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-faint focus:border-brand focus:outline-none"
          />
        </label>

        {companies.data && companies.data.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {companies.data.slice(0, 12).map((company) => (
              <button
                key={company.id}
                type="button"
                onClick={() =>
                  setCompanyId(company.id === companyId ? null : company.id)
                }
                className={`rounded-full border px-3 py-1 text-sm transition-colors ${
                  company.id === companyId
                    ? "border-brand bg-brand text-white"
                    : "border-line text-ink hover:border-brand"
                }`}
              >
                {company.name}
                {company.report_count > 0 && (
                  <span
                    className={
                      company.id === companyId
                        ? "ml-1.5 text-white/70"
                        : "ml-1.5 text-ink-faint"
                    }
                  >
                    {company.report_count}
                  </span>
                )}
              </button>
            ))}
          </div>
        )}

        {companies.data?.length === 0 && query.trim() !== "" && (
          <p className="mt-3 text-sm text-ink-soft">
            No company by that name has been reported yet. Paste the posting
            below instead &mdash; and if you sit the drive, the next student
            searching this gets what you did not.
          </p>
        )}

        {/* The chips. §2.3's highest-value element, and the reason picking the
            company alone is not enough: one company runs several interviews. */}
        {companyId && drives.data && (
          <div className="mt-5">
            <span className="rule-label">
              Which drive {chosen ? `at ${chosen.name}` : ""}
            </span>
            {drives.data.length === 0 ? (
              <p className="mt-1.5 text-sm text-ink-soft">
                No specific drives recorded for this company yet. Pick a role
                below, or paste the posting.
              </p>
            ) : (
              <div className="mt-2 grid gap-2 sm:grid-cols-2">
                {drives.data.map((drive) => (
                  <button
                    key={drive.id}
                    type="button"
                    disabled={
                      drive.archetype_id === null || fromDrive.isPending
                    }
                    onClick={() =>
                      fromDrive.mutate(
                        { company_id: drive.company_id, drive_id: drive.id },
                        { onSuccess: (jd) => navigate(`/jds/${jd.id}`) },
                      )
                    }
                    className="rounded-md border border-line px-3.5 py-2.5 text-left transition-colors hover:border-brand disabled:cursor-not-allowed disabled:opacity-55 disabled:hover:border-line"
                  >
                    <span className="block text-sm font-medium text-ink">
                      {drive.name}
                    </span>
                    <span className="provenance mt-0.5 block">
                      {drive.archetype_id === null
                        ? "we do not know which role this drive hires for"
                        : figures(drive) || "no figures reported yet"}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {fromDrive.isError && (
          <div className="mt-4">
            <ErrorNote>
              {fromDrive.error instanceof Error
                ? fromDrive.error.message
                : "Could not set that up"}
            </ErrorNote>
          </div>
        )}
      </Panel>
    </Section>
  );
}
