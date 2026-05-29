import { createFileRoute } from "@tanstack/react-router";

import { PageHeader } from "@/components/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { useServices, type ServiceKey } from "@/lib/services";
import { showRecoveryModules, isRecoveryServiceKey } from "@/lib/feature-flags";
import { PhoneCall, ClipboardList, HeartPulse, CalendarClock } from "lucide-react";

const items: { key: ServiceKey; title: string; desc: string; Icon: typeof PhoneCall }[] = [
  { key: "interviews", title: "Interviews", desc: "AI phone screening for hiring.", Icon: PhoneCall },
  { key: "surveys", title: "Surveys", desc: "AI phone & WhatsApp questionnaires.", Icon: ClipboardList },
  { key: "recovery", title: "Recovery", desc: "Missed-appointment & recall outreach.", Icon: HeartPulse },
  { key: "followup", title: "Follow up", desc: "WhatsApp appointment reminders.", Icon: CalendarClock },
];

export const Route = createFileRoute("/_app/settings/services")({
  head: () => ({ meta: [{ title: "Services — VoxBulk" }] }),
  component: ServicesSettings,
});

function ServicesSettings() {
  const { enabled, loaded } = useServices();

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="Settings"
        title="Services"
        description="Modules enabled for your organisation. Contact VoxBulk support or your account manager to change these."
      />
      <Card>
        <CardHeader><CardTitle className="text-base">Modules (read-only)</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          {!loaded ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : (
            items.filter((it) => showRecoveryModules || !isRecoveryServiceKey(it.key)).map((it) => (
              <div key={it.key} className="flex items-center justify-between rounded-lg border border-border p-3">
                <div className="flex items-center gap-3">
                  <div className="grid size-9 place-items-center rounded-md bg-primary/10 text-primary"><it.Icon className="size-4" /></div>
                  <div>
                    <p className="text-sm font-medium">{it.title}</p>
                    <p className="text-xs text-muted-foreground">{it.desc}</p>
                  </div>
                </div>
                <Switch checked={enabled[it.key]} disabled aria-readonly />
              </div>
            ))
          )}
        </CardContent>
      </Card>
    </div>
  );
}
