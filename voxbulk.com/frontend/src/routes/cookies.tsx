import { createFileRoute, redirect } from "@tanstack/react-router";

export const Route = createFileRoute("/cookies")({
  beforeLoad: () => {
    throw redirect({ to: "/legal-policies", search: { tab: "cookies" } });
  },
});
