import { createFileRoute } from "@tanstack/react-router";

import { PublicSmartCardLanding } from "@/components/smart-card/PublicSmartCardLanding";

/** Alias for SoT path `/smartcard/{token}` — printed QRs still use `/smart-card/{token}`. */
export const Route = createFileRoute("/smartcard/$token")({
  head: () => ({
    meta: [
      { title: "Digital Smart Card — tap to connect" },
      {
        name: "description",
        content:
          "Scan-to-open digital business card: save contact, WhatsApp, call, email, website and directions in one tap.",
      },
      { name: "robots", content: "noindex,nofollow" },
    ],
  }),
  component: PublicSmartCardAliasPage,
});

function PublicSmartCardAliasPage() {
  const { token } = Route.useParams();
  return <PublicSmartCardLanding token={token} />;
}
