import { createFileRoute, Link } from "@tanstack/react-router";
import { Plus, Send, Sparkles } from "lucide-react";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { requireEnabledService } from "@/lib/guards/service-route";

export const Route = createFileRoute("/_app/campaigns/")({
  beforeLoad: () => requireEnabledService("campaigns"),
  head: () => ({ meta: [{ title: "My templates — Campaigns" }] }),
  component: CampaignTemplatesPage,
});

const MOCK_TEMPLATES = [
  { id: "t1", name: "Spring offer", status: "approved", updated: "2d ago" },
  { id: "t2", name: "Refer a friend", status: "pending", updated: "4h ago" },
];

function CampaignTemplatesPage() {
  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="Campaigns"
        title="My templates"
        description="WhatsApp broadcast templates for one-to-many messaging."
        actions={
          <div className="flex gap-2">
            <Button asChild variant="outline" className="gap-1.5">
              <Link to="/campaigns/send"><Send className="size-4" /> Send campaign</Link>
            </Button>
            <Button className="gap-1.5" onClick={() => toast.info("Template creation will be available shortly.")}>
              <Plus className="size-4" /> New template
            </Button>
          </div>
        }
      />

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {MOCK_TEMPLATES.map((t) => (
          <Card key={t.id}>
            <CardContent className="p-4">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="font-medium">{t.name}</p>
                  <p className="text-xs text-muted-foreground">Updated {t.updated}</p>
                </div>
                <Badge variant="outline">{t.status}</Badge>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card className="border-dashed">
        <CardContent className="flex flex-col items-center gap-2 p-8 text-center text-sm text-muted-foreground">
          <Sparkles className="size-8 text-primary/60" />
          <p>Manage WhatsApp broadcast templates and send to your audience when ready.</p>
        </CardContent>
      </Card>
    </div>
  );
}
