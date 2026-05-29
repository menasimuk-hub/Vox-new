import { createFileRoute, Link } from "@tanstack/react-router";
import * as React from "react";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { SortHeader, useTableSort } from "@/components/sortable-table";
import { orderTab, orderToCampaign } from "@/lib/mappers/orders";
import { useServiceOrders } from "@/lib/queries";

export const Route = createFileRoute("/_app/interviews/results/")({
  head: () => ({ meta: [{ title: "Interview results — VoxBulk" }] }),
  component: InterviewResultsHub,
});

function InterviewResultsHub() {
  const [tab, setTab] = React.useState<"live" | "finished">("live");
  const ordersQ = useServiceOrders("interview");

  const rows = React.useMemo(
    () =>
      (ordersQ.data || [])
        .filter((o) => {
          const t = orderTab(o);
          return tab === "live" ? t === "live" || t === "scheduled" || t === "paused" : t === "finished";
        })
        .map((o) => ({
          id: o.id,
          campaignId: o.campaign_id || o.reference_id || "—",
          name: orderToCampaign(o, "interview").name,
          status: orderToCampaign(o, "interview").status,
          candidates: o.recipient_count ?? 0,
        })),
    [ordersQ.data, tab],
  );

  const s = useTableSort(rows);

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="Interviews · Results"
        title="Interview results"
        description="Pick a campaign to view candidate scores, recordings, transcripts, and scheduling."
      />

      <Tabs value={tab} onValueChange={(v) => setTab(v as "live" | "finished")}>
        <TabsList>
          <TabsTrigger value="live">Live & scheduled</TabsTrigger>
          <TabsTrigger value="finished">Finished</TabsTrigger>
        </TabsList>
      </Tabs>

      <Card>
        <CardContent className="px-0">
          {ordersQ.isLoading ? (
            <div className="space-y-2 p-6">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          ) : rows.length === 0 ? (
            <p className="p-8 text-center text-sm text-muted-foreground">
              No {tab === "live" ? "live" : "finished"} interview campaigns yet. Create one from Saved interviews.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <SortHeader label="Campaign ID" sortKey="campaignId" active={s.sortKey} dir={s.sortDir} onToggle={s.toggleSort} className="pl-6" />
                  <SortHeader label="Campaign" sortKey="name" active={s.sortKey} dir={s.sortDir} onToggle={s.toggleSort} />
                  <SortHeader label="Status" sortKey="status" active={s.sortKey} dir={s.sortDir} onToggle={s.toggleSort} />
                  <SortHeader label="Candidates" sortKey="candidates" active={s.sortKey} dir={s.sortDir} onToggle={s.toggleSort} />
                  <TableHead className="pr-6 text-right">Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {s.sorted.map((c) => (
                  <TableRow key={c.id}>
                    <TableCell className="pl-6 font-mono text-xs">{c.campaignId}</TableCell>
                    <TableCell className="font-medium">{c.name}</TableCell>
                    <TableCell>
                      <StatusBadge tone={c.status} />
                    </TableCell>
                    <TableCell>{c.candidates}</TableCell>
                    <TableCell className="pr-6 text-right">
                      <Button size="sm" variant="outline" asChild>
                        <Link to="/interviews/results/$orderId" params={{ orderId: c.id }}>
                          View results
                        </Link>
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
