import { createFileRoute, Outlet } from "@tanstack/react-router";

import { requireEnabledService } from "@/lib/guards/service-route";

export const Route = createFileRoute("/_app/smart-card")({
  beforeLoad: () => requireEnabledService("smartCard"),
  component: () => <Outlet />,
});
