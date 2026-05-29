import { createFileRoute } from "@tanstack/react-router";

import { PageHeader } from "@/components/page-header";
import { requireFollowUpModule } from "@/lib/guards/recovery-route";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const steps = [
  { id: "s1", when: "72h before", default: true },
  { id: "s2", when: "48h before", default: true },
  { id: "s3", when: "24h before", default: true },
  { id: "s4", when: "2h before", default: true },
  { id: "s5", when: "After no-show", default: true },
];

export const Route = createFileRoute("/_app/follow-up")({
  beforeLoad: requireFollowUpModule,
  head: () => ({ meta: [{ title: "Reminder sequences — VoxBulk" }] }),
  component: () => (
    <div className="flex w-full flex-col gap-6">
      <PageHeader eyebrow="Follow up" title="Reminder sequences" description="WhatsApp appointment reminders, fully editable." />
      <div className="flex flex-col gap-3">
        {steps.map((s, i) => (
          <Card key={s.id}>
            <CardContent className="flex flex-col gap-3 p-4 md:flex-row md:items-start">
              <div className="flex items-center gap-3 md:w-48">
                <div className="grid size-7 place-items-center rounded-full bg-primary/15 text-xs font-semibold text-primary">{i + 1}</div>
                <Select defaultValue={s.when}>
                  <SelectTrigger className="h-8 w-full"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {["72h before", "48h before", "24h before", "12h before", "2h before", "After no-show"].map((w) => (
                      <SelectItem key={w} value={w}>{w}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex-1">
                <Textarea rows={2} defaultValue={`Hi {first_name}, just a reminder of your appointment ${s.when}. Reply Y to confirm, R to reschedule.`} />
              </div>
              <Switch defaultChecked={s.default} />
            </CardContent>
          </Card>
        ))}
      </div>
      <div className="flex justify-end"><Button>Save sequence</Button></div>
    </div>
  ),
});
