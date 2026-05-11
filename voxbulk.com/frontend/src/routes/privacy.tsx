import { createFileRoute } from "@tanstack/react-router";
import { PageShell } from "@/components/SiteShell";

export const Route = createFileRoute("/privacy")({
  head: () => ({
    meta: [
      { title: "Privacy Policy — VOXBULK" },
      { name: "description", content: "VOXBULK Privacy Policy." },
    ],
  }),
  component: () => <PageShell eyebrow="Legal" title="Privacy Policy" />,
});
