import { createFileRoute } from "@tanstack/react-router";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";

export const Route = createFileRoute("/_app/recovery/no-show")({
  head: () => ({ meta: [{ title: "No-show follow-up — VoxBulk" }] }),
  component: () => (
    <div className="flex w-full flex-col gap-6">
      <PageHeader eyebrow="Recovery" title="No-show follow-up" description="AI calling behaviour after a missed appointment." />
      <Card>
        <CardHeader><CardTitle>AI calling settings</CardTitle></CardHeader>
        <CardContent className="space-y-5">
          <div className="space-y-1.5">
            <Label className="text-xs">Opening message</Label>
            <Textarea rows={4} defaultValue="Hi {first_name}, this is {clinic_name}. We noticed you couldn't make your appointment today — can I help you rebook?" />
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-1.5"><Label className="text-xs">Max attempts</Label><Input type="number" defaultValue={3} /></div>
            <div className="flex items-center justify-between rounded-lg border border-border p-3">
              <div>
                <p className="text-sm font-medium">WhatsApp fallback</p>
                <p className="text-xs text-muted-foreground">Send WhatsApp if no answer after attempts</p>
              </div>
              <Switch defaultChecked />
            </div>
          </div>
          <div className="flex justify-end"><Button>Save settings</Button></div>
        </CardContent>
      </Card>
    </div>
  ),
});
