import * as React from "react";
import { RefreshCw, Users } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useCrmContacts,
  useCrmSyncStatus,
  useImportCrmToOrder,
  useSyncCrmContacts,
} from "@/lib/queries";

type Props = {
  orderId: string;
  onImported?: () => void;
};

export function CrmImportContactsPanel({ orderId, onImported }: Props) {
  const statusQ = useCrmSyncStatus();
  const status = (statusQ.data || {}) as Record<string, unknown>;
  const provider = String(status.provider || "");
  const connected = status.connected === true;
  const syncEnabled = status.sync_settings_enabled !== false;

  const contactsQ = useCrmContacts(50, connected && syncEnabled);
  const syncM = useSyncCrmContacts();
  const importM = useImportCrmToOrder();

  const [importConsent, setImportConsent] = React.useState(false);
  const [selectedContactIds, setSelectedContactIds] = React.useState<string[]>([]);

  const items = contactsQ.data?.items || [];

  if (!connected || !syncEnabled) {
    return (
      <p className="rounded-lg border border-dashed bg-muted/30 p-4 text-sm text-muted-foreground">
        Connect a CRM in Settings → Integrations to import contacts here instead of CSV.
      </p>
    );
  }

  const runSync = async () => {
    try {
      const result = await syncM.mutateAsync({ limit: 100 });
      toast.success(`Synced ${result.imported + result.updated} contact(s) from CRM`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Sync failed");
    }
  };

  const toggleContact = (id: string, checked: boolean) => {
    setSelectedContactIds((prev) => (checked ? [...prev, id] : prev.filter((x) => x !== id)));
  };

  const runImport = async () => {
    if (!importConsent) {
      toast.error("Confirm consent before importing");
      return;
    }
    const ids = selectedContactIds.length ? selectedContactIds : items.map((c) => c.id);
    if (!ids.length) {
      toast.error("Sync contacts from CRM first");
      return;
    }
    try {
      const result = await importM.mutateAsync({ order_id: orderId, contact_ids: ids });
      toast.success(`Added ${result.added} contact(s) (${result.skipped} skipped)`);
      setSelectedContactIds([]);
      onImported?.();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Import failed");
    }
  };

  const providerLabel =
    provider === "pipedrive" ? "Pipedrive" : provider === "zoho_crm" ? "Zoho CRM" : provider === "hubspot" ? "HubSpot" : "CRM";

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant="outline" className="gap-1.5" disabled={syncM.isPending} onClick={() => void runSync()}>
          <RefreshCw className={`size-3.5 ${syncM.isPending ? "animate-spin" : ""}`} />
          Sync from {providerLabel}
        </Button>
        <span className="text-xs text-muted-foreground">{items.length} contacts loaded</span>
      </div>

      {contactsQ.isLoading ? (
        <Skeleton className="h-32 w-full" />
      ) : items.length ? (
        <div className="max-h-48 space-y-2 overflow-y-auto rounded-md border p-2">
          {items.map((c) => (
            <label key={c.id} className="flex items-center gap-2 text-sm">
              <Checkbox
                checked={selectedContactIds.includes(c.id)}
                onCheckedChange={(v) => toggleContact(c.id, v === true)}
              />
              <span className="min-w-0 truncate">{c.name}</span>
              <span className="ml-auto shrink-0 text-xs text-muted-foreground">{c.phone || "no phone"}</span>
            </label>
          ))}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">No contacts yet — click Sync from {providerLabel}.</p>
      )}

      <label className="flex items-start gap-2 text-xs text-muted-foreground">
        <Checkbox checked={importConsent} onCheckedChange={(v) => setImportConsent(v === true)} className="mt-0.5" />
        <span>I confirm these contacts may be contacted for this survey.</span>
      </label>

      <Button type="button" className="gap-1.5" disabled={importM.isPending} onClick={() => void runImport()}>
        <Users className="size-4" />
        {importM.isPending ? "Importing…" : "Import selected into survey"}
      </Button>
    </div>
  );
}
