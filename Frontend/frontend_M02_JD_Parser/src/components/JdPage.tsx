/**
 * The requirement read-back, and the gap.
 *
 * Spec: plan_in_depth/M02_JD_Parser.md §2.3 (Screen 2)
 *
 * The spec's Screen 2 groups requirements into MUST / SHOULD, weights them,
 * resolves disjunctions, banners the eligibility criteria, highlights ONE gap
 * with a time-to-close estimate, and offers an edit control.
 *
 * Grouping and weighting are real now — the backend reads necessity from the
 * posting's own modal language, so §3.2.1's trap ("Good knowledge of DSA" and
 * "Bonus: familiarity with Docker" are not equal) is no longer flattened here.
 * Disjunctive any-of groups are still missing, and this screen says so rather
 * than letting three alternatives read as three separate demands.
 *
 * What it still does not do is pick a "biggest gap" out of severities that are
 * all the same number.
 *
 * What it does carry is the part the spec is most emphatic about, which is also
 * the part that costs nothing to get right: every requirement shows where its
 * concept id came from, and an unmeasured requirement never looks like a bad
 * score. `CoveragePanel` owns that.
 */

import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
  useCoverage,
  useEditRequirement,
  useEffectiveRequirements,
  useJd,
  useResetRequirementEdits,
} from "../api";
import { useCandidateId } from "./candidate-hook";
import { CompanyBriefPanel } from "./CompanyBriefPanel";
import { CoveragePanel } from "./CoveragePanel";
import { PlanPanel } from "./PlanPanel";
import { ScanSourceNote } from "./ConceptSourceChip";
import {
  Empty,
  ErrorNote,
  Panel,
  Pill,
  Section,
  SkeletonRows,
} from "../ui/primitives";
import type {
  EligibilityCriteria,
  RequirementEditIn,
  Necessity,
  Requirement,
  RequirementGroup,
} from "../types";

export function JdPage() {
  const { jdId } = useParams<{ jdId: string }>();
  const candidateId = useCandidateId();
  const jd = useJd(jdId);
  const coverage = useCoverage(jdId, candidateId);
  // The JD is shared across every student who pasted this posting (FR-2.12).
  // THIS is the student's own view of it, with their corrections applied.
  const mine = useEffectiveRequirements(jdId, candidateId);
  const edit = useEditRequirement(jdId, candidateId);
  const resetEdits = useResetRequirementEdits(jdId, candidateId);

  if (jd.isLoading) return <SkeletonRows rows={6} />;

  if (jd.isError || !jd.data) {
    return (
      <Empty title="No such job description">
        The id in the URL does not match a stored JD. Paste one and it gets a
        fresh id.
        <div className="mt-3">
          <Link
            to="/"
            className="text-sm font-medium text-brand hover:text-brand-hover"
          >
            Paste a JD &rarr;
          </Link>
        </div>
      </Empty>
    );
  }

  const data = jd.data;
  // The student's corrections if they have any, the shared parse otherwise.
  // Falling back rather than blocking means a slow or failed edits call costs
  // the correction, not the whole screen.
  const requirements = mine.data?.requirements ?? data.requirements;
  const groups = mine.data?.requirement_groups ?? data.requirement_groups;
  const editCount = mine.data?.edit_count ?? 0;
  const skillCount = data.required_skills.length;

  return (
    <>
      <header className="mb-8">
        <p className="rule-label">{data.company_name}</p>
        <h1 className="mt-0.5 text-display font-semibold text-ink">
          {data.role_title}
        </h1>
        <div className="mt-2.5 max-w-2xl">
          <ScanSourceNote scannedAgainst={data.scanned_against} />
        </div>
      </header>

      {/* EC-2.13. Shown because the student did not write this posting: they
          pasted something a placement list forwarded, and one poisoned JD is
          parsed once and shared across everybody preparing for that drive. */}
      {data.injections_removed > 0 && (
        <div className="mb-6 rounded-md border border-contested-line bg-contested-soft px-4 py-3">
          <p className="text-sm text-contested">
            <span className="font-medium">
              {data.injections_removed} part
              {data.injections_removed === 1 ? "" : "s"} of this posting{" "}
              {data.injections_removed === 1 ? "was" : "were"} removed.
            </span>{" "}
            They were written to give instructions to whatever reads the
            document rather than to describe a job. Nothing there was used, and
            the rest of the posting is intact.
          </p>
        </div>
      )}

      {/* §6.3: "The UI shows these in a lighter style with a tooltip: 'This
          wasn't in the JD, but it's standard for this role.' Honesty here
          costs nothing and buys credibility."

          Said once at the top as well as per row, because the per-row marker
          answers "why is this here" and only a count answers "how much of what
          I am reading did the company actually write". */}
      {data.inferred_count > 0 && (
        <div className="mb-6 rounded-md border border-line bg-surface-sunken px-4 py-3">
          <p className="text-sm text-ink-soft">
            <span className="font-medium text-ink">
              {data.inferred_count} of these {data.requirements.length}{" "}
              requirements
            </span>{" "}
            {data.inferred_count === 1 ? "was" : "were"} not in the posting. It
            was short, so we added what is standard for{" "}
            {data.role_archetype ? "this role" : "the role we matched"} &mdash;
            marked on each row, and weighted lower than anything the company
            actually wrote.
          </p>
        </div>
      )}

      {/* Said out loud, because a corrected list that looks like the parse
          is a list nobody can audit. The reset is a real button: a student who
          made three edits and cannot remember which is left distrusting the
          whole screen. */}
      {editCount > 0 && (
        <div className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-md border border-brand-line bg-brand-soft px-4 py-3">
          <p className="text-sm text-ink">
            <span className="font-medium">
              You have corrected this posting {editCount} time
              {editCount === 1 ? "" : "s"}.
            </span>{" "}
            This is your view of it. The posting itself is shared with everyone
            else preparing for this drive and is unchanged.
          </p>
          <button
            type="button"
            onClick={() => resetEdits.mutate()}
            className="shrink-0 text-sm font-medium text-brand hover:text-brand-hover"
          >
            {resetEdits.isPending ? "Undoing\u2026" : "Undo my corrections"}
          </button>
        </div>
      )}

      {/* EC-2.14: *"Two roles in one JD ('SDE or QA') — detect, ask the
          student which, default to the first."*

          The matcher already refused this case — two archetypes inside the
          margin and it returns nothing rather than tossing a coin — and the
          refusal was silent. Asking is the other half of a decision that was
          already being made. */}
      {data.role_candidates.length > 1 && (
        <div className="mb-6 rounded-md border border-reported-line bg-reported-soft px-4 py-3">
          <p className="text-sm text-ink">
            <span className="font-medium">
              This posting reads as more than one role.
            </span>{" "}
            We did not guess, because guessing decides which eight requirements
            get filled in. Pick the one you are sitting:
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            {data.role_candidates.map((candidate) => (
              <a
                key={candidate.id}
                href={`/?role=${candidate.id}`}
                className="rounded-md border border-line bg-surface px-3 py-1.5 text-sm text-ink-soft hover:border-brand hover:text-brand"
              >
                {candidate.name}
              </a>
            ))}
          </div>
          <p className="provenance mt-2">
            Until you pick, nothing is inferred — the requirements below are
            only what the posting states.
          </p>
        </div>
      )}

      <EligibilityBanner eligibility={data.eligibility} />

      {/* The offer, not the analysis. FR-2.15's sentence — "you have 7.2,
          cutoff is 7.5" — needs the student's own resume, and reading it is
          something they should be asked about rather than something that
          happens because they pasted a job posting. */}
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-md border border-brand-line bg-brand-soft px-4 py-3">
        <p className="text-sm text-ink">
          <span className="font-medium">Hold this up against your resume?</span>{" "}
          We can tell you whether you clear the eligibility bar and which of
          these requirements your resume actually mentions.
        </p>
        <Link
          to={`/jds/${jdId}/compare`}
          className="shrink-0 text-sm font-medium text-brand hover:text-brand-hover"
        >
          Compare &rarr;
        </Link>
      </div>

      <Section
        label="What this job asks for"
        meta={`${skillCount} matched · ${data.unresolved_skills.length} unmapped`}
      >
        {skillCount === 0 ? (
          <Empty title="No requirements matched">
            Nothing in this text matched a concept we know about. With M04 down
            the scan only looks for five concepts, so this is more likely an
            outage than an empty JD &mdash; check{" "}
            <Link
              to="/deps"
              className="font-medium text-brand hover:text-brand-hover"
            >
              dependencies
            </Link>
            .
          </Empty>
        ) : (
          <div className="space-y-4">
            {NECESSITY_ORDER.map((necessity) => {
              const group = requirements.filter(
                (r) => r.necessity === necessity,
              );
              if (group.length === 0) return null;
              return (
                <NecessityGroup
                  key={necessity}
                  necessity={necessity}
                  requirements={group}
                  groups={groups}
                  rawText={data.raw_text}
                  onEdit={edit.mutate}
                />
              );
            })}
          </div>
        )}

        {/* Which passes read this posting, and what §5 still lacks. Kept on the
            screen rather than in a backlog, because a reader looking at a thin
            list should be able to tell "the posting says little" from "the
            model was unavailable" without asking anybody. */}
        <p className="provenance mt-2">read by: {data.extracted_by}</p>

        <details className="mt-3 text-sm">
          <summary className="cursor-pointer text-xs text-ink-faint hover:text-ink-soft">
            What is still missing here
          </summary>
          <div className="mt-2 space-y-1.5 border-l-2 border-line pl-3 text-xs text-ink-soft">
            <p>
              <code className="provenance">necessity</code> and{" "}
              <code className="provenance">weight</code> are read from the
              posting now &mdash; from its modal language (&ldquo;strong&rdquo;,
              &ldquo;a plus&rdquo;) and the heading each line sits under &mdash;
              so the groups above are the JD&rsquo;s ordering and not one this
              module invented. Where the posting says nothing, the requirement
              is a <strong>should</strong>: that means unstated, not optional.
            </p>
            <p>
              Any-of groups are read now: &ldquo;Docker or Kubernetes&rdquo; is
              one requirement with two acceptable answers rather than two
              demands, and the alternatives share one requirement&rsquo;s
              weight. A slash is the ambiguous case &mdash;
              &ldquo;Java/Python/C++&rdquo; is a choice and &ldquo;CI/CD&rdquo;
              is a name &mdash; so it splits only when the ontology recognises
              at least two of the parts. With M04 down nothing splits, which is
              why a slashed requirement can appear here whole.
            </p>
            <p>
              <code className="provenance">kind</code>,{" "}
              <code className="provenance">measured_by</code> and{" "}
              <code className="provenance">seniority_signal</code> are read now,
              from a lexicon rather than a model &mdash; deterministic, and the
              fallback that has to exist behind §6.2&rsquo;s extraction call
              anyway. <code className="provenance">measured_by</code> prices a
              coding question at 12 minutes against a verbal one at 3.5, so the
              coverage plan below has stopped pretending every question takes
              the same time.
            </p>
            <p>
              A requirement marked <em>nothing can test this</em> is
              §3.2.1&rsquo;s third tier: &ldquo;communication&rdquo; maps to
              constructs M12 and M17 measure, &ldquo;team player&rdquo; to a
              behavioural round, and &ldquo;go-getter attitude&rdquo; to nothing
              at all. It stays on the list because the company asked for it; it
              earns no questions because no answer to one could be scored.
            </p>
            <p>
              Eligibility (CGPA cutoff, backlogs, batch, bond) IS extracted now
              and shows above. What is still missing there is the comparison
              &mdash; FR-2.15&rsquo;s &ldquo;you have 7.2, cutoff is 7.5&rdquo;
              needs the student&rsquo;s own CGPA, which lives in M01, so the
              banner states the bar rather than whether you clear it.
            </p>
          </div>
        </details>
      </Section>

      {coverage.isLoading && <SkeletonRows rows={4} />}
      {coverage.isError && (
        <ErrorNote>
          Could not load the gap for this candidate.{" "}
          {coverage.error instanceof Error ? coverage.error.message : ""}
        </ErrorNote>
      )}
      {/* FR-2.13. Before the gap, because it is about the JOB and the two
          panels below it are about the student. A brief that says the posting
          advertises 6.5 LPA and the reports say 4.2 changes whether the rest
          of this page is worth reading at all. */}
      <CompanyBriefPanel jdId={jdId} candidateId={candidateId} />

      {coverage.data && <CoveragePanel coverage={coverage.data} />}

      {/* The plan goes AFTER the gap, because it is an answer to it. Reading
          "you are weak here" and then "so spend four questions there" is the
          order the student thinks in. */}
      {coverage.data && <PlanPanel jdId={jdId} candidateId={candidateId} />}

      <Section label="The pasted text">
        <Panel tone="sunken" className="px-4 py-3">
          <pre className="text-source whitespace-pre-wrap break-words font-mono text-ink-soft">
            {data.raw_text}
          </pre>
        </Panel>
        <p className="mt-2 text-xs text-ink-faint">
          The posting exactly as it was pasted. Every requirement above quotes
          its own line out of this text, so anything the parser claims can be
          checked against what the company actually wrote &mdash; including what
          it left out.
        </p>
      </Section>
    </>
  );
}

/**
 * The rows of one necessity band: single requirements, and choices.
 *
 * A choice is rendered ONCE, as one row holding its alternatives, because that
 * is what the posting wrote. Rendering "Docker" and "Kubernetes" as two rows
 * is the §3.2.1 mistake at the last possible moment — the parser got it right
 * and the screen put it back.
 */
type Row =
  | { kind: "one"; requirement: Requirement }
  | { kind: "choice"; group: RequirementGroup; members: Requirement[] };

function rowsFor(
  requirements: Requirement[],
  groups: RequirementGroup[],
): Row[] {
  const byId = new Map(groups.map((group) => [group.id, group]));
  const emitted = new Set<string>();
  const rows: Row[] = [];

  for (const requirement of requirements) {
    const group = requirement.group_id
      ? byId.get(requirement.group_id)
      : undefined;
    if (!group) {
      rows.push({ kind: "one", requirement });
      continue;
    }
    if (emitted.has(group.id)) continue;
    emitted.add(group.id);
    rows.push({
      kind: "choice",
      group,
      members: requirements.filter((r) => r.group_id === group.id),
    });
  }
  return rows;
}

/**
 * EC-2.2: *"Cap displayed at 8 by weight; all stored; plan uses top 12."*
 *
 * The real Cognizant brochure yields seventy-three requirements. Nobody reads
 * seventy-three rows — and a list nobody reads might as well hold three, which
 * is the failure this cap exists to prevent rather than cause.
 *
 * Applied per BAND, not overall. The bands are already an ordering that means
 * something: a nice-to-have at the top of its own section is readable, and the
 * same row at position sixty of one flat list is not. Everything beyond the cap
 * is one click away and counted in the summary, so nothing is hidden — it is
 * ranked.
 */
const SHOWN_PER_BAND = 8;

/**
 * Strongest first. A student reading top-down reads the things that will
 * actually get asked before the things that might.
 */
const NECESSITY_ORDER: Necessity[] = ["must", "should", "could"];

/**
 * What each level means in the student's terms, not the spec's.
 *
 * `should` is the one worth being careful about: it is the DEFAULT, assigned
 * when the posting used no modal language at all. Labelling it "optional" would
 * turn silence into permission to skip — so it says the posting did not say.
 */
const NECESSITY_COPY: Record<Necessity, { title: string; note: string }> = {
  must: {
    title: "Must have",
    note: "Stated as required, or listed under a requirements heading.",
  },
  should: {
    title: "Asked for",
    note: "Named without a qualifier. The posting did not say how firm this is.",
  },
  could: {
    title: "Nice to have",
    note: "Explicitly a bonus, a plus, or under a nice-to-have heading.",
  },
};

/**
 * One necessity band, with its requirements under it.
 *
 * The band header carries its share of the total weight, which is the number
 * that matters downstream: FR-2.8 allocates the interview's question budget
 * across these, so "nice-to-have is 6% of this posting" is the difference
 * between one throwaway question about Kubernetes and four.
 */
function NecessityGroup({
  necessity,
  requirements,
  groups,
  rawText,
  onEdit,
}: {
  necessity: Necessity;
  requirements: Requirement[];
  groups: RequirementGroup[];
  rawText: string;
  onEdit: (body: RequirementEditIn) => void;
}) {
  const copy = NECESSITY_COPY[necessity];
  const share = requirements.reduce((sum, r) => sum + r.weight, 0);
  const [showAll, setShowAll] = useState(false);

  // Sorted by weight before the cap, so the eight shown are the eight that
  // matter rather than the first eight the posting happened to write.
  const ranked = [...requirements].sort((a, b) => b.weight - a.weight);
  const rows = rowsFor(
    showAll ? ranked : ranked.slice(0, SHOWN_PER_BAND),
    groups,
  );
  const hidden =
    requirements.length - Math.min(requirements.length, SHOWN_PER_BAND);

  return (
    <div>
      {/* The separator IS the group label — a rule with the name sitting in it,
          so the stack reads as bands rather than as one list with headings. */}
      <div className="flex items-center gap-3">
        <span className="rule-label shrink-0">{copy.title}</span>
        <span className="h-px flex-1 bg-line" />
        <span
          className="provenance shrink-0"
          title="Share of this posting's total weight — what fraction of the interview these should earn"
        >
          {requirements.length} &middot; {Math.round(share * 100)}% of the ask
        </span>
      </div>
      <p className="mt-1 text-xs text-ink-faint">{copy.note}</p>

      <Panel className="mt-2 px-4 py-1">
        <div className="divide-y divide-line">
          {rows.map((row) =>
            row.kind === "one" ? (
              <RequirementRow
                key={row.requirement.id}
                requirement={row.requirement}
                rawText={rawText}
                onEdit={onEdit}
              />
            ) : (
              <ChoiceRow
                key={row.group.id}
                group={row.group}
                members={row.members}
                rawText={rawText}
              />
            ),
          )}
        </div>
      </Panel>

      {hidden > 0 && !showAll && (
        <button
          type="button"
          onClick={() => setShowAll(true)}
          className="mt-1.5 text-xs text-ink-faint hover:text-ink-soft"
        >
          {hidden} more, lower weighted &mdash; show{" "}
          {hidden === 1 ? "it" : "them"}
        </button>
      )}
      {showAll && hidden > 0 && (
        <button
          type="button"
          onClick={() => setShowAll(false)}
          className="mt-1.5 text-xs text-ink-faint hover:text-ink-soft"
        >
          Show the top {SHOWN_PER_BAND} only
        </button>
      )}
    </div>
  );
}

/**
 * One requirement, quoting the words it came from.
 *
 * The span is the reason this is a list rather than a row of chips: "we found
 * Python" is a claim about the posting, and a student can only check it
 * against the line it was read from.
 */
function RequirementRow({
  requirement,
  rawText,
  compact = false,
  onEdit,
}: {
  requirement: Requirement;
  rawText: string;
  compact?: boolean;
  onEdit?: (body: RequirementEditIn) => void;
}) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 py-2">
      <span className="min-w-0">
        <span className="text-sm text-ink">{requirement.text}</span>
        {requirement.mentions > 1 && (
          <span
            className="provenance ml-2"
            title="Repetition is emphasis — a posting that says it three times means it"
          >
            &times;{requirement.mentions}
          </span>
        )}
        {requirement.source === "archetype" && (
          <span
            className="provenance ml-2"
            title="This wasn't in the job description, but it's standard for this role. It counts for less than something the company actually wrote."
          >
            standard for this role
          </span>
        )}
        {requirement.measured_by.length === 0 && (
          <span
            className="provenance ml-2"
            title="No round in this platform can produce evidence about this, so no question will be asked about it and no score can be earned against it."
          >
            nothing can test this
          </span>
        )}
        {!compact && requirement.span && (
          <span className="provenance ml-2 break-words">
            &ldquo;{quote(rawText, requirement.span)}&rdquo;
          </span>
        )}
      </span>
      <span className="flex shrink-0 items-center gap-2">
        {/* FR-2.10. Extraction scores F1 0.857 — about one row in seven is
            wrong — and until now a student looking at a requirement the
            posting never made had no way to say so.

            Two controls, not a form. "Not in the posting" and "this is a must"
            are the two things a student reliably knows better than the parser;
            a span or a concept id is not, and letting either be typed would
            turn provenance into an opinion. */}
        {onEdit && requirement.necessity !== "must" && (
          <button
            type="button"
            title="The posting treats this as more important than we read it"
            onClick={() =>
              onEdit({
                action: "necessity",
                target: requirement.text,
                value: "must",
              })
            }
            className="text-xs text-ink-faint hover:text-brand"
          >
            must-have
          </button>
        )}
        {onEdit && (
          <button
            type="button"
            title="Remove this from your view of the posting. Nobody else's copy changes."
            onClick={() =>
              onEdit({ action: "remove", target: requirement.text })
            }
            className="text-xs text-ink-faint hover:text-contested"
          >
            not in the posting
          </button>
        )}
        <ConceptPill requirement={requirement} />
      </span>
    </div>
  );
}

/**
 * A choice: one requirement with several acceptable answers.
 *
 * §3.2.1: *"'Java/Python/C++' is a disjunction, not three requirements.
 * Missing this makes a Python-only student look 33% qualified."* Rendering the
 * alternatives as sibling rows would reintroduce exactly that reading after
 * the parser had already got it right, so they are indented under one heading
 * that says what the posting actually asked.
 */
function ChoiceRow({
  group,
  members,
  rawText,
}: {
  group: RequirementGroup;
  members: Requirement[];
  rawText: string;
}) {
  return (
    <div className="py-2">
      <div className="flex flex-wrap items-baseline gap-x-2">
        <span className="text-sm text-ink">Any one of</span>
        <span className="text-sm font-medium text-ink">
          {members.map((member) => member.text).join(" · ")}
        </span>
        {group.span && (
          <span className="provenance break-words">
            &ldquo;{quote(rawText, group.span)}&rdquo;
          </span>
        )}
      </div>
      <p className="mt-0.5 text-xs text-ink-faint">
        The posting offered a choice, so knowing one of these meets it. They
        share one requirement&rsquo;s weight between them rather than counting
        as {members.length}.
      </p>
      <div className="mt-1 divide-y divide-line border-l-2 border-line pl-3">
        {members.map((member) => (
          <RequirementRow
            key={member.id}
            requirement={member}
            rawText={rawText}
            compact
          />
        ))}
      </div>
    </div>
  );
}

/** Where a requirement's concept id came from, or that it has none. */
function ConceptPill({ requirement }: { requirement: Requirement }) {
  return (
    <Pill
      tone={requirement.concept_source === "m04" ? "confirmed" : "reported"}
      title={
        requirement.concept_ids[0]
          ? `${requirement.concept_ids[0]} · ${
              requirement.concept_source === "m04"
                ? "resolved by M04"
                : "guessed offline, unconfirmed"
            }`
          : "no concept id — nothing downstream can test this"
      }
    >
      {requirement.grounded
        ? requirement.concept_source === "m04"
          ? "ontology"
          : "guessed offline"
        : "no concept yet"}
    </Pill>
  );
}

/**
 * The line a requirement was read from, trimmed to something quotable.
 *
 * Widened past the matched word on both sides, because "Python" on its own
 * proves nothing — the whole question a student is checking is whether it
 * appeared in the requirements or in "no Python required".
 */
function quote(text: string, span: { start: number; end: number }): string {
  const from = Math.max(0, text.lastIndexOf("\n", span.start) + 1);
  const to = text.indexOf("\n", span.end);
  const line = text.slice(from, to === -1 ? undefined : to).trim();
  return line.length > 90 ? `${line.slice(0, 90)}…` : line;
}

/**
 * The bar for sitting this drive, at the top of the screen (§2.3, FR-2.4).
 *
 * §2.3 puts this above the requirements for a reason a student feels directly:
 * they waste weeks preparing for drives they are not eligible to sit. The
 * module recognised these lines and threw them away, so the banner could not
 * exist.
 *
 * It states the bar and does NOT say whether the student clears it. FR-2.15's
 * sentence — "you have 7.2, cutoff is 7.5" — needs their CGPA, which is M01's
 * (`entities.education.grade`), and asserting they fall short on a number this
 * module does not hold would be the worst possible thing to be wrong about.
 */
function EligibilityBanner({
  eligibility,
}: {
  eligibility: EligibilityCriteria;
}) {
  // `stated` rather than checking the fields: "the posting says nothing about
  // eligibility" and "we found nothing" look identical from the values alone,
  // and only one of them means we looked.
  if (!eligibility?.stated) return null;

  const bars: string[] = [];
  if (eligibility.min_cgpa !== null)
    bars.push(`CGPA ${eligibility.min_cgpa} or above`);
  if (eligibility.max_backlogs_active !== null) {
    bars.push(
      eligibility.max_backlogs_active === 0
        ? "no active backlogs"
        : `at most ${eligibility.max_backlogs_active} active backlog${
            eligibility.max_backlogs_active === 1 ? "" : "s"
          }`,
    );
  }
  if (eligibility.year_of_passing.length > 0) {
    bars.push(`${eligibility.year_of_passing.join(", ")} batch`);
  }
  if (eligibility.max_backlogs_history !== null) {
    // Distinct from "no ACTIVE backlogs" on purpose: a student who cleared an
    // old arrear passes that bar and fails this one.
    bars.push("no backlogs ever");
  }
  if (eligibility.allowed_branches.length > 0) {
    bars.push(eligibility.allowed_branches.join(" / "));
  }
  if (eligibility.bond_months !== null) {
    bars.push(
      eligibility.bond_months % 12 === 0
        ? `${eligibility.bond_months / 12}-year bond`
        : `${eligibility.bond_months}-month bond`,
    );
  }
  if (eligibility.location.length > 0) {
    bars.push(eligibility.location.join(" / "));
  }
  if (eligibility.package_lpa_total !== null) {
    // Both numbers when the posting gives both. A 6.5 LPA headline with 2 LPA
    // of variable is a 4.5 LPA salary, and students compare the wrong one.
    bars.push(
      eligibility.package_lpa_fixed !== null &&
        eligibility.package_lpa_fixed !== eligibility.package_lpa_total
        ? `${eligibility.package_lpa_total} LPA (${eligibility.package_lpa_fixed} fixed)`
        : `${eligibility.package_lpa_total} LPA`,
    );
  }

  return (
    <div
      className="mb-7 rounded-md border border-reported-line bg-reported-soft px-4 py-3"
      role="note"
    >
      <p className="text-sm font-medium text-reported">
        Who can sit this drive
      </p>
      <p className="mt-1 text-sm text-ink">{bars.join(" · ")}</p>
      <p className="mt-2 text-xs text-ink-soft">
        Read off the posting, not checked against you &mdash; your CGPA is not
        something this screen holds. Check these before you spend a fortnight
        preparing.
      </p>
      {eligibility.raw_spans.length > 0 && (
        <p className="provenance mt-1.5 break-words">
          {eligibility.raw_spans.map((span) => `“${span.text}”`).join(" · ")}
        </p>
      )}
    </div>
  );
}
