import { createFileRoute } from "@tanstack/react-router";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { requireOrgSettingsAccess } from "@/lib/guards/settings-route";
import { useServices, type ServiceKey } from "@/lib/services";
import { showRecoveryModules, isRecoveryServiceKey } from "@/lib/feature-flags";
import { PhoneCall, ClipboardList, HeartPulse, CalendarClock, QrCode } from "lucide-react";
import { brandAssets } from "@/lib/brand";

type ServiceItem = {
  key: ServiceKey;
  title: string;
  desc: string;
  Icon?: typeof PhoneCall;
  brandIcon?: string;
};

const items: ServiceItem[] = [
  { key: "interviews", title: "Interviews", desc: "AI phone screening for hiring.", Icon: PhoneCall },
  { key: "surveys", title: "Surveys", desc: "AI phone & WhatsApp questionnaires.", Icon: ClipboardList },
  { key: "feedback", title: "Customer feedback", desc: "WhatsApp QR feedback by location.", Icon: QrCode },
  { key: "campaigns", title: "Broadcast campaigns", desc: "WhatsApp template broadcasts.", brandIcon: brandAssets.iconDark },
  { key: "recovery", title: "Recovery", desc: "Missed-appointment & recall outreach.", Icon: HeartPulse },
  { key: "followup", title: "Follow up", desc: "WhatsApp appointment reminders.", Icon: CalendarClock },
];

export const Route = createFileRoute("/_app/settings/services")({
  head: () => ({ meta: [{ title: "Services — VoxBulk" }] }),
  beforeLoad: () => requireOrgSettingsAccess(),
  component: ServicesSettings,
});

function ServicesSettings() {
  const { allowed, enabled, visible, toggle, saving, loaded, error } = useServices();
  const visibleCount = items.filter((it) => visible[it.key]).length;

  const onToggle = async (key: ServiceKey, value: boolean) => {
    try {
      await toggle(key, value);
      toast.success(
        value
          ? "Service shown in sidebar and dashboard"
          : "Service hidden from sidebar — you can turn it back on here anytime",
      );
    } catch {
      toast.error("Could not update service");
    }
  };

  const available = items.filter((it) => allowed[it.key] && (showRecoveryModules || !isRecoveryServiceKey(it.key)));

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="Settings"
        title="Services"
        description="Turn modules on or off for your sidebar and dashboard. Hidden modules stay listed here so you can enable them again. Only your account manager can remove a module completely."
      />
      <Card>
        <CardHeader><CardTitle className="text-base">Your modules</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          {!loaded ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : available.length === 0 ? (
            <p className="text-sm text-muted-foreground">No modules are available on your account. Contact VoxBulk support.</p>
          ) : (
            available.map((it) => {
              const isOn = enabled[it.key];
              const lockOff = isOn && visibleCount <= 1;
              return (
                <div key={it.key} className="flex items-center justify-between rounded-lg border border-border p-3">
                  <div className="flex items-center gap-3">
                    <div className="grid size-9 place-items-center rounded-md bg-primary/10 text-primary">
                      {it.brandIcon ? (
                        <img src={it.brandIcon} alt="" className="size-5 object-contain" aria-hidden />
                      ) : it.Icon ? (
                        <it.Icon className="size-4" />
                      ) : null}
                    </div>
                    <div>
                      <p className="text-sm font-medium">{it.title}</p>
                      <p className="text-xs text-muted-foreground">
                        {it.desc}
                        {!isOn ? " · Hidden from menu — switch on to use again." : ""}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-xs text-muted-foreground">{isOn ? "Shown" : "Hidden"}</span>
                    <Switch
                      checked={isOn}
                      disabled={saving || lockOff}
                      onCheckedChange={(v) => void onToggle(it.key, v)}
                    />
                  </div>
                </div>
              );
            })
          )}
          {error ? <p className="text-sm text-destructive">{error}</p> : null}
          {saving ? <p className="text-xs text-muted-foreground">Saving…</p> : null}
        </CardContent>
      </Card>
    </div>
  );
}
