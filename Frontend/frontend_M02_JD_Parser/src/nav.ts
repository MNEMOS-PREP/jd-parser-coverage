import type { NavItem } from "@ai/core";

/** Nav for M02 running standalone. The platform shell supplies its own. */
export const M02_NAV: NavItem[] = [
  { to: "/", label: "Paste a JD" },
  { to: "/deps", label: "Dependencies" },
];
