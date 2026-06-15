import { createFileRoute, Link } from "@tanstack/react-router";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { requireEnabledService } from "@/lib/guards/service-route";

export const Route = createFileRoute("/_app/campaigns/new")({
  beforeLoad: () => requireEnabledService("campaigns"),
  head: () => ({ meta: [{ title: "Create template — Campaigns" }] }),
  component: CampaignNewPage,
});

function CampaignNewPage() {
  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="Campaigns"
        title="Create WhatsApp template"
        description="Design a Meta-approved broadcast template for your audience."
      />
      <Card>
        <CardContent className="space-y-4 p-6">
          <p className="text-sm text-muted-foreground">
            Template fields and approval workflow will appear here. Use Surveys → WhatsApp custom templates for outbound questionnaires in the meantime.
          </p>
          <div className="flex flex-wrap gap-2">
            <Button type="button" onClick={() => toast.info("Template saving will be available shortly.")}>
              Save draft
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
