/**
 * M02 — JD Parser & Coverage Planner · API client.
 *
 * Spec: plan_in_depth/M02_JD_Parser.md §7 (API surface)
 *
 * One hook per backend endpoint, and no hook without one. The backend's own
 * README puts it as "absent, not stubbed — an endpoint that returns a
 * placeholder is worse than one that does not, because a caller writes against
 * it and finds out later." The same holds on this side: there is no hook here
 * for `/v1/archetypes` or `/v1/jds/{id}/plan`, because writing one would let a
 * screen be built on an endpoint that does not exist.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@ai/core";
import type { Coverage, Deps, Health, JdParseIn, JobDescription, ModuleStatus } from "./types";

export const m02Keys = {
  health: ["m02", "health"] as const,
  status: ["m02", "status"] as const,
  deps: ["m02", "deps"] as const,
  jd: (jdId: string) => ["m02", "jd", jdId] as const,
  coverage: (jdId: string, candidateId: string) =>
    ["m02", "coverage", jdId, candidateId] as const,
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
    mutationFn: (body: JdParseIn) => api.post<JobDescription>("/v1/jds/parse", body),
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
export function useCoverage(jdId: string | undefined, candidateId: string | undefined) {
  return useQuery({
    queryKey: m02Keys.coverage(jdId ?? "", candidateId ?? ""),
    enabled: Boolean(jdId && candidateId),
    retry: false,
    queryFn: () => api.get<Coverage>(`/v1/jds/${jdId}/coverage/${candidateId}`),
  });
}
