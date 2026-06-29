import { createFileRoute, redirect } from "@tanstack/react-router";

/** Bare /account → default sub-page */
export const Route = createFileRoute("/_app/account/")({
  beforeLoad: ({ search }) => {
    throw redirect({ to: "/account/packages", search });
  },
});
