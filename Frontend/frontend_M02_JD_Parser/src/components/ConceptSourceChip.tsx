/**
 * Where a concept_id came from.
 *
 * ── Why this is module-local when provenance components are supposed to be a
 * platform contract ─────────────────────────────────────────────────────────
 *
 * `@ai/core` owns `SourceChip` and `VerificationBadge`, and the rule is that a
 * module does not write its own. Both of those model M15's domain, though: a
 * fact retrieved from a URL at a time, or a claim some number of students
 * reported. Rendering "this concept_id was resolved by M04" through `SourceChip`
 * would mean inventing a `retrieved_at` and a `source_type` for something that
 * has neither — fabricating provenance metadata inside the provenance system.
 *
 * So the WORDS are local and the PALETTE is inherited: `confirmed` and
 * `reported` are the platform's tokens for "provenance checks out" and
 * "asserted, unverified", and that is exactly the distinction here. A student
 * who has learned what green means in M15 reads this correctly on sight.
 *
 * If a second module ever needs to render concept provenance, this moves into
 * core and the words get settled there.
 */

import type { ConceptSource, ScannedAgainst } from "../types";
import { Pill } from "../ui/primitives";

const COPY: Record<ConceptSource, { label: string; tone: "confirmed" | "reported"; hint: string }> =
  {
    m04: {
      label: "ontology",
      tone: "confirmed",
      hint: "M04 resolved this label to a concept in the skill graph. Anything downstream can test it.",
    },
    offline_fallback: {
      label: "guessed offline",
      tone: "reported",
      hint:
        "M04 was unreachable, so this id comes from a five-entry table in M02. " +
        "It has not been confirmed to exist in the ontology.",
    },
  };

export function ConceptSourceChip({
  source,
  conceptId,
}: {
  source: ConceptSource | undefined;
  conceptId?: string;
}) {
  if (!source) return null;
  const copy = COPY[source];
  return (
    <Pill tone={copy.tone} title={conceptId ? `${copy.hint}\n\n${conceptId}` : copy.hint}>
      {copy.label}
    </Pill>
  );
}

/**
 * Which ontology the scan itself ran against.
 *
 * Separate from the per-label chip, and it matters more than it looks: the
 * difference between M04's ontology and five hardcoded concepts is most of the
 * requirements a real JD contains. A page that showed three requirements
 * without saying this would read as "your JD only asks for three things".
 */
export function ScanSourceNote({ scannedAgainst }: { scannedAgainst: ScannedAgainst }) {
  if (scannedAgainst === "m04") {
    return (
      <p className="text-xs text-ink-soft">
        Scanned against M04&rsquo;s full concept ontology.
      </p>
    );
  }
  return (
    <p className="text-xs text-ink-soft">
      Scanned against M02&rsquo;s five-concept offline lexicon, because M04 was unreachable.{" "}
      <strong className="font-medium text-ink">
        Requirements outside those five were not looked for at all
      </strong>{" "}
      &mdash; this is a short list because of the outage, not because the job asks for little.
    </p>
  );
}
