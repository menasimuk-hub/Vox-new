import * as React from "react";
import { CheckCircle2, ExternalLink, Plug, PowerOff, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { apiFetch } from "@/lib/api";

import { GoogleScheduleUrlHelp } from "@/components/google-schedule-url-help";
import { HubspotSyncSettingsCard } from "@/components/hubspot-sync-settings-card";
import {
  IntegrationStatusPill,
  type IntegrationStatus,
} from "@/components/integrations/integration-status-pill";
import { ProviderLogo } from "@/components/integrations/provider-logo";
import {
  TestResultCard,
  type TestResult,
} from "@/components/integrations/test-result-card";
import type { IntegrationView } from "@/components/integrations/provider-tile";

function statusFor(view: IntegrationView): IntegrationStatus {
  if (!view.platform_ready) return "disabled";
  if (view.last_check_ok === false) return "error";
  if (view.connected) return "connected";
  return "not_connected";
}

type Props = {
  view: IntegrationView | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConnect: (view: IntegrationView) => void;
  onTest: (view: IntegrationView) => Promise<TestResult | null>;
  onDisconnect: (view: IntegrationView) => Promise<void>;
  onRefresh: () => void;
  hubspot?: {
    syncSettingsEnabled: boolean;
    usesOAuth: boolean;
    usesAccessToken: boolean;
    showHubspotSettingsCard: boolean;
  };
};

export function ProviderDetailSheet({
  view,
  open,
  onOpenChange,
  onConnect,
  onTest,
  onDisconnect,
  onRefresh,
  hubspot,
}: Props) {
  const [testing, setTesting] = React.useState(false);
  const [testResult, setTestResult] = React.useState<TestResult | null>(null);
  const [scheduleDraft, setScheduleDraft] = React.useState("");
  const [scheduleBusy, setScheduleBusy] = React.useState(false);
  const [hubspotTokenDraft, setHubspotTokenDraft] = React.useState("");
  const [hubspotTokenBusy, setHubspotTokenBusy] = React.useState(false);

  React.useEffect(() => {
    setTestResult(null);
    setScheduleDraft("");
    setHubspotTokenDraft("");
  }, [view?.key]);

  if (!view) return null;
  const status = statusFor(view);
  const isBookingPage = view.group === "booking";

  const runTest = async () => {
    setTesting(true);
    try {
      const res = await onTest(view);
      setTestResult(res);
    } finally {
      setTesting(false);
    }
  };

  const disconnect = async () => {
    try {
      await onDisconnect(view);
      onOpenChange(false);
    } catch {
      /* parent toast */
    }
  };

  const saveScheduleUrl = async (endpoint: string, validatorHint: string) => {
    const url = scheduleDraft.trim();
    if (!url.startsWith("http")) {
      toast.error(validatorHint);
      return;
    }
    setScheduleBusy(true);
    try {
      await apiFetch(endpoint, {
        method: "POST",
        body: JSON.stringify({ schedule_url: url, schedule_name: "" }),
      });
      toast.success("Booking page URL saved");
      setScheduleDraft("");
      onRefresh();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not save URL");
    } finally {
      setScheduleBusy(false);
    }
  };

  const connectHubspotToken = async () => {
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
      onRefresh();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not connect HubSpot");
    } finally {
      setHubspotTokenBusy(false);
    }
  };

  const showGoogleScheduleField =
    isBookingPage && view.key === "google_calendar" && view.connected;
  const showMicrosoftScheduleField =
    isBookingPage && view.key === "microsoft_calendar" && view.connected;
  const showHubspotTokenField =
    !isBookingPage && view.key === "hubspot" && hubspot?.usesAccessToken && !view.connected;
  const showHubspotSyncToggles =
    !isBookingPage && view.key === "hubspot" && view.connected;
  const crmSettingsUrl =
    view.key === "pipedrive"
      ? "/service-orders/pipedrive/settings"
      : view.key === "zoho_crm"
        ? "/service-orders/zoho-crm/settings"
        : null;
  const showGenericCrmSyncToggles = !isBookingPage && Boolean(crmSettingsUrl) && view.connected;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-md">
        <SheetHeader className="space-y-3">
          <div className="flex items-start gap-3">
            <ProviderLogo
              iconSlug={view.icon_slug}
              providerKey={view.key}
              label={view.label}
              className="size-14"
              imgClassName="max-h-10 max-w-10"
            />
            <div className="min-w-0 flex-1 space-y-2">
              <div className="flex items-center justify-between gap-2">
                <SheetTitle>{view.label}</SheetTitle>
                <IntegrationStatusPill status={status} />
              </div>
              <SheetDescription>{view.short_description}</SheetDescription>
            </div>
          </div>
        </SheetHeader>

        <div className="mt-5 space-y-4">
          {!view.platform_ready ? (
            <p className="rounded-md border border-border bg-muted/40 p-3 text-xs text-muted-foreground">
              This provider is not yet configured by your VoxBulk admin. Once admin enables it and toggles
              <strong className="text-foreground"> Visible to organisations</strong>, it will become connectable here.
            </p>
          ) : null}

          {view.connected ? (
            <div className="rounded-md border border-border bg-muted/30 p-3 text-sm">
              <div className="flex items-center gap-2 font-medium">
                <CheckCircle2 className="size-4 text-success" /> Connected
              </div>
              <dl className="mt-2 grid grid-cols-1 gap-1 text-xs text-muted-foreground">
                {view.connected_account ? (
                  <div className="flex items-center justify-between gap-2">
                    <dt>Account</dt>
                    <dd className="truncate text-foreground">{view.connected_account}</dd>
                  </div>
                ) : null}
                {view.last_check_at ? (
                  <div className="flex items-center justify-between gap-2">
                    <dt>Last tested</dt>
                    <dd className="text-foreground">{new Date(view.last_check_at).toLocaleString()}</dd>
                  </div>
                ) : null}
                {typeof view.extra?.event_type_url === "string" && view.extra.event_type_url ? (
                  <div className="flex items-center justify-between gap-2">
                    <dt>Booking URL</dt>
                    <dd>
                      <a
                        href={view.extra.event_type_url as string}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-primary underline-offset-2 hover:underline"
                      >
                        Open <ExternalLink className="size-3" />
                      </a>
                    </dd>
                  </div>
                ) : null}
              </dl>
            </div>
          ) : null}

          {view.blocked_reason ? (
            <p className="rounded-md border border-warning/50 bg-warning/10 p-3 text-xs text-foreground">
              {view.blocked_reason}
            </p>
          ) : null}

          {showGoogleScheduleField ? (
            <div className="space-y-2 rounded-md border bg-muted/30 p-3">
              <div className="flex items-center gap-1">
                <Label htmlFor="google-schedule-url" className="text-sm">
                  Google appointment schedule URL
                </Label>
                <GoogleScheduleUrlHelp />
              </div>
              <Input
                id="google-schedule-url"
                placeholder="https://calendar.google.com/calendar/appointments/schedules/…"
                value={scheduleDraft}
                onChange={(e) => setScheduleDraft(e.target.value)}
              />
              <Button
                variant="outline"
                size="sm"
                disabled={scheduleBusy}
                onClick={() =>
                  void saveScheduleUrl(
                    "/service-orders/scheduling/google-calendar/select-schedule",
                    "Paste your Google appointment schedule booking link (calendar.google.com/calendar/appointments/… or calendar.app.google/…)",
                  )
                }
              >
                Save schedule
              </Button>
            </div>
          ) : null}

          {showMicrosoftScheduleField ? (
            <div className="space-y-2 rounded-md border bg-muted/30 p-3">
              <Label htmlFor="microsoft-schedule-url" className="text-sm">
                Microsoft Bookings page URL
              </Label>
              <Input
                id="microsoft-schedule-url"
                placeholder="https://outlook.office365.com/owa/calendar/…/bookings/"
                value={scheduleDraft}
                onChange={(e) => setScheduleDraft(e.target.value)}
              />
              <Button
                variant="outline"
                size="sm"
                disabled={scheduleBusy}
                onClick={() =>
                  void saveScheduleUrl(
                    "/service-orders/scheduling/microsoft-calendar/select-schedule",
                    "Paste your Microsoft Bookings public booking page URL (outlook.office365.com/owa/calendar/…/bookings/ or book.ms/…)",
                  )
                }
              >
                Save Bookings page
              </Button>
              <p className="text-[11px] text-muted-foreground">
                When you send interview links from Results, each candidate gets an email with this URL — Microsoft Bookings does not send those emails for you.
              </p>
            </div>
          ) : null}

          {showHubspotTokenField ? (
            <div className="space-y-2 rounded-md border bg-muted/30 p-3">
              <Label htmlFor="hubspot-token" className="text-sm">HubSpot Service key</Label>
              <Input
                id="hubspot-token"
                type="password"
                autoComplete="off"
                placeholder="Service key from HubSpot"
                value={hubspotTokenDraft}
                onChange={(e) => setHubspotTokenDraft(e.target.value)}
                disabled={hubspotTokenBusy}
              />
              <Button
                variant="outline"
                size="sm"
                disabled={hubspotTokenBusy || !hubspotTokenDraft.trim()}
                onClick={() => void connectHubspotToken()}
              >
                <Plug className="size-4" /> Connect HubSpot
              </Button>
            </div>
          ) : null}

          {showHubspotSyncToggles ? (
            <div className="space-y-3 rounded-md border p-3">
              <p className="text-sm font-medium">Auto-sync</p>
              <div className="flex items-center justify-between gap-4">
                <Label htmlFor="hubspot-shortlist" className="text-sm">Sync when saving shortlist</Label>
                <Switch
                  id="hubspot-shortlist"
                  checked={(view.extra?.auto_sync_shortlist ?? true) !== false}
                  onCheckedChange={async (checked) => {
                    try {
                      await apiFetch("/service-orders/hubspot/settings", {
                        method: "PATCH",
                        body: JSON.stringify({ auto_sync_shortlist: checked }),
                      });
                      onRefresh();
                    } catch (e) {
                      toast.error(e instanceof Error ? e.message : "Update failed");
                    }
                  }}
                />
              </div>
              <div className="flex items-center justify-between gap-4">
                <Label htmlFor="hubspot-send" className="text-sm">Sync when sending interview links</Label>
                <Switch
                  id="hubspot-send"
                  checked={(view.extra?.auto_sync_scheduling_send ?? true) !== false}
                  onCheckedChange={async (checked) => {
                    try {
                      await apiFetch("/service-orders/hubspot/settings", {
                        method: "PATCH",
                        body: JSON.stringify({ auto_sync_scheduling_send: checked }),
                      });
                      onRefresh();
                    } catch (e) {
                      toast.error(e instanceof Error ? e.message : "Update failed");
                    }
                  }}
                />
              </div>
              <div className="flex items-start justify-between gap-4">
                <div className="space-y-0.5">
                  <Label htmlFor="hubspot-unhappy-task" className="text-sm">
                    Create CRM task on unhappy survey
                  </Label>
                  <p className="text-xs text-muted-foreground">
                    Adds a follow-up task (due in 24h) when a WA or AI call survey response is flagged unhappy.
                  </p>
                </div>
                <Switch
                  id="hubspot-unhappy-task"
                  checked={view.extra?.create_task_on_unhappy_score === true}
                  onCheckedChange={async (checked) => {
                    try {
                      await apiFetch("/service-orders/hubspot/settings", {
                        method: "PATCH",
                        body: JSON.stringify({ create_task_on_unhappy_score: checked }),
                      });
                      onRefresh();
                    } catch (e) {
                      toast.error(e instanceof Error ? e.message : "Update failed");
                    }
                  }}
                />
              </div>
            </div>
          ) : null}

          {showGenericCrmSyncToggles && crmSettingsUrl ? (
            <div className="space-y-3 rounded-md border p-3">
              <p className="text-sm font-medium">Auto-sync</p>
              <div className="flex items-center justify-between gap-4">
                <Label htmlFor="crm-shortlist" className="text-sm">Sync when saving shortlist</Label>
                <Switch
                  id="crm-shortlist"
                  checked={(view.extra?.auto_sync_shortlist ?? true) !== false}
                  onCheckedChange={async (checked) => {
                    try {
                      await apiFetch(crmSettingsUrl, {
                        method: "PATCH",
                        body: JSON.stringify({ auto_sync_shortlist: checked }),
                      });
                      onRefresh();
                    } catch (e) {
                      toast.error(e instanceof Error ? e.message : "Update failed");
                    }
                  }}
                />
              </div>
              <div className="flex items-center justify-between gap-4">
                <Label htmlFor="crm-send" className="text-sm">Sync when sending interview links</Label>
                <Switch
                  id="crm-send"
                  checked={(view.extra?.auto_sync_scheduling_send ?? true) !== false}
                  onCheckedChange={async (checked) => {
                    try {
                      await apiFetch(crmSettingsUrl, {
                        method: "PATCH",
                        body: JSON.stringify({ auto_sync_scheduling_send: checked }),
                      });
                      onRefresh();
                    } catch (e) {
                      toast.error(e instanceof Error ? e.message : "Update failed");
                    }
                  }}
                />
              </div>
              <div className="flex items-start justify-between gap-4">
                <div className="space-y-0.5">
                  <Label htmlFor="crm-unhappy-task" className="text-sm">
                    Create CRM task on unhappy survey
                  </Label>
                  <p className="text-xs text-muted-foreground">
                    Adds a follow-up task (due in 24h) when a WA or AI call survey response is flagged unhappy.
                  </p>
                </div>
                <Switch
                  id="crm-unhappy-task"
                  checked={view.extra?.create_task_on_unhappy_score === true}
                  onCheckedChange={async (checked) => {
                    try {
                      await apiFetch(crmSettingsUrl, {
                        method: "PATCH",
                        body: JSON.stringify({ create_task_on_unhappy_score: checked }),
                      });
                      onRefresh();
                    } catch (e) {
                      toast.error(e instanceof Error ? e.message : "Update failed");
                    }
                  }}
                />
              </div>
            </div>
          ) : null}

          {showHubspotSyncToggles && hubspot?.showHubspotSettingsCard ? <HubspotSyncSettingsCard /> : null}

          <TestResultCard loading={testing} result={testResult} />

          <div className="flex flex-wrap gap-2 pt-2">
            {!view.connected && view.actions.connect_url ? (
              <Button
                variant="default"
                className="gap-1.5"
                disabled={!view.platform_ready || Boolean(view.blocked_reason)}
                onClick={() => onConnect(view)}
              >
                <Plug className="size-4" /> Connect {view.label}
              </Button>
            ) : null}
            <Button
              variant="outline"
              className="gap-1.5"
              disabled={!view.connected || testing}
              onClick={() => void runTest()}
            >
              <RefreshCw className={`size-4 ${testing ? "animate-spin" : ""}`} /> Test connection
            </Button>
            {view.connected ? (
              <Button variant="outline" className="gap-1.5" onClick={() => void disconnect()}>
                <PowerOff className="size-4" /> Disconnect
              </Button>
            ) : null}
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}
