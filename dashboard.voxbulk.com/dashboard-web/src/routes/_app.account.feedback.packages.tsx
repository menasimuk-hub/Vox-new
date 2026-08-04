import { createFileRoute, redirect } from "@tanstack/react-router";

export const Route = createFileRoute("/_app/account/feedback/packages")({
  beforeLoad: () => {
    throw redirect({ to: "/account/packages", search: { tab: "feedback" } });
  },
});
