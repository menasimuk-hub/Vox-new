import { createFileRoute, Link } from "@tanstack/react-router";
import * as React from "react";
import { Plus } from "lucide-react";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { SortHeader, useTableSort } from "@/components/sortable-table";
import { orderTab, orderToCampaign } from "@/lib/mappers/orders";
import { useArchiveOrder, useDeleteOrder, useHomeSummary, useServiceOrders } from "@/lib/queries";

export const Route = createFileRoute("/_app/surveys/")({
  head: () => ({ meta: [{ title: "Saved surveys — VoxBulk" }] }),
  component: SavedSurveys,
});

function SavedSurveys() {
  const [tab, setTab] = React.useState<"live" | "finished" | "archived">("live");
  const ordersQ = useServiceOrders("survey");
  const summaryQ = useHomeSummary();
  const archiveM = useArchiveOrder();
  const deleteM = useDeleteOrder();

  const filtered = React.useMemo(
    () => (ordersQ.data || []).filter((o) => orderTab(o) === tab).map((o) => orderToCampaign(o, "survey")),
    [ordersQ.data, tab],
  );
  const s = useTableSort(filtered);
  const running = (ordersQ.data || []).filter((o) => o.status === "running").length;
  const sur = summaryQ.data?.survey;

  const onArchive = async (id: string) => {
    try {
      await archiveM.mutateAsync(id);
      toast.success("Survey archived");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Archive failed");
    }
  };

  const onDelete = async (id: string) => {
    try {
      await deleteM.mutateAsync(id);
      toast.success("Survey deleted");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Delete failed");
    }
  };

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="Surveys"
        title="Saved surveys"
        description="All your AI phone and WhatsApp survey campaigns."
        actions={<Button asChild className="gap-1.5"><Link to="/surveys/new"><Plus className="size-4" /> Create new</Link></Button>}
      />

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Live" value={summaryQ.isLoading ? "…" : String(sur?.live ?? 0)} />
        <Stat label="Finished" value={summaryQ.isLoading ? "…" : String(sur?.finished ?? 0)} />
        <Stat label="Responses" value={summaryQ.isLoading ? "…" : String(sur?.responses ?? 0)} />
        <Stat label="Paused" value={summaryQ.isLoading ? "…" : String(sur?.paused ?? 0)} />
      </div>

      <Tabs value={tab} onValueChange={(v) => setTab(v as typeof tab)}>
        <TabsList>
          <TabsTrigger value="live">Live</TabsTrigger>
          <TabsTrigger value="finished">Finished</TabsTrigger>
          <TabsTrigger value="archived">Archived</TabsTrigger>
        </TabsList>
      </Tabs>

      {running > 0 && tab === "live" && (
        <div className="flex items-center justify-between rounded-lg border border-success/40 bg-success/10 px-4 py-2 text-sm text-success">
          <span>{running} live survey{running === 1 ? "" : "s"} running.</span>
        </div>
      )}

      <Card><CardContent className="px-0">
        {ordersQ.isLoading ? (
          <div className="space-y-2 p-6"><Skeleton className="h-10 w-full" /><Skeleton className="h-10 w-full" /></div>
        ) : s.sorted.length === 0 ? (
          <p className="p-8 text-center text-sm text-muted-foreground">No {tab} surveys yet.</p>
        ) : (
          <Table>
            <TableHeader><TableRow>
              <SortHeader label="Survey" sortKey="name" active={s.sortKey} dir={s.sortDir} onToggle={s.toggleSort} className="pl-6" />
              <SortHeader label="Status" sortKey="status" active={s.sortKey} dir={s.sortDir} onToggle={s.toggleSort} />
              <SortHeader label="Progress" sortKey="completion" active={s.sortKey} dir={s.sortDir} onToggle={s.toggleSort} />
              <TableHead className="pr-6 text-right">Actions</TableHead>
            </TableRow></TableHeader>
            <TableBody>
              {s.sorted.map((c) => (
                <TableRow key={c.id} className="cursor-pointer">
                  <TableCell className="pl-6">
                    <Link to="/surveys/$id" params={{ id: c.id }} className="font-medium hover:underline">{c.name}</Link>
                  </TableCell>
                  <TableCell><StatusBadge tone={c.status} /></TableCell>
                  <TableCell className="min-w-[180px]">
                    <div className="flex items-center gap-2">
                      <Progress value={c.completion} className="h-1.5" />
                      <span className="w-9 text-right text-xs tabular-nums text-muted-foreground">{c.completion}%</span>
                    </div>
                  </TableCell>
                  <TableCell className="pr-6 text-right">
                    <div className="inline-flex gap-1">
                      <Button size="sm" variant="ghost" asChild><Link to="/surveys/$id" params={{ id: c.id }}>Edit</Link></Button>
                      {tab === "finished" && (
                        <Button size="sm" variant="ghost" onClick={() => void onArchive(c.id)}>Archive</Button>
                      )}
                      {tab === "live" && (
                        <Button size="sm" variant="ghost" className="text-destructive hover:text-destructive" onClick={() => void onDelete(c.id)}>Delete</Button>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent></Card>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <Card><CardContent className="p-4">
      <p className="text-[11px] uppercase tracking-wider text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-semibold">{value}</p>
    </CardContent></Card>
  );
}
