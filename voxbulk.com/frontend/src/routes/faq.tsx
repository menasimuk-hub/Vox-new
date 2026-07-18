import { Outlet, createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/faq")({
  component: () => <Outlet />,
});
