import { createFileRoute } from "@tanstack/react-router";

import { PageHeader } from "@/components/page-header";
import { Card, CardContent } from "@/components/ui/card";

export const Route = createFileRoute("/_app/settings/opt-out")({
  head: () => ({ meta: [{ title: "Opt-out list — VoxBulk" }] }),
  component: OptOutPage,
});

function OptOutPage() {
  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="Settings"
        title="Opt-out list"
        description="These contacts will never be called or messaged."
      />
      <Card>
        <CardContent className="flex flex-col items-center gap-2 p-12 text-center">
          <p className="text-sm font-medium">Opt-out management is not available yet</p>
          <p className="max-w-md text-sm text-muted-foreground">
            There is no customer-facing opt-out API at the moment. Contact VoxBulk support if you need a number added to the global suppression list.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
