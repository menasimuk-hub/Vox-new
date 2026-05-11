import { createFileRoute } from "@tanstack/react-router";
import { PageShell } from "@/components/SiteShell";

export const Route = createFileRoute("/cookies")({
  head: () => ({
    meta: [
      { title: "Cookie Policy — VOXBULK" },
      { name: "description", content: "VOXBULK Cookie Policy." },
    ],
  }),
  component: () => <PageShell eyebrow="Legal" title="Cookie Policy" />,
});
