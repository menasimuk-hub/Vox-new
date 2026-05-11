import { createFileRoute } from "@tanstack/react-router";
import { PageShell } from "@/components/SiteShell";

export const Route = createFileRoute("/legal")({
  head: () => ({
    meta: [
      { title: "Legal — VOXBULK" },
      { name: "description", content: "VOXBULK legal information." },
    ],
  }),
  component: () => <PageShell eyebrow="Legal" title="Legal" />,
});
