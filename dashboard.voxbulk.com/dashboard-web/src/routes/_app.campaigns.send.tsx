import { createFileRoute, Link } from "@tanstack/react-router";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { requireEnabledService } from "@/lib/guards/service-route";

export const Route = createFileRoute("/_app/campaigns/send")({
  beforeLoad: () => requireEnabledService("campaigns"),
  head: () => ({ meta: [{ title: "Send campaign — Campaigns" }] }),
  component: CampaignSendPage,
});

function CampaignSendPage() {
  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="Campaigns"
        title="Send broadcast"
        description="Choose an approved template and audience for your broadcast."
      />
      <Card>
        <CardContent className="space-y-4 p-6">
          <p className="text-sm text-muted-foreground">
            Pick a template, select contacts, and schedule your send when ready.
          </p>
          <div className="flex flex-wrap gap-2">
            <Button type="button" onClick={() => toast.info("Send will be available shortly.")}>
              Send now
            </Button>
            <Button asChild variant="outline">
              <Link to="/campaigns">Back to templates</Link>
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
