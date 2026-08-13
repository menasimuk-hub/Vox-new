import { createFileRoute, redirect } from "@tanstack/react-router";

export const Route = createFileRoute("/_app/settings/opt-out")({
  head: () => ({ meta: [{ title: "Opt-out list — VoxBulk" }] }),
  beforeLoad: () => {
    throw redirect({ to: "/feedback/consent", search: { tab: "opt-out" } });
  },
});
