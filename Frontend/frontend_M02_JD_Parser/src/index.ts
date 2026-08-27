/**
 * M02 - JD Parser & Coverage Planner · public surface.
 *
 * Anything not exported here is private to this module. `CoveragePanel` is
 * exported because M06 shows the same gap when configuring a mock and M16
 * shows it in a study plan - and two copies of the component that decides
 * whether an unmeasured topic may be drawn as a bar is exactly how "not
 * measured is not zero" stops being true in one of them.
 */

export { m02Routes } from "./routes";
export { M02_NAV } from "./nav";
export { AppShell } from "./ui/AppShell";
export { CoveragePanel } from "./components/CoveragePanel";
export {
  ConceptSourceChip,
  ScanSourceNote,
} from "./components/ConceptSourceChip";
// Mounted by name in the platform shell, which owns "/" and cannot take a
// second index route. Standalone still routes to them through m02Routes.
export { ParsePage } from "./components/ParsePage";
export { JdPage } from "./components/JdPage";
export { useCoverage, useJd, useParseJd, useDeps } from "./api";
export type {
  Coverage,
  GapState,
  JobDescription,
  ConceptSource,
} from "./types";
