import { createFileRoute, redirect } from "@tanstack/react-router";

export const Route = createFileRoute("/gdpr")({
  beforeLoad: () => {
    throw redirect({ to: "/legal-policies", search: { tab: "gdpr" } });
  },
});
