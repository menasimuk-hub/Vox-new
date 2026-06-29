import { createFileRoute, redirect } from "@tanstack/react-router";

/** Bare /settings → default sub-page */
export const Route = createFileRoute("/_app/settings/")({
  beforeLoad: ({ search }) => {
    throw redirect({ to: "/settings/profile", search });
  },
});
