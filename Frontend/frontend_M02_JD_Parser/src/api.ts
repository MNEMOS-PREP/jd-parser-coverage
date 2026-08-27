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
import type {
  Coverage,
  CoveragePlan,
  Deps,
  Health,
  JdParseIn,
  JobDescription,
  MatchReport,
  ModuleStatus,
} from "./types";

export const m02Keys = {
  health: ["m02", "health"] as const,
  status: ["m02", "status"] as const,
  deps: ["m02", "deps"] as const,
  jd: (jdId: string) => ["m02", "jd", jdId] as const,
  coverage: (jdId: string, candidateId: string) =>
    ["m02", "coverage", jdId, candidateId] as const,
  // Keyed by minutes too: changing the session length is a different plan, not
  // a stale one, and caching per length means dragging the control back and
  // forth does not re-ask the server for an answer it already gave.
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
