import { createFileRoute } from "@tanstack/react-router";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

export const Route = createFileRoute("/_app/recovery/recall")({
  head: () => ({ meta: [{ title: "Recall campaigns — VoxBulk" }] }),
  component: () => (
    <div className="flex w-full flex-col gap-6">
      <PageHeader eyebrow="Recovery" title="Recall campaigns" description="Reach overdue patients automatically." />
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {[["Overdue", "428"], ["Contacted", "312"], ["Booked", "61"], ["Revenue", "£4,820"]].map(([l, v]) => (
          <Card key={l}><CardContent className="p-4">
            <p className="text-[11px] uppercase tracking-wider text-muted-foreground">{l}</p>
            <p className="mt-1 text-2xl font-semibold">{v}</p>
          </CardContent></Card>
        ))}
      </div>
      <Card>
        <CardHeader><CardTitle>Settings</CardTitle></CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          <Field label="Recall interval">
            <Select defaultValue="6">
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>{[3, 6, 9, 12].map((m) => <SelectItem key={m} value={String(m)}>{m} months overdue</SelectItem>)}</SelectContent>
            </Select>
          </Field>
          <Field label="Appointment types">
            <Select defaultValue="hygiene">
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="hygiene">Hygiene</SelectItem>
                <SelectItem value="checkup">Check-up</SelectItem>
                <SelectItem value="both">Both</SelectItem>
              </SelectContent>
            </Select>
          </Field>
          <Field label="Contact method">
            <Select defaultValue="whatsapp">
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="whatsapp">WhatsApp first, then call</SelectItem>
                <SelectItem value="call">AI call only</SelectItem>
                <SelectItem value="wa">WhatsApp only</SelectItem>
              </SelectContent>
            </Select>
          </Field>
          <Field label="Max bookings / week"><Input type="number" defaultValue={50} /></Field>
          <div className="md:col-span-2 space-y-1.5">
            <Label className="text-xs">AI message</Label>
            <Textarea rows={4} defaultValue="Hi {first_name}, it's been a while since your last hygiene visit. Shall I book you in for next week?" />
          </div>
        </CardContent>
      </Card>
      <div className="flex justify-end"><Button>Launch recall campaign</Button></div>
    </div>
  ),
});

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="space-y-1.5"><Label className="text-xs">{label}</Label>{children}</div>;
}
