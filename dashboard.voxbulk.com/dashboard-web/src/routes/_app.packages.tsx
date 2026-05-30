import { createFileRoute, redirect } from "@tanstack/react-router";

/** Legacy GoCardless return URL — /packages → /account/packages */
export const Route = createFileRoute("/_app/packages")({
  beforeLoad: ({ search }) => {
    throw redirect({ to: "/account/packages", search });
  },
});
