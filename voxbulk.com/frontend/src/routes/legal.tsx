import { createFileRoute } from "@tanstack/react-router";
import { LegalPageView } from "@/components/LegalPageView";

export const Route = createFileRoute("/legal")({
  head: () => ({
    meta: [
      { title: "Legal — VOXBULK" },
      { name: "description", content: "VOXBULK legal information." },
    ],
  }),
  component: () => (
    <LegalPageView slug="legal" fallbackTitle="Legal" fallbackDescription="VOXBULK legal information." />
  ),
});
