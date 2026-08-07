import { createFileRoute } from "@tanstack/react-router";
import { PublicExpoLanding } from "@/components/expo/PublicExpoLanding";

export const Route = createFileRoute("/expo/$token")({
  validateSearch: (search: Record<string, unknown>) => ({
    preview: search.preview === "1" || search.preview === 1 || search.preview === true,
  }),
  head: () => ({
    meta: [
      { title: "Expo stand — VoxBulk" },
      { name: "description", content: "Scan choice: WhatsApp or web. Under a minute." },
      { name: "robots", content: "noindex,nofollow" },
    ],
  }),
  component: ExpoRoute,
});

function ExpoRoute() {
  const { token } = Route.useParams();
  const { preview } = Route.useSearch();
  return <PublicExpoLanding token={token} livePreview={Boolean(preview)} />;
}
