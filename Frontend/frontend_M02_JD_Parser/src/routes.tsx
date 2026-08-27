/**
 * M02 - JD Parser & Coverage Planner · routes.
 *
 * Two screens, because there are two the backend can fill. The spec's §7
 * surface has eight endpoints and §8 names seven components; a route for
 * /archetypes or /plan would be a link to a page that cannot load.
 */

import { Route } from "react-router-dom";

import { DepsPage } from "./components/DepsPage";
import { JdPage } from "./components/JdPage";
import { MatchConfirmPage } from "./components/MatchConfirmPage";
import { MatchPage } from "./components/MatchPage";
import { ParsePage } from "./components/ParsePage";

export const m02Routes = (
  <Route key="m02">
    <Route index element={<ParsePage />} />
    <Route path="/jds/:jdId" element={<JdPage />} />
    {/* Confirm before analyse. This is the first screen in the platform that
        reads a student's RESUME to say something about their chances, and
        "you miss the CGPA cutoff" as a side effect of parsing a posting is
        the right sentence at a moment nobody asked for it. */}
    <Route path="/jds/:jdId/compare" element={<MatchConfirmPage />} />
    <Route path="/jds/:jdId/match" element={<MatchPage />} />
    <Route path="/deps" element={<DepsPage />} />
  </Route>
);
