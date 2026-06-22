import { createFileRoute } from "@tanstack/react-router";

import { AppointmentManagerPage } from "@/components/appointments/appointment-manager-page";

export const Route = createFileRoute("/_app/appointments/")({
  head: () => ({ meta: [{ title: "Appointment Manager — VoxBulk" }] }),
  component: AppointmentManagerPage,
});
