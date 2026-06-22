import { createFileRoute, Outlet } from "@tanstack/react-router";

import { requireEnabledService } from "@/lib/guards/service-route";

export const Route = createFileRoute("/_app/appointments")({
  beforeLoad: () => requireEnabledService("appointments"),
  component: () => <Outlet />,
});
