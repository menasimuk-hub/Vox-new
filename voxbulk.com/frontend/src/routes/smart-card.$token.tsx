import { createFileRoute } from "@tanstack/react-router";

import { PublicSmartCardLanding } from "@/components/smart-card/PublicSmartCardLanding";

export const Route = createFileRoute("/smart-card/$token")({
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
  component: PublicSmartCardTokenPage,
});

function PublicSmartCardTokenPage() {
  const { token } = Route.useParams();
  return <PublicSmartCardLanding token={token} />;
}
