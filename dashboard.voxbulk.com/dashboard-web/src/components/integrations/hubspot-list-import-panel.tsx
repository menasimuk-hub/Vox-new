import * as React from "react";
import { ListChecks } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
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
import {
  useHubSpotLists,
  useHubSpotStatus,
  useImportHubSpotListToOrder,
  usePatchHubSpotSettings,
} from "@/lib/queries";

type Props = {
  orderId: string;
  onImported?: () => void;
};

export function HubSpotListImportPanel({ orderId, onImported }: Props) {
  const hubspotQ = useHubSpotStatus();
  const connected = hubspotQ.data?.connected === true;
  const savedListId = String(hubspotQ.data?.survey_list_id || "");

  const listsQ = useHubSpotLists(connected);
  const patchM = usePatchHubSpotSettings();
  const importM = useImportHubSpotListToOrder();

  const [listId, setListId] = React.useState(savedListId);
  const [importConsent, setImportConsent] = React.useState(false);

  React.useEffect(() => {
    if (savedListId) setListId(savedListId);
  }, [savedListId]);

  const items = listsQ.data?.items || [];

  if (!connected) {
    return (
      <p className="rounded-lg border border-dashed bg-muted/30 p-4 text-sm text-muted-foreground">
        Connect HubSpot in Settings → Integrations to import a contact list.
      </p>
    );
  }

  const runImport = async () => {
    if (!listId) {
      toast.error("Select a HubSpot list");
      return;
    }
    if (!importConsent) {
      toast.error("Confirm consent before importing contacts");
      return;
    }
    try {
      if (listId !== savedListId) {
        await patchM.mutateAsync({ survey_list_id: listId });
      }
      const result = await importM.mutateAsync({ order_id: orderId, list_id: listId });
      toast.success(`Imported ${result.added} contact(s) from HubSpot list (${result.skipped} skipped)`);
      onImported?.();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "List import failed");
    }
  };

  return (
    <div className="space-y-4 rounded-lg border bg-muted/20 p-4">
      <div>
        <p className="text-sm font-medium">Import from HubSpot list</p>
        <p className="text-xs text-muted-foreground">
          Choose a static HubSpot list — all members with a phone number are added as survey recipients.
        </p>
      </div>

      {listsQ.isLoading ? (
        <Skeleton className="h-10 w-full" />
      ) : (
        <div className="grid gap-2">
          <Label>HubSpot list</Label>
          <Select value={listId || undefined} onValueChange={setListId}>
            <SelectTrigger>
              <SelectValue placeholder={items.length ? "Select a list" : "No lists found — create a static list in HubSpot"} />
            </SelectTrigger>
            <SelectContent>
              {items.map((row) => (
                <SelectItem key={row.id} value={row.id}>
                  {row.name}
                  {typeof row.size === "number" ? ` (${row.size})` : ""}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      <label className="flex items-start gap-2 text-xs text-muted-foreground">
        <Checkbox checked={importConsent} onCheckedChange={(v) => setImportConsent(v === true)} className="mt-0.5" />
        <span>I confirm these contacts may be contacted for this survey.</span>
      </label>

      <Button
        type="button"
        className="gap-1.5"
        disabled={importM.isPending || patchM.isPending || !listId}
        onClick={() => void runImport()}
      >
        <ListChecks className="size-4" />
        {importM.isPending ? "Importing…" : "Import list into survey"}
      </Button>
    </div>
  );
}

type PickerProps = {
  appointmentListId: string;
  confirmedListId: string;
  cancelledListId: string;
  onChange: (patch: {
    appointment_list_id?: string;
    appointment_confirmed_list_id?: string;
    appointment_cancelled_list_id?: string;
  }) => void;
  enabled?: boolean;
};

export function HubSpotAppointmentListPickers({
  appointmentListId,
  confirmedListId,
  cancelledListId,
  onChange,
  enabled = true,
}: PickerProps) {
  const listsQ = useHubSpotLists(enabled);

  const items = listsQ.data?.items || [];

  const renderSelect = (
    label: string,
    hint: string,
    value: string,
    key: "appointment_list_id" | "appointment_confirmed_list_id" | "appointment_cancelled_list_id",
    optional = false,
  ) => (
    <div className="grid gap-2">
      <Label>{label}</Label>
      <p className="text-xs text-muted-foreground">{hint}</p>
      <Select
        value={value || (optional ? "__none__" : undefined)}
        onValueChange={(v) => onChange({ [key]: v === "__none__" ? "" : v })}
      >
        <SelectTrigger>
          <SelectValue placeholder={optional ? "None (optional)" : "Select a list"} />
        </SelectTrigger>
        <SelectContent>
          {optional && <SelectItem value="__none__">None</SelectItem>}
          {items.map((row) => (
            <SelectItem key={`${key}-${row.id}`} value={row.id}>
              {row.name}
              {typeof row.size === "number" ? ` (${row.size})` : ""}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );

  if (listsQ.isLoading) return <Skeleton className="h-32 w-full" />;

  return (
    <div className="grid gap-4">
      {renderSelect(
        "Appointment source list",
        "Contacts in this HubSpot static list are synced into Appointment Manager (phone + appointment date required).",
        appointmentListId,
        "appointment_list_id",
      )}
      {renderSelect(
        "Confirmed list (write-back)",
        "After confirm, contact is added here and removed from the source list.",
        confirmedListId,
        "appointment_confirmed_list_id",
        true,
      )}
      {renderSelect(
        "Cancelled list (write-back)",
        "After cancel, contact is moved here.",
        cancelledListId,
        "appointment_cancelled_list_id",
        true,
      )}
    </div>
  );
}
