import { createFileRoute } from "@tanstack/react-router";

import { AppointmentReportsPanel } from "@/components/appointments/appointment-reports-panel";
import { PageHeader } from "@/components/page-header";
import { requireEnabledService } from "@/lib/guards/service-route";

export const Route = createFileRoute("/_app/appointments/reports")({
  beforeLoad: () => requireEnabledService("appointments"),
  head: () => ({ meta: [{ title: "Reports — Appointment Manager" }] }),
  component: AppointmentsReportsPage,
});

function AppointmentsReportsPage() {
  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="Appointment Manager"
        title="Reports"
        description="Confirmation rates, volume trends, and branch performance."
      />
      <AppointmentReportsPanel />
    </div>
  );
}
