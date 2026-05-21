import { createFileRoute } from "@tanstack/react-router";
import { LegalPoliciesPage } from "@/components/LegalPoliciesPage";
import { isLegalTabId, LEGAL_TAB_LABELS, type LegalTabId } from "@/lib/legalPoliciesConfig";

type LegalPoliciesSearch = {
  tab?: LegalTabId;
};

export const Route = createFileRoute("/legal-policies")({
  validateSearch: (search: Record<string, unknown>): LegalPoliciesSearch => ({
    tab: isLegalTabId(search.tab) ? search.tab : "terms",
  }),
  head: ({ search }) => {
    const tab = isLegalTabId(search.tab) ? search.tab : "terms";
    const title = LEGAL_TAB_LABELS[tab];
    return {
      meta: [
        { title: `${title} — VOXBULK Legal & policies` },
        {
          name: "description",
          content: `VOXBULK ${title}. Legal documents, privacy, cookies, and GDPR information.`,
        },
      ],
    };
  },
  component: LegalPoliciesRoute,
});

function LegalPoliciesRoute() {
  const { tab } = Route.useSearch();
  const activeTab = tab ?? "terms";
  return <LegalPoliciesPage activeTab={activeTab} />;
}
