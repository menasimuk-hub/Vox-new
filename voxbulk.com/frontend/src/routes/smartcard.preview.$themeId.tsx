import { createFileRoute } from "@tanstack/react-router";

import { PLACEHOLDER_CARD, SmartCardTemplate } from "@/components/smart-card/SmartCardTemplate";
import {
  getSmartCardThemeTokens,
  normalizeSmartCardThemeId,
  type SmartCardThemeId,
} from "@/components/smart-card/smart-card-themes";

export const Route = createFileRoute("/smartcard/preview/$themeId")({
  validateSearch: (search: Record<string, unknown>) => ({
    company: typeof search.company === "string" ? search.company : undefined,
    name: typeof search.name === "string" ? search.name : undefined,
    job: typeof search.job === "string" ? search.job : undefined,
  }),
  head: ({ params }) => {
    const tokens = getSmartCardThemeTokens(params.themeId);
    return {
      meta: [
        { title: `${tokens.label} Smart Card preview — VoxBulk` },
        { name: "description", content: `Preview the ${tokens.label} Smart Card theme.` },
        { name: "robots", content: "noindex,nofollow" },
      ],
    };
  },
  component: SmartCardThemePreviewPage,
});

function SmartCardThemePreviewPage() {
  const { themeId } = Route.useParams();
  const search = Route.useSearch();
  const id = normalizeSmartCardThemeId(themeId) as SmartCardThemeId;
  const tokens = getSmartCardThemeTokens(id);
  const card = {
    ...PLACEHOLDER_CARD,
    companyName: search.company?.trim() || PLACEHOLDER_CARD.companyName,
    personName: search.name?.trim() || PLACEHOLDER_CARD.personName,
    jobTitle: search.job?.trim() || PLACEHOLDER_CARD.jobTitle,
  };

  return (
    <SmartCardTemplate
      card={card}
      tokens={tokens}
      actions={{
        hideFeedback: false,
        whatsappHref: "https://wa.me/447700900000?text=Hi",
        onWebSurvey: () => undefined,
        webSurveyLabel: "Web survey",
        previewBanner: (
          <p
            className="mt-4 rounded-full px-3 py-1 text-center text-[11px] font-medium"
            style={{
              background: "rgba(251,191,36,0.15)",
              color: "#fbbf24",
              border: "1px solid rgba(251,191,36,0.35)",
            }}
          >
            Theme preview — {tokens.label}
          </p>
        ),
      }}
    />
  );
}
