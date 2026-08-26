/**
 * One entry in a module's own top bar.
 *
 * Declared here rather than imported. `@ai/core` exported a `NavItem` up to
 * v0.6.0 and dropped it in 0.7.0 — on the stated grounds that it "was imported
 * by nothing", which was not true: this file imported it, and so did M01's.
 * Both were pinned at v0.6.0, so the break was real and invisible until the
 * pin moved for an unrelated reason.
 *
 * Two words and a URL is not a platform contract in any case, and 0.7.0's own
 * reasoning agrees: *"a module owns its own chrome; this package owns the
 * vocabulary."*
 */
export interface NavItem {
  to: string;
  label: string;
}


/** Nav for M02 running standalone. The platform shell supplies its own. */
export const M02_NAV: NavItem[] = [
  { to: "/", label: "Paste a JD" },
  { to: "/deps", label: "Dependencies" },
];
