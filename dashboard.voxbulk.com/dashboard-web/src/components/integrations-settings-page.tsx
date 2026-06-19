import * as React from "react";
import { Link } from "@tanstack/react-router";
import { CalendarCheck, Plug, RefreshCw, Users } from "lucide-react";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

import { ProviderTile, type IntegrationView } from "@/components/integrations/provider-tile";
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
  tab?: string;
};

const PROVIDER_LABEL: Record<string, string> = {
  calendly: "Calendly",
  cal_com: "Cal.com",
  google_calendar: "Google Calendar",
  microsoft_calendar: "Microsoft 365 Calendar",
  hubspot_meetings: "HubSpot Meetings",
  hubspot: "HubSpot CRM",
  cronofy: "Cronofy",
};

function tabFromSearch(tab?: string): "booking" | "crm" {
  return tab === "crm" ? "crm" : "booking";
}

export function IntegrationsSettingsPage({ search }: { search: IntegrationsSearch }) {
  const catalogueQ = useIntegrationsCatalogue();
  const hubspotQ = useHubSpotStatus();
  const testMutation = useTestIntegration();
  const disconnectMutation = useDisconnectIntegration();

  const [activeTab, setActiveTab] = React.useState<"booking" | "crm">(() => tabFromSearch(search.tab));
  const [sheetView, setSheetView] = React.useState<IntegrationView | null>(null);
  const [sheetOpen, setSheetOpen] = React.useState(false);

  React.useEffect(() => {
    const next = tabFromSearch(search.tab);
    setActiveTab(next);
  }, [search.tab]);

  React.useEffect(() => {
    if (search.scheduling === "connected") {
      const label = PROVIDER_LABEL[search.provider || ""] || search.provider || "scheduling";
      toast.success(`Connected ${label} successfully`);
      void catalogueQ.refetch();
    }
    if (search.scheduling === "error") {
      toast.error(search.message || "Calendar connection failed");
    }
    if (search.hubspot === "connected") {
      toast.success("Connected HubSpot successfully");
      void catalogueQ.refetch();
      void hubspotQ.refetch();
    }
    if (search.hubspot === "error") {
      toast.error(search.message || "HubSpot connection failed");
    }
  }, [search.scheduling, search.provider, search.message, search.hubspot, catalogueQ, hubspotQ]);

  const data = catalogueQ.data;
  const booking = (data?.booking ?? []) as IntegrationView[];
  const crm = (data?.crm ?? []) as IntegrationView[];
  const activeBookingProvider = data?.active_booking_provider ?? null;
  const activeBookingView = booking.find((b) => b.connected) || null;

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
      if (!view.platform_ready) {
        toast.error("Connect HubSpot CRM first");
        return;
      }
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
        <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full rounded-md" />
          ))}
        </div>
      );
    }
    if (rows.length === 0) {
      return (
        <p className="rounded-md border border-dashed bg-muted/30 p-4 text-sm text-muted-foreground">
          No providers in this group are available yet. Your VoxBulk admin can enable more in
          Admin → Integrations.
        </p>
      );
    }
    return (
      <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
        {rows.map((row) => (
          <ProviderTile key={row.key} view={row} active={row.key === activeBookingProvider} onOpen={openTile} />
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

      {activeBookingView && activeBookingView.connected ? (
        <Card>
          <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-3">
              <span className="grid size-9 shrink-0 place-items-center rounded-md border bg-muted/40">
                <CalendarCheck className="size-4 text-success" strokeWidth={1.75} />
              </span>
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

      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v === "crm" ? "crm" : "booking")}>
        <TabsList className="grid w-full grid-cols-2 sm:w-auto">
          <TabsTrigger value="booking" className="gap-1.5">
            <CalendarCheck className="size-4" /> Booking providers
          </TabsTrigger>
          <TabsTrigger value="crm" className="gap-1.5">
            <Users className="size-4" /> CRM
          </TabsTrigger>
        </TabsList>
        <TabsContent value="booking" className="mt-4 space-y-3">
          {renderGrid(booking)}
        </TabsContent>
        <TabsContent value="crm" className="mt-4 space-y-3">
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

      {catalogueQ.isError ? (
        <p className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          Could not load integrations. <Button variant="link" className="h-auto p-0" onClick={refresh}>Retry</Button>
        </p>
      ) : null}
    </div>
  );
}
