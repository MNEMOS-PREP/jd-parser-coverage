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
import { ParsePage } from "./components/ParsePage";

export const m02Routes = (
  <Route key="m02">
    <Route index element={<ParsePage />} />
    <Route path="/jds/:jdId" element={<JdPage />} />
    <Route path="/deps" element={<DepsPage />} />
  </Route>
);
