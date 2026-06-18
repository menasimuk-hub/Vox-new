import * as React from "react";
import { useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  AlertTriangle,
  ArrowDownRight,
  ArrowLeft,
  ArrowUpRight,
  CheckCircle2,
  Download,
  Filter,
  MessageSquareText,
  Phone,
  Search,
  Smile,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  TrendingUp,
  Users,
  XCircle,
} from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { MapPin } from "lucide-react";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { SortHeader, useTableSort } from "@/components/sortable-table";
import { cn } from "@/lib/utils";
import type {
  FeedbackSurveyResultsData,
  Question,
  Respondent,
  VoiceComment,
} from "@/components/feedback-results/feedback-results-mappers";

export type FeedbackSurveyResultsProps = {
  data: FeedbackSurveyResultsData;
  locationId: string;
  locations: Array<{ id: string; name: string }>;
  onLocationChange: (id: string) => void;
  onExportPdf: () => void;
  onExportCsv: () => void;
  headerActions?: React.ReactNode;
  insightsLoading?: boolean;
};

export function FeedbackSurveyResults({
  data,
  locationId,
  locations,
  onLocationChange,
  onExportPdf,
  onExportCsv,
  headerActions,
  insightsLoading,
}: FeedbackSurveyResultsProps) {
  const [tab, setTab] = useState("overview");
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<"all" | "unhappy" | "neutral" | "happy" | "flagged">("all");
  const [openId, setOpenId] = useState<string | null>(null);

  const {
    pageTitle,
    metaLine,
    weeklyImprovementBadge,
    weeklyTrend,
    sentimentDistribution,
    questions,
    voiceComments,
    textComments,
    respondents,
    themes,
    recommendations,
    kpi,
  } = data;

  const branches = [{ id: "all", name: "All locations" }, ...locations.map((l) => ({ id: l.id, name: l.name }))];
  const branch = locationId;

  const filtered = useMemo(() => {
    return respondents.filter((r) => {
      if (filter === "flagged" && !r.flagged) return false;
      if (filter !== "all" && filter !== "flagged" && r.sentiment !== filter) return false;
      if (search && !r.name.toLowerCase().includes(search.toLowerCase()) && !r.mobile.includes(search)) return false;
      return true;
    });
  }, [search, filter, respondents]);

  type SortableRespondent = Respondent & {
    sortName: string;
    sortMobile: string;
    sortSentiment: number;
    sortCompletedAt: number;
  };

  const rowsForSort = useMemo<SortableRespondent[]>(
    () =>
      filtered.map((r) => ({
        ...r,
        sortName: r.name,
        sortMobile: r.mobile,
        sortSentiment: r.sentiment === "unhappy" ? 0 : r.sentiment === "neutral" ? 1 : 2,
        sortCompletedAt: r.completedAtTs,
      })),
    [filtered],
  );

  const tableSort = useTableSort(rowsForSort as Record<string, unknown>[], "sortSentiment", "asc");

  const counts = useMemo(() => ({
    unhappy: respondents.filter((r) => r.sentiment === "unhappy").length,
    neutral: respondents.filter((r) => r.sentiment === "neutral").length,
    happy: respondents.filter((r) => r.sentiment === "happy").length,
    flagged: respondents.filter((r) => r.flagged).length,
  }), [respondents]);

  const openRespondent = respondents.find((r) => r.id === openId) ?? null;

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="Customer Feedback · Results"
        title={pageTitle}
        description="Track week-over-week improvement, dive into each question, and find unhappy customers fast."
        actions={
          <>
            {headerActions}
            <Button variant="outline" className="gap-1.5" onClick={onExportPdf}><Download className="size-4" /> Export PDF</Button>
            <Button variant="outline" className="gap-1.5" onClick={onExportCsv}><Download className="size-4" /> Export CSV</Button>
          </>
        }
      />

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card p-3">
        <div className="flex flex-wrap items-center gap-3">
          <StatusBadge tone="live" />
          <span className="text-sm text-muted-foreground">{metaLine}</span>
          <Select value={branch} onValueChange={onLocationChange}>
            <SelectTrigger className="h-8 w-[180px] gap-1.5">
              <MapPin className="size-3.5 text-primary" />
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {branches.map((b) => (
                <SelectItem key={b.id} value={b.id}>{b.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList>
            <TabsTrigger value="overview">Overview</TabsTrigger>
            <TabsTrigger value="questions">Questions</TabsTrigger>
            <TabsTrigger value="responses">Responses</TabsTrigger>
            <TabsTrigger value="details" className="gap-1.5">
              More details
              {counts.flagged > 0 && (
                <span className="rounded-full bg-destructive px-1.5 py-0.5 text-[10px] font-semibold text-destructive-foreground">
                  {counts.flagged}
                </span>
              )}
            </TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        {/* OVERVIEW */}
        <TabsContent value="overview" className="space-y-6">
          <div className="grid gap-4 md:grid-cols-4">
            <Kpi title="Satisfaction" value={kpi.satisfaction} delta={kpi.satisfactionDelta} sub={kpi.satisfactionSub} icon={<Smile className="size-4" />} />
            <Kpi title="Would recommend" value={kpi.recommend} delta={kpi.recommendDelta} sub={kpi.recommendSub} icon={<ThumbsUp className="size-4" />} />
            <Kpi title="Response rate" value={kpi.responseRate} delta={kpi.responseRateDelta} sub={kpi.responseRateSub} icon={<Users className="size-4" />} />
            <Kpi title="Unhappy customers" value={kpi.unhappy} delta={kpi.unhappyDelta} sub={kpi.unhappySub} icon={<AlertTriangle className="size-4" />} tone="destructive" invertDelta />
          </div>

          <div className="grid gap-4 lg:grid-cols-[1.6fr_1fr]">
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle className="text-base">Weekly improvement</CardTitle>
                    <p className="text-xs text-muted-foreground">% positive responses over the last 8 waves</p>
                  </div>
                  {weeklyImprovementBadge && (
                    <Badge variant="secondary" className="gap-1"><ArrowUpRight className="size-3" /> {weeklyImprovementBadge}</Badge>
                  )}
                </div>
              </CardHeader>
              <CardContent className="h-[280px]">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={weeklyTrend} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
                    <defs>
                      <linearGradient id="sat" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#6366f1" stopOpacity={0.35} />
                        <stop offset="100%" stopColor="#6366f1" stopOpacity={0} />
                      </linearGradient>
                      <linearGradient id="rec" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#14b8a6" stopOpacity={0.3} />
                        <stop offset="100%" stopColor="#14b8a6" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                    <XAxis dataKey="week" stroke="#9ca3af" fontSize={12} />
                    <YAxis stroke="#9ca3af" fontSize={12} />
                    <Tooltip contentStyle={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 8, fontSize: 12 }} />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Area type="monotone" dataKey="satisfaction" stroke="#6366f1" strokeWidth={2} fill="url(#sat)" name="Satisfaction %" />
                    <Area type="monotone" dataKey="positive" stroke="#14b8a6" strokeWidth={2} fill="url(#rec)" name="Would recommend %" />
                  </AreaChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Sentiment split</CardTitle>
                <p className="text-xs text-muted-foreground">Happy · Neutral · Unhappy</p>
              </CardHeader>
              <CardContent className="h-[280px]">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={sentimentDistribution} dataKey="value" innerRadius={60} outerRadius={95} paddingAngle={3} stroke="#fff">
                      {sentimentDistribution.map((d) => <Cell key={d.name} fill={d.color} />)}
                    </Pie>
                    <Tooltip contentStyle={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 8, fontSize: 12 }} />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                  </PieChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <Card>
              <CardHeader><CardTitle className="text-base">Response volume / week</CardTitle></CardHeader>
              <CardContent className="h-[200px]">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={weeklyTrend} margin={{ top: 5, right: 5, left: -20, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                    <XAxis dataKey="week" stroke="#9ca3af" fontSize={11} />
                    <YAxis stroke="#9ca3af" fontSize={11} />
                    <Tooltip contentStyle={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 8, fontSize: 12 }} />
                    <Bar dataKey="responses" fill="#6366f1" radius={[6, 6, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            <Card>
              <CardHeader><CardTitle className="text-base">AI themes</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                {insightsLoading && themes.length === 0 ? (
                  <p className="text-sm text-muted-foreground">Generating themes…</p>
                ) : themes.length === 0 ? (
                  <p className="text-sm text-muted-foreground">Themes appear once enough responses are collected.</p>
                ) : (
                  themes.map((t) => <Theme key={t.label} label={t.label} value={t.value} sentiment={t.sentiment} />)
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center gap-2">
                <Sparkles className="size-4 text-primary" />
                <CardTitle className="text-base">AI recommended actions</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                {insightsLoading && recommendations.length === 0 ? (
                  <p className="text-muted-foreground">Generating recommendations…</p>
                ) : recommendations.length === 0 ? (
                  <p className="text-muted-foreground">Recommendations appear once enough responses are analysed.</p>
                ) : (
                  recommendations.map((a) => <Action key={a.title} text={a.text} impact={a.impact} />)
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* QUESTIONS */}
        <TabsContent value="questions" className="space-y-4">
          <div className="rounded-xl border border-border bg-card p-3 text-sm text-muted-foreground">
            Each question is shown with its own scale — <b>Poor / Good / Excellent</b> or <b>Yes / No</b> — so you see exactly where wins or losses come from.
          </div>
          {questions.map((q) => <QuestionBlock key={q.id} q={q} />)}
        </TabsContent>

        {/* RESPONSES (anonymous voice + text) */}
        <TabsContent value="responses" className="space-y-6">
          <Card>
            <CardHeader>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <CardTitle className="text-base flex items-center gap-2">
                    <MessageSquareText className="size-4 text-primary" />
                    Anonymous voice & text comments
                  </CardTitle>
                  <p className="text-xs text-muted-foreground">For poor ratings we ask <i>why?</i> — for excellent ratings we ask <i>anything to add?</i> Voice replies are auto-transcribed.</p>
                </div>
                <Badge variant="secondary">{voiceComments.length} voice replies this wave</Badge>
              </div>
            </CardHeader>
            <CardContent className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {voiceComments.map((v) => <VoiceCard key={v.id} v={v} />)}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <CardTitle className="text-base">Anonymous text responses</CardTitle>
                <div className="flex gap-2">
                  <div className="relative">
                    <Search className="absolute left-2 top-2.5 size-4 text-muted-foreground" />
                    <Input placeholder="Search themes" className="h-9 w-48 pl-8" />
                  </div>
                  <Button variant="outline" size="sm" className="gap-1.5"><Filter className="size-4" /> Filter</Button>
                </div>
              </div>
            </CardHeader>
            <CardContent className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              {textComments.map((r, i) => <Response key={i} {...r} />)}
            </CardContent>
          </Card>
        </TabsContent>

        {/* MORE DETAILS — per respondent */}
        <TabsContent value="details" className="space-y-4">
          <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-4">
            <div className="flex items-start gap-3">
              <AlertTriangle className="mt-0.5 size-5 text-destructive" />
              <div className="flex-1">
                <p className="text-sm font-medium">{counts.flagged} customer{counts.flagged === 1 ? "" : "s"} flagged as unhappy</p>
                <p className="text-xs text-muted-foreground">These respondents rated multiple questions <b>poor</b> or answered <b>no</b> to "would recommend". Call them within 24 hours to recover the relationship.</p>
              </div>
              <Button size="sm" variant="destructive" className="gap-1.5" onClick={() => setFilter("flagged")}>
                <Phone className="size-3.5" /> View {counts.flagged}
              </Button>
            </div>
          </div>

          <Card>
            <CardHeader>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <CardTitle className="text-base">All respondents · {filtered.length} of {respondents.length}</CardTitle>
                  <p className="text-xs text-muted-foreground">Click any row to see that customer's full answers &amp; contact details.</p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <div className="relative">
                    <Search className="absolute left-2 top-2.5 size-4 text-muted-foreground" />
                    <Input
                      placeholder="Search name or mobile"
                      className="h-9 w-56 pl-8"
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                    />
                  </div>
                  <div className="flex rounded-md border border-border p-0.5">
                    <FilterPill active={filter === "all"} onClick={() => setFilter("all")}>All</FilterPill>
                    <FilterPill active={filter === "flagged"} onClick={() => setFilter("flagged")} tone="destructive">
                      <AlertTriangle className="size-3" /> Flagged
                    </FilterPill>
                    <FilterPill active={filter === "unhappy"} onClick={() => setFilter("unhappy")} tone="destructive">Unhappy</FilterPill>
                    <FilterPill active={filter === "neutral"} onClick={() => setFilter("neutral")} tone="warning">Neutral</FilterPill>
                    <FilterPill active={filter === "happy"} onClick={() => setFilter("happy")} tone="success">Happy</FilterPill>
                  </div>
                </div>
              </div>
            </CardHeader>
            <CardContent className="p-0">
              {tableSort.sorted.length === 0 ? (
                <div className="p-8 text-center text-sm text-muted-foreground">No respondents match these filters.</div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[720px] text-sm">
                    <thead>
                      <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-muted-foreground">
                        <SortHeader
                          label="Customer"
                          sortKey="sortName"
                          active={tableSort.sortKey}
                          dir={tableSort.sortDir}
                          onToggle={tableSort.toggleSort}
                          className="px-4 py-2"
                        />
                        <SortHeader
                          label="Mobile"
                          sortKey="sortMobile"
                          active={tableSort.sortKey}
                          dir={tableSort.sortDir}
                          onToggle={tableSort.toggleSort}
                          className="px-4 py-2"
                        />
                        <SortHeader
                          label="Sentiment"
                          sortKey="sortSentiment"
                          active={tableSort.sortKey}
                          dir={tableSort.sortDir}
                          onToggle={tableSort.toggleSort}
                          className="px-4 py-2"
                        />
                        <SortHeader
                          label="Completed"
                          sortKey="sortCompletedAt"
                          active={tableSort.sortKey}
                          dir={tableSort.sortDir}
                          onToggle={tableSort.toggleSort}
                          className="px-4 py-2"
                        />
                        <th className="px-4 py-2 text-left text-xs font-medium text-muted-foreground">Quick view</th>
                        <th className="px-4 py-2 text-right text-xs font-medium text-muted-foreground">Action</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {(tableSort.sorted as SortableRespondent[]).map((r) => (
                        <tr
                          key={r.id}
                          onClick={() => setOpenId(r.id)}
                          className={cn(
                            "cursor-pointer transition-colors hover:bg-muted/50",
                            r.flagged && "bg-destructive/[0.03]",
                          )}
                        >
                          <td className="px-4 py-3">
                            <p className="font-medium leading-tight">{r.name}</p>
                          </td>
                          <td className="px-4 py-3 tabular-nums text-muted-foreground">{r.mobile}</td>
                          <td className="px-4 py-3">
                            <SentimentBadge sentiment={r.sentiment} flagged={r.flagged} />
                          </td>
                          <td className="px-4 py-3 text-xs text-muted-foreground">{r.completedAt}</td>
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-1">
                              {r.answers
                                .filter((a) => a.type !== "Voice")
                                .map((a, i) => <AnswerDot key={i} a={a as any} />)}
                            </div>
                          </td>
                          <td className="px-4 py-3 text-right">
                            <span className="text-xs font-medium text-primary">Open →</span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <p className="text-center text-[11px] text-muted-foreground">Results are for one selected feedback location. Export includes full client contact details for follow-up.</p>

      <RespondentSheet
        open={!!openRespondent}
        onOpenChange={(v) => !v && setOpenId(null)}
        respondent={openRespondent}
        questions={questions}
      />
    </div>
  );
}

// ---------- Components ----------
function Kpi({
  title, value, sub, icon, tone = "primary", delta, invertDelta,
}: {
  title: string; value: string; sub: string; icon: React.ReactNode;
  tone?: "primary" | "destructive"; delta?: number; invertDelta?: boolean;
}) {
  const positive = invertDelta ? (delta ?? 0) < 0 : (delta ?? 0) >= 0;
  return (
    <Card className="overflow-hidden">
      <CardContent className="p-4">
        <div className="flex items-center justify-between">
          <div className={cn("rounded-lg p-2", tone === "destructive" ? "bg-destructive/10 text-destructive" : "bg-primary/10 text-primary")}>{icon}</div>
          {delta !== undefined && (
            <span className={cn("flex items-center gap-0.5 text-xs font-medium", positive ? "text-success" : "text-destructive")}>
              {positive ? <ArrowUpRight className="size-3" /> : <ArrowDownRight className="size-3" />}
              {Math.abs(delta)} pts
            </span>
          )}
        </div>
        <p className="mt-3 text-xs uppercase tracking-wider text-muted-foreground">{title}</p>
        <p className="text-3xl font-semibold tracking-tight">{value}</p>
        <p className="text-xs text-muted-foreground">{sub}</p>
      </CardContent>
    </Card>
  );
}

function QuestionBlock({ q }: { q: Question }) {
  const avgLabel =
    q.scale === "PGE"
      ? `${q.breakdown.excellent}% excellent`
      : q.scale === "YN"
        ? `${q.breakdown.yes}% yes`
        : `${q.samples} voice replies`;

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <div className="flex items-center gap-2">
              <CardTitle className="text-base">{q.title}</CardTitle>
              <Badge variant="outline">{q.type}</Badge>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">{q.responses.toLocaleString()} responses</p>
          </div>
          <div className="text-right">
            <p className="text-2xl font-semibold tracking-tight">{avgLabel}</p>
            {"delta" in q && q.delta !== undefined && (
              <span className={cn("flex items-center justify-end gap-0.5 text-xs font-medium", q.delta >= 0 ? "text-success" : "text-destructive")}>
                {q.delta >= 0 ? <ArrowUpRight className="size-3" /> : <ArrowDownRight className="size-3" />}
                {Math.abs(q.delta)} vs last wave
              </span>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {q.scale === "PGE" && <PGEBars b={q.breakdown} />}
        {q.scale === "YN" && <YNBars b={q.breakdown} />}
        {q.scale === "OPEN" && (
          <p className="text-sm text-muted-foreground">
            Open-ended replies are listed in the <b>Responses</b> tab. {q.samples} voice replies in this wave.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function PGEBars({ b }: { b: { poor: number; good: number; excellent: number } }) {
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-4 text-xs text-muted-foreground">
        <LegendDot color="bg-success" label="Excellent" />
        <LegendDot color="bg-warning" label="Good" />
        <LegendDot color="bg-destructive" label="Poor" />
      </div>
      <Row label="Excellent" pct={b.excellent} tone="success" />
      <Row label="Good" pct={b.good} tone="warning" />
      <Row label="Poor" pct={b.poor} tone="destructive" />
      <div className="flex h-3 overflow-hidden rounded-full bg-border">
        <div className="bg-success" style={{ width: `${b.excellent}%` }} title={`Excellent ${b.excellent}%`} />
        <div className="bg-warning" style={{ width: `${b.good}%` }} title={`Good ${b.good}%`} />
        <div className="bg-destructive" style={{ width: `${b.poor}%` }} title={`Poor ${b.poor}%`} />
      </div>
    </div>
  );
}

function YNBars({ b }: { b: { yes: number; no: number } }) {
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-4 text-xs text-muted-foreground">
        <LegendDot color="bg-success" label="Yes" />
        <LegendDot color="bg-destructive" label="No" />
      </div>
      <Row label="Yes" pct={b.yes} tone="success" icon={<ThumbsUp className="size-3" />} />
      <Row label="No" pct={b.no} tone="destructive" icon={<ThumbsDown className="size-3" />} />
      <div className="flex h-3 overflow-hidden rounded-full bg-border">
        <div className="bg-success" style={{ width: `${b.yes}%` }} title={`Yes ${b.yes}%`} />
        <div className="bg-destructive" style={{ width: `${b.no}%` }} title={`No ${b.no}%`} />
      </div>
    </div>
  );
}

function Row({ label, pct, tone, icon }: { label: string; pct: number; tone: "success" | "warning" | "destructive"; icon?: React.ReactNode }) {
  return (
    <div className="flex items-center gap-3">
      <div className="flex w-24 items-center gap-1.5 text-sm font-medium">
        {icon}{label}
      </div>
      <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-border">
        <div className={cn("h-full rounded-full transition-all", tone === "success" && "bg-success", tone === "warning" && "bg-warning", tone === "destructive" && "bg-destructive")} style={{ width: `${pct}%` }} />
      </div>
      <span className="w-10 text-right text-xs tabular-nums text-muted-foreground">{pct}%</span>
    </div>
  );
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className={cn("size-2 rounded-full", color)} />
      {label}
    </span>
  );
}

function VoiceCard({ v }: { v: VoiceComment }) {
  const isLow = v.tone === "destructive";
  return (
    <div className={cn("rounded-xl border bg-background p-4 transition-shadow hover:shadow-md", isLow ? "border-destructive/30" : "border-success/30")}>
      <div className="mb-3 flex items-center justify-between">
        <span className={cn("rounded-full px-2 py-0.5 text-[11px] font-medium", isLow ? "bg-destructive/10 text-destructive" : "bg-success/10 text-success")}>
          {isLow ? "Unhappy" : "Excellent"}
        </span>
        <Badge variant="outline" className="text-[10px]">{v.reason}</Badge>
      </div>
      <p className="mb-2 text-[11px] uppercase tracking-wider text-muted-foreground">Transcript · {v.question}</p>
      <p className="text-sm leading-relaxed">"{v.transcript}"</p>
    </div>
  );
}

function Theme({ label, value, sentiment }: { label: string; value: number; sentiment: string }) {
  const tone = sentiment === "positive" ? "bg-success" : sentiment === "negative" ? "bg-destructive" : "bg-warning";
  return (
    <div className="rounded-lg border border-border bg-background p-3">
      <div className="flex justify-between text-sm">
        <span className="font-medium">{label}</span>
        <span className="tabular-nums text-muted-foreground">{value}%</span>
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-border">
        <div className={cn("h-full rounded-full", tone)} style={{ width: `${value * 2}%` }} />
      </div>
      <p className="mt-1 text-xs capitalize text-muted-foreground">{sentiment} sentiment</p>
    </div>
  );
}

function Action({ text, impact }: { text: string; impact: string }) {
  return (
    <div className="rounded-lg border border-border bg-background p-3">
      <p>{text}</p>
      <p className="mt-1 text-xs text-success">{impact} impact</p>
    </div>
  );
}

function Response({ quote, rating, theme }: { quote: string; rating: string; theme: string }) {
  const tone = rating === "excellent" ? "success" : rating === "good" ? "warning" : "destructive";
  return (
    <div className="rounded-xl border border-border bg-background p-4">
      <div className="mb-3 flex justify-between text-xs">
        <span className={cn(
          "rounded-full px-2 py-0.5 font-medium capitalize",
          tone === "success" && "bg-success/10 text-success",
          tone === "warning" && "bg-warning/10 text-warning",
          tone === "destructive" && "bg-destructive/10 text-destructive",
        )}>{rating}</span>
        <span className="text-muted-foreground">{theme}</span>
      </div>
      <p className="text-sm leading-relaxed">"{quote}"</p>
    </div>
  );
}

// ---------- Per-respondent components ----------
function Avatar({ name, sentiment }: { name: string; sentiment: "happy" | "neutral" | "unhappy" }) {
  const initials = name.split(" ").map((n) => n[0]).slice(0, 2).join("");
  const ring =
    sentiment === "unhappy" ? "ring-destructive/40 bg-destructive/10 text-destructive"
    : sentiment === "neutral" ? "ring-warning/40 bg-warning/10 text-warning"
    : "ring-success/40 bg-success/10 text-success";
  return (
    <span className={cn("flex size-8 items-center justify-center rounded-full text-xs font-semibold ring-2", ring)}>
      {initials}
    </span>
  );
}

function SentimentBadge({ sentiment, flagged }: { sentiment: "happy" | "neutral" | "unhappy"; flagged: boolean }) {
  if (sentiment === "unhappy") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-destructive/10 px-2 py-0.5 text-xs font-medium text-destructive">
        {flagged && <AlertTriangle className="size-3" />} Unhappy
      </span>
    );
  }
  if (sentiment === "neutral") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-warning/10 px-2 py-0.5 text-xs font-medium text-warning">
        Neutral
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-success/10 px-2 py-0.5 text-xs font-medium text-success">
      Happy
    </span>
  );
}

function AnswerDot({ a }: { a: { type: "Rating"; value: "poor" | "good" | "excellent" } | { type: "Yes/No"; value: "yes" | "no" } }) {
  let color = "bg-muted";
  let title = "";
  if (a.type === "Rating") {
    color = a.value === "excellent" ? "bg-success" : a.value === "good" ? "bg-warning" : "bg-destructive";
    title = a.value;
  } else {
    color = a.value === "yes" ? "bg-success" : "bg-destructive";
    title = a.value;
  }
  return <span className={cn("size-2.5 rounded-sm", color)} title={title} />;
}

function FilterPill({ children, active, onClick, tone }: { children: React.ReactNode; active: boolean; onClick: () => void; tone?: "destructive" | "warning" | "success" }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1 rounded px-2.5 py-1 text-xs font-medium transition-colors",
        active
          ? tone === "destructive" ? "bg-destructive text-destructive-foreground"
          : tone === "warning" ? "bg-warning text-warning-foreground"
          : tone === "success" ? "bg-success text-success-foreground"
          : "bg-primary text-primary-foreground"
          : "text-muted-foreground hover:bg-muted",
      )}
    >
      {children}
    </button>
  );
}

function RespondentSheet({
  open, onOpenChange, respondent, questions,
}: { open: boolean; onOpenChange: (v: boolean) => void; respondent: Respondent | null; questions: Question[] }) {
  if (!respondent) return null;
  const qmap = Object.fromEntries(questions.map((q) => [q.id, q]));
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-xl">
        <SheetHeader className="space-y-3">
          <button onClick={() => onOpenChange(false)} className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
            <ArrowLeft className="size-3" /> Back to list
          </button>
          <div className="flex items-start gap-3">
            <Avatar name={respondent.name} sentiment={respondent.sentiment} />
            <div className="flex-1">
              <SheetTitle className="text-lg">{respondent.name}</SheetTitle>
              <SheetDescription className="flex items-center gap-2">
                <span className="tabular-nums">{respondent.mobile}</span>
                <span>·</span>
                <span>completed {respondent.completedAt}</span>
              </SheetDescription>
            </div>
            <SentimentBadge sentiment={respondent.sentiment} flagged={respondent.flagged} />
          </div>

          {respondent.sentiment === "unhappy" && (
            <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-xs">
              <p className="font-medium text-destructive">Recommended: call within 24h</p>
              <p className="mt-0.5 text-muted-foreground">This customer answered "no" to recommending you and rated multiple questions poor.</p>
            </div>
          )}
        </SheetHeader>

        <div className="mt-6 space-y-3">
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Full survey answers</p>
          {respondent.answers.map((a, i) => {
            const q = qmap[a.qid];
            if (!q) return null;
            return (
              <div key={i} className="rounded-lg border border-border bg-background p-3">
                <p className="text-sm font-medium">{q.title}</p>
                <div className="mt-2">
                  {a.type === "Rating" && <RatingChip value={a.value} />}
                  {a.type === "Yes/No" && <YNChip value={a.value} />}
                  {a.type === "Voice" && (
                    <p className="rounded-md bg-muted/50 p-2 text-sm italic leading-relaxed">"{a.value}"</p>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </SheetContent>
    </Sheet>
  );
}

function RatingChip({ value }: { value: "poor" | "good" | "excellent" }) {
  const tone = value === "excellent" ? "success" : value === "good" ? "warning" : "destructive";
  const Icon = value === "excellent" ? CheckCircle2 : value === "poor" ? XCircle : Smile;
  return (
    <span className={cn(
      "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium capitalize",
      tone === "success" && "bg-success/10 text-success",
      tone === "warning" && "bg-warning/10 text-warning",
      tone === "destructive" && "bg-destructive/10 text-destructive",
    )}>
      <Icon className="size-3.5" />
      {value}
    </span>
  );
}

function YNChip({ value }: { value: "yes" | "no" }) {
  const yes = value === "yes";
  return (
    <span className={cn(
      "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium uppercase",
      yes ? "bg-success/10 text-success" : "bg-destructive/10 text-destructive",
    )}>
      {yes ? <ThumbsUp className="size-3.5" /> : <ThumbsDown className="size-3.5" />}
      {value}
    </span>
  );
}
