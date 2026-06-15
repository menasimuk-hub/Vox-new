import * as React from "react";
import { Link } from "@tanstack/react-router";
import { CalendarCheck, ListChecks, Plug, Users } from "lucide-react";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { HubspotSyncSettingsCard } from "@/components/hubspot-sync-settings-card";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api";
import { useHubSpotStatus, useSchedulingStatus } from "@/lib/queries";

export type IntegrationsSearch = {
  scheduling?: string;
  provider?: string;
  message?: string;
  hubspot?: string;
};

export function IntegrationsSettingsPage({ search }: { search: IntegrationsSearch }) {
  const schedulingQ = useSchedulingStatus();
  const hubspotQ = useHubSpotStatus();

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
    if (search.hubspot === "connected") {
      toast.success("Connected HubSpot successfully");
      void hubspotQ.refetch();
    }
    if (search.hubspot === "error") {
      toast.error(search.message || "HubSpot connection failed");
    }
  }, [search.scheduling, search.provider, search.message, search.hubspot, schedulingQ, hubspotQ]);

  const scheduling = (schedulingQ.data || {}) as Record<string, unknown>;
  const hubspot = (hubspotQ.data || {}) as Record<string, unknown>;
  const humanReady = scheduling.human_scheduling_ready === true;
  const eventTypeReady = scheduling.event_type_configured === true;
  const calPlatformReady = scheduling.calendly_platform_configured === true;
  const cronPlatformReady = scheduling.cronofy_platform_configured === true;
  const hubspotConnected = hubspot.connected === true;
  const hubspotPlatformReady = hubspot.platform_configured === true;
  const hubspotSyncSettingsEnabled = hubspot.sync_settings_enabled === true;
  const hubspotUsesOAuth = hubspot.uses_oauth_connect === true;
  const hubspotUsesToken = hubspot.uses_access_token === true;
  const [hubspotTokenDraft, setHubspotTokenDraft] = React.useState("");
  const [hubspotTokenBusy, setHubspotTokenBusy] = React.useState(false);

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

  const startHubSpotOAuth = async () => {
    try {
      const data = await apiFetch<{ authorize_url?: string }>("/service-orders/hubspot/oauth/start");
      if (data?.authorize_url) {
        window.location.href = data.authorize_url;
        return;
      }
      toast.error("No authorization URL returned");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "HubSpot OAuth start failed");
    }
  };

  const patchHubSpotSettings = async (patch: Record<string, boolean>) => {
    try {
      await apiFetch("/service-orders/hubspot/settings", { method: "PATCH", body: JSON.stringify(patch) });
      void hubspotQ.refetch();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not update HubSpot settings");
    }
  };

  const disconnectHubSpot = async () => {
    try {
      await apiFetch("/service-orders/hubspot/disconnect", { method: "POST" });
      toast.success("HubSpot disconnected");
      setHubspotTokenDraft("");
      void hubspotQ.refetch();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Disconnect failed");
    }
  };

  const saveHubSpotAccessToken = async () => {
    const token = hubspotTokenDraft.trim();
    if (!token) {
      toast.error("Paste your HubSpot access token first");
      return;
    }
    setHubspotTokenBusy(true);
    try {
      await apiFetch("/service-orders/hubspot/connect-token", {
        method: "POST",
        body: JSON.stringify({ access_token: token }),
      });
      toast.success("HubSpot connected");
      setHubspotTokenDraft("");
      void hubspotQ.refetch();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not connect HubSpot");
    } finally {
      setHubspotTokenBusy(false);
    }
  };

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="Settings"
        title="Integrations"
        description="Connect Calendly or Cronofy for human interview booking, and HubSpot to sync shortlisted candidates to your CRM."
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
                : scheduling.calendly_connected && !eventTypeReady
                  ? "Calendly connected — pick an active event type in Calendly (or reconnect) before sending links"
                  : "Connect Calendly or Cronofy below before sending human interview links from Results"}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Calendly & Cronofy</CardTitle>
          <CardDescription>
            Required to send real booking links when you shortlist candidates after AI phone screening.
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
              name="Calendly"
              ok={Boolean(scheduling.calendly_connected)}
              note={calPlatformReady ? (scheduling.calendly_connected ? "Connected" : "Not connected") : "Admin setup required"}
            />
            <Health
              name="Cronofy"
              ok={Boolean(scheduling.cronofy_connected)}
              note={cronPlatformReady ? (scheduling.cronofy_connected ? "Connected" : "Not connected") : "Admin setup required"}
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><Users className="size-5 text-primary" /> HubSpot CRM</CardTitle>
          <CardDescription>
            Sync shortlisted candidates to HubSpot as contacts when you save a shortlist or send human interview links from Results.
            {hubspotUsesToken ? " Paste your HubSpot Service key here." : ""}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {!hubspotPlatformReady ? (
            <p className="rounded-md border border-border bg-muted/40 p-3 text-sm text-muted-foreground">
              HubSpot must be enabled in <strong className="text-foreground">VoxBulk admin → Integrations → HubSpot</strong> before you can connect your account.
            </p>
          ) : null}
          {hubspotQ.isLoading ? (
            <Skeleton className="h-10 w-full" />
          ) : (
            <>
              <div className="flex items-center gap-2 text-sm">
                <span className={"size-2 rounded-full " + (hubspotConnected ? "bg-success" : "bg-warning")} />
                {hubspotConnected
                  ? `Connected${hubspot.account_name ? ` — ${String(hubspot.account_name)}` : ""}`
                  : "Connect HubSpot to push shortlisted candidates into your CRM"}
              </div>
              <div className="flex flex-wrap gap-2">
                {hubspotUsesOAuth ? (
                  <Button variant="outline" className="gap-1.5" disabled={!hubspotPlatformReady || hubspotConnected} onClick={() => void startHubSpotOAuth()}>
                    <Plug className="size-4" /> Connect HubSpot
                  </Button>
                ) : (
                  <div className="flex w-full flex-col gap-2 sm:flex-row sm:items-end">
                    <div className="grid flex-1 gap-1.5">
                      <Label htmlFor="hubspot-token" className="text-sm">HubSpot Service key</Label>
                      <Input
                        id="hubspot-token"
                        type="password"
                        autoComplete="off"
                        placeholder={hubspotConnected ? "Paste new key to replace" : "Service key from HubSpot"}
                        value={hubspotTokenDraft}
                        onChange={(e) => setHubspotTokenDraft(e.target.value)}
                        disabled={!hubspotPlatformReady || hubspotTokenBusy}
                      />
                    </div>
                    <Button
                      variant="outline"
                      className="gap-1.5 shrink-0"
                      disabled={!hubspotPlatformReady || hubspotTokenBusy || !hubspotTokenDraft.trim()}
                      onClick={() => void saveHubSpotAccessToken()}
                    >
                      <Plug className="size-4" /> {hubspotConnected ? "Update token" : "Connect HubSpot"}
                    </Button>
                  </div>
                )}
                {hubspotConnected ? (
                  <Button variant="outline" onClick={() => void disconnectHubSpot()}>Disconnect</Button>
                ) : null}
              </div>
              {hubspotUsesToken && !hubspotConnected ? (
                <p className="text-xs text-muted-foreground">
                  In HubSpot: Settings → Integrations → <strong>Service Keys</strong> → create key → scopes{" "}
                  <code className="text-[11px]">crm.objects.contacts.read/write</code> → copy key. Do not use Developer API Key or Personal Access Key.
                </p>
              ) : null}
              {hubspotConnected ? (
                <div className="space-y-3 rounded-md border border-border p-3">
                  <div className="flex items-center justify-between gap-4">
                    <Label htmlFor="hubspot-shortlist" className="text-sm">Sync when saving shortlist</Label>
                    <Switch
                      id="hubspot-shortlist"
                      checked={hubspot.auto_sync_shortlist !== false}
                      onCheckedChange={(checked) => void patchHubSpotSettings({ auto_sync_shortlist: checked })}
                    />
                  </div>
                  <div className="flex items-center justify-between gap-4">
                    <Label htmlFor="hubspot-send" className="text-sm">Sync when sending interview links</Label>
                    <Switch
                      id="hubspot-send"
                      checked={hubspot.auto_sync_scheduling_send !== false}
                      onCheckedChange={(checked) => void patchHubSpotSettings({ auto_sync_scheduling_send: checked })}
                    />
                  </div>
                </div>
              ) : null}
            </>
          )}
        </CardContent>
      </Card>

      {hubspotSyncSettingsEnabled ? <HubspotSyncSettingsCard /> : null}

      <p className="text-xs text-muted-foreground">
        Need help? Open <Link to="/account/support" className="text-primary underline-offset-2 hover:underline">Support</Link> or ask your VoxBulk account manager to enable integrations in admin.
      </p>
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
