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

type BookingProviderKey = "calendly" | "cal_com" | "google_calendar" | "hubspot_meetings";

const BOOKING_OPTIONS: { key: BookingProviderKey; label: string }[] = [
  { key: "calendly", label: "Calendly" },
  { key: "hubspot_meetings", label: "HubSpot Meetings" },
  { key: "google_calendar", label: "Google Calendar" },
  { key: "cal_com", label: "Cal.com" },
];

const PROVIDER_LABEL: Record<string, string> = {
  calendly: "Calendly",
  cal_com: "Cal.com",
  google_calendar: "Google Calendar",
  hubspot_meetings: "HubSpot Meetings",
  cronofy: "Cronofy",
};

export function IntegrationsSettingsPage({ search }: { search: IntegrationsSearch }) {
  const schedulingQ = useSchedulingStatus();
  const hubspotQ = useHubSpotStatus();

  React.useEffect(() => {
    if (search.scheduling === "connected") {
      const label = PROVIDER_LABEL[search.provider || ""] || search.provider || "scheduling";
      toast.success(`Connected ${label} successfully`);
      void schedulingQ.refetch();
    }
    if (search.scheduling === "error") {
      toast.error(search.message || "Calendar connection failed");
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
  const connectedProvider = String(scheduling.provider || "").trim() as BookingProviderKey | "";
  const providerLabel = String(scheduling.provider_label || PROVIDER_LABEL[connectedProvider] || "").trim();
  const connectedAccount = String(scheduling.connected_account || scheduling.owner_name || "").trim();
  const legacyUnsupported = Boolean(scheduling.legacy_unsupported_provider);
  const hubspotConnected = hubspot.connected === true;
  const hubspotPlatformReady = hubspot.platform_configured === true;
  const hubspotSyncSettingsEnabled = hubspot.sync_settings_enabled === true;
  const hubspotUsesOAuth = hubspot.uses_oauth_connect === true;
  const hubspotUsesToken = hubspot.uses_access_token === true;

  const [hubspotTokenDraft, setHubspotTokenDraft] = React.useState("");
  const [hubspotTokenBusy, setHubspotTokenBusy] = React.useState(false);
  const [meetingLinks, setMeetingLinks] = React.useState<Array<{ id: string; name: string; url: string }>>([]);
  const [meetingLinksBusy, setMeetingLinksBusy] = React.useState(false);
  const [scheduleUrlDraft, setScheduleUrlDraft] = React.useState("");
  const [switchConfirm, setSwitchConfirm] = React.useState<BookingProviderKey | null>(null);

  const platformReady = (key: BookingProviderKey) => {
    if (key === "hubspot_meetings") return Boolean(scheduling.hubspot_platform_configured);
    return Boolean(scheduling[`${key}_platform_configured`]);
  };

  const disconnectScheduling = async () => {
    try {
      await apiFetch("/service-orders/scheduling/disconnect", { method: "POST", body: JSON.stringify({}) });
      toast.success("Booking provider disconnected");
      void schedulingQ.refetch();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Disconnect failed");
    }
  };

  const startOAuth = async (provider: "calendly" | "cal_com" | "google_calendar", replace = false) => {
    try {
      const path = provider === "cal_com"
        ? "cal-com"
        : provider === "google_calendar"
          ? "google-calendar"
          : provider;
      const qs = replace ? "?replace=true" : "";
      const data = await apiFetch<{ authorize_url?: string }>(`/service-orders/scheduling/oauth/${path}/start${qs}`);
      if (data?.authorize_url) {
        window.location.href = data.authorize_url;
        return;
      }
      toast.error("No authorization URL returned");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "OAuth start failed");
    }
  };

  const connectProvider = async (provider: BookingProviderKey) => {
    if (connectedProvider && connectedProvider !== provider) {
      setSwitchConfirm(provider);
      return;
    }
    if (provider === "hubspot_meetings") {
      if (!hubspotConnected) {
        toast.error("Connect HubSpot CRM first");
        return;
      }
      if (hubspotUsesToken) {
        toast.error("HubSpot Meetings requires OAuth HubSpot CRM (not Service key mode)");
        return;
      }
      setMeetingLinksBusy(true);
      try {
        const data = await apiFetch<{ meeting_links?: Array<{ id: string; name: string; url: string }> }>(
          "/service-orders/scheduling/hubspot/meeting-links",
        );
        const links = data?.meeting_links || [];
        setMeetingLinks(links);
        if (links.length === 0) {
          toast.error("No HubSpot meeting links found — check Scheduler scopes and reconnect CRM");
        }
      } catch (e) {
        toast.error(e instanceof Error ? e.message : "Could not load meeting links");
      } finally {
        setMeetingLinksBusy(false);
      }
      return;
    }
    await startOAuth(provider);
  };

  const confirmSwitch = async () => {
    const next = switchConfirm;
    setSwitchConfirm(null);
    if (!next) return;
    await disconnectScheduling();
    if (next === "hubspot_meetings") {
      await connectProvider(next);
    } else {
      await startOAuth(next, true);
    }
  };

  const selectMeetingLink = async (link: { id: string; name: string; url: string }) => {
    try {
      await apiFetch("/service-orders/scheduling/hubspot/select-meeting-link", {
        method: "POST",
        body: JSON.stringify({
          meeting_link_id: link.id,
          meeting_link_url: link.url,
          meeting_link_name: link.name,
        }),
      });
      toast.success("HubSpot Meetings connected");
      setMeetingLinks([]);
      void schedulingQ.refetch();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not connect meeting link");
    }
  };

  const saveGoogleScheduleUrl = async () => {
    const url = scheduleUrlDraft.trim();
    if (!url.startsWith("http")) {
      toast.error("Enter a valid appointment schedule URL");
      return;
    }
    try {
      await apiFetch("/service-orders/scheduling/google-calendar/select-schedule", {
        method: "POST",
        body: JSON.stringify({ schedule_url: url, schedule_name: "Appointment schedule" }),
      });
      toast.success("Google Calendar schedule saved");
      setScheduleUrlDraft("");
      void schedulingQ.refetch();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not save schedule URL");
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
      void schedulingQ.refetch();
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
        description="Connect one booking provider for human interview scheduling after AI screening, and HubSpot CRM to sync shortlisted candidates."
        actions={<Button variant="outline" className="gap-1.5"><ListChecks className="size-4" /> Show setup checklist</Button>}
      />

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><CalendarCheck className="size-5 text-success" /> Booking provider</CardTitle>
          <CardDescription>
            Choose <strong className="text-foreground">one</strong> calendar provider. Used when you send booking links from campaign Results.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {schedulingQ.isLoading ? (
            <Skeleton className="h-10 w-full" />
          ) : (
            <>
              <div className="flex items-center gap-2 text-sm">
                <span className={"size-2 rounded-full " + (humanReady ? "bg-success" : legacyUnsupported ? "bg-destructive" : "bg-warning")} />
                {legacyUnsupported
                  ? "Previous provider (Cronofy) is no longer supported — connect a provider below"
                  : humanReady
                    ? `Connected — ${providerLabel}${connectedAccount ? ` (${connectedAccount})` : ""}`
                    : connectedProvider
                      ? `${providerLabel} connected — finish setup (event type or meeting link)`
                      : "No booking provider connected"}
              </div>
              <div className="flex flex-wrap gap-2">
                {BOOKING_OPTIONS.map(({ key, label }) => {
                  const isConnected = connectedProvider === key && humanReady;
                  const isActive = connectedProvider === key;
                  const disabled = !platformReady(key) || (Boolean(connectedProvider) && connectedProvider !== key && humanReady);
                  return (
                    <Button
                      key={key}
                      variant={isActive ? "default" : "outline"}
                      className="gap-1.5"
                      disabled={disabled || isConnected || meetingLinksBusy}
                      onClick={() => void connectProvider(key)}
                    >
                      <Plug className="size-4" /> {isConnected ? `${label} connected` : `Connect ${label}`}
                    </Button>
                  );
                })}
                {connectedProvider ? (
                  <Button variant="outline" onClick={() => void disconnectScheduling()}>Disconnect</Button>
                ) : null}
              </div>
              {meetingLinks.length > 0 ? (
                <div className="space-y-2 rounded-md border border-border p-3">
                  <p className="text-sm font-medium">Pick a HubSpot meeting link</p>
                  {meetingLinks.map((link) => (
                    <Button key={link.id || link.url} variant="outline" className="w-full justify-start" onClick={() => void selectMeetingLink(link)}>
                      {link.name || link.url}
                    </Button>
                  ))}
                </div>
              ) : null}
              {connectedProvider === "google_calendar" && !humanReady ? (
                <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
                  <div className="grid flex-1 gap-1.5">
                    <Label htmlFor="google-schedule-url" className="text-sm">Google appointment schedule URL</Label>
                    <Input
                      id="google-schedule-url"
                      placeholder="https://calendar.google.com/calendar/appointments/..."
                      value={scheduleUrlDraft}
                      onChange={(e) => setScheduleUrlDraft(e.target.value)}
                    />
                  </div>
                  <Button variant="outline" onClick={() => void saveGoogleScheduleUrl()}>Save schedule</Button>
                </div>
              ) : null}
            </>
          )}
        </CardContent>
      </Card>

      {switchConfirm ? (
        <Card className="border-warning/50">
          <CardContent className="space-y-3 p-4">
            <p className="text-sm">
              Switch from {providerLabel || connectedProvider} to {PROVIDER_LABEL[switchConfirm]}? This disconnects your current booking provider.
            </p>
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setSwitchConfirm(null)}>Cancel</Button>
              <Button onClick={() => void confirmSwitch()}>Switch provider</Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

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
                  Service key mode supports CRM sync only. HubSpot Meetings booking requires OAuth CRM.
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
