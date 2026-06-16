import { createFileRoute, Link } from "@tanstack/react-router";
import * as React from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ArrowLeft, Lock, MapPin, Sparkles, Check } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api";
import { isMultiLocationFeedbackPlan } from "@/lib/feedback-plan";
import {
  useFeedbackLocations,
  useFeedbackResultsCompare,
  useFeedbackSubscription,
  type FeedbackCompareLocation,
} from "@/lib/queries";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/feedback/compare")({
  head: () => ({ meta: [{ title: "Compare locations — VoxBulk" }] }),
  component: FeedbackCompare,
});

const PALETTE = ["#6366f1", "#14b8a6", "#f59e0b", "#ec4899", "#8b5cf6", "#06b6d4", "#f97316", "#22c55e"];

type Loc = {
  id: string;
  name: string;
  color: string;
  responses: number;
  invited: number;
  satisfaction: number;
  recommend: number;
  happy: number;
  neutral: number;
  unhappy: number;
  trend: number[];
  perQuestion: Record<string, number>;
};

function mapLoc(row: FeedbackCompareLocation): Loc {
  const sp = row.sentiment_pct || { happy: 0, neutral: 0, unhappy: 0 };
  return {
    id: row.id,
    name: row.name,
    color: row.color,
    responses: row.responses,
    invited: row.invited,
    satisfaction: row.satisfaction_pct ?? 0,
    recommend: row.recommend_pct ?? 0,
    happy: sp.happy ?? 0,
    neutral: sp.neutral ?? 0,
    unhappy: sp.unhappy ?? 0,
    trend: row.weekly_trend || [],
    perQuestion: row.per_question || {},
  };
}

function FeedbackCompare() {
  const subscriptionQ = useFeedbackSubscription();
  const locationsQ = useFeedbackLocations();
  const allLocations = locationsQ.data || [];
  const multiLocation = isMultiLocationFeedbackPlan(subscriptionQ.data);

  const [selected, setSelected] = React.useState<string[]>([]);

  React.useEffect(() => {
    if (allLocations.length === 0 || selected.length > 0) return;
    setSelected(allLocations.slice(0, Math.min(3, allLocations.length)).map((l) => l.id));
  }, [allLocations, selected.length]);

  const compareQ = useFeedbackResultsCompare(selected);
  const compareLocs = (compareQ.data?.locations || []).map(mapLoc);
  const locById = React.useMemo(() => new Map(compareLocs.map((l) => [l.id, l])), [compareLocs]);
  const locs = compareLocs.filter((l) => selected.includes(l.id));
  const chartsLoading = selected.length > 0 && compareQ.isLoading && compareLocs.length === 0;

  const sharedQuestions = compareQ.data?.shared_questions || [];
  const allQuestions = compareQ.data?.all_questions || [];

  if (!subscriptionQ.isLoading && !multiLocation) {
    return <Locked />;
  }

  if (subscriptionQ.isLoading || locationsQ.isLoading) {
    return (
      <div className="flex w-full flex-col gap-6">
        <Skeleton className="h-24 rounded-xl" />
        <Skeleton className="h-48 rounded-xl" />
        <div className="grid gap-4 md:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-28 rounded-xl" />
          ))}
        </div>
      </div>
    );
  }

  const trendData = Array.from({ length: 8 }, (_, i) => {
    const row: Record<string, number | string> = { week: `W${i + 1}` };
    locs.forEach((l) => {
      row[l.id] = l.trend[i] ?? 0;
    });
    return row;
  });

  const perQuestionData = sharedQuestions.map((q) => {
    const row: Record<string, number | string> = { question: q.short };
    locs.forEach((l) => {
      row[l.id] = l.perQuestion[q.key] ?? 0;
    });
    return row;
  });

  const totalResponses = locs.reduce((a, l) => a + l.responses, 0);
  const totalInvited = locs.reduce((a, l) => a + l.invited, 0);
  const avgSat = locs.length ? Math.round(locs.reduce((a, l) => a + l.satisfaction, 0) / locs.length) : 0;
  const best = [...locs].sort((a, b) => b.satisfaction - a.satisfaction)[0];
  const worst = [...locs].sort((a, b) => a.satisfaction - b.satisfaction)[0];

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="Customer feedback · Compare"
        title="Compare locations"
        description="Side-by-side performance across your venues. Charts only include questions that appear in every selected location's survey."
        actions={
          <Button variant="outline" asChild className="gap-1.5">
            <Link to="/feedback/results"><ArrowLeft className="size-4" /> Back to results</Link>
          </Button>
        }
      />

      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between gap-3">
            <CardTitle className="text-base flex items-center gap-2">
              <MapPin className="size-4 text-primary" /> Pick locations to compare
            </CardTitle>
            <p className="text-xs text-muted-foreground">{selected.length} of {allLocations.length} selected</p>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {allLocations.map((l, idx) => {
              const on = selected.includes(l.id);
              const metrics = locById.get(l.id);
              const color = metrics?.color || PALETTE[idx % PALETTE.length];
              return (
                <button
                  key={l.id}
                  type="button"
                  onClick={() =>
                    setSelected((s) => (s.includes(l.id) ? s.filter((x) => x !== l.id) : [...s, l.id]))
                  }
                  className={cn(
                    "flex items-start gap-3 rounded-xl border p-3 text-left transition",
                    on
                      ? "border-primary/50 bg-primary/5 shadow-sm"
                      : "border-border bg-background/40 hover:border-primary/30",
                  )}
                >
                  <span
                    className="mt-1 size-3.5 shrink-0 rounded-full ring-2 ring-background"
                    style={{ background: color }}
                  />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">{l.name}</p>
                    <p className="mt-1 text-[11px] text-muted-foreground">
                      {metrics
                        ? `${metrics.responses.toLocaleString()} responses · ${metrics.satisfaction}% positive`
                        : `${l.scan_count ?? 0} scans`}
                    </p>
                  </div>
                  <Checkbox checked={on} className="mt-0.5" tabIndex={-1} />
                </button>
              );
            })}
          </div>
          {sharedQuestions.length < allQuestions.length && allQuestions.length > 0 && selected.length > 1 && (
            <p className="mt-3 flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-900 dark:text-amber-200">
              <Sparkles className="mt-0.5 size-3.5 shrink-0" />
              Showing the {sharedQuestions.length} of {allQuestions.length} questions that all selected locations
              have in common. Questions unique to a single location are hidden.
            </p>
          )}
        </CardContent>
      </Card>

      {compareQ.isError ? (
        <CompareError error={compareQ.error} onRetry={() => void compareQ.refetch()} />
      ) : null}

      {compareQ.isFetching && locs.length > 0 ? (
        <p className="text-center text-xs text-muted-foreground">Updating comparison…</p>
      ) : null}

      {selected.length === 0 ? (
        <Card><CardContent className="py-12 text-center text-sm text-muted-foreground">
          Select at least one location above to start comparing.
        </CardContent></Card>
      ) : chartsLoading ? (
        <CompareChartsSkeleton />
      ) : locs.length === 0 ? (
        <Card><CardContent className="py-12 text-center text-sm text-muted-foreground">
          No comparison data returned for the selected locations. Check that the API is deployed and try again.
        </CardContent></Card>
      ) : (
        <>
          <div className="grid gap-4 md:grid-cols-4">
            <Summary label="Locations" value={`${locs.length}`} sub="In comparison" />
            <Summary label="Total responses" value={totalResponses.toLocaleString()} sub={`of ${totalInvited.toLocaleString()} invited`} />
            <Summary label="Avg satisfaction" value={`${avgSat}%`} sub="Across selected" />
            <Summary
              label="Top vs lowest"
              value={best && worst ? `${best.satisfaction - worst.satisfaction} pts` : "—"}
              sub={best && worst ? `${best.name} → ${worst.name}` : ""}
            />
          </div>

          <div className="flex flex-wrap items-center gap-2 rounded-xl border border-border bg-card p-3">
            <span className="text-xs font-medium text-muted-foreground mr-1">Legend:</span>
            {locs.map((l) => (
              <Badge key={l.id} variant="outline" className="gap-1.5 border-transparent" style={{ background: `${l.color}15`, color: l.color }}>
                <span className="size-2 rounded-full" style={{ background: l.color }} />
                {l.name}
              </Badge>
            ))}
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Satisfaction trend (8 weeks)</CardTitle>
                <p className="text-xs text-muted-foreground">% positive responses per week, by location</p>
              </CardHeader>
              <CardContent className="h-[300px]">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={trendData} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                    <XAxis dataKey="week" stroke="hsl(var(--muted-foreground))" fontSize={12} />
                    <YAxis stroke="hsl(var(--muted-foreground))" fontSize={12} domain={[40, 100]} />
                    <Tooltip contentStyle={{ background: "hsl(var(--background))", border: "1px solid hsl(var(--border))", borderRadius: 8, fontSize: 12 }} />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    {locs.map((l) => (
                      <Line key={l.id} type="monotone" dataKey={l.id} name={l.name} stroke={l.color} strokeWidth={2.5} dot={{ r: 3 }} activeDot={{ r: 5 }} />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Per-question · % positive</CardTitle>
                <p className="text-xs text-muted-foreground">Only shared questions across selected locations</p>
              </CardHeader>
              <CardContent className="h-[300px]">
                {perQuestionData.length === 0 ? (
                  <p className="flex h-full items-center justify-center text-sm text-muted-foreground">No shared questions for this selection.</p>
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={perQuestionData} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                      <XAxis dataKey="question" stroke="hsl(var(--muted-foreground))" fontSize={12} />
                      <YAxis stroke="hsl(var(--muted-foreground))" fontSize={12} domain={[0, 100]} />
                      <Tooltip contentStyle={{ background: "hsl(var(--background))", border: "1px solid hsl(var(--border))", borderRadius: 8, fontSize: 12 }} />
                      <Legend wrapperStyle={{ fontSize: 12 }} />
                      {locs.map((l) => (
                        <Bar key={l.id} dataKey={l.id} name={l.name} fill={l.color} radius={[4, 4, 0, 0]} />
                      ))}
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Response count & rate</CardTitle>
                <p className="text-xs text-muted-foreground">Responses received vs scans per location</p>
              </CardHeader>
              <CardContent className="h-[300px]">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={locs.map((l) => ({
                      name: l.name,
                      Responses: l.responses,
                      Invited: l.invited,
                      color: l.color,
                    }))}
                    margin={{ top: 10, right: 10, left: -10, bottom: 0 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                    <XAxis dataKey="name" stroke="hsl(var(--muted-foreground))" fontSize={12} />
                    <YAxis stroke="hsl(var(--muted-foreground))" fontSize={12} />
                    <Tooltip contentStyle={{ background: "hsl(var(--background))", border: "1px solid hsl(var(--border))", borderRadius: 8, fontSize: 12 }} />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Bar dataKey="Invited" fill="hsl(var(--muted))" radius={[4, 4, 0, 0]} />
                    <Bar dataKey="Responses" radius={[4, 4, 0, 0]}>
                      {locs.map((l) => (
                        <Cell key={l.id} fill={l.color} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Sentiment split</CardTitle>
                <p className="text-xs text-muted-foreground">Happy / Neutral / Unhappy per location</p>
              </CardHeader>
              <CardContent className="h-[300px]">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    layout="vertical"
                    data={locs.map((l) => ({ name: l.name, Happy: l.happy, Neutral: l.neutral, Unhappy: l.unhappy }))}
                    margin={{ top: 10, right: 10, left: 30, bottom: 0 }}
                    stackOffset="expand"
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                    <XAxis type="number" tickFormatter={(v) => `${Math.round(Number(v) * 100)}%`} stroke="hsl(var(--muted-foreground))" fontSize={12} />
                    <YAxis dataKey="name" type="category" stroke="hsl(var(--muted-foreground))" fontSize={12} width={100} />
                    <Tooltip
                      contentStyle={{ background: "hsl(var(--background))", border: "1px solid hsl(var(--border))", borderRadius: 8, fontSize: 12 }}
                      formatter={(v: number) => `${v}%`}
                    />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Bar dataKey="Happy" stackId="a" fill="#22c55e" />
                    <Bar dataKey="Neutral" stackId="a" fill="#f59e0b" />
                    <Bar dataKey="Unhappy" stackId="a" fill="#ef4444" />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Side-by-side breakdown</CardTitle>
              <p className="text-xs text-muted-foreground">All key metrics in one place</p>
            </CardHeader>
            <CardContent className="overflow-x-auto">
              <table className="w-full min-w-[640px] text-sm">
                <thead>
                  <tr className="border-b border-border text-left text-xs text-muted-foreground">
                    <th className="py-2 pr-3 font-medium">Metric</th>
                    {locs.map((l) => (
                      <th key={l.id} className="py-2 px-3 font-medium">
                        <span className="inline-flex items-center gap-1.5">
                          <span className="size-2.5 rounded-full" style={{ background: l.color }} />
                          {l.name}
                        </span>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  <Row label="Responses" locs={locs} render={(l) => l.responses.toLocaleString()} />
                  <Row label="Response rate" locs={locs} render={(l) => `${l.invited ? Math.round((l.responses / l.invited) * 100) : 0}%`} highlight={(l) => (l.invited ? Math.round((l.responses / l.invited) * 100) : 0)} />
                  <Row label="Satisfaction" locs={locs} render={(l) => `${l.satisfaction}%`} highlight={(l) => l.satisfaction} />
                  <Row label="Would recommend" locs={locs} render={(l) => `${l.recommend}%`} highlight={(l) => l.recommend} />
                  <Row label="Happy" locs={locs} render={(l) => `${l.happy}%`} />
                  <Row label="Neutral" locs={locs} render={(l) => `${l.neutral}%`} />
                  <Row label="Unhappy" locs={locs} render={(l) => `${l.unhappy}%`} highlight={(l) => -l.unhappy} />
                  {sharedQuestions.map((q) => (
                    <Row
                      key={q.key}
                      label={q.title}
                      locs={locs}
                      render={(l) => `${l.perQuestion[q.key] ?? 0}%`}
                      highlight={(l) => l.perQuestion[q.key] ?? 0}
                    />
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

function CompareError({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  let title = "Could not load comparison data";
  let detail = error instanceof Error ? error.message : "Unknown error";
  if (error instanceof ApiError) {
    if (error.status === 403) {
      title = "Multi-location plan required";
      detail = "Upgrade your Customer feedback package to compare results across branches.";
    } else if (error.status === 404) {
      title = "Compare API not available";
      detail = "Deploy the latest API on the server, then refresh this page.";
    }
  }
  return (
    <Card className="border-destructive/40 bg-destructive/5">
      <CardContent className="flex flex-col gap-3 py-6 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="font-medium text-destructive">{title}</p>
          <p className="mt-1 text-sm text-muted-foreground">{detail}</p>
        </div>
        <Button variant="outline" size="sm" onClick={onRetry}>
          Retry
        </Button>
      </CardContent>
    </Card>
  );
}

function CompareChartsSkeleton() {
  return (
    <>
      <div className="grid gap-4 md:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-28 rounded-xl" />
        ))}
      </div>
      <Skeleton className="h-14 rounded-xl" />
      <div className="grid gap-4 lg:grid-cols-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-[360px] rounded-xl" />
        ))}
      </div>
      <Skeleton className="h-64 rounded-xl" />
    </>
  );
}

function Summary({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <Card>
      <CardContent className="p-4">
        <p className="text-[11px] uppercase tracking-wider text-muted-foreground">{label}</p>
        <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
        <p className="text-xs text-muted-foreground">{sub}</p>
      </CardContent>
    </Card>
  );
}

function Row({
  label,
  locs,
  render,
  highlight,
}: {
  label: string;
  locs: Loc[];
  render: (l: Loc) => string;
  highlight?: (l: Loc) => number;
}) {
  let bestId: string | null = null;
  if (highlight) {
    const sorted = [...locs].sort((a, b) => highlight(b) - highlight(a));
    bestId = sorted[0]?.id ?? null;
  }
  return (
    <tr>
      <td className="py-2.5 pr-3 text-muted-foreground">{label}</td>
      {locs.map((l) => (
        <td key={l.id} className="py-2.5 px-3 tabular-nums">
          <span className={cn("inline-flex items-center gap-1.5", bestId === l.id && "font-semibold text-foreground")}>
            {render(l)}
            {bestId === l.id && locs.length > 1 && <Check className="size-3.5 text-emerald-500" />}
          </span>
        </td>
      ))}
    </tr>
  );
}

function Locked() {
  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="Customer feedback · Compare"
        title="Compare locations"
        description="Side-by-side performance across all your venues."
      />
      <Card className="border-dashed">
        <CardContent className="flex flex-col items-center gap-4 py-16 text-center">
          <div className="grid size-14 place-items-center rounded-2xl bg-primary/10 text-primary">
            <Lock className="size-6" />
          </div>
          <div className="max-w-md space-y-1">
            <h3 className="text-lg font-semibold">Multi-location is part of a higher plan</h3>
            <p className="text-sm text-muted-foreground">
              Upgrade your Customer feedback package to compare results across branches in one place. Same survey,
              one dashboard, instant winners and laggards.
            </p>
          </div>
          <Button asChild>
            <Link to="/account/feedback/packages">Upgrade plan</Link>
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
