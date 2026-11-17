import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

/**
 * M02 - JD Parser & Coverage Planner, on its reserved port 5202 (PORTS.txt).
 *
 * This repo holds one module, so this is the app. When the platform shell
 * exists it mounts the same `src/routes.tsx` - the components are identical
 * either way, so what you fix here is what students get.
 */
const API_TARGET = process.env.VITE_API_BASE ?? "http://127.0.0.1:8102";

/**
 * M01, for tailoring a resume to a posting (2026-11-17).
 *
 * The tailoring screen mounts M01's own editor, PDF preview and resume list
 * rather than copies of them, exactly as the platform shell mounts every
 * module: as SOURCE from the checkout beside this one. Its API is M01's, so
 * `/v1/resumes` goes to M01's port. Without the sibling checkout everything
 * else in this app still works; the tailoring screen is the part that needs it.
 */
const here = dirname(fileURLToPath(import.meta.url));
const M01_SRC = resolve(here, "../../../resume-ingestion/Frontend/frontend_M01_Resume_Ingestion/src/index.ts");
const M01_TARGET = process.env.M01_API_BASE ?? "http://127.0.0.1:8101";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    // M01's source sits in another repo with its own node_modules: one React,
    // one router, one query client, or every hook throws "Invalid hook call".
    dedupe: ["react", "react-dom", "react-router-dom", "@tanstack/react-query", "@ai/core"],
    alias: existsSync(M01_SRC) ? [{ find: "@ai/m01", replacement: M01_SRC }] : [],
  },
  optimizeDeps: {
    // @ai/core ships TypeScript source rather than a build, so Vite must
    // transform it instead of pre-bundling it as an opaque dependency.
    exclude: ["@ai/core", "@ai/m01"],
  },
  server: {
    port: 5202,
    // Proxy to the M02 backend so the browser sees one origin and CORS never
    // comes up. Point at the platform gateway (:8000) instead by setting
    // VITE_API_BASE. M01's nouns go to M01, most specific first.
    proxy: {
      "/v1/resumes": { target: M01_TARGET, changeOrigin: true },
      "/sys/m01": {
        target: M01_TARGET,
        changeOrigin: true,
        rewrite: (path: string) => path.replace("/sys/m01", ""),
      },
      "/v1": { target: API_TARGET, changeOrigin: true },
      "/health": { target: API_TARGET, changeOrigin: true },
    },
  },
  preview: { port: 5202 },
});
