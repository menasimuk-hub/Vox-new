import { createFileRoute } from "@tanstack/react-router";
import VOXBULKHome from "@/components/VOXBULKHome";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "VOXBULK — AI-Powered Appointment Recovery for Dental Clinics" },
      {
        name: "description",
        content:
          "VOXBULK automatically recovers cancelled appointments and fills empty slots using AI voice calls and WhatsApp. Built for UK dental clinics.",
      },
      {
        property: "og:title",
        content: "VOXBULK — AI-Powered Appointment Recovery for Dental Clinics",
      },
      {
        property: "og:description",
        content:
          "Recover lost revenue from cancellations and no-shows with AI voice calls and WhatsApp. Built for UK dental clinics. Works with Dentally.",
      },
      { property: "og:type", content: "website" },
    ],
    links: [{ rel: "icon", href: "/favicon.svg" }],
  }),
  component: VOXBULKHome,
});
