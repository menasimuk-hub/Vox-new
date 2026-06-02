import { createFileRoute, Link } from "@tanstack/react-router";
import * as React from "react";
import { Plus } from "lucide-react";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { SortHeader, useTableSort } from "@/components/sortable-table";
import { orderTab, orderToCampaign } from "@/lib/mappers/orders";
import { useArchiveOrder, useDeleteOrder, useHomeSummary, usePromoCredits, useServiceOrders, useStopInterviewCampaign } from "@/lib/queries";

export const Route = createFileRoute("/_app/interviews/")({
  head: () => ({ meta: [{ title: "Saved interviews — VoxBulk" }] }),
  component: SavedInterviews,
});

function fmtWhen(iso?: string | null) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  } catch {
    return iso;
  }
}

function SavedInterviews() {
  const [tab, setTab] = React.useState<"live" | "finished" | "archived">("live");
  const ordersQ = useServiceOrders("interview");
  const summaryQ = useHomeSummary();
  const creditsQ = usePromoCredits();
  const archiveM = useArchiveOrder();
  const deleteM = useDeleteOrder();
  const stopM = useStopInterviewCampaign();
  const [stopTarget, setStopTarget] = React.useState<{ id: string; name: string } | null>(null);
  const [stopConfirmText, setStopConfirmText] = React.useState("");

  const filtered = React.useMemo(
    () =>
      (ordersQ.data || [])
        .filter((o) => orderTab(o) === tab)
        .map((o) => ({
          ...orderToCampaign(o, "interview"),
          campaignId: o.campaign_id || o.reference_id || "—",
        })),
    [ordersQ.data, tab],
  );
  const orderById = React.useMemo(() => {
    const map = new Map<string, NonNullable<typeof ordersQ.data>[number]>();
    (ordersQ.data || []).forEach((o) => map.set(o.id, o));
    return map;
  }, [ordersQ.data]);

  const s = useTableSort(filtered);
  const running = (ordersQ.data || []).filter((o) => o.status === "running").length;
  const int = summaryQ.data?.interview;
  const credits = creditsQ.data?.interview_credits ?? creditsQ.data?.credits;

  const onArchive = async (id: string) => {
    try {
      await archiveM.mutateAsync(id);
      toast.success("Interview archived");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Archive failed");
    }
  };

  const onStop = async () => {
    if (!stopTarget) return;
    try {
      await stopM.mutateAsync({ orderId: stopTarget.id, reason: "Stopped by user" });
      toast.success("Interview stopped");
      setStopTarget(null);
      setStopConfirmText("");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Stop failed");
    }
  };

  const onDelete = async (id: string) => {
    try {
      await deleteM.mutateAsync(id);
      toast.success("Interview deleted");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Delete failed");
    }
  };

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="Interviews"
        title="Interviews"
        description="All your AI phone screening campaigns — open any interview to edit schedule, prompt, and questions."
        actions={
          <Button asChild className="gap-1.5"><Link to="/interviews/new" search={{ new: true }}><Plus className="size-4" /> Create new</Link></Button>
        }
      />

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Credits remaining" value={creditsQ.isLoading ? "…" : String(credits ?? "—")} />
        <Stat label="Finished" value={summaryQ.isLoading ? "…" : String(int?.finished ?? 0)} />
        <Stat label="Live campaigns" value={summaryQ.isLoading ? "…" : String(int?.live ?? 0)} />
        <Stat label="Running now" value={ordersQ.isLoading ? "…" : String(running)} />
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
          <span>{running} live campaign{running === 1 ? "" : "s"} calling now.</span>
        </div>
      )}

      <Card>
        <CardContent className="px-0">
          {ordersQ.isLoading ? (
            <div className="space-y-2 p-6"><Skeleton className="h-10 w-full" /><Skeleton className="h-10 w-full" /></div>
          ) : s.sorted.length === 0 ? (
            <p className="p-8 text-center text-sm text-muted-foreground">No {tab} interviews yet.</p>
          ) : (
            <div className="table-scroll">
            <Table>
              <TableHeader>
                <TableRow>
                  <SortHeader label="Interview #" sortKey="campaignId" active={s.sortKey} dir={s.sortDir} onToggle={s.toggleSort} className="pl-6" />
                  <SortHeader label="Name" sortKey="name" active={s.sortKey} dir={s.sortDir} onToggle={s.toggleSort} />
                  <SortHeader label="Status" sortKey="status" active={s.sortKey} dir={s.sortDir} onToggle={s.toggleSort} />
                  <SortHeader label="Candidates" sortKey="target" active={s.sortKey} dir={s.sortDir} onToggle={s.toggleSort} />
                  {tab === "live" && <TableHead>Schedule</TableHead>}
                  <SortHeader label="Progress" sortKey="completion" active={s.sortKey} dir={s.sortDir} onToggle={s.toggleSort} />
                  <TableHead className="pr-6 text-right">Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {s.sorted.map((c) => {
                  const raw = orderById.get(c.id);
                  return (
                    <TableRow key={c.id}>
                      <TableCell className="pl-6 font-mono text-xs">{c.campaignId}</TableCell>
                      <TableCell>
                        <div className="font-medium">{c.name}</div>
                      </TableCell>
                      <TableCell><StatusBadge tone={c.status} /></TableCell>
                      <TableCell>{c.target}</TableCell>
                      {tab === "live" && (
                        <TableCell className="text-xs text-muted-foreground">
                          {fmtWhen(raw?.scheduled_start_at)}
                          {raw?.scheduled_end_at ? ` → ${fmtWhen(raw.scheduled_end_at)}` : ""}
                        </TableCell>
                      )}
                      <TableCell className="min-w-[140px]">
                        <div className="flex items-center gap-2">
                          <Progress value={c.completion} className="h-1.5" />
                          <span className="w-9 text-right text-xs tabular-nums text-muted-foreground">{c.completion}%</span>
                        </div>
                      </TableCell>
                      <TableCell className="pr-6 text-right">
                        <div className="inline-flex flex-wrap justify-end gap-1">
                          <Button size="sm" variant="default" asChild>
                            <Link to="/interviews/$orderId" params={{ orderId: c.id }}>Open</Link>
                          </Button>
                          <Button size="sm" variant="ghost" asChild>
                            <Link to="/interviews/results/$orderId" params={{ orderId: c.id }}>Results</Link>
                          </Button>
                          {tab === "live" && raw && ["running", "paused", "scheduled"].includes(String(raw.status || "")) ? (
                            <Button size="sm" variant="ghost" className="text-destructive hover:text-destructive" onClick={() => setStopTarget({ id: c.id, name: c.name })}>
                              Stop
                            </Button>
                          ) : null}
                          {tab === "finished" && (
                            <Button size="sm" variant="ghost" onClick={() => void onArchive(c.id)}>Archive</Button>
                          )}
                          {tab === "live" && (raw?.status === "draft" || raw?.status === "quoted") ? (
                            <Button size="sm" variant="ghost" className="text-destructive hover:text-destructive" onClick={() => void onDelete(c.id)}>Delete</Button>
                          ) : null}
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={!!stopTarget} onOpenChange={(open) => { if (!open) { setStopTarget(null); setStopConfirmText(""); } }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Stop interview campaign</DialogTitle>
            <DialogDescription>
              This stops pending AI calls for <strong>{stopTarget?.name}</strong>. Candidates already booked keep their slots until you cancel them individually.
            </DialogDescription>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">Type <strong>STOP</strong> to confirm.</p>
          <Input value={stopConfirmText} onChange={(e) => setStopConfirmText(e.target.value)} placeholder="STOP" />
          <DialogFooter>
            <Button variant="outline" onClick={() => { setStopTarget(null); setStopConfirmText(""); }}>Cancel</Button>
            <Button variant="destructive" disabled={stopConfirmText !== "STOP" || stopM.isPending} onClick={() => void onStop()}>
              {stopM.isPending ? "Stopping…" : "Stop campaign"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
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
