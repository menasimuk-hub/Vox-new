import * as React from "react";
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
  ArrowUpDown,
  Download,
  Filter,
  MapPin,
  MessageSquareText,
  Mic,
  Phone,
  QrCode,
  Search,
  Smile,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  Users,
} from "lucide-react";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { downloadAuthenticatedFile } from "@/lib/api";
import type {
  FeedbackAggregateBlock,
  FeedbackOpenComment,
  FeedbackRespondent,
  FeedbackResultsInsightsPayload,
  FeedbackResultsPayload,
} from "@/lib/queries";
import { cn } from "@/lib/utils";

type SortKey = "unhappy" | "date" | "sentiment" | "phone";
type FilterKey = "all" | "unhappy" | "neutral" | "happy" | "flagged";

type Props = {
  data: FeedbackResultsPayload | undefined;
  insights: FeedbackResultsInsightsPayload | undefined;
  isLoading: boolean;
  insightsLoading: boolean;
  isError: boolean;
  error: Error | null;
  locationId: string;
  surveyTypeId: string;
  onLocationChange: (id: string) => void;
  onSurveyTypeChange: (id: string) => void;
  headerActions?: React.ReactNode;
};

(block: FeedbackAggregateBlock) {
  const breakdown = block.breakdown || [];
  const poor = breakdown.find((b) => b.key === "poor")?.pct ?? 0;
  const good = breakdown.find((b) => b.key === "good")?.pct ?? 0;
  const excellent = breakdown.find((b) => b.key === "excellent")?.pct ?? 0;
  const yes = breakdown.find((b) => b.key === "yes")?.pct ?? 0;
  const no = breakdown.find((b) => b.key === "no")?.pct ?? 0;
  const role = String(block.step_role || "").toLowerCase();
  if (yes || no || role.includes("yes")) {
    return { type: "YN" as const, title: block.question || "", responses: block.total || 0, breakdown: { yes, no } };
  }
  if (excellent || good || poor || role === "rating") {
    return { type: "PGE" as const, title: block.question || "", responses: block.total || 0, breakdown: { poor, good, excellent } };
  }
  return { type: "OPEN" as const, title: block.question || "", responses: block.total || 0, samples: block.total || 0 };
}

export function FeedbackResultsView({
  data,
  insights,
  isLoading,
  insightsLoading,
  isError,
  error,
  locationId,
  surveyTypeId,
  onLocationChange,
  onSurveyTypeChange,
  headerActions,
}: Props) {
  const [tab, setTab] = React.useState("overview");
  const [search, setSearch] = React.useState("");
  const [filter, setFilter] = React.useState<FilterKey>("all");
  const [sortKey, setSortKey] = React.useState<SortKey>("unhappy");
  const [openId, setOpenId] = React.useState<string | null>(null);

  const summary = data?.summary;
  const aggregates = data?.aggregates || [];
  const respondents = data?.respondents || [];
  const weeklyTrend = data?.weekly_trend || [];
  const openComments = insights?.open_comments?.length ? insights.open_comments : data?.open_comments || [];
  const ai = insights?.ai;
  const voiceComments = openComments.filter((c) => c.answer_source === "voice");
  const textComments = openComments.filter((c) => c.answer_source !== "voice");

  const sentimentDistribution = React.useMemo(() => {
    const counts = summary?.sentiment_counts || { unhappy: 0, neutral: 0, happy: 0 };
    return [
      { name: "Unhappy", value: counts.unhappy || 0, color: "#ef4444" },
      { name: "Neutral", value: counts.neutral || 0, color: "#f59e0b" },
      { name: "Happy", value: counts.happy || 0, color: "#22c55e" },
    ].filter((d) => d.value > 0);
  }, [summary?.sentiment_counts]);

  const filteredRespondents = React.useMemo(() => {
    let rows = [...respondents];
    const q = search.trim().toLowerCase();
    if (q) {
      rows = rows.filter(
        (r) =>
          String(r.phone || "").toLowerCase().includes(q) ||
          String(r.quote || "").toLowerCase().includes(q) ||
          String(r.location_name || "").toLowerCase().includes(q),
      );
    }
    if (filter === "unhappy") rows = rows.filter((r) => r.sentiment_label === "unhappy");
    if (filter === "happy") rows = rows.filter((r) => r.sentiment_label === "happy");
    if (filter === "neutral") rows = rows.filter((r) => r.sentiment_label === "neutral");
    if (filter === "flagged") rows = rows.filter((r) => r.flagged || r.is_unhappy);

    rows.sort((a, b) => {
      if (sortKey === "unhappy") {
        const af = a.is_unhappy ? 1 : 0;
        const bf = b.is_unhappy ? 1 : 0;
        if (bf !== af) return bf - af;
      }
      if (sortKey === "sentiment") {
        const order = { unhappy: 0, neutral: 1, happy: 2 };
        const av = order[(a.sentiment_label as keyof typeof order) || "neutral"] ?? 1;
        const bv = order[(b.sentiment_label as keyof typeof order) || "neutral"] ?? 1;
        if (av !== bv) return av - bv;
      }
      if (sortKey === "phone") return String(a.phone || "").localeCompare(String(b.phone || ""));
      const ad = a.completed_at ? new Date(a.completed_at).getTime() : 0;
      const bd = b.completed_at ? new Date(b.completed_at).getTime() : 0;
      return bd - ad;
    });
    return rows;
  }, [respondents, search, filter, sortKey]);

  const openRespondent = respondents.find((r) => r.id === openId) || null;

  async function handleExport(kind: "csv" | "pdf") {
    const params = new URLSearchParams();
    if (locationId !== "all") params.set("location_id", locationId);
    if (surveyTypeId !== "all") params.set("survey_type_id", surveyTypeId);
    const qs = params.toString();
    const path = `/customer-feedback/results/export.${kind}${qs ? `?${qs}` : ""}`;
    try {
      await downloadAuthenticatedFile(path, `feedback-results.${kind}`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Export failed");
    }
  }

  if (isLoading) {
    return (
      <div className="flex w-full flex-col gap-6">
        <Skeleton className="h-24 rounded-xl" />
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-28 rounded-xl" />
          ))}
        </div>
        <Skeleton className="h-96 rounded-xl" />
      </div>
    );
  }

  if (isError) {
    return (
      <Card>
        <CardContent className="p-8 text-center text-sm text-destructive">
          Could not load feedback results
          {error instanceof Error ? `: ${error.message}` : ""}.
        </CardContent>
      </Card>
    );
  }

  const questions = aggregates.map(aggregateToQuestion);
  const unhappyCount = summary?.unhappy_count ?? 0;
  const responseRate =
    summary?.completion_rate_pct ??
    (summary?.total_scans
      ? Math.min(100, Math.round(((summary.completed_sessions || 0) / summary.total_scans) * 100))
      : null);

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="Customer feedback"
        title="Feedback results"
        description="Responses from QR WhatsApp surveys — filter by location and topic."
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="outline" size="sm" className="gap-1.5" onClick={() => void handleExport("csv")}>
              <Download className="size-4" /> Export CSV
            </Button>
            <Button variant="outline" size="sm" className="gap-1.5" onClick={() => void handleExport("pdf")}>
              <Download className="size-4" /> Export PDF
            </Button>
            {headerActions}
          </div>
        }
      />

      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-[200px] space-y-1">
          <label className="text-xs font-medium text-muted-foreground">Location</label>
          <Select value={locationId} onValueChange={onLocationChange}>
            <SelectTrigger>
              <SelectValue placeholder="All locations" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All locations</SelectItem>
              {(data?.locations || []).map((loc) => (
                <SelectItem key={loc.id} value={loc.id}>
                  {loc.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {(data?.survey_types?.length || 0) > 1 ? (
          <div className="min-w-[200px] space-y-1">
            <label className="text-xs font-medium text-muted-foreground">Topic</label>
            <Select value={surveyTypeId} onValueChange={onSurveyTypeChange}>
              <SelectTrigger>
                <SelectValue placeholder="All topics" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All topics</SelectItem>
                {(data?.survey_types || []).map((st) => (
                  <SelectItem key={st.id} value={st.id}>
                    {st.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        ) : null}
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="flex h-auto flex-wrap gap-1">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="questions">Questions</TabsTrigger>
          <TabsTrigger value="responses">Responses</TabsTrigger>
          <TabsTrigger value="details">More details</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="mt-4 space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Kpi
              title="Satisfaction"
              value={summary?.satisfaction_pct != null ? `${summary.satisfaction_pct}%` : "—"}
              sub="good + excellent"
              icon={<Smile className="size-4" />}
            />
            <Kpi
              title="Would recommend"
              value={summary?.recommend_pct != null ? `${summary.recommend_pct}%` : "—"}
              sub="yes on recommend questions"
              icon={<ThumbsUp className="size-4" />}
            />
            <Kpi
              title="Response rate"
              value={responseRate != null ? `${responseRate}%` : "—"}
              sub={`${summary?.completed_sessions ?? 0} of ${summary?.total_scans ?? 0} scans`}
              icon={<Users className="size-4" />}
            />
            <Kpi
              title="Unhappy customers"
              value={String(unhappyCount)}
              sub="needs follow up"
              icon={<AlertTriangle className="size-4" />}
              tone="destructive"
            />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Satisfaction trend</CardTitle>
              </CardHeader>
              <CardContent className="h-[280px]">
                {weeklyTrend.length ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={weeklyTrend}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                      <XAxis dataKey="week" stroke="#9ca3af" fontSize={11} />
                      <YAxis stroke="#9ca3af" fontSize={11} domain={[0, 100]} />
                      <Tooltip />
                      <Area type="monotone" dataKey="satisfaction" stroke="#6366f1" fill="#6366f133" name="Satisfaction %" />
                    </AreaChart>
                  </ResponsiveContainer>
                ) : (
                  <p className="text-sm text-muted-foreground">Not enough data yet.</p>
                )}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Sentiment split</CardTitle>
              </CardHeader>
              <CardContent className="h-[280px]">
                {sentimentDistribution.length ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie data={sentimentDistribution} dataKey="value" innerRadius={60} outerRadius={95} paddingAngle={3}>
                        {sentimentDistribution.map((d) => (
                          <Cell key={d.name} fill={d.color} />
                        ))}
                      </Pie>
                      <Tooltip />
                      <Legend />
                    </PieChart>
                  </ResponsiveContainer>
                ) : (
                  <p className="text-sm text-muted-foreground">No completed sessions yet.</p>
                )}
              </CardContent>
            </Card>
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Response volume / week</CardTitle>
              </CardHeader>
              <CardContent className="h-[200px]">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={weeklyTrend}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="week" fontSize={11} />
                    <YAxis fontSize={11} />
                    <Tooltip />
                    <Bar dataKey="responses" fill="#6366f1" radius={[6, 6, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle className="text-base">AI themes</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {insightsLoading ? (
                  <Skeleton className="h-20" />
                ) : (ai?.themes || []).length ? (
                  ai!.themes!.map((t) => <Theme key={t.label} label={t.label} value={t.value} sentiment={t.sentiment} />)
                ) : (
                  <p className="text-sm text-muted-foreground">Complete at least 3 surveys to generate themes.</p>
                )}
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="flex flex-row items-center gap-2">
                <Sparkles className="size-4 text-primary" />
                <CardTitle className="text-base">AI recommended actions</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                {insightsLoading ? (
                  <Skeleton className="h-20" />
                ) : (ai?.recommendations || []).length ? (
                  ai!.recommendations!.map((r, i) => (
                    <Action key={i} text={r.text} title={r.title} impact={r.impact || "Medium"} />
                  ))
                ) : (
                  <p className="text-muted-foreground">Recommendations appear after enough responses.</p>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="questions" className="mt-4 space-y-4">
          <div className="rounded-xl border border-border bg-card p-3 text-sm text-muted-foreground">
            Each question uses its own scale — <b>Poor / Good / Excellent</b> or <b>Yes / No</b>.
          </div>
          {questions.length ? (
            questions.map((q, i) => <QuestionBlock key={i} q={q} />)
          ) : (
            <Card>
              <CardContent className="p-8 text-center text-sm text-muted-foreground">No question data yet.</CardContent>
            </Card>
          )}
        </TabsContent>

        <TabsContent value="responses" className="mt-4 space-y-6">
          <Card>
            <CardHeader>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <CardTitle className="flex items-center gap-2 text-base">
                    <Mic className="size-4 text-primary" />
                    Voice comments
                  </CardTitle>
                  <p className="text-xs text-muted-foreground">Auto-transcribed via DeepInfra when visitors send voice notes.</p>
                </div>
                <Badge variant="secondary">{voiceComments.length} voice</Badge>
              </div>
            </CardHeader>
            <CardContent className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {voiceComments.length ? (
                voiceComments.map((v) => <VoiceCard key={v.id} v={v} />)
              ) : (
                <p className="text-sm text-muted-foreground md:col-span-2">No voice replies yet.</p>
              )}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Text responses</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              {textComments.length ? (
                textComments.map((r, i) => <TextComment key={r.id || i} comment={r} />)
              ) : (
                <p className="text-sm text-muted-foreground">No open text comments yet.</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="details" className="mt-4 space-y-4">
          {unhappyCount > 0 ? (
            <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-4">
              <div className="flex flex-wrap items-start gap-3">
                <AlertTriangle className="mt-0.5 size-5 text-destructive" />
                <div className="flex-1">
                  <p className="text-sm font-medium">
                    {unhappyCount} customer{unhappyCount === 1 ? "" : "s"} flagged as unhappy
                  </p>
                  <p className="text-xs text-muted-foreground">Call them within 24 hours to recover the relationship.</p>
                </div>
                <Button size="sm" variant="destructive" className="gap-1.5" onClick={() => setFilter("flagged")}>
                  <Phone className="size-3.5" /> View {unhappyCount}
                </Button>
              </div>
            </div>
          ) : null}

          <Card>
            <CardHeader>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <CardTitle className="text-base">
                    All respondents · {filteredRespondents.length} of {respondents.length}
                  </CardTitle>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <div className="relative">
                    <Search className="absolute left-2 top-2.5 size-4 text-muted-foreground" />
                    <Input
                      placeholder="Search phone or quote"
                      className="h-9 w-48 pl-8"
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                    />
                  </div>
                  <Select value={filter} onValueChange={(v) => setFilter(v as FilterKey)}>
                    <SelectTrigger className="h-9 w-36">
                      <Filter className="mr-1 size-3.5" />
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All</SelectItem>
                      <SelectItem value="flagged">Flagged</SelectItem>
                      <SelectItem value="unhappy">Unhappy</SelectItem>
                      <SelectItem value="neutral">Neutral</SelectItem>
                      <SelectItem value="happy">Happy</SelectItem>
                    </SelectContent>
                  </Select>
                  <Select value={sortKey} onValueChange={(v) => setSortKey(v as SortKey)}>
                    <SelectTrigger className="h-9 w-40">
                      <ArrowUpDown className="mr-1 size-3.5" />
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="unhappy">Unhappy first</SelectItem>
                      <SelectItem value="date">Newest first</SelectItem>
                      <SelectItem value="sentiment">By sentiment</SelectItem>
                      <SelectItem value="phone">By phone</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </CardHeader>
            <CardContent className="px-0">
              <div className="divide-y divide-border">
                {filteredRespondents.map((r) => (
                  <button
                    key={r.id}
                    type="button"
                    onClick={() => setOpenId(r.id || null)}
                    className={cn(
                      "grid w-full grid-cols-12 items-center gap-3 px-4 py-3 text-left text-sm transition-colors hover:bg-muted/50",
                      r.flagged && "bg-destructive/[0.03]",
                    )}
                  >
                    <div className="col-span-4">
                      <p className="font-medium">{r.phone || "WhatsApp visitor"}</p>
                      <p className="text-xs text-muted-foreground">
                        {r.completed_at ? new Date(r.completed_at).toLocaleString("en-GB") : "—"}
                      </p>
                    </div>
                    <div className="col-span-3 text-muted-foreground">{r.location_name || "—"}</div>
                    <div className="col-span-2">
                      <SentimentBadge sentiment={r.sentiment_label || "neutral"} flagged={!!r.flagged} />
                    </div>
                    <div className="col-span-2 truncate text-xs text-muted-foreground">{r.quote || "—"}</div>
                    <div className="col-span-1 text-right text-xs font-medium text-primary">Open →</div>
                  </button>
                ))}
                {!filteredRespondents.length ? (
                  <div className="p-8 text-center text-sm text-muted-foreground">No respondents match these filters.</div>
                ) : null}
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <RespondentSheet open={!!openRespondent} onOpenChange={(v) => !v && setOpenId(null)} respondent={openRespondent} />
    </div>
  );
}

function Kpi({
  title,
  value,
  sub,
  icon,
  tone = "primary",
}: {
  title: string;
  value: string;
  sub: string;
  icon: React.ReactNode;
  tone?: "primary" | "destructive";
}) {
  return (
    <Card>
      <CardContent className="p-4">
        <div
          className={cn(
            "mb-3 inline-flex rounded-lg p-2",
            tone === "destructive" ? "bg-destructive/10 text-destructive" : "bg-primary/10 text-primary",
          )}
        >
          {icon}
        </div>
        <p className="text-xs uppercase tracking-wider text-muted-foreground">{title}</p>
        <p className="text-3xl font-semibold tracking-tight">{value}</p>
        <p className="text-xs text-muted-foreground">{sub}</p>
      </CardContent>
    </Card>
  );
}

function Theme({ label, value, sentiment }: { label: string; value: number; sentiment: string }) {
  return (
    <div>
      <div className="mb-1 flex justify-between text-sm">
        <span>{label}</span>
        <span className="text-muted-foreground">{value}%</span>
      </div>
      <Progress value={value} className="h-2" />
      <p className="mt-0.5 text-[10px] capitalize text-muted-foreground">{sentiment}</p>
    </div>
  );
}

function Action({ title, text, impact }: { title?: string; text: string; impact: string }) {
  return (
    <div className="rounded-lg border border-border p-3">
      {title ? <p className="font-medium">{title}</p> : null}
      <p className="text-muted-foreground">{text}</p>
      <Badge variant="outline" className="mt-2 text-[10px]">
        {impact} impact
      </Badge>
    </div>
  );
}

type Question =
  | { type: "PGE"; title: string; responses: number; breakdown: { poor: number; good: number; excellent: number } }
  | { type: "YN"; title: string; responses: number; breakdown: { yes: number; no: number } }
  | { type: "OPEN"; title: string; responses: number; samples: number };

function QuestionBlock({ q }: { q: Question }) {
  const avgLabel =
    q.type === "PGE"
      ? `${q.breakdown.excellent}% excellent`
      : q.type === "YN"
        ? `${q.breakdown.yes}% yes`
        : `${q.samples} replies`;

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <CardTitle className="text-base">{q.title}</CardTitle>
            <p className="mt-1 text-xs text-muted-foreground">{q.responses.toLocaleString()} responses</p>
          </div>
          <p className="text-2xl font-semibold">{avgLabel}</p>
        </div>
      </CardHeader>
      <CardContent>
        {q.type === "PGE" ? <PGEBars b={q.breakdown} /> : null}
        {q.type === "YN" ? <YNBars b={q.breakdown} /> : null}
        {q.type === "OPEN" ? (
          <p className="text-sm text-muted-foreground">See the Responses tab for open replies.</p>
        ) : null}
      </CardContent>
    </Card>
  );
}

function PGEBars({ b }: { b: { poor: number; good: number; excellent: number } }) {
  return (
    <div className="space-y-3">
      <BarRow label="Excellent" pct={b.excellent} tone="bg-success" />
      <BarRow label="Good" pct={b.good} tone="bg-warning" />
      <BarRow label="Poor" pct={b.poor} tone="bg-destructive" />
    </div>
  );
}

function YNBars({ b }: { b: { yes: number; no: number } }) {
  return (
    <div className="space-y-3">
      <BarRow label="Yes" pct={b.yes} tone="bg-success" icon={<ThumbsUp className="size-3" />} />
      <BarRow label="No" pct={b.no} tone="bg-destructive" icon={<ThumbsDown className="size-3" />} />
    </div>
  );
}

function BarRow({
  label,
  pct,
  tone,
  icon,
}: {
  label: string;
  pct: number;
  tone: string;
  icon?: React.ReactNode;
}) {
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-xs">
        <span className="flex items-center gap-1">
          {icon}
          {label}
        </span>
        <span>{pct}%</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-border">
        <div className={cn("h-full rounded-full", tone)} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function VoiceCard({ v }: { v: FeedbackOpenComment }) {
  return (
    <div className="rounded-xl border border-border p-3 text-sm">
      <div className="mb-2 flex items-center gap-2 text-xs text-muted-foreground">
        <Mic className="size-3.5" />
        Voice · {v.created_at ? new Date(v.created_at).toLocaleDateString("en-GB") : "—"}
      </div>
      <p>{v.text}</p>
    </div>
  );
}

function TextComment({ comment }: { comment: FeedbackOpenComment }) {
  return (
    <div className="rounded-xl border border-border p-3 text-sm">
      {comment.theme ? (
        <Badge variant="secondary" className="mb-2 text-[10px]">
          {comment.theme}
        </Badge>
      ) : null}
      <p>{comment.text}</p>
    </div>
  );
}

function SentimentBadge({ sentiment, flagged }: { sentiment: string; flagged: boolean }) {
  const tone =
    sentiment === "happy" ? "bg-success/15 text-success" : sentiment === "unhappy" ? "bg-destructive/15 text-destructive" : "bg-muted text-muted-foreground";
  return (
    <span className={cn("inline-flex rounded-full px-2 py-0.5 text-xs font-medium capitalize", tone)}>
      {flagged ? "Flagged · " : ""}
      {sentiment}
    </span>
  );
}

function RespondentSheet({
  open,
  onOpenChange,
  respondent,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  respondent: FeedbackRespondent | null;
}) {
  if (!respondent) return null;
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="overflow-y-auto sm:max-w-md">
        <SheetHeader>
          <SheetTitle>{respondent.phone || "WhatsApp visitor"}</SheetTitle>
          <SheetDescription>
            {respondent.location_name} ·{" "}
            {respondent.completed_at ? new Date(respondent.completed_at).toLocaleString("en-GB") : "—"}
          </SheetDescription>
        </SheetHeader>
        <div className="mt-4 space-y-4">
          <div className="flex items-center gap-2">
            <Phone className="size-4 text-primary" />
            <a href={`tel:${respondent.phone}`} className="font-medium text-primary">
              {respondent.phone}
            </a>
          </div>
          {respondent.quote ? (
            <blockquote className="border-l-2 border-primary pl-3 text-sm italic text-muted-foreground">
              {respondent.quote}
            </blockquote>
          ) : null}
          <div className="space-y-3">
            {(respondent.answers || []).map((a, i) => (
              <div key={i} className="rounded-lg border border-border p-3 text-sm">
                <p className="text-xs text-muted-foreground">{a.question}</p>
                <p className="font-medium">{a.answer}</p>
                {a.answer_source === "voice" ? (
                  <Badge variant="outline" className="mt-1 text-[10px]">
                    Voice
                  </Badge>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}