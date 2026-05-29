import { createFileRoute } from "@tanstack/react-router";

import { PageHeader } from "@/components/page-header";
import { Card, CardContent } from "@/components/ui/card";

export const Route = createFileRoute("/_app/settings/team")({
  head: () => ({ meta: [{ title: "Team — VoxBulk" }] }),
  component: TeamSettings,
});

function TeamSettings() {
  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader eyebrow="Settings" title="Team members" description="Invite people and assign roles." />
      <Card>
        <CardContent className="flex flex-col items-center gap-2 p-12 text-center">
          <p className="text-sm font-medium">Team invites are managed by your VoxBulk admin</p>
          <p className="max-w-md text-sm text-muted-foreground">
            User accounts and role assignments are configured from the admin portal. Contact your account manager if you need a new teammate added to this organisation.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
