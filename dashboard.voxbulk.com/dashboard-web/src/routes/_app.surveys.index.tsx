import { createFileRoute, Link } from "@tanstack/react-router";
import * as React from "react";
import { MessageCircle, Phone, Plus } from "lucide-react";
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
import { assistantHighlightClass, useAssistantHighlight } from "@/lib/assistant-highlight";
import { cn } from "@/lib/utils";
import { AnimatedAllowanceKpi } from "@/components/billing/animated-allowance-kpi";
import { useUsageAllowances } from "@/lib/billing/use-usage-allowances";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  useArchiveOrder,
  useDeleteOrder,
  useDuplicateSurveyOrder,
  useHomeSummary,
  useServiceOrders,
  useStopSurveyOrder,
} from "@/lib/queries";

export const Route = createFileRoute("/_app/surveys/")({
  head: () => ({ meta: [{ title: "Saved surveys — VoxBulk" }] }),
  component: SavedSurveys,
});

const PAGE_SIZE = 10;

function SavedSurveys() {
  const { highlight } = useAssistantHighlight();
  const [tab, setTab] = React.useState<"live" | "finished" | "archived">("live");
  const [page, setPage] = React.useState(1);
  const [deleteTarget, setDeleteTarget] = React.useState<{ id: string; name: string; status: string } | null>(null);
  const ordersQ = useServiceOrders("survey");
  const summaryQ = useHomeSummary();
  const allowancesState = useUsageAllowances();
  const waAllowance = allowancesState.coreRows.find((r) => r.key === "whatsapp");
  const archiveM = useArchiveOrder();
  const deleteM = useDeleteOrder();
  const duplicateM = useDuplicateSurveyOrder();
  const stopM = useStopSurveyOrder();

  const filtered = React.useMemo(
    () => (ordersQ.data || []).filter((o) => orderTab(o) === tab).map((o) => orderToCampaign(o, "survey")),
    [ordersQ.data, tab],
  );
  const s = useTableSort(filtered);
  const totalPages = Math.max(1, Math.ceil(s.sorted.length / PAGE_SIZE));
  const pageRows = s.sorted.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  React.useEffect(() => {
    setPage(1);
  }, [tab]);
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

  const onDuplicate = async (id: string) => {
    try {
      await duplicateM.mutateAsync(id);
      toast.success("Survey duplicated");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Duplicate failed");
    }
  };

  const onConfirmDelete = async () => {
    if (!deleteTarget) return;
    const runningLike = ["running", "paused", "scheduled"].includes(deleteTarget.status);
    try {
      if (runningLike) {
        await stopM.mutateAsync(deleteTarget.id);
      }
      await deleteM.mutateAsync({ orderId: deleteTarget.id, confirmRunningDelete: runningLike });
      toast.success("Survey removed — recipient data kept for reference");
      setDeleteTarget(null);
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

      {waAllowance ? (
        <div className="max-w-md">
          <AnimatedAllowanceKpi row={waAllowance} compact />
        </div>
      ) : null}

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
        ) : ordersQ.isError ? (
          <p className="p-8 text-center text-sm text-destructive">
            Could not load saved surveys{ordersQ.error instanceof Error ? `: ${ordersQ.error.message}` : ""}.
          </p>
        ) : s.sorted.length === 0 ? (
          <p className="p-8 text-center text-sm text-muted-foreground">No {tab} surveys yet.</p>
        ) : (
          <div className="table-scroll">
          <Table>
            <TableHeader><TableRow>
              <SortHeader label="Survey" sortKey="name" active={s.sortKey} dir={s.sortDir} onToggle={s.toggleSort} className="pl-6" />
              <SortHeader label="Status" sortKey="status" active={s.sortKey} dir={s.sortDir} onToggle={s.toggleSort} />
              <SortHeader label="Progress" sortKey="completion" active={s.sortKey} dir={s.sortDir} onToggle={s.toggleSort} />
              <TableHead className="pr-6 text-right">Actions</TableHead>
            </TableRow></TableHeader>
            <TableBody>
              {pageRows.map((c) => (
                <TableRow
                  key={c.id}
                  data-assistant-highlight={c.id}
                  className={cn(assistantHighlightClass(c.id, highlight))}
                >
                  <TableCell className="pl-6">
                    <div className="block">
                      <div className="flex items-center gap-2">
                        {c.surveyChannel === "whatsapp" ? (
                          <MessageCircle className="size-4 shrink-0 text-primary" aria-label="WhatsApp survey" />
                        ) : c.surveyChannel === "ai_call" ? (
                          <Phone className="size-4 shrink-0 text-primary" aria-label="Calling survey" />
                        ) : null}
                        <span className="font-medium">{c.name}</span>
                      </div>
                      {c.surveyId ? (
                        <span className="mt-0.5 block font-mono text-[11px] text-muted-foreground">ID {c.surveyId}</span>
                      ) : null}
                      {c.subtitle ? (
                        <span className="mt-0.5 block text-xs text-muted-foreground">Step 1 · {c.subtitle}</span>
                      ) : null}
                    </div>
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
                      <Button size="sm" variant="ghost" asChild><Link to="/surveys/new" search={{ order_id: c.id }}>Edit</Link></Button>
                      <Button size="sm" variant="ghost" onClick={() => void onDuplicate(c.id)}>Duplicate</Button>
                      {(tab === "finished" || tab === "live") && c.status !== "running" ? (
                        <Button size="sm" variant="ghost" onClick={() => void onArchive(c.id)}>Archive</Button>
                      ) : null}
                      <Button
                        size="sm"
                        variant="ghost"
                        className="text-destructive hover:text-destructive"
                        onClick={() => setDeleteTarget({ id: c.id, name: c.name, status: c.status })}
                      >
                        Delete
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          </div>
        )}
        {!ordersQ.isLoading && s.sorted.length > PAGE_SIZE ? (
          <div className="flex items-center justify-between border-t border-border px-6 py-3 text-sm">
            <span className="text-muted-foreground">
              Page {page} of {totalPages} · {s.sorted.length} surveys
            </span>
            <div className="flex gap-2">
              <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                Previous
              </Button>
              <Button size="sm" variant="outline" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
                Next
              </Button>
            </div>
          </div>
        ) : null}
      </CardContent></Card>

      <AlertDialog open={Boolean(deleteTarget)} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete survey?</AlertDialogTitle>
            <AlertDialogDescription>
              {deleteTarget && ["running", "paused", "scheduled"].includes(deleteTarget.status)
                ? `"${deleteTarget.name}" is still active. It will be stopped, then permanently deleted. This cannot be undone.`
                : deleteTarget
                  ? `Permanently delete "${deleteTarget.name}"? This cannot be undone.`
                  : ""}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction className="bg-destructive text-destructive-foreground hover:bg-destructive/90" onClick={() => void onConfirmDelete()}>
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
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
