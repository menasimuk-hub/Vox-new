import * as React from "react";
import { RefreshCw, UserRoundSearch } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
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
  useHubSpotContacts,
  useHubSpotStatus,
  useImportHubSpotToOrder,
  usePatchHubSpotSyncSettings,
  useServiceOrders,
  useSyncHubSpotContacts,
} from "@/lib/queries";

type FieldMap = {
  first_name: string;
  last_name: string;
  email: string;
  phone: string;
};

const DEFAULT_FIELD_MAP: FieldMap = {
  first_name: "firstname",
  last_name: "lastname",
  email: "email",
  phone: "phone",
};

function readFieldMap(raw: unknown): FieldMap {
  if (!raw || typeof raw !== "object") return { ...DEFAULT_FIELD_MAP };
  const obj = raw as Record<string, unknown>;
  return {
    first_name: String(obj.first_name || DEFAULT_FIELD_MAP.first_name),
    last_name: String(obj.last_name || DEFAULT_FIELD_MAP.last_name),
    email: String(obj.email || DEFAULT_FIELD_MAP.email),
    phone: String(obj.phone || DEFAULT_FIELD_MAP.phone),
  };
}

export function HubspotSyncSettingsCard() {
  const hubspotQ = useHubSpotStatus();
  const hubspot = (hubspotQ.data || {}) as Record<string, unknown>;
  const connected = hubspot.connected === true;
  const contactsQ = useHubSpotContacts(50, connected);
  const surveyOrdersQ = useServiceOrders("survey");
  const syncM = useSyncHubSpotContacts();
  const patchM = usePatchHubSpotSyncSettings();
  const importM = useImportHubSpotToOrder();

  const [fieldMap, setFieldMap] = React.useState<FieldMap>(DEFAULT_FIELD_MAP);
  const [selectedOrderId, setSelectedOrderId] = React.useState("");
  const [importConsent, setImportConsent] = React.useState(false);
  const [selectedContactIds, setSelectedContactIds] = React.useState<string[]>([]);

  React.useEffect(() => {
    setFieldMap(readFieldMap(hubspot.field_map));
  }, [hubspot.field_map]);

  const draftSurveys = React.useMemo(() => {
    const rows = surveyOrdersQ.data || [];
    return rows.filter(
      (o) => o.status === "draft" && String(o.payment_status || "").toLowerCase() !== "approved",
    );
  }, [surveyOrdersQ.data]);

  const previewItems = (contactsQ.data?.items || []).slice(0, 5);
  const contactCount = Number(hubspot.contact_count || contactsQ.data?.count || 0);
  const lastSyncAt = hubspot.last_sync_at ? String(hubspot.last_sync_at) : null;
  const lastSummary = hubspot.last_sync_summary as Record<string, unknown> | undefined;

  const saveFieldMap = async () => {
    try {
      await patchM.mutateAsync({ field_map: fieldMap });
      toast.success("Field mapping saved");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not save field mapping");
    }
  };

  const runSync = async () => {
    try {
      const result = await syncM.mutateAsync({ limit: 100 });
      const parts = [`${result.imported} new`, `${result.updated} updated`];
      if (result.skipped) parts.push(`${result.skipped} skipped`);
      toast.success(`Synced contacts: ${parts.join(", ")}`);
      if (result.has_more) {
        toast.message("More contacts available in HubSpot — run Sync again to fetch the next batch.");
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
      toast.error("Sync contacts from HubSpot first");
      return;
    }
    try {
      const result = await importM.mutateAsync({ order_id: selectedOrderId, contact_ids: ids });
      toast.success(`Added ${result.added} contact(s) to survey${result.skipped ? ` (${result.skipped} skipped)` : ""}`);
      setSelectedContactIds([]);
      setImportConsent(false);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Import failed");
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <UserRoundSearch className="size-5 text-primary" />
          HubSpot contact sync (beta)
        </CardTitle>
        <CardDescription>
          Pull contacts from HubSpot into VoxBulk, optionally add them to a draft WA survey, and write survey results back as HubSpot notes.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {!connected ? (
          <p className="rounded-md border border-border bg-muted/40 p-3 text-sm text-muted-foreground">
            Connect HubSpot in the card above before using contact sync.
          </p>
        ) : null}

        <div className="space-y-3 rounded-md border border-border p-3">
          <p className="text-sm font-medium">Field mapping</p>
          <p className="text-xs text-muted-foreground">Map HubSpot contact properties to VoxBulk name, email, and phone fields.</p>
          <div className="grid gap-3 sm:grid-cols-2">
            {(["first_name", "last_name", "email", "phone"] as const).map((key) => (
              <div key={key} className="grid gap-1.5">
                <Label htmlFor={`hs-map-${key}`} className="text-xs capitalize">
                  {key.replace("_", " ")} property
                </Label>
                <Input
                  id={`hs-map-${key}`}
                  value={fieldMap[key]}
                  disabled={!connected || patchM.isPending}
                  onChange={(e) => setFieldMap((s) => ({ ...s, [key]: e.target.value }))}
                />
              </div>
            ))}
          </div>
          <Button variant="outline" size="sm" disabled={!connected || patchM.isPending} onClick={() => void saveFieldMap()}>
            Save mapping
          </Button>
        </div>

        <div className="space-y-3 rounded-md border border-border p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <p className="text-sm font-medium">Sync contacts</p>
              <p className="text-xs text-muted-foreground">
                {contactCount} in pool
                {lastSyncAt ? ` · Last sync ${new Date(lastSyncAt).toLocaleString()}` : ""}
              </p>
              {lastSummary ? (
                <p className="text-xs text-muted-foreground">
                  Last run: {String(lastSummary.imported ?? 0)} new, {String(lastSummary.updated ?? 0)} updated
                </p>
              ) : null}
            </div>
            <Button
              variant="outline"
              className="gap-1.5"
              disabled={!connected || syncM.isPending}
              onClick={() => void runSync()}
            >
              <RefreshCw className={"size-4 " + (syncM.isPending ? "animate-spin" : "")} />
              Sync contacts
            </Button>
          </div>

          {contactsQ.isLoading ? (
            <Skeleton className="h-16 w-full" />
          ) : previewItems.length ? (
            <div className="overflow-x-auto rounded-md border border-border">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-muted/30 text-left text-xs text-muted-foreground">
                    <th className="p-2 w-8" />
                    <th className="p-2">Name</th>
                    <th className="p-2">Email</th>
                    <th className="p-2">Phone</th>
                  </tr>
                </thead>
                <tbody>
                  {previewItems.map((row) => (
                    <tr key={row.id} className="border-b border-border/60 last:border-0">
                      <td className="p-2">
                        <Checkbox
                          checked={selectedContactIds.includes(row.id)}
                          onCheckedChange={(checked) => toggleContact(row.id, checked === true)}
                          aria-label={`Select ${row.name}`}
                        />
                      </td>
                      <td className="p-2">{row.name}</td>
                      <td className="p-2 text-muted-foreground">{row.email || "—"}</td>
                      <td className="p-2 text-muted-foreground">{row.phone || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">No synced contacts yet — run Sync contacts to preview up to 5 rows here.</p>
          )}
        </div>

        <div className="space-y-3 rounded-md border border-border p-3">
          <p className="text-sm font-medium">Add to survey draft</p>
          <p className="text-xs text-muted-foreground">
            Imports selected contacts (or all preview rows) into a draft survey. Contacts without a valid phone are skipped.
          </p>
          <Select value={selectedOrderId} onValueChange={setSelectedOrderId} disabled={!connected || importM.isPending}>
            <SelectTrigger>
              <SelectValue placeholder="Choose draft WA survey" />
            </SelectTrigger>
            <SelectContent>
              {draftSurveys.map((order) => (
                <SelectItem key={order.id} value={order.id}>
                  {order.title || order.survey_name || order.id}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {!draftSurveys.length && !surveyOrdersQ.isLoading ? (
            <p className="text-xs text-muted-foreground">Create a draft survey first, then return here to import HubSpot contacts.</p>
          ) : null}
          <label className="flex items-start gap-2 text-xs text-muted-foreground">
            <Checkbox checked={importConsent} onCheckedChange={(v) => setImportConsent(v === true)} className="mt-0.5" />
            <span>
              I confirm these contacts may be contacted for this survey and that import complies with our data and consent policies.
            </span>
          </label>
          <Button disabled={!connected || importM.isPending} onClick={() => void runImport()}>
            Import to survey
          </Button>
        </div>

        <div className="flex items-center justify-between gap-4 rounded-md border border-border p-3">
          <div>
            <Label htmlFor="hubspot-writeback" className="text-sm">
              Write results back to HubSpot
            </Label>
            <p className="text-xs text-muted-foreground">When a WhatsApp survey completes, add a note on the matching HubSpot contact.</p>
          </div>
          <Switch
            id="hubspot-writeback"
            checked={hubspot.auto_sync_results_back !== false}
            disabled={!connected || patchM.isPending}
            onCheckedChange={(checked) => {
              void patchM
                .mutateAsync({ auto_sync_results_back: checked })
                .then(() => toast.success(checked ? "Write-back enabled" : "Write-back disabled"))
                .catch((e: unknown) => toast.error(e instanceof Error ? e.message : "Could not update write-back setting"));
            }}
          />
        </div>
      </CardContent>
    </Card>
  );
}
