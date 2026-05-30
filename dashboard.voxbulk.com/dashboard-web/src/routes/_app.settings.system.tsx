import { createFileRoute, useSearch } from "@tanstack/react-router";
import * as React from "react";
import { CalendarCheck, ListChecks, Plug } from "lucide-react";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { apiFetch } from "@/lib/api";
import { useSchedulingStatus } from "@/lib/queries";

export const Route = createFileRoute("/_app/settings/system")({
  head: () => ({ meta: [{ title: "System settings — VoxBulk" }] }),
  component: SystemSettings,
  validateSearch: (s: Record<string, unknown>) => ({
    scheduling: typeof s.scheduling === "string" ? s.scheduling : undefined,
    provider: typeof s.provider === "string" ? s.provider : undefined,
    message: typeof s.message === "string" ? s.message : undefined,
  }),
});

function SystemSettings() {
  const search = useSearch({ from: "/_app/settings/system" });
  const schedulingQ = useSchedulingStatus();

  React.useEffect(() => {
    if (search.scheduling === "connected") {
      toast.success(`Connected ${search.provider || "scheduling"} successfully`);
      void schedulingQ.refetch();
    }
    if (search.scheduling === "error") {
      const msg = search.message || "Calendar connection failed";
      toast.error(msg);
      if (search.provider === "cronofy" && /invalid_client|data center/i.test(msg)) {
        toast.message("Ask your admin to set Cronofy data center to United Kingdom in Admin → Integrations → Cronofy, then Save.");
      }
    }
  }, [search.scheduling, search.provider, search.message, schedulingQ]);

  const scheduling = (schedulingQ.data || {}) as Record<string, unknown>;
  const humanReady = scheduling.human_scheduling_ready === true;
  const calPlatformReady = scheduling.calendly_platform_configured === true;
  const cronPlatformReady = scheduling.cronofy_platform_configured === true;

  const startOAuth = async (provider: "calendly" | "cronofy") => {
    try {
      const data = await apiFetch<{ authorize_url?: string }>(`/service-orders/scheduling/oauth/${provider}/start`);
      if (data?.authorize_url) {
        window.location.href = data.authorize_url;
        return;
      }
      toast.error("No authorization URL returned");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "OAuth start failed");
    }
  };

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="Settings"
        title="System"
        description="AI call booking uses VoxBulk. Connect Calendly or Cronofy here for the final human interview stage."
        actions={<Button variant="outline" className="gap-1.5"><ListChecks className="size-4" /> Show setup checklist</Button>}
      />

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><CalendarCheck className="size-5 text-success" /> Human interview scheduling</CardTitle>
          <CardDescription>
            After AI screening, send candidates a link to book with <strong className="text-foreground">your company&apos;s</strong> Calendly or Cronofy account — not VoxBulk&apos;s calendar.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {schedulingQ.isLoading ? (
            <Skeleton className="h-10 w-full" />
          ) : (
            <div className="flex items-center gap-2 text-sm">
              <span className={"size-2 rounded-full " + (humanReady ? "bg-success" : "bg-warning")} />
              {humanReady
                ? `Ready — ${String(scheduling.human_scheduling_mode || scheduling.provider || "calendar")} connected for Results → Send`
                : "Connect Calendly or Cronofy below before sending human interview links from Results"}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Connect your calendar (Calendly or Cronofy)</CardTitle>
          <CardDescription>
            Required to send real booking links from your organisation when you shortlist candidates after AI phone screening. VoxBulk only sends the link — the interview happens on your calendar account.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {!calPlatformReady && !cronPlatformReady ? (
            <p className="rounded-md border border-border bg-muted/40 p-3 text-sm text-muted-foreground">
              Calendly and Cronofy must be enabled first in the <strong className="text-foreground">VoxBulk admin → Integrations</strong> panel
              (client ID, secret, redirect URI). Until then, Connect buttons will not work.
            </p>
          ) : null}
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" className="gap-1.5" disabled={!calPlatformReady} onClick={() => void startOAuth("calendly")}>
              <Plug className="size-4" /> Connect Calendly
            </Button>
            <Button variant="outline" className="gap-1.5" disabled={!cronPlatformReady} onClick={() => void startOAuth("cronofy")}>
              <Plug className="size-4" /> Connect Cronofy
            </Button>
          </div>
          <div className="space-y-2 text-sm">
            <Health
              name="Calendly (optional)"
              ok={Boolean(scheduling.calendly_connected)}
              note={calPlatformReady ? (scheduling.calendly_connected ? "Connected" : "Not connected") : "Admin setup required"}
            />
            <Health
              name="Cronofy (optional)"
              ok={Boolean(scheduling.cronofy_connected)}
              note={cronPlatformReady ? (scheduling.cronofy_connected ? "Connected" : "Not connected") : "Admin setup required"}
            />
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function Health({ name, ok, note }: { name: string; ok: boolean; note?: string }) {
  return (
    <div className="flex items-center justify-between rounded-md border border-border p-2.5">
      <div className="flex items-center gap-2">
        <span className={"size-2 rounded-full " + (ok ? "bg-success" : "bg-muted-foreground/40")} />
        {name}
      </div>
      <span className="text-[11px] text-muted-foreground">{note || (ok ? "OK" : "Off")}</span>
    </div>
  );
}
