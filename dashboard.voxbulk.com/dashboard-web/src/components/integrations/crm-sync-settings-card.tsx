import * as React from "react";
import { RefreshCw, UserRoundSearch } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import {
  useCrmContacts,
  useCrmSyncStatus,
  useImportCrmToOrder,
  usePatchCrmSyncSettings,
  useServiceOrders,
  useSyncCrmContacts,
} from "@/lib/queries";

const CRM_LABELS: Record<string, string> = {
  hubspot: "HubSpot",
  pipedrive: "Pipedrive",
  zoho_crm: "Zoho CRM",
};

type Props = {
  providerKey?: string;
};

export function CrmSyncSettingsCard({ providerKey }: Props) {
  const statusQ = useCrmSyncStatus();
  const status = (statusQ.data || {}) as Record<string, unknown>;
  const provider = String(providerKey || status.provider || "");
  const label = CRM_LABELS[provider] || "CRM";
  const connected = status.connected === true;
  const syncEnabled = status.sync_settings_enabled !== false;

  const contactsQ = useCrmContacts(50, connected && syncEnabled);
  const surveyOrdersQ = useServiceOrders("survey");
  const syncM = useSyncCrmContacts();
  const patchM = usePatchCrmSyncSettings();
  const importM = useImportCrmToOrder();

  const [selectedOrderId, setSelectedOrderId] = React.useState("");
  const [importConsent, setImportConsent] = React.useState(false);
  const [selectedContactIds, setSelectedContactIds] = React.useState<string[]>([]);

  const draftSurveys = React.useMemo(() => {
    const rows = surveyOrdersQ.data || [];
    return rows.filter(
      (o) => o.status === "draft" && String(o.payment_status || "").toLowerCase() !== "approved",
    );
  }, [surveyOrdersQ.data]);

  const previewItems = (contactsQ.data?.items || []).slice(0, 8);
  const contactCount = Number(status.contact_count || contactsQ.data?.count || 0);
  const lastSyncAt = status.last_sync_at ? String(status.last_sync_at) : null;

  const runSync = async () => {
    try {
      const result = await syncM.mutateAsync({ limit: 100 });
      const parts = [`${result.imported} new`, `${result.updated} updated`];
      if (result.skipped) parts.push(`${result.skipped} skipped`);
      toast.success(`Synced ${label} contacts: ${parts.join(", ")}`);
      if (result.has_more) {
        toast.message(`More contacts in ${label} — run Sync again for the next batch.`);
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Contact sync failed");
    }
  };

  const toggleContact = (id: string, checked: boolean) => {
    setSelectedContactIds((prev) => (checked ? [...prev, id] : prev.filter((x) => x !== id)));
  };

  const runImport = async () => {
    if (!selectedOrderId) {
      toast.error("Choose a draft survey first");
      return;
    }
    if (!importConsent) {
      toast.error("Confirm consent before importing contacts");
      return;
    }
    const ids = selectedContactIds.length ? selectedContactIds : previewItems.map((c) => c.id);
    if (!ids.length) {
      toast.error("Sync contacts from CRM first");
      return;
    }
    try {
      const result = await importM.mutateAsync({ order_id: selectedOrderId, contact_ids: ids });
      toast.success(`Added ${result.added} contact(s) to survey (${result.skipped} skipped)`);
      setSelectedContactIds([]);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Import failed");
    }
  };

  if (!connected) return null;

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <UserRoundSearch className="size-4" /> {label} contact sync
        </CardTitle>
        <CardDescription>
          Pull contacts from {label} into VoxBulk, then import them into a draft survey (or use Import from CRM in the survey wizard).
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {!syncEnabled ? (
          <p className="rounded-md border border-dashed p-3 text-xs text-muted-foreground">
            Contact sync is disabled. Ask your VoxBulk admin to enable HubSpot contact sync, or reconnect {label}.
          </p>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <Button size="sm" variant="outline" className="gap-1.5" disabled={syncM.isPending} onClick={() => void runSync()}>
                <RefreshCw className={`size-3.5 ${syncM.isPending ? "animate-spin" : ""}`} />
                Sync contacts
              </Button>
              <span className="text-xs text-muted-foreground">
                {contactCount} cached · {lastSyncAt ? `Last sync ${new Date(lastSyncAt).toLocaleString()}` : "Not synced yet"}
              </span>
            </div>

            {contactsQ.isLoading ? (
              <Skeleton className="h-24 w-full" />
            ) : previewItems.length ? (
              <div className="max-h-40 space-y-2 overflow-y-auto rounded-md border p-2">
                {previewItems.map((c) => (
                  <label key={c.id} className="flex items-center gap-2 text-sm">
                    <Checkbox
                      checked={selectedContactIds.includes(c.id)}
                      onCheckedChange={(v) => toggleContact(c.id, v === true)}
                    />
                    <span className="min-w-0 truncate">{c.name}</span>
                    <span className="ml-auto shrink-0 text-xs text-muted-foreground">{c.phone || c.email || "—"}</span>
                  </label>
                ))}
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">No synced contacts yet — run Sync contacts.</p>
            )}

            <div className="space-y-2">
              <Label className="text-sm">Import into draft survey</Label>
              <Select value={selectedOrderId} onValueChange={setSelectedOrderId}>
                <SelectTrigger>
                  <SelectValue placeholder="Select draft survey" />
                </SelectTrigger>
                <SelectContent>
                  {draftSurveys.map((o) => (
                    <SelectItem key={o.id} value={o.id}>
                      {o.title || o.survey_name || o.id}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <label className="flex items-start gap-2 text-xs text-muted-foreground">
                <Checkbox checked={importConsent} onCheckedChange={(v) => setImportConsent(v === true)} className="mt-0.5" />
                <span>I confirm these contacts may be contacted for this survey.</span>
              </label>
              <Button size="sm" disabled={importM.isPending} onClick={() => void runImport()}>
                Import to survey
              </Button>
            </div>
          </>
        )}

        <div className="flex items-center justify-between gap-4 rounded-md border border-border p-3">
          <div>
            <Label htmlFor="crm-writeback" className="text-sm">
              Write results back to {label}
            </Label>
            <p className="text-xs text-muted-foreground">
              When a WhatsApp or AI call survey completes, add a note on the matching CRM contact.
            </p>
          </div>
          <Switch
            id="crm-writeback"
            checked={status.auto_sync_results_back !== false}
            disabled={patchM.isPending}
            onCheckedChange={(checked) => {
              void patchM
                .mutateAsync({ auto_sync_results_back: checked })
                .then(() => toast.success(checked ? "Write-back enabled" : "Write-back disabled"))
                .catch((e: unknown) => toast.error(e instanceof Error ? e.message : "Could not update write-back"));
            }}
          />
        </div>
      </CardContent>
    </Card>
  );
}
