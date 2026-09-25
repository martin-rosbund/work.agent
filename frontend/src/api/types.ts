// Public wire types are generated from the backend contract. Local editor state
// relaxes server-assigned fields only while a proposal has not been saved yet.
import type { components } from "./generated";
export type Source = components["schemas"]["SourceView"];
export type Item = components["schemas"]["ItemView"] & {
  focus?: components["schemas"]["CitationView"];
};
export type Proposal = Omit<
  components["schemas"]["ProposalView"],
  "created_at"
> & { created_at?: string };
