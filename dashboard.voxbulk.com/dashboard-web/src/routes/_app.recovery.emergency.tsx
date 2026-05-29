import { createFileRoute } from "@tanstack/react-router";
import { Phone } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

export const Route = createFileRoute("/_app/recovery/emergency")({
  head: () => ({ meta: [{ title: "Emergency reschedule — VoxBulk" }] }),
  component: () => (
    <div className="flex w-full flex-col gap-6">
      <PageHeader eyebrow="Recovery" title="Emergency reschedule" description="Cancel and rebook a window of patients in one go." />
      <Card>
        <CardHeader><CardTitle>What to cancel</CardTitle></CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          <Field label="Date"><Input type="date" defaultValue="2026-05-30" /></Field>
          <Field label="Scope">
            <Select defaultValue="day">
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="day">Full day</SelectItem>
                <SelectItem value="from">From a time</SelectItem>
                <SelectItem value="window">Time window</SelectItem>
              </SelectContent>
            </Select>
          </Field>
          <Field label="From time"><Input type="time" defaultValue="09:00" /></Field>
          <Field label="To time"><Input type="time" defaultValue="13:00" /></Field>
          <div className="md:col-span-2 space-y-1.5">
            <Label className="text-xs">Reason</Label>
            <Input defaultValue="Dr. Patel out sick" />
          </div>
          <div className="md:col-span-2 space-y-1.5">
            <Label className="text-xs">Alternative slots for AI script</Label>
            <Textarea rows={3} defaultValue="Friday 31 May 10:00–16:00, Monday 3 June 09:00–17:00" />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="flex items-center justify-between p-4">
          <p className="text-sm text-muted-foreground">Estimated cost: <span className="font-medium text-foreground">£36.40</span> for 28 calls</p>
          <Button className="gap-1.5"><Phone className="size-4" /> Start AI calling — 28 patients</Button>
        </CardContent>
      </Card>
    </div>
  ),
});

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="space-y-1.5"><Label className="text-xs">{label}</Label>{children}</div>;
}
