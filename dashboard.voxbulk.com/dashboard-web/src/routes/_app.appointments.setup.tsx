import { createFileRoute } from "@tanstack/react-router";

import { AppointmentSetupWizard } from "@/components/appointments/appointment-setup-wizard";
import { requireEnabledService } from "@/lib/guards/service-route";

export const Route = createFileRoute("/_app/appointments/setup")({
  beforeLoad: () => requireEnabledService("appointments"),
  head: () => ({ meta: [{ title: "Setup — Appointment Manager" }] }),
  component: AppointmentSetupWizard,
});
