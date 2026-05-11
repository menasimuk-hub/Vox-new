import { createFileRoute } from "@tanstack/react-router";
import { PageShell } from "@/components/SiteShell";

export const Route = createFileRoute("/gdpr")({
  head: () => ({
    meta: [
      { title: "GDPR — VOXBULK" },
      { name: "description", content: "VOXBULK GDPR information." },
    ],
  }),
  component: () => <PageShell eyebrow="Legal" title="GDPR" />,
});
