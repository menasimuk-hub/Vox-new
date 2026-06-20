import * as React from "react";
import { Link, useNavigate } from "@tanstack/react-router";
import { CalendarCheck, Plug, RefreshCw, Users } from "lucide-react";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

import { ProviderTile, type IntegrationView } from "@/components/integrations/provider-tile";
import { ProviderLogo } from "@/components/integrations/provider-logo";
import { ProviderDetailSheet } from "@/components/integrations/provider-detail-sheet";
import type { TestResult } from "@/components/integrations/test-result-card";
import { apiFetch } from "@/lib/api";
import {
  useDisconnectIntegration,
  useHubSpotStatus,
  useIntegrationsCatalogue,
  useTestIntegration,
} from "@/lib/queries";

export type IntegrationsSearch = {
  scheduling?: string;
  provider?: string;
  message?: string;
  hubspot?: string;
  crm?: string;
  tab?: string;
};

const PROVIDER_LABEL: Record<string, string> = {
  calendly: "Calendly",
  cal_com: "Cal.com",
  google_calendar: "Google Calendar",
  microsoft_calendar: "Microsoft 365 Calendar",
  hubspot_meetings: "HubSpot Meetings",
  zoho_bookings: "Zoho Bookings",
  hubspot: "HubSpot CRM",
  pipedrive: "Pipedrive",
  zoho_crm: "Zoho CRM",
  cronofy: "Cronofy",
};

function tabFromSearch(tab?: string): "booking" | "crm" {
  return tab === "crm" ? "crm" : "booking";
}

export function IntegrationsSettingsPage({ search }: { search: IntegrationsSearch }) {
  const navigate = useNavigate();
  const catalogueQ = useIntegrationsCatalogue();
  const hubspotQ = useHubSpotStatus();
  const testMutation = useTestIntegration();
  const disconnectMutation = useDisconnectIntegration();
  const oauthNoticeShown = React.useRef<string | null>(null);

  const [activeTab, setActiveTab] = React.useState<"booking" | "crm">(() => tabFromSearch(search.tab));
  const [sheetView, setSheetView] = React.useState<IntegrationView | null>(null);
  const [sheetOpen, setSheetOpen] = React.useState(false);

  React.useEffect(() => {
    const next = tabFromSearch(search.tab);
    setActiveTab(next);
  }, [search.tab]);

  React.useEffect(() => {
    const noticeKey = [
      search.scheduling,
      search.hubspot,
      search.crm,
      search.provider,
      search.message,
    ]
      .filter(Boolean)
      .join("|");
    if (!noticeKey || oauthNoticeShown.current === noticeKey) return;

    let message: string | null = null;
    let isError = false;

    if (search.scheduling === "connected") {
      const label = PROVIDER_LABEL[search.provider || ""] || search.provider || "scheduling";
      message = `Connected ${label} successfully`;
    } else if (search.scheduling === "error") {
      message = search.message || "Calendar connection failed";
      isError = true;
    } else if (search.hubspot === "connected") {
      message = "Connected HubSpot successfully";
    } else if (search.hubspot === "error") {
      message = search.message || "HubSpot connection failed";
      isError = true;
    } else if (search.crm === "connected") {
      const label = PROVIDER_LABEL[search.provider || ""] || search.provider || "CRM";
      message = `Connected ${label} successfully`;
    } else if (search.crm === "error") {
      message = search.message || "CRM connection failed";
      isError = true;
    }

    if (!message) return;

    oauthNoticeShown.current = noticeKey;
    if (isError) {
      toast.error(message);
    } else {
      toast.success(message);
    }
    void catalogueQ.refetch();
    if (search.hubspot === "connected" || search.crm === "connected") {
      void hubspotQ.refetch();
    }
    void navigate({
      to: "/settings/integrations",
      search: { tab: tabFromSearch(search.tab) },
      replace: true,
    });
  }, [
    search.scheduling,
    search.provider,
    search.message,
    search.hubspot,
    search.crm,
    search.tab,
    catalogueQ,
    hubspotQ,
    navigate,
  ]);

  const data = catalogueQ.data;
  const booking = (data?.booking ?? []) as IntegrationView[];
  const crm = (data?.crm ?? []) as IntegrationView[];
  const activeBookingProvider = data?.active_booking_provider ?? null;
  const activeBookingView = booking.find((b) => b.connected) || null;
  const activeCrmProvider = (data as { active_crm_provider?: string | null })?.active_crm_provider ?? null;
  const activeCrmView = crm.find((c) => c.connected) || null;

  const hubspot = (hubspotQ.data || {}) as Record<string, unknown>;
  const hubspotMeta = {
    syncSettingsEnabled: hubspot.sync_settings_enabled === true,
    usesOAuth: hubspot.uses_oauth_connect === true,
    usesAccessToken: hubspot.uses_access_token === true,
    showHubspotSettingsCard: hubspot.sync_settings_enabled === true,
  };

  const openTile = (view: IntegrationView) => {
    setSheetView(view);
    setSheetOpen(true);
  };

  const refresh = () => {
    void catalogueQ.refetch();
    void hubspotQ.refetch();
  };

  const connect = async (view: IntegrationView) => {
    if (!view.platform_ready) {
      toast.error(`${view.label} is not yet enabled by your VoxBulk admin`);
      return;
    }
    if (view.blocked_reason) {
      toast.error(view.blocked_reason);
      return;
    }
    if (view.key === "hubspot_meetings") {
      try {
        const meetings = await apiFetch<{ meeting_links?: Array<{ id: string; name: string; url: string }> }>(
          "/service-orders/scheduling/hubspot/meeting-links",
        );
        const links = meetings?.meeting_links || [];
        if (links.length === 0) {
          toast.error("No HubSpot meeting links found — check Scheduler scopes and reconnect CRM");
          return;
        }
        const first = links[0];
        await apiFetch("/service-orders/scheduling/hubspot/select-meeting-link", {
          method: "POST",
          body: JSON.stringify({
            meeting_link_id: first.id,
            meeting_link_url: first.url,
            meeting_link_name: first.name,
          }),
        });
        toast.success("HubSpot Meetings connected");
        refresh();
      } catch (e) {
        toast.error(e instanceof Error ? e.message : "Could not connect HubSpot Meetings");
      }
      return;
    }
    if (view.key === "zoho_bookings") {
      try {
        const services = await apiFetch<{ booking_services?: Array<{ id: string; name: string; url: string }> }>(
          "/service-orders/scheduling/zoho/booking-services",
        );
        const rows = services?.booking_services || [];
        if (rows.length === 0) {
          toast.error("No Zoho Bookings services found — check Zoho Bookings scopes and reconnect Zoho CRM");
          return;
        }
        const first = rows[0];
        await apiFetch("/service-orders/scheduling/zoho/select-booking-service", {
          method: "POST",
          body: JSON.stringify({
            service_id: first.id,
            service_url: first.url,
            service_name: first.name,
          }),
        });
        toast.success("Zoho Bookings connected");
        refresh();
      } catch (e) {
        toast.error(e instanceof Error ? e.message : "Could not connect Zoho Bookings");
      }
      return;
    }
    if (view.key === "hubspot") {
      if (hubspotMeta.usesOAuth) {
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
        return;
      }
      // Token-mode: detail sheet renders the paste field; nothing else to do here.
      return;
    }
    if (!view.actions.connect_url) {
      toast.error("This provider does not support direct connect from the dashboard");
      return;
    }
    try {
      const data = await apiFetch<{ authorize_url?: string }>(view.actions.connect_url);
      if (data?.authorize_url) {
        window.location.href = data.authorize_url;
        return;
      }
      toast.error("No authorization URL returned");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "OAuth start failed");
    }
  };

  const test = async (view: IntegrationView): Promise<TestResult | null> => {
    try {
      return await testMutation.mutateAsync(view.key);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Test failed");
      return null;
    }
  };

  const disconnect = async (view: IntegrationView) => {
    try {
      await disconnectMutation.mutateAsync(view.key);
      toast.success(`${view.label} disconnected`);
      refresh();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Disconnect failed");
      throw e;
    }
  };

  const renderGrid = (rows: IntegrationView[]) => {
    if (catalogueQ.isLoading) {
      return (
        <div className="grid gap-4 md:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-[5.25rem] w-full rounded-lg" />
          ))}
        </div>
      );
    }
    if (rows.length === 0) {
      return (
        <p className="rounded-lg border border-dashed bg-muted/30 p-6 text-sm leading-relaxed text-muted-foreground">
          No providers in this group are available yet. In Admin → Integrations, open the provider, turn on{" "}
          <strong>Enable</strong> and <strong>Visible to organisations</strong>, then save.
        </p>
      );
    }
    return (
      <div className="grid gap-4 md:grid-cols-2">
        {rows.map((row) => (
          <ProviderTile
            key={row.key}
            view={row}
            active={row.key === activeBookingProvider || row.key === activeCrmProvider}
            onOpen={openTile}
          />
        ))}
      </div>
    );
  };

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="Settings"
        title="Integrations"
        description="Connect one booking provider for human interview scheduling, and your CRM to sync shortlisted candidates and survey results."
        actions={
          <Button variant="outline" className="gap-1.5" onClick={refresh}>
            <RefreshCw className="size-4" /> Refresh
          </Button>
        }
      />

      {catalogueQ.isError ? (
        <p className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          Could not load integrations. <Button variant="link" className="h-auto p-0" onClick={refresh}>Retry</Button>
        </p>
      ) : null}

      {activeBookingView && activeBookingView.connected ? (
        <Card>
          <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-3">
              <ProviderLogo
                iconSlug={activeBookingView.icon_slug}
                providerKey={activeBookingView.key}
                label={activeBookingView.label}
                className="size-11"
                imgClassName="max-h-8 max-w-8"
              />
              <div className="min-w-0">
                <p className="text-sm font-medium leading-tight">Active booking provider: {activeBookingView.label}</p>
                <p className="truncate text-xs text-muted-foreground">
                  {activeBookingView.connected_account || "Connected"} · used when you send interview booking links
                  from campaign Results.
                </p>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" size="sm" className="gap-1.5" onClick={() => openTile(activeBookingView)}>
                <Plug className="size-4" /> Manage
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {activeCrmView && activeCrmView.connected ? (
        <Card>
          <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-3">
              <ProviderLogo
                iconSlug={activeCrmView.icon_slug}
                providerKey={activeCrmView.key}
                label={activeCrmView.label}
                className="size-11"
                imgClassName="max-h-8 max-w-8"
              />
              <div className="min-w-0">
                <p className="text-sm font-medium leading-tight">Active CRM: {activeCrmView.label}</p>
                <p className="truncate text-xs text-muted-foreground">
                  {activeCrmView.connected_account || "Connected"} · shortlist push and scheduling sync use this CRM only.
                </p>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" size="sm" className="gap-1.5" onClick={() => openTile(activeCrmView)}>
                <Plug className="size-4" /> Manage
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v === "crm" ? "crm" : "booking")} className="w-full">
        <TabsList className="grid h-14 w-full grid-cols-2 gap-1 p-1.5 md:max-w-xl">
          <TabsTrigger value="booking" className="h-11 gap-2 px-4 text-sm font-medium">
            <CalendarCheck className="size-4" /> Booking providers
          </TabsTrigger>
          <TabsTrigger value="crm" className="h-11 gap-2 px-4 text-sm font-medium">
            <Users className="size-4" /> CRM
          </TabsTrigger>
        </TabsList>
        <TabsContent value="booking" className="mt-6 space-y-4">
          {renderGrid(booking)}
        </TabsContent>
        <TabsContent value="crm" className="mt-6 space-y-4">
          {renderGrid(crm)}
        </TabsContent>
      </Tabs>

      <ProviderDetailSheet
        view={sheetView}
        open={sheetOpen}
        onOpenChange={(v) => {
          setSheetOpen(v);
          if (!v) setSheetView(null);
        }}
        onConnect={(v) => void connect(v)}
        onTest={test}
        onDisconnect={disconnect}
        onRefresh={refresh}
        hubspot={hubspotMeta}
      />

      <p className="text-xs text-muted-foreground">
        Need help? Open <Link to="/account/support" className="text-primary underline-offset-2 hover:underline">Support</Link>
        {" "}or ask your VoxBulk account manager to enable additional integrations in admin.
      </p>
    </div>
  );
}
