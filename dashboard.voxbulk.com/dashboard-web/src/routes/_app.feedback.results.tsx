import { createFileRoute, Link } from "@tanstack/react-router";
import * as React from "react";
import { BarChart3, Download, MapPin, QrCode, Users } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useFeedbackResults } from "@/lib/queries";

export const Route = createFileRoute("/_app/feedback/results")({
  head: () => ({ meta: [{ title: "Feedback results — VoxBulk" }] }),
  validateSearch: (search: Record<string, unknown>) => ({
    location_id: typeof search.location_id === "string" ? search.location_id : undefined,
  }),
  component: FeedbackResults,
});

function FeedbackResults() {
  const { location_id: initialLocationId } = Route.useSearch();
  const [locationId, setLocationId] = React.useState(initialLocationId || "all");

  React.useEffect(() => {
    if (initialLocationId) setLocationId(initialLocationId);
  }, [initialLocationId]);

  const resultsQ = useFeedbackResults(locationId === "all" ? {} : { location_id: locationId });
  const data = resultsQ.data;
  const summary = data?.summary;
  const locations = data?.locations || [];
  const rows = data?.rows || [];

  const responseCountByLocation = React.useMemo(() => {
    const map = new Map<string, number>();
    for (const row of rows) {
      if (row.location_id) map.set(row.location_id, (map.get(row.location_id) || 0) + 1);
    }
    return map;
  }, [rows]);

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="Customer feedback"
        title="Feedback results"
        description="Responses collected from QR surveys in your venues — filter by location."
        actions={
          <Button asChild variant="outline" className="gap-1.5">
            <Link to="/feedback">
              <QrCode className="size-4" /> Saved QR surveys
            </Link>
          </Button>
        }
      />

      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-[220px] space-y-1">
          <label className="text-xs font-medium text-muted-foreground">Location</label>
          <Select value={locationId} onValueChange={setLocationId}>
            <SelectTrigger>
              <SelectValue placeholder="All locations" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All locations</SelectItem>
              {locations.map((loc) => (
                <SelectItem key={loc.id} value={loc.id}>
                  {loc.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {resultsQ.isLoading ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24 rounded-xl" />
          ))}
        </div>
      ) : resultsQ.isError ? (
        <Card>
          <CardContent className="p-8 text-center text-sm text-destructive">
            Could not load feedback results
            {resultsQ.error instanceof Error ? `: ${resultsQ.error.message}` : ""}.
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard icon={Users} label="Sessions" value={String(summary?.sessions ?? 0)} />
            <StatCard icon={BarChart3} label="Completed" value={String(summary?.completed_sessions ?? 0)} />
            <StatCard icon={MapPin} label="Responses" value={String(summary?.responses ?? 0)} />
            <StatCard icon={QrCode} label="Total scans" value={String(summary?.total_scans ?? 0)} />
          </div>

          {locationId === "all" && locations.length > 0 ? (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {locations.map((loc) => (
                <Card key={loc.id}>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base">{loc.name}</CardTitle>
                    <p className="text-xs text-muted-foreground">{loc.industry_name}</p>
                  </CardHeader>
                  <CardContent className="flex items-center justify-between gap-3 text-sm">
                    <div>
                      <p className="text-muted-foreground">Scans</p>
                      <p className="font-semibold tabular-nums">{loc.scan_count ?? 0}</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">Responses</p>
                      <p className="font-semibold tabular-nums text-primary">{responseCountByLocation.get(loc.id) ?? 0}</p>
                    </div>
                    <Button size="sm" variant="outline" onClick={() => setLocationId(loc.id)}>
                      View
                    </Button>
                  </CardContent>
                </Card>
              ))}
            </div>
          ) : null}

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Recent responses</CardTitle>
            </CardHeader>
            <CardContent className="px-0">
              {rows.length === 0 ? (
                <p className="px-6 pb-6 text-center text-sm text-muted-foreground">
                  No responses yet. Print your QR codes and place them in your venue.
                </p>
              ) : (
                <div className="table-scroll">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="pl-6">When</TableHead>
                        <TableHead>Location</TableHead>
                        <TableHead>Topic</TableHead>
                        <TableHead>Question</TableHead>
                        <TableHead className="pr-6">Answer</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {rows.map((row) => (
                        <TableRow key={row.id}>
                          <TableCell className="pl-6 text-xs text-muted-foreground">
                            {row.created_at ? new Date(row.created_at).toLocaleString("en-GB") : "—"}
                          </TableCell>
                          <TableCell>{row.location_name || "—"}</TableCell>
                          <TableCell className="text-sm">{row.survey_type_name || "—"}</TableCell>
                          <TableCell className="max-w-[200px] truncate text-sm">{row.question_key || "—"}</TableCell>
                          <TableCell className="pr-6 font-medium">{row.answer_text || "—"}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

function StatCard({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
}) {
  return (
    <Card>
      <CardContent className="flex items-center gap-3 p-4">
        <div className="grid size-10 place-items-center rounded-lg bg-primary/10 text-primary">
          <Icon className="size-5" />
        </div>
        <div>
          <p className="text-[11px] uppercase tracking-wider text-muted-foreground">{label}</p>
          <p className="text-2xl font-semibold tabular-nums">{value}</p>
        </div>
      </CardContent>
    </Card>
  );
}
