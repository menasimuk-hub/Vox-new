import { createFileRoute } from "@tanstack/react-router";
import * as React from "react";
import { Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { SortHeader, useTableSort } from "@/components/sortable-table";
import { requireOrgSettingsAccess } from "@/lib/guards/settings-route";
import { useAddOptOut, useOptOuts, useRemoveOptOut } from "@/lib/queries";

export const Route = createFileRoute("/_app/settings/opt-out")({
  head: () => ({ meta: [{ title: "Opt-out list — VoxBulk" }] }),
  beforeLoad: () => requireOrgSettingsAccess(),
  component: OptOutPage,
});

function OptOutPage() {
  const listQ = useOptOuts();
  const addM = useAddOptOut();
  const removeM = useRemoveOptOut();

  const [phone, setPhone] = React.useState("");
  const [name, setName] = React.useState("");
  const [reason, setReason] = React.useState("Requested removal");

  const rows = (listQ.data || []).map((o) => ({
    id: o.id,
    phone: o.phone_e164 || o.phone,
    name: o.name || o.contact_name || "—",
    reason: o.reason || "—",
    added: o.created_at ? new Date(o.created_at).toLocaleDateString() : "—",
  }));
  const table = useTableSort(rows, "added", "desc");

  const onAdd = async () => {
    if (!phone.trim()) {
      toast.error("Enter a phone number");
      return;
    }
    try {
      await addM.mutateAsync({ phone: phone.trim(), name: name.trim() || undefined, reason: reason.trim() || undefined });
      toast.success("Number added to opt-out list");
      setPhone("");
      setName("");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not add number");
    }
  };

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="Settings"
        title="Opt-out list"
        description="These contacts will never be called or messaged by your campaigns."
      />

      <Card>
        <CardHeader><CardTitle>Add number</CardTitle></CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-4 md:items-end">
          <div className="space-y-1.5">
            <Label className="text-xs">Phone (E.164)</Label>
            <Input placeholder="+447700900123" value={phone} onChange={(e) => setPhone(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Name (optional)</Label>
            <Input placeholder="J. Walker" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="space-y-1.5 md:col-span-2">
            <Label className="text-xs">Reason</Label>
            <Input value={reason} onChange={(e) => setReason(e.target.value)} />
          </div>
          <Button className="gap-1.5 md:col-span-4 md:w-auto" onClick={() => void onAdd()} disabled={addM.isPending}>
            <Plus className="size-4" /> {addM.isPending ? "Adding…" : "Add to list"}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="px-0">
          {listQ.isLoading ? (
            <div className="p-6"><Skeleton className="h-10 w-full" /></div>
          ) : table.sorted.length === 0 ? (
            <p className="p-6 text-sm text-muted-foreground">No opt-outs yet. Numbers are also added automatically when someone opts out on a call.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <SortHeader label="Phone" sortKey="phone" active={table.sortKey} dir={table.sortDir} onToggle={table.toggleSort} className="pl-6" />
                  <SortHeader label="Name" sortKey="name" active={table.sortKey} dir={table.sortDir} onToggle={table.toggleSort} />
                  <SortHeader label="Reason" sortKey="reason" active={table.sortKey} dir={table.sortDir} onToggle={table.toggleSort} />
                  <SortHeader label="Added" sortKey="added" active={table.sortKey} dir={table.sortDir} onToggle={table.toggleSort} />
                  <TableHead className="pr-6 text-right"></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {table.sorted.map((row) => (
                  <TableRow key={row.id}>
                    <TableCell className="pl-6 font-mono text-xs">{row.phone}</TableCell>
                    <TableCell>{row.name}</TableCell>
                    <TableCell className="text-muted-foreground">{row.reason}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">{row.added}</TableCell>
                    <TableCell className="pr-6 text-right">
                      <Button
                        size="sm"
                        variant="ghost"
                        className="gap-1 text-destructive"
                        onClick={() => void removeM.mutateAsync(row.id).then(() => toast.success("Removed")).catch((e) => toast.error(e instanceof Error ? e.message : "Failed"))}
                      >
                        <Trash2 className="size-3.5" /> Remove
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
