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
 * Door 2 now takes a FILE as well as pasted text (FR-2.1), which is the half
 * of it that was missing: §1 calls the input "usually a badly formatted blob
 * from a placement-portal email", and such a mail arrives as an attachment at
 * least as often as it arrives as a body a student can select.
 *
 * Doors 1 and 3 still do not exist, because neither has a backend — there is no
 * company picker, no role archetype and no drives feed. Rendering them greyed
 * out would be the honest-looking version of the same problem: a student
 * clicks, nothing happens, and the product looks broken rather than unfinished.
 * So they are named in a note instead, which is what the platform does
 * everywhere else — absent, not stubbed, and said out loud.
 */

import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { useParseJd, useUploadJd } from "../api";
import {
  Btn,
  ErrorNote,
  Panel,
  Section,
  TextArea,
  TextField,
} from "../ui/primitives";

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
  const upload = useUploadJd();
  const [dragging, setDragging] = useState(false);

  const [company, setCompany] = useState("");
  const [role, setRole] = useState("");
  const [text, setText] = useState("");

  const canSubmit =
    company.trim() && role.trim() && text.trim() && !parse.isPending;

  /**
   * Upload, refusing early when the company and role are blank.
   *
   * They are two thirds of the content hash (FR-2.12), so an upload without
   * them would either 422 from the backend after the file had been read, or —
   * worse, if they were defaulted — merge two different drives at the same firm
   * into one cached parse.
   */
  function sendFile(file: File) {
    if (!company.trim() || !role.trim()) {
      window.alert(
        "Fill in the company and role first — they identify the posting.",
      );
      return;
    }
    upload.mutate(
      { company_name: company.trim(), role_title: role.trim(), file },
      { onSuccess: (jd) => navigate(`/jds/${jd.id}`) },
    );
  }

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
        <h1 className="text-display font-semibold text-ink">
          What are you preparing for?
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-ink-soft">
          Paste the job description &mdash; the messy placement-cell email is
          fine, that is the normal case. We read the requirements out of it and
          show where you stand against each one.
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

            {/* The file door. Above the textarea rather than beside it,
                because a student holding an attachment should not have to read
                past a 12-row text box to find out they can just drop it. */}
            <div>
              <p className="rule-label mb-1.5">Job description</p>
              <label
                onDragOver={(event) => {
                  event.preventDefault();
                  setDragging(true);
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={(event) => {
                  event.preventDefault();
                  setDragging(false);
                  const dropped = event.dataTransfer.files?.[0];
                  if (dropped) sendFile(dropped);
                }}
                className={`flex cursor-pointer flex-wrap items-center justify-center gap-2 rounded-md border border-dashed px-4 py-4 text-sm transition-colors ${
                  dragging
                    ? "border-brand bg-brand-soft text-brand"
                    : "border-line text-ink-soft hover:border-ink-faint hover:text-ink"
                }`}
              >
                <input
                  type="file"
                  accept=".pdf,.docx,.txt,application/pdf,text/plain"
                  className="sr-only"
                  onChange={(event) => {
                    const picked = event.target.files?.[0];
                    if (picked) sendFile(picked);
                    event.target.value = "";
                  }}
                />
                {upload.isPending ? (
                  <span>Reading the file&hellip;</span>
                ) : (
                  <>
                    <span className="font-medium">
                      Drop a PDF, .docx or .txt
                    </span>
                    <span className="text-ink-faint">
                      or click to choose one
                    </span>
                  </>
                )}
              </label>
              <p className="mt-1.5 text-xs text-ink-faint">
                Needs the company and role above first &mdash; they are part of
                what identifies this posting, so two drives at the same firm do
                not collapse into one.
              </p>
            </div>

            {upload.isError && (
              <ErrorNote>
                {upload.error instanceof Error
                  ? upload.error.message
                  : "Upload failed"}
              </ErrorNote>
            )}

            <TextArea
              label="Or paste it"
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
                {parse.error instanceof Error
                  ? parse.error.message
                  : "unknown error"}
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
            The spec&rsquo;s input screen has three doors. This is the second
            one.
          </p>
          <ul className="mt-2 space-y-1.5 text-sm text-ink-soft">
            <li>
              <strong className="font-medium text-ink">Pick a company</strong>{" "}
              &mdash; needs the company + drive-variant table (§3.2). Not built.
            </li>
            <li>
              <strong className="font-medium text-ink">Just pick a role</strong>{" "}
              &mdash; needs the role-archetype library and{" "}
              <code className="provenance">/v1/archetypes</code> (§6.3). Not
              built, and the spec calls this door mandatory: a student with no
              drive scheduled cannot use this module at all today.
            </li>
            <li>
              <strong className="font-medium text-ink">
                Campus-drive chips
              </strong>{" "}
              &mdash; needs the placement-cell calendar. Not built.
            </li>
          </ul>
          <p className="mt-2.5 text-xs text-ink-faint">
            Listed rather than greyed out on purpose. A control that looks live
            and does nothing reads as a broken product; a named gap reads as an
            unfinished one.
          </p>
        </Panel>
      </Section>
    </>
  );
}
