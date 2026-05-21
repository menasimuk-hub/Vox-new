import { createFileRoute } from "@tanstack/react-router";
import { LegalPageView } from "@/components/LegalPageView";

export const Route = createFileRoute("/privacy")({
  head: () => ({
    meta: [
      { title: "Privacy Policy — VOXBULK" },
      { name: "description", content: "VOXBULK Privacy Policy." },
    ],
  }),
  component: () => (
    <LegalPageView slug="privacy" fallbackTitle="Privacy Policy" fallbackDescription="VOXBULK Privacy Policy." />
  ),
});
