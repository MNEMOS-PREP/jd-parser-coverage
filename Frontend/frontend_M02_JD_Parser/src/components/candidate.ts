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

import { setIdentityHeaders } from "@ai/core";

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
  publishIdentity();
  listeners.forEach((listener) => listener());
}

/** The headers a raw `fetch` has to send for itself. See `api.ts`. */
export function identityHeaders(): Record<string, string> {
  return { "X-Role": "student", "X-Candidate-Id": current };
}

/**
 * Tell `@ai/core` who the browser is.
 *
 * The backend resolves a caller through `ai_core.identity` and answers 403 for
 * `/coverage/{candidate_id}` without one, so this is what keeps the panel
 * working — and, more to the point, what makes "this is YOUR gap analysis"
 * true rather than assumed.
 *
 * This is the DEV shape: a header naming the candidate, honoured only under
 * `AI_AUTH_MODE=dev`. It is the same trust this control always had — the id
 * was already whatever you typed — except that it now has one name, is refused
 * in production, and the swap for a real session is one call in this file,
 * which is what the note at the top of it has always promised.
 */
export function publishIdentity(): void {
  setIdentityHeaders(identityHeaders());
}

// At module load, before any screen has rendered or fetched.
publishIdentity();

export function subscribeCandidateId(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
