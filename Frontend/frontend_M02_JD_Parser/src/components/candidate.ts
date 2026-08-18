/**
 * Which candidate the gap is computed for, while there is no auth.
 *
 * The platform has no session yet, and the coverage endpoint needs a
 * `candidate_id`. Two wrong ways to bridge that: hardcode a uuid (every
 * developer then looks at the same fake student and nobody notices when
 * scoping breaks), or generate a fresh one per page load (M04 has never seen
 * it, so every screen shows "not measured" forever and the measured path never
 * gets exercised).
 *
 * So it is a persisted value with a visible control. It defaults to the id
 * `Backend/seed.py` uses in M01, which is the one an M04 seed is most likely to
 * know about, and the header lets you paste another. Replaced wholesale when
 * auth lands — this file is the only place that has to change.
 */

const KEY = "m02.candidateId";

/** M01's first seeded candidate. Deliberately shared across the module seeds. */
export const DEFAULT_CANDIDATE_ID = "4d0aa1c0-0000-4000-8000-000000000004";

const listeners = new Set<() => void>();
let current = read();

function read(): string {
  if (typeof window === "undefined") return DEFAULT_CANDIDATE_ID;
  const fromUrl = new URLSearchParams(window.location.search).get("candidate");
  if (fromUrl) return fromUrl;
  return window.localStorage.getItem(KEY) ?? DEFAULT_CANDIDATE_ID;
}

export function getCandidateId(): string {
  return current;
}

export function setCandidateId(next: string): void {
  const trimmed = next.trim();
  if (trimmed === current) return;
  current = trimmed || DEFAULT_CANDIDATE_ID;
  window.localStorage.setItem(KEY, current);
  listeners.forEach((listener) => listener());
}

export function subscribeCandidateId(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
