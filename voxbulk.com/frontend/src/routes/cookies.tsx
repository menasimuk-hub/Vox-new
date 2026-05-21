import { createFileRoute } from "@tanstack/react-router";
import { LegalPageView } from "@/components/LegalPageView";

export const Route = createFileRoute("/cookies")({
  head: () => ({
    meta: [
      { title: "Cookie Policy — VOXBULK" },
      { name: "description", content: "VOXBULK Cookie Policy." },
    ],
  }),
  component: () => (
    <LegalPageView slug="cookies" fallbackTitle="Cookie Policy" fallbackDescription="VOXBULK Cookie Policy." />
  ),
});
