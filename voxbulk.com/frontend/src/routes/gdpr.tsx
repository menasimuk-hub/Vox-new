import { createFileRoute } from "@tanstack/react-router";
import { LegalPageView } from "@/components/LegalPageView";

export const Route = createFileRoute("/gdpr")({
  head: () => ({
    meta: [
      { title: "GDPR — VOXBULK" },
      { name: "description", content: "VOXBULK GDPR information." },
    ],
  }),
  component: () => (
    <LegalPageView slug="gdpr" fallbackTitle="GDPR" fallbackDescription="VOXBULK GDPR information." />
  ),
});
