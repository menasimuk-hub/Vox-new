import * as React from "react";
import { Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Plug, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import { cn } from "@/lib/utils";

export type CrmSyncStatus = {
  crm_connected: boolean;
  crm_provider?: string | null;
  date_property?: string;
  eligible_contacts?: number;
  appointment_list_id?: string | null;
  appointment_list_name?: string | null;
  last_sync_at?: string | null;
  last_sync_fetched?: number;
  last_sync_created?: number;
  last_sync_updated?: number;
  ready?: boolean;
  message?: string;
};

export type CrmSyncResult = CrmSyncStatus & {
  ok?: boolean;
  fetched?: number;
  created?: number;
  updated?: number;
  synced?: number;
};

function formatWhen(iso?: string | null) {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleString();
}

export function showCrmSyncToast(data: CrmSyncResult) {
  const fetched = data.fetched ?? data.last_sync_fetched ?? 0;
  const created = data.created ?? data.last_sync_created ?? 0;
  const updated = data.updated ?? data.last_sync_updated ?? 0;
  if (fetched > 0) {
    toast.success(`CRM sync complete — ${created} new, ${updated} updated (${fetched} from CRM)`);
    return;
  }
  toast.warning(data.message || "CRM sync finished — no appointments found in HubSpot.", { duration: 9000 });
}

type Props = {
  status: CrmSyncStatus | undefined;
  loading?: boolean;
  syncing?: boolean;
  onSync: () => void;
};

export function AppointmentCrmSyncPanel({ status, loading, syncing, onSync }: Props) {
  if (loading) {
    return (
      <Card>
        <CardContent className="p-4 text-sm text-muted-foreground">Checking CRM sync status…</CardContent>
      </Card>
    );
  }

  const connected = status?.crm_connected === true;
  const last = formatWhen(status?.last_sync_at);

  return (
    <Card className={cn(!connected && "border-amber-500/40 bg-amber-500/5")}>
      <CardContent className="flex flex-wrap items-start gap-3 p-4">
        <div className="min-w-0 flex-1 space-y-1">
          <p className="text-sm font-medium">CRM sync</p>
          {connected ? (
            <>
              <p className="text-xs text-muted-foreground">{status?.message}</p>
              {status?.crm_provider === "hubspot" && (
                <p className="text-xs text-muted-foreground">
                  Source list:{" "}
                  <strong>{status.appointment_list_name || "VoxBulk · Appointments"}</strong>
                  {typeof status.eligible_contacts === "number"
                    ? ` · ${status.eligible_contacts} eligible contact(s)`
                    : null}
                </p>
              )}
              {last ? (
                <p className="text-xs text-muted-foreground">
                  Last sync: {last}
                  {typeof status?.last_sync_fetched === "number"
                    ? ` — ${status.last_sync_fetched} fetched, ${status.last_sync_created ?? 0} new`
                    : null}
                </p>
              ) : null}
            </>
          ) : (
            <p className="text-xs text-muted-foreground">
              Connect HubSpot (or another CRM) in Settings → Integrations, then return here and sync.
            </p>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          {!connected ? (
            <Button asChild size="sm" variant="outline" className="gap-1.5">
              <Link to="/settings/integrations">
                <Plug className="size-4" /> Integrations
              </Link>
            </Button>
          ) : (
            <Button size="sm" className="gap-1.5" disabled={syncing} onClick={onSync}>
              <RefreshCw className={cn("size-4", syncing && "animate-spin")} />
              {syncing ? "Syncing…" : "Sync CRM"}
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

export function useCrmSyncStatus() {
  return useQuery({
    queryKey: ["appointments", "crm-sync-status"],
    queryFn: () => apiFetch<CrmSyncStatus>("/appointments/crm-sync-status"),
  });
}
