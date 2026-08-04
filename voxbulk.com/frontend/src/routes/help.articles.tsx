import { createFileRoute, Outlet } from "@tanstack/react-router";

export const Route = createFileRoute("/help/articles")({
  component: () => <Outlet />,
});
