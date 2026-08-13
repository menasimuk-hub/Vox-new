import { createFileRoute } from "@tanstack/react-router";
import { Download, Plus, ShieldCheck, Trash2, UserX } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { SortHeader, useTableSort } from "@/components/sortable-table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { apiFetch, downloadAuthenticatedFile } from "@/lib/api";
import {
  queryKeys,
  useAddOptOut,
  useFeedbackConsentEvents,
  useOptOuts,
  useRemoveOptOut,
  type FeedbackConsentEventRow,
} from "@/lib/queries";

export const Route = createFileRoute("/_app/feedback/consent")({
  validateSearch: (search: Record<string, unknown>) => ({
    tab: search.tab === "opt-out" ? ("opt-out" as const) : ("consent" as const),
  }),
  head: () => ({ meta: [{ title: "Opt-out & Consent — Customer feedback" }] }),
  component: OptOutConsentPage,
});

function OptOutConsentPage() {
  const navigate = Route.useNavigate();
  const { tab: tabSearch } = Route.useSearch();
  const tab = tabSearch === "opt-out" ? "opt-out" : "consent";

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="Customer feedback"
        title="Opt-out & Consent"
        description="Consent Yes answers and the organisation do-not-contact list in one place."
      />

      <Tabs
        value={tab}
        onValueChange={(value) => {
          void navigate({
            search: (prev) => ({ ...prev, tab: value === "opt-out" ? "opt-out" : "consent" }),
            replace: true,
          });
        }}
      >
        <TabsList>
          <TabsTrigger value="consent">Consent</TabsTrigger>
          <TabsTrigger value="opt-out">Opt-out list</TabsTrigger>
        </TabsList>

        <TabsContent value="consent" className="mt-4 space-y-4">
          <ConsentTab />
        </TabsContent>
        <TabsContent value="opt-out" className="mt-4 space-y-4">
          <OptOutTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function ConsentTab() {
  const [purpose, setPurpose] = React.useState<"callback_call" | "marketing">("callback_call");
  const consentsQ = useFeedbackConsentEvents({ purpose, consent_given: "true" });
  const qc = useQueryClient();
  const [optingOut, setOptingOut] = React.useState<string | null>(null);
  const items = consentsQ.data || [];

  const onExport = async () => {
    try {
      const qs = new URLSearchParams({ purpose, consent_given: "true" });
      await downloadAuthenticatedFile(
        `/customer-feedback/consent-events/export.xlsx?${qs.toString()}`,
        `feedback-consent-${purpose}.xlsx`,
      );
      toast.success("Consent list exported to Excel");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Export failed");
    }
  };

  const onOptOut = async (row: FeedbackConsentEventRow) => {
    setOptingOut(row.id);
    try {
      await apiFetch("/customer-feedback/consent-events/opt-out", {
        method: "POST",
        body: JSON.stringify({
          phone_number: row.phone_number,
          session_id: row.session_id,
          location_id: row.location_id,
          purpose: row.purpose,
        }),
      });
      toast.success(`Opted out ${row.phone_number}`);
      await qc.invalidateQueries({ queryKey: queryKeys.feedbackConsentEvents({ purpose, consent_given: "true" }) });
      await qc.invalidateQueries({ queryKey: queryKeys.optOuts });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not opt out");
    } finally {
      setOptingOut(null);
    }
  };

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 rounded-lg border border-primary/20 bg-primary/5 p-3 text-sm">
          <ShieldCheck className="size-4 shrink-0 text-primary" />
          <span>
            Callback consent is for AI follow-up calls only. Marketing consent is separate. Both are append-only audit
            events.
          </span>
        </div>
        <Button type="button" variant="outline" className="gap-1.5" onClick={() => void onExport()}>
          <Download className="size-4" /> Export Excel
        </Button>
      </div>

      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          variant={purpose === "callback_call" ? "default" : "outline"}
          onClick={() => setPurpose("callback_call")}
        >
          Callback Yes
        </Button>
        <Button
          size="sm"
          variant={purpose === "marketing" ? "default" : "outline"}
          onClick={() => setPurpose("marketing")}
        >
          Marketing Yes
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {purpose === "callback_call" ? "Callback consent" : "Marketing consent"}
          </CardTitle>
          <CardDescription>
            Showing latest Yes answers. Opt out removes them from active use and records a revoke event.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          {consentsQ.isLoading ? (
            <div className="space-y-2 p-4">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          ) : consentsQ.isError ? (
            <p className="p-6 text-sm text-destructive">Could not load consent events.</p>
          ) : items.length === 0 ? (
            <p className="p-6 text-sm text-muted-foreground">No Yes consents yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[880px] text-left text-sm">
                <thead className="border-b bg-muted/40 text-xs uppercase tracking-wider text-muted-foreground">
                  <tr>
                    <th className="px-4 py-3 font-medium">Name</th>
                    <th className="px-4 py-3 font-medium">Email</th>
                    <th className="px-4 py-3 font-medium">Mobile</th>
                    <th className="px-4 py-3 font-medium">Service opt-in</th>
                    <th className="px-4 py-3 font-medium">Location</th>
                    <th className="px-4 py-3 font-medium">Method</th>
                    <th className="px-4 py-3 font-medium">When</th>
                    <th className="px-4 py-3 font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {items.map((row) => (
                    <tr key={row.id}>
                      <td className="px-4 py-3">{row.name || "—"}</td>
                      <td className="px-4 py-3 text-muted-foreground">{row.email || "—"}</td>
                      <td className="px-4 py-3 font-medium tabular-nums">{row.phone_number}</td>
                      <td className="px-4 py-3">
                        <Badge variant="secondary">
                          {row.service_optin ||
                            (row.purpose === "marketing" ? "Marketing opt-in" : "Callback opt-in")}
                        </Badge>
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">{row.location_name || "—"}</td>
                      <td className="px-4 py-3">
                        <Badge variant="outline">{row.method}</Badge>
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {row.timestamp ? new Date(row.timestamp).toLocaleString() : "—"}
                      </td>
                      <td className="px-4 py-3">
                        <Button
                          size="sm"
                          variant="ghost"
                          className="gap-1.5 text-destructive hover:text-destructive"
                          disabled={optingOut === row.id}
                          onClick={() => void onOptOut(row)}
                        >
                          <UserX className="size-3.5" />
                          {optingOut === row.id ? "Opting out…" : "Opt out"}
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </>
  );
}

function OptOutTab() {
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

  const onExport = async () => {
    try {
      await downloadAuthenticatedFile("/organisations/me/opt-outs/export.xlsx", "org-opt-outs.xlsx");
      toast.success("Opt-out list exported to Excel");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Export failed");
    }
  };

  return (
    <>
      <div className="flex justify-end">
        <Button type="button" variant="outline" className="gap-1.5" onClick={() => void onExport()}>
          <Download className="size-4" /> Export Excel
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Add number</CardTitle>
          <CardDescription>These contacts will never be called or messaged by your campaigns.</CardDescription>
        </CardHeader>
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
            <div className="p-6">
              <Skeleton className="h-10 w-full" />
            </div>
          ) : table.sorted.length === 0 ? (
            <p className="p-6 text-sm text-muted-foreground">
              No opt-outs yet. Numbers are also added automatically when someone opts out on a call.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <SortHeader
                    label="Phone"
                    sortKey="phone"
                    active={table.sortKey}
                    dir={table.sortDir}
                    onToggle={table.toggleSort}
                    className="pl-6"
                  />
                  <SortHeader label="Name" sortKey="name" active={table.sortKey} dir={table.sortDir} onToggle={table.toggleSort} />
                  <SortHeader
                    label="Reason"
                    sortKey="reason"
                    active={table.sortKey}
                    dir={table.sortDir}
                    onToggle={table.toggleSort}
                  />
                  <SortHeader
                    label="Added"
                    sortKey="added"
                    active={table.sortKey}
                    dir={table.sortDir}
                    onToggle={table.toggleSort}
                  />
                  <TableHead className="pr-6 text-right" />
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
                        onClick={() =>
                          void removeM
                            .mutateAsync(row.id)
                            .then(() => toast.success("Removed"))
                            .catch((e) => toast.error(e instanceof Error ? e.message : "Failed"))
                        }
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
    </>
  );
}
