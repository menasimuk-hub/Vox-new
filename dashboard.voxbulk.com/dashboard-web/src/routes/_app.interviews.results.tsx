import { createFileRoute, Outlet } from "@tanstack/react-router";

export const Route = createFileRoute("/_app/interviews/results")({
  component: () => <Outlet />,
});
