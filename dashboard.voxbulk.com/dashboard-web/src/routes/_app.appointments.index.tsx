import { createFileRoute } from "@tanstack/react-router";

import { AppointmentManagerPage } from "@/components/appointments/appointment-manager-page";
import { requireEnabledService } from "@/lib/guards/service-route";

export const Route = createFileRoute("/_app/appointments/")({
  beforeLoad: () => requireEnabledService("appointments"),
  head: () => ({ meta: [{ title: "Appointment Manager — VoxBulk" }] }),
  component: AppointmentManagerPage,
});
