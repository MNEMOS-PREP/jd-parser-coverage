/**
 * Where the other modules' screens live.
 *
 * Every module in this platform is a separate app on a separate port, which is
 * a deployment fact the student should never have to know. When M02 needs to
 * send somebody to M01 — "you have no resume, go make one" — it needs a URL,
 * and hard-coding `http://localhost:5201` into a component means the link works
 * on one machine and 404s everywhere else.
 *
 * So it comes from the environment, with the dev port as the fallback. The
 * fallback is the DEV one on purpose: in production the variable is set, and a
 * missing variable in production produces a visibly wrong link rather than a
 * silently plausible one that leads to nothing.
 *
 * `module.json` already carries M01's BACKEND base_url and this is its
 * FRONTEND, which is a different thing on a different port — the backend URL is
 * what M02's server calls, this is where a browser is sent.
 */

/** M01 — Resume Ingestion. Port 5201 per its own `module.json`. */
export const M01_URL: string =
  import.meta.env.VITE_M01_URL ?? "http://localhost:5201";
