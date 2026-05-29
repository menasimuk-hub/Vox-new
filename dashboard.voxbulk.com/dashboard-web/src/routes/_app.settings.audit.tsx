import { createFileRoute } from "@tanstack/react-router";

import { PageHeader } from "@/components/page-header";
import { Card, CardContent } from "@/components/ui/card";

export const Route = createFileRoute("/_app/settings/audit")({
  head: () => ({ meta: [{ title: "Audit log — VoxBulk" }] }),
  component: AuditPage,
});

function AuditPage() {
  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="Settings"
        title="Audit log"
        description="Compliance-grade activity log of who did what, and when."
      />
      <Card>
        <CardContent className="flex flex-col items-center gap-2 p-12 text-center">
          <p className="text-sm font-medium">Audit log API coming soon</p>
          <p className="max-w-md text-sm text-muted-foreground">
            Activity history for your organisation will appear here once the customer audit log endpoint is available.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
