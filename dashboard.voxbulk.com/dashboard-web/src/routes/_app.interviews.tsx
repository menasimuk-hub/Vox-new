import { createFileRoute, Outlet } from "@tanstack/react-router";

import { requireEnabledService } from "@/lib/guards/service-route";

export const Route = createFileRoute("/_app/interviews")({
  beforeLoad: () => requireEnabledService("interviews"),
  component: () => <Outlet />,
});
