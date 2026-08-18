/**
 * Paste a job description.
 *
 * Spec: plan_in_depth/M02_JD_Parser.md §2.3 (Screen 1 — "Input, with three doors")
 *
 * ── One door of three, and the page says so ──────────────────────────────────
 *
 * The spec's Screen 1 has three: pick a company, paste a JD, or just pick a
 * role. It calls door 3 **mandatory** — "a student in September with no drive
 * scheduled still needs to practise. Requiring a JD to use the product would be
 * a self-inflicted wound" — and it calls the campus-drive chips the
 * highest-value element on the screen.
 *
 * Only door 2 exists, because only door 2 has a backend. `POST /v1/jds/parse`
 * takes text; there is no company picker, no role archetype, and no drives
 * feed. Rendering the other two doors greyed out would be the honest-looking
 * version of the same problem — a student clicks, nothing happens, and the
 * product looks broken rather than unfinished. So they are named in a note
 * instead, which is what the platform does everywhere else: absent, not
 * stubbed, and said out loud.
 */

import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { useParseJd } from "../api";
import { Btn, ErrorNote, Panel, Section, TextArea, TextField } from "../ui/primitives";

const SAMPLE = `Company: XYZ Technologies
Role: Software Engineer Trainee
Package: 6.5 LPA (4.5 fixed + 2 variable)
Eligibility: 7.5 CGPA, no active backlogs, CSE/IT/ECE
JD: Good knowledge of DSA, OOPs, DBMS. Should be a team player with
excellent communication. Knowledge of any one of Java/Python/C++.
Bond: 18 months`;

export function ParsePage() {
  const navigate = useNavigate();
  const parse = useParseJd();

  const [company, setCompany] = useState("");
  const [role, setRole] = useState("");
  const [text, setText] = useState("");

  const canSubmit = company.trim() && role.trim() && text.trim() && !parse.isPending;

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!canSubmit) return;
    parse.mutate(
      { company_name: company.trim(), role_title: role.trim(), raw_text: text },
      { onSuccess: (jd) => navigate(`/jds/${jd.id}`) },
    );
  }

  return (
    <>
      <header className="mb-8">
        <h1 className="text-display font-semibold text-ink">What are you preparing for?</h1>
        <p className="mt-2 max-w-2xl text-sm text-ink-soft">
          Paste the job description &mdash; the messy placement-cell email is fine, that is the
          normal case. We read the requirements out of it and show where you stand against each
          one.
        </p>
      </header>

      <Section label="Paste a JD">
        <Panel className="p-5">
          <form onSubmit={submit} className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <TextField
                label="Company"
                value={company}
                onChange={(e) => setCompany(e.target.value)}
                placeholder="XYZ Technologies"
                required
              />
              <TextField
                label="Role"
                value={role}
                onChange={(e) => setRole(e.target.value)}
                placeholder="Software Engineer Trainee"
                required
              />
            </div>

            <TextArea
              label="Job description"
              hint="Any format. Forwarded emails, signatures and eligibility tables are fine."
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={12}
              placeholder={SAMPLE}
              required
            />

            {parse.isError && (
              <ErrorNote>
                The parse failed. Check that the API is up on :8102 &mdash;{" "}
                {parse.error instanceof Error ? parse.error.message : "unknown error"}
              </ErrorNote>
            )}

            <div className="flex flex-wrap items-center gap-3">
              <Btn type="submit" variant="primary" disabled={!canSubmit}>
                {parse.isPending ? "Reading it…" : "Read the requirements"}
              </Btn>
              <Btn
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => {
                  setCompany("XYZ Technologies");
                  setRole("Software Engineer Trainee");
                  setText(SAMPLE);
                }}
              >
                Use a sample campus JD
              </Btn>
            </div>
          </form>
        </Panel>
      </Section>

      <Section label="Not built yet">
        <Panel tone="sunken" className="px-4 py-3.5">
          <p className="text-sm text-ink-soft">
            The spec&rsquo;s input screen has three doors. This is the second one.
          </p>
          <ul className="mt-2 space-y-1.5 text-sm text-ink-soft">
            <li>
              <strong className="font-medium text-ink">Pick a company</strong> &mdash; needs the
              company + drive-variant table (§3.2). Not built.
            </li>
            <li>
              <strong className="font-medium text-ink">Just pick a role</strong> &mdash; needs the
              role-archetype library and <code className="provenance">/v1/archetypes</code> (§6.3).
              Not built, and the spec calls this door mandatory: a student with no drive scheduled
              cannot use this module at all today.
            </li>
            <li>
              <strong className="font-medium text-ink">Campus-drive chips</strong> &mdash; needs the
              placement-cell calendar. Not built.
            </li>
          </ul>
          <p className="mt-2.5 text-xs text-ink-faint">
            Listed rather than greyed out on purpose. A control that looks live and does nothing
            reads as a broken product; a named gap reads as an unfinished one.
          </p>
        </Panel>
      </Section>
    </>
  );
}
