import * as React from "react";
import { CheckCircle2, ExternalLink, Plug, PowerOff, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { apiFetch } from "@/lib/api";

import { GoogleScheduleUrlHelp } from "@/components/google-schedule-url-help";
import { integrationStatusFor } from "@/components/integrations/integration-status";
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
import { ZohoRecruitLaunchPanel } from "@/components/integrations/zoho-recruit-launch-panel";

function statusFor(view: IntegrationView): IntegrationStatus {
  return integrationStatusFor(view);
}

type Props = {
  view: IntegrationView | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConnect: (view: IntegrationView, options?: { dataCenter?: string }) => void;
  onTest: (view: IntegrationView) => Promise<TestResult | null>;
  onDisconnect: (view: IntegrationView) => Promise<void>;
  onRefresh: () => void;
  hubspot?: {
    usesOAuth: boolean;
    usesAccessToken: boolean;
  };
};

type DataCenterOption = { id: string; label: string; accounts?: string };

const DEFAULT_RECRUIT_DCS: DataCenterOption[] = [
  { id: "eu", label: "Europe (EU)" },
  { id: "uk", label: "United Kingdom" },
  { id: "com", label: "United States" },
  { id: "ca", label: "Canada" },
  { id: "in", label: "India" },
  { id: "au", label: "Australia" },
  { id: "jp", label: "Japan" },
  { id: "ae", label: "UAE" },
  { id: "sa", label: "Saudi Arabia" },
];

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
  const [recruitDc, setRecruitDc] = React.useState("eu");

  React.useEffect(() => {
    setTestResult(null);
    setScheduleDraft("");
    setHubspotTokenDraft("");
    const extras = view?.extra?.data_centers;
    const first =
      Array.isArray(extras) && extras.length > 0 && typeof (extras[0] as { id?: string })?.id === "string"
        ? String((extras[0] as { id: string }).id)
        : "eu";
    const connectedDc = typeof view?.extra?.data_center === "string" ? view.extra.data_center : null;
    setRecruitDc(connectedDc || first);
  }, [view?.key, view?.extra?.data_center, view?.extra?.data_centers]);

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

          {view.extra?.token_decrypt_failed === true ? (
            <p className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-xs text-destructive">
              A Microsoft/Google token is stored for this organisation but the API cannot decrypt it. Ask your admin to
              verify <code className="text-[11px]">ENCRYPTION_KEY</code> on the API server has not changed, then
              disconnect and reconnect here.
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
              {!isBookingPage ? (
                <p className="mt-3 text-xs text-muted-foreground">
                  Appointment-specific mapping (CRM object, lists, WhatsApp template) is configured in Appointment Setup.
                </p>
              ) : null}
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
                autoFocus={open && view.extra?.event_type_configured === false}
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
                autoFocus={open && view.extra?.event_type_configured === false}
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

          {view.key === "zoho_recruit" && !view.connected ? (
            <div className="space-y-2 rounded-md border bg-muted/30 p-3">
              <Label htmlFor="zoho-recruit-dc" className="text-sm">
                Zoho data centre
              </Label>
              <select
                id="zoho-recruit-dc"
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/40"
                value={recruitDc}
                onChange={(e) => setRecruitDc(e.target.value)}
              >
                {(
                  (Array.isArray(view.extra?.data_centers)
                    ? (view.extra.data_centers as DataCenterOption[])
                    : DEFAULT_RECRUIT_DCS) as DataCenterOption[]
                ).map((dc) => (
                  <option key={dc.id} value={dc.id}>
                    {dc.label}
                  </option>
                ))}
              </select>
              <p className="text-[11px] leading-relaxed text-muted-foreground">
                Choose the region where your Zoho Recruit company is hosted (EU, UK, US, Canada, and more). Wrong region
                usually causes login or API errors.
              </p>
            </div>
          ) : null}

          {view.key === "zoho_recruit" && view.connected ? (
            <ZohoRecruitLaunchPanel onLaunched={onRefresh} />
          ) : null}

          {view.key === "zoho_recruit" && view.connected && view.extra?.data_center ? (
            <p className="text-xs text-muted-foreground">
              Connected data centre: <span className="font-medium text-foreground">{String(view.extra.data_center).toUpperCase()}</span>
              {view.extra.api_domain ? ` · ${String(view.extra.api_domain)}` : ""}
            </p>
          ) : null}

          <TestResultCard loading={testing} result={testResult} />

          <div className="flex flex-wrap gap-2 pt-2">
            {!view.connected && view.actions.connect_url ? (
              <Button
                variant="default"
                className="gap-1.5"
                disabled={!view.platform_ready || Boolean(view.blocked_reason)}
                onClick={() =>
                  onConnect(
                    view,
                    view.key === "zoho_recruit" ? { dataCenter: recruitDc } : undefined,
                  )
                }
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
