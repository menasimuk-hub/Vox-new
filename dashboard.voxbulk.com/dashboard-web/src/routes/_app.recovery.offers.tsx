import { createFileRoute } from "@tanstack/react-router";
import { Wand2 } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const live = [
  { name: "Whitening £199 special", booked: 14, cap: 30 },
  { name: "New patient consult — free", booked: 22, cap: 40 },
];

export const Route = createFileRoute("/_app/recovery/offers")({
  head: () => ({ meta: [{ title: "Offer campaigns — VoxBulk" }] }),
  component: () => (
    <div className="flex w-full flex-col gap-6">
      <PageHeader eyebrow="Recovery" title="Offer campaigns" description="Fill gaps with promotional outreach." />

      <div className="grid gap-4 md:grid-cols-2">
        {live.map((o) => (
          <Card key={o.name}>
            <CardContent className="p-4">
              <p className="text-sm font-medium">{o.name}</p>
              <div className="mt-3 flex items-center gap-2">
                <Progress value={(o.booked / o.cap) * 100} className="h-1.5" />
                <span className="text-xs tabular-nums text-muted-foreground">{o.booked}/{o.cap}</span>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader><CardTitle>New offer</CardTitle></CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          <Field label="Name"><Input placeholder="e.g. Spring whitening £149" /></Field>
          <Field label="Booking cap"><Input type="number" defaultValue={50} /></Field>
          <div className="md:col-span-2 space-y-1.5">
            <Label className="text-xs">Description</Label>
            <Textarea rows={3} placeholder="Short description sent to AI script writer…" />
          </div>
          <Field label="Booking method">
            <Select defaultValue="dentally">
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="dentally">Auto-book in Dentally</SelectItem>
                <SelectItem value="link">Booking link sent via WhatsApp</SelectItem>
                <SelectItem value="callback">Request callback</SelectItem>
              </SelectContent>
            </Select>
          </Field>
          <div className="md:col-span-2 flex flex-wrap gap-2">
            <Button variant="outline" className="gap-1.5"><Wand2 className="size-4" /> AI write message</Button>
            <Button className="ml-auto">Next — choose audience</Button>
          </div>
        </CardContent>
      </Card>
    </div>
  ),
});

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="space-y-1.5"><Label className="text-xs">{label}</Label>{children}</div>;
}
