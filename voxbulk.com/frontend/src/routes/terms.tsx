import { createFileRoute } from "@tanstack/react-router";
import { PageShell } from "@/components/SiteShell";

export const Route = createFileRoute("/terms")({
  head: () => ({
    meta: [
      { title: "Terms & Conditions — VOXBULK" },
      { name: "description", content: "VOXBULK Terms & Conditions." },
    ],
  }),
  component: () => <PageShell eyebrow="Legal" title="Terms & Conditions" />,
});
