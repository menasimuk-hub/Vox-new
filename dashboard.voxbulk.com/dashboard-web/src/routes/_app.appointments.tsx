import { createFileRoute, Outlet } from "@tanstack/react-router";

import { requireAppointmentsRoute } from "@/lib/guards/service-route";

export const Route = createFileRoute("/_app/appointments")({
  beforeLoad: ({ location }) => requireAppointmentsRoute(location),
  component: () => <Outlet />,
});
