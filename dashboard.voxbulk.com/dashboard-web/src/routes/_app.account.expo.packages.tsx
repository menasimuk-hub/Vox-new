import { createFileRoute, redirect } from "@tanstack/react-router";

export const Route = createFileRoute("/_app/account/expo/packages")({
  beforeLoad: () => {
    throw redirect({ to: "/account/packages", search: { tab: "expo" } });
  },
});
