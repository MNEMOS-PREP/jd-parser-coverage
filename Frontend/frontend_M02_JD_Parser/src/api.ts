/**
 * M02 — JD Parser & Coverage Planner · API client.
 *
 * Spec: plan_in_depth/M02_JD_Parser.md §7 (API surface)
 *
 * One hook per backend endpoint, and no hook without one. The backend's own
 * README puts it as "absent, not stubbed — an endpoint that returns a
 * placeholder is worse than one that does not, because a caller writes against
 * it and finds out later." The same holds on this side: there is no hook here
 * for `/v1/archetypes`, because writing one would let a screen be built on an
 * endpoint that does not exist.
 *
 * `/v1/jds/{id}/plan/{candidate}` was on that list until FR-2.8 landed. It is
 * a hook now because the endpoint is, and `test_every_endpoint_has_a_client`
 * failed the moment the route appeared without one — which is the check doing
 * exactly its job.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@ai/core";
import { identityHeaders } from "./components/candidate";
import type {
  ArchetypeOut,
  Coverage,
  EffectiveRequirements,
  CoveragePlan,
  Deps,
  Health,
  JdParseIn,
  JobDescription,
  RequirementEditIn,
  MatchReport,
  ModuleStatus,
  StagePerf,
} from "./types";

export const m02Keys = {
  health: ["m02", "health"] as const,
  status: ["m02", "status"] as const,
  deps: ["m02", "deps"] as const,
  archetypes: ["m02", "archetypes"] as const,
  performance: ["m02", "performance"] as const,
  jd: (jdId: string) => ["m02", "jd", jdId] as const,
  coverage: (jdId: string, candidateId: string) =>
    ["m02", "coverage", jdId, candidateId] as const,
  // Keyed by minutes too: changing the session length is a different plan, not
  // a stale one, and caching per length means dragging the control back and
  // forth does not re-ask the server for an answer it already gave.
  requirements: (jdId: string, candidateId: string) =>
    ["m02", "requirements", jdId, candidateId] as const,
  match: (jdId: string, candidateId: string) =>
    ["m02", "match", jdId, candidateId] as const,
  plan: (jdId: string, candidateId: string, minutes: number) =>
    ["m02", "plan", jdId, candidateId, minutes] as const,
};

/* ------------------------------------------------------------------ */
/*  Meta                                                              */
/* ------------------------------------------------------------------ */

export function useHealth() {
  return useQuery({
    queryKey: m02Keys.health,
    queryFn: () => api.get<Health>("/health"),
    retry: false,
  });
}

/** What the platform registry says this module is — not what it says itself. */
export function useModuleStatus() {
  return useQuery({
    queryKey: m02Keys.status,
    queryFn: () => api.get<ModuleStatus>("/status"),
    retry: false,
  });
}

export function useDeps() {
  return useQuery({
    queryKey: m02Keys.deps,
    queryFn: () => api.get<Deps>("/v1/deps"),
    retry: false,
  });
}

/* ------------------------------------------------------------------ */
/*  JDs                                                               */
/* ------------------------------------------------------------------ */

export function useParseJd() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: JdParseIn) =>
      api.post<JobDescription>("/v1/jds/parse", body),
    onSuccess: (jd) => {
      qc.setQueryData(m02Keys.jd(jd.id), jd);
      // A parse reads the ontology, so whether M04 answered is now known more
      // precisely than the last cached probe said.
      qc.invalidateQueries({ queryKey: m02Keys.deps });
    },
  });
}

export function useJd(jdId: string | undefined) {
  return useQuery({
    queryKey: m02Keys.jd(jdId ?? ""),
    enabled: Boolean(jdId),
    retry: false,
    queryFn: () => api.get<JobDescription>(`/v1/jds/${jdId}`),
  });
}

/**
 * The gap, for one candidate against one JD.
 *
 * `retry: false` on purpose. A 404 here means the JD id in the URL is wrong,
 * and retrying it three times only delays saying so.
 */
export function useCoverage(
  jdId: string | undefined,
  candidateId: string | undefined,
) {
  return useQuery({
    queryKey: m02Keys.coverage(jdId ?? "", candidateId ?? ""),
    enabled: Boolean(jdId && candidateId),
    retry: false,
    queryFn: () => api.get<Coverage>(`/v1/jds/${jdId}/coverage/${candidateId}`),
  });
}

/**
 * The allocation of question budget across requirements (FR-2.8).
 *
 * A POST behind a `useQuery`, which looks odd and is right: the call is
 * idempotent and derived — the same JD, student and minute count always give
 * the same plan — so it wants caching and refetch-on-change, not mutation
 * semantics. It is a POST only because the minute count is a request body.
 */
export function usePlan(
  jdId: string | undefined,
  candidateId: string | undefined,
  minutes: number,
) {
  return useQuery({
    queryKey: m02Keys.plan(jdId ?? "", candidateId ?? "", minutes),
    enabled: Boolean(jdId && candidateId),
    retry: false,
    queryFn: () =>
      api.post<CoveragePlan>(`/v1/jds/${jdId}/plan/${candidateId}`, {
        minutes,
      }),
  });
}

/**
 * This student's resume against this posting (FR-2.15).
 *
 * Distinct from `useCoverage`, and the distinction is the point: coverage asks
 * the Skill Graph what the student CAN DO across every session they have run,
 * this asks the resume what a recruiter will READ about them next week. The
 * two disagree constantly, and a student needs both — one says what to
 * practise, the other what to rewrite.
 *
 * Never throws on a missing resume. M01 is optional, and the report carries
 * `resume_status` rather than the hook carrying an error.
 */
export function useMatch(
  jdId: string | undefined,
  candidateId: string | undefined,
) {
  return useQuery({
    queryKey: m02Keys.match(jdId ?? "", candidateId ?? ""),
    enabled: Boolean(jdId && candidateId),
    retry: false,
    queryFn: () => api.get<MatchReport>(`/v1/jds/${jdId}/match/${candidateId}`),
  });
}

/**
 * A job description as a PDF, .docx or .txt (FR-2.1).
 *
 * A raw `fetch`, because `api.post` sends JSON and multipart needs the browser
 * to set its own `Content-Type` with the boundary. That means the identity
 * headers have to be attached BY HAND — the exact hole that answered 403 to
 * every upload in M01 the day identity landed, and the reason
 * `test_every_raw_fetch_in_the_client_sends_identity` exists.
 *
 * The JD routes are ungated on purpose (a posting is the company's, not the
 * student's), so this would work without them today. They are sent anyway: the
 * day one of these routes becomes candidate-scoped, the failure would be a 403
 * on upload and nothing else, and nobody would connect it to this line.
 */
export function useUploadJd() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: {
      company_name: string;
      role_title: string;
      file: File;
    }) => {
      const body = new FormData();
      body.append("company_name", input.company_name);
      body.append("role_title", input.role_title);
      body.append("file", input.file);

      // Relative, like every `api.*` call: the dev server proxies /v1 to the
      // backend and production serves both from one origin. An absolute URL
      // here would work in dev and break the moment it is deployed.
      const res = await fetch("/v1/jds/upload", {
        method: "POST",
        headers: identityHeaders(),
        body,
      });
      if (!res.ok) {
        // The backend writes a sentence the student can act on — "that is a
        // zip, upload the PDF inside it". Replacing it with "Upload failed"
        // throws away the only part that tells them what to do.
        const detail = await res.json().catch(() => null);
        throw new Error(detail?.detail ?? `Upload failed (${res.status})`);
      }
      return (await res.json()) as JobDescription;
    },
    onSuccess: (jd) => {
      qc.setQueryData(m02Keys.jd(jd.id), jd);
      qc.invalidateQueries({ queryKey: m02Keys.deps });
    },
  });
}

/* ------------------------------------------------------------------ */
/*  Role-only mode (FR-2.14)                                          */
/* ------------------------------------------------------------------ */

/**
 * The role picker list.
 *
 * `staleTime: Infinity` because the archetype library is a constant compiled
 * into the backend, not data. Refetching it on window focus would be a request
 * per tab switch for an answer that cannot have changed.
 */
export function useArchetypes() {
  return useQuery({
    queryKey: m02Keys.archetypes,
    staleTime: Infinity,
    retry: false,
    queryFn: () => api.get<ArchetypeOut[]>("/v1/archetypes"),
  });
}

/**
 * A requirement set with no job description at all.
 *
 * §2.3 calls this door mandatory: *"a student in September with no drive
 * scheduled still needs to practise. Requiring a JD to use the product would be
 * a self-inflicted wound."*
 */
export function useParseFromRole() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { archetype_id: string; company_name?: string }) =>
      api.post<JobDescription>("/v1/jds/from-role", body),
    onSuccess: (jd) => {
      qc.setQueryData(m02Keys.jd(jd.id), jd);
      qc.invalidateQueries({ queryKey: m02Keys.deps });
    },
  });
}

/**
 * This student's view of the posting, with their corrections applied.
 *
 * A separate call from `useJd` on purpose. The JD is shared across every
 * student who pasted the same posting; the corrections are not, and collapsing
 * the two would mean one student's "that is not in the posting" quietly
 * deleted a requirement from fifty-nine other people's coverage plans.
 */
export function useEffectiveRequirements(
  jdId: string | undefined,
  candidateId: string | undefined,
) {
  return useQuery({
    queryKey: m02Keys.requirements(jdId ?? "", candidateId ?? ""),
    enabled: Boolean(jdId && candidateId),
    retry: false,
    queryFn: () =>
      api.get<EffectiveRequirements>(
        `/v1/jds/${jdId}/requirements/${candidateId}`,
      ),
  });
}

/** Record one correction. Returns the corrected set, so nothing re-fetches. */
export function useEditRequirement(
  jdId: string | undefined,
  candidateId: string | undefined,
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: RequirementEditIn) =>
      api.post<EffectiveRequirements>(
        `/v1/jds/${jdId}/requirements/${candidateId}`,
        body,
      ),
    onSuccess: (data) => {
      qc.setQueryData(
        m02Keys.requirements(jdId ?? "", candidateId ?? ""),
        data,
      );
      // The plan and the gap both allocate over this list, so both are stale.
      qc.invalidateQueries({ queryKey: ["m02", "plan"] });
      qc.invalidateQueries({ queryKey: ["m02", "coverage"] });
    },
  });
}

/** Throw the corrections away and go back to the parse. */
export function useResetRequirementEdits(
  jdId: string | undefined,
  candidateId: string | undefined,
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      api.del<EffectiveRequirements>(
        `/v1/jds/${jdId}/requirements/${candidateId}`,
      ),
    onSuccess: (data) => {
      qc.setQueryData(
        m02Keys.requirements(jdId ?? "", candidateId ?? ""),
        data,
      );
      qc.invalidateQueries({ queryKey: ["m02", "plan"] });
      qc.invalidateQueries({ queryKey: ["m02", "coverage"] });
    },
  });
}

/**
 * p95 per stage, over what this instance has actually parsed (AC-2.5).
 *
 * Empty until something has been parsed, and that is the honest answer to
 * "what is your p95" before there is one — different from a zero.
 */
export function usePerformance() {
  return useQuery({
    queryKey: m02Keys.performance,
    retry: false,
    queryFn: () => api.get<StagePerf[]>("/v1/performance"),
  });
}
