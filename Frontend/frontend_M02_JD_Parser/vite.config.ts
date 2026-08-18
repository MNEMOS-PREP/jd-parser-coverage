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

export default defineConfig({
  plugins: [react(), tailwindcss()],
  optimizeDeps: {
    // @ai/core ships TypeScript source rather than a build, so Vite must
    // transform it instead of pre-bundling it as an opaque dependency.
    exclude: ["@ai/core"],
  },
  server: {
    port: 5202,
    // Proxy to the M02 backend so the browser sees one origin and CORS never
    // comes up. Point at the platform gateway (:8000) instead by setting
    // VITE_API_BASE.
    proxy: {
      "/v1": { target: API_TARGET, changeOrigin: true },
      "/health": { target: API_TARGET, changeOrigin: true },
    },
  },
  preview: { port: 5202 },
});
