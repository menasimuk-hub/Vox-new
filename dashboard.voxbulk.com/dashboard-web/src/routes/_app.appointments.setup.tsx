import { createFileRoute } from "@tanstack/react-router";

import { AppointmentSetupWizard } from "@/components/appointments/appointment-setup-wizard";

export const Route = createFileRoute("/_app/appointments/setup")({
  head: () => ({ meta: [{ title: "Setup — Appointment Manager" }] }),
  component: AppointmentSetupWizard,
});
