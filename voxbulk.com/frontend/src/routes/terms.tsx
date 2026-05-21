import { createFileRoute } from "@tanstack/react-router";
import { LegalPageView } from "@/components/LegalPageView";

export const Route = createFileRoute("/terms")({
  head: () => ({
    meta: [
      { title: "Terms & Conditions — VOXBULK" },
      { name: "description", content: "VOXBULK Terms & Conditions." },
    ],
  }),
  component: () => (
    <LegalPageView slug="terms" fallbackTitle="Terms & Conditions" fallbackDescription="VOXBULK Terms & Conditions." />
  ),
});
