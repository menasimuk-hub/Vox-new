import { createFileRoute } from "@tanstack/react-router";
import * as React from "react";
import {
  AlertCircle,
  ArrowLeft,
  ArrowUpDown,
  ChartBar as BarChart3,
  CircleCheck as CheckCircle2,
  Circle as HelpCircle,
  Clock,
  Circle as XCircle,
  Download,
  ListFilter as Filter,
  MessageCircle,
  MessageSquareText,
  Mic,
  PanelRightOpen,
  Phone,
  Search,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  TrendingUp,
  TriangleAlert as AlertTriangle,
  Users,
} from "lucide-react";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { SurveyResultsRespondentsTab } from "@/components/survey-results/survey-results-respondents-tab";
import { SurveyIdentityHeader } from "@/components/survey-identity-header";
import { StatusBadge } from "@/components/status-badge";
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
import { logLaunchFlow } from "@/lib/launch-flow-log";
import { orderToCampaign } from "@/lib/mappers/orders";
import { useServiceOrders, useSurveyResults } from "@/lib/queries";
import { cn } from "@/lib/utils";

type BreakdownGroup = { label: string; key: string; count: number; pct: number };
type AggregateBlock = {
  question: string;
  total: number;
  visualization?: string;
  breakdown?: BreakdownGroup[];
  responses: Array<{ answer: string; count: number }>;
  step_role?: string;
};
type WaAnswer = {
  question?: string;
  answer?: string;
  answer_text?: string;
  answer_source?: string;
  transcription_status?: string;
};
type OpenFeedbackRow = {
  question?: string;
  transcript?: string | null;
  text?: string | null;
  translated_text?: string | null;
  original_text?: string | null;
  answer_source?: string;
};
type ExtractedAnswer = { question?: string; answer?: string };
type Respondent = {
  id?: string;
  name?: string;
  phone?: string | null;
  email?: string | null;
  quote?: string | null;
  short_summary?: string | null;
  recommend_score?: number | string | null;
  satisfaction_score?: number | string | null;
  rating_label?: string | null;
  theme?: string | null;
  sentiment_label?: string | null;
  status_label?: string;
  completed_at?: string | null;
  duration_label?: string | null;
  needs_follow_up?: boolean;
  is_unhappy?: boolean;
  primary_response_type?: string | null;
  wa_answers?: WaAnswer[];
  extracted_answers?: ExtractedAnswer[];
  open_feedback?: OpenFeedbackRow[];
  final_additional_feedback?: string | null;
};
type Recommendation = { title?: string; text?: string; impact?: string; source?: string };
type TrendPoint = { week: string; csat_pct?: number | null; completed_count?: number };

type OptionRow = { label: string; count: number; pct: number; tone: string };
type DetailQuestion = {
  id: string;
  title: string;
  type: "Rating" | "Yes / No" | "Open text" | "Choice";
  options: OptionRow[];
  totalResponses: number;
  avgTime: string;
};

type ResponseCardData = {
  id: string;
  date: string;
  rating: string;
  answers: { question: string; answer: string }[];
  theme: string;
  quote: string;
  duration: string;
  isUnhappy: boolean;
  responseType: "text" | "voice" | null;
};

export const Route = createFileRoute("/_app/surveys/results")({
  validateSearch: (search: Record<string, unknown>) => ({
    orderId: typeof search.orderId === "string" ? search.orderId : undefined,
  }),
  head: () => ({ meta: [{ title: "Survey results — VoxBulk" }] }),
  component: SurveyResults,
});

function toneForAnswer(label: string): string {
  const lower = label.toLowerCase();
  const num = parseInt(label, 10);
  if (lower === "yes" || lower.includes("excellent") || num >= 9) return "success";
  if (lower === "no" || lower.includes("poor") || (Number.isFinite(num) && num <= 6)) return "destructive";
  if (lower.includes("good") || num === 7 || num === 8) return "info";
  return "warning";
}

function inferQuestionType(block: AggregateBlock): DetailQuestion["type"] {
  const role = String(block.step_role || "").toLowerCase();
  const answers = block.responses.map((r) => String(r.answer || "").trim().toLowerCase());
  if (role.includes("yes_no") || role === "true_false") return "Yes / No";
  if (answers.length > 0 && answers.every((a) => a === "yes" || a === "no")) return "Yes / No";
  if (block.step_role === "final_feedback_text" || block.step_role === "reason") return "Open text";
  if (block.visualization === "sentiment_breakdown") return "Rating";
  if (block.responses.length > 0 && block.responses.every((r) => /^\d+$/.test(String(r.answer || "").trim()))) {
    return "Rating";
  }
  if (block.responses.length >= 4) return "Open text";
  return "Choice";
}

function buildYesNoOptions(
  responses: Array<{ answer: string; count: number }>,
  total: number,
): OptionRow[] {
  const counts = new Map<string, number>();
  for (const row of responses) {
    const key = String(row.answer || "").trim().toLowerCase();
    if (key === "yes" || key === "no") counts.set(key, (counts.get(key) || 0) + row.count);
  }
  const yes = counts.get("yes") || 0;
  const no = counts.get("no") || 0;
  const answered = yes + no;
  const base = answered || total || 1;
  return [
    { label: "Yes", count: yes, pct: answered ? Math.round((yes / base) * 100) : 0, tone: "success" },
    { label: "No", count: no, pct: answered ? Math.round((no / base) * 100) : 0, tone: "destructive" },
  ];
}

function buildRatingOptions(block: AggregateBlock): OptionRow[] {
  const total = block.total || 0;
  const ratingLabels = [
    { key: "positive", label: "Excellent", tone: "success" },
    { key: "neutral", label: "Expected", tone: "info" },
    { key: "negative", label: "Poor", tone: "destructive" },
  ] as const;

  if (block.visualization === "sentiment_breakdown" && block.breakdown?.length) {
    const byKey = new Map(block.breakdown.map((g) => [g.key, g]));
    const counts = ratingLabels.map(({ key }) => byKey.get(key)?.count ?? 0);
    const answered = counts.reduce((sum, n) => sum + n, 0);
    const base = answered || total || 1;
    return ratingLabels.map(({ key, label, tone }, idx) => ({
      label,
      count: counts[idx],
      pct: answered ? Math.round((counts[idx] / base) * 100) : 0,
      tone,
    }));
  }

  let excellent = 0;
  let expected = 0;
  let poor = 0;
  for (const row of block.responses) {
    const raw = String(row.answer || "").trim();
    const num = parseInt(raw, 10);
    if (!Number.isFinite(num)) {
      const lower = raw.toLowerCase();
      if (lower.includes("excellent") || lower.includes("good") || lower === "positive") excellent += row.count;
      else if (lower.includes("poor") || lower.includes("bad") || lower === "negative") poor += row.count;
      else expected += row.count;
      continue;
    }
    if (num >= 9) excellent += row.count;
    else if (num >= 7) expected += row.count;
    else poor += row.count;
  }

  const answered = excellent + expected + poor;
  const base = answered || total || 1;
  return [
    { label: "Excellent", count: excellent, pct: answered ? Math.round((excellent / base) * 100) : 0, tone: "success" },
    { label: "Expected", count: expected, pct: answered ? Math.round((expected / base) * 100) : 0, tone: "info" },
    { label: "Poor", count: poor, pct: answered ? Math.round((poor / base) * 100) : 0, tone: "destructive" },
  ];
}

function buildChoiceOptions(
  responses: Array<{ answer: string; count: number }>,
  total: number,
  maxOptions = 3,
): OptionRow[] {
  return responses.slice(0, maxOptions).map((row) => ({
    label: String(row.answer || "—"),
    count: row.count,
    pct: total ? Math.round((row.count / total) * 100) : 0,
    tone: toneForAnswer(String(row.answer)),
  }));
}

function mapAggregateToDetailQuestion(block: AggregateBlock): DetailQuestion {
  const total = block.total || 0;
  const type = inferQuestionType(block);

  if (type === "Yes / No") {
    return {
      id: block.question,
      title: block.question,
      type,
      options: buildYesNoOptions(block.responses, total),
      totalResponses: total,
      avgTime: "—",
    };
  }

  if (type === "Rating") {
    return {
      id: block.question,
      title: block.question,
      type,
      options: buildRatingOptions(block),
      totalResponses: total,
      avgTime: "—",
    };
  }

  if (type === "Open text") {
    const options = buildChoiceOptions(block.responses, total, 5);
    return {
      id: block.question,
      title: block.question,
      type,
      options: options.length ? options : [{ label: "No answers yet", count: 0, pct: 0, tone: "warning" }],
      totalResponses: total,
      avgTime: "—",
    };
  }

  const optionCount = Math.min(Math.max(block.responses.length, 2), 3);
  const options = buildChoiceOptions(block.responses, total, optionCount);

  return {
    id: block.question,
    title: block.question,
    type: "Choice",
    options: options.length ? options : [{ label: "No answers yet", count: 0, pct: 0, tone: "warning" }],
    totalResponses: total,
    avgTime: "—",
  };
}

function scoreToRatingLabel(score: number): string {
  if (score >= 9) return "Excellent";
  if (score >= 7) return "Good";
  if (score > 0) return "Poor";
  return "—";
}

function mapRespondentToCard(r: Respondent, index: number): ResponseCardData | null {
  const quote = String(
    r.quote || r.short_summary || r.final_additional_feedback || r.open_feedback?.[0]?.transcript || "",
  ).trim();
  const score = Number(r.recommend_score ?? r.satisfaction_score ?? 0);
  const answers: { question: string; answer: string }[] = [];

  for (const item of r.wa_answers || []) {
    const q = String(item.question || "").trim();
    const a = String(item.answer_text || item.answer || "").trim();
    const isVoice = String(item.answer_source || "") === "voice_note";
    if (!q) continue;
    if (a) {
      answers.push({ question: q.slice(0, 28), answer: a });
      continue;
    }
    if (isVoice) {
      const status = String(item.transcription_status || "").trim().toLowerCase();
      const label =
        status === "failed"
          ? "Voice note (failed)"
          : status === "completed"
            ? "Voice note"
            : "Voice note (transcribing)";
      answers.push({ question: q.slice(0, 28), answer: label });
    }
  }
  for (const fb of r.open_feedback || []) {
    const q = String(fb.question || "Feedback").trim();
    const a = String(fb.transcript || fb.text || "").trim();
    if (q && a && !answers.some((row) => row.question === q.slice(0, 28))) {
      answers.push({ question: q.slice(0, 28), answer: a.slice(0, 80) });
    }
  }
  if (answers.length === 0 && r.final_additional_feedback) {
    answers.push({ question: "Feedback", answer: "Provided" });
  }

  if (!quote && answers.length === 0 && score <= 0 && !(r.open_feedback || []).length) return null;

  const rating =
    String(r.rating_label || "").trim() ||
    (r.sentiment_label === "Negative" ? "Poor" : scoreToRatingLabel(score));
  const responseType =
    r.primary_response_type === "voice"
      ? "voice"
      : r.primary_response_type === "text"
        ? "text"
        : (r.open_feedback || []).some((fb) => fb.answer_source === "voice")
          ? "voice"
          : (r.wa_answers || []).some((a) => a.answer_source === "voice_note")
            ? "voice"
            : null;

  return {
    id: String(r.id || index),
    date: r.completed_at ? new Date(r.completed_at).toLocaleDateString() : r.status_label || "Completed",
    rating,
    answers: answers.slice(0, 4),
    theme: String(r.theme || r.sentiment_label || "General"),
    quote: quote || "No written comment.",
    duration: r.duration_label || "—",
    isUnhappy: Boolean(r.is_unhappy),
    responseType,
  };
}

function formatRespondentScore(r: Respondent): string {
  if (r.rating_label) return r.rating_label;
  if (r.sentiment_label) return r.sentiment_label;
  const score = Number(r.recommend_score ?? r.satisfaction_score ?? 0);
  return scoreToRatingLabel(score);
}

function formatRespondentDate(r: Respondent): string {
  if (r.completed_at) {
    try {
      return new Date(r.completed_at).toLocaleString();
    } catch {
      return r.completed_at;
    }
  }
  return r.status_label || "—";
}

function SurveyResults() {
  const { orderId: searchOrderId } = Route.useSearch();
  const ordersQ = useServiceOrders("survey");
  const campaigns = React.useMemo(
    () => (ordersQ.data || []).map((o) => orderToCampaign(o, "survey")),
    [ordersQ.data],
  );
  const [pendingOrderId, setPendingOrderId] = React.useState<string | undefined>(searchOrderId);
  const [activeOrderId, setActiveOrderId] = React.useState<string | undefined>(searchOrderId);
  const [responseSearch, setResponseSearch] = React.useState("");
  const [visibleResponses, setVisibleResponses] = React.useState(12);
  const [activeTab, setActiveTab] = React.useState("overview");
  const [detailRespondent, setDetailRespondent] = React.useState<Respondent | null>(null);

  React.useEffect(() => {
    logLaunchFlow("[results:init]", {
      component: "SurveyResults",
      orderId: searchOrderId || null,
      selectedCampaignId: activeOrderId || pendingOrderId || null,
      survey_name: "",
      title: "",
    });
  }, []);

  React.useEffect(() => {
    if (!searchOrderId) return;
    setPendingOrderId(searchOrderId);
    setActiveOrderId(searchOrderId);
  }, [searchOrderId]);

  React.useEffect(() => {
    if (searchOrderId) return;
    if (ordersQ.isLoading || ordersQ.isFetching) return;
    if (!pendingOrderId && campaigns[0]) setPendingOrderId(campaigns[0].id);
  }, [searchOrderId, campaigns, pendingOrderId, ordersQ.isLoading, ordersQ.isFetching]);

  const selected = campaigns.find((c) => c.id === (activeOrderId || pendingOrderId));
  const pendingSelected = campaigns.find((c) => c.id === pendingOrderId);
  const showDisabled = !pendingOrderId || pendingOrderId === activeOrderId;
  const resultsQ = useSurveyResults(activeOrderId || null);
  const payload = resultsQ.data || {};
  const summary = (payload.summary || {}) as Record<string, number | string | null | undefined>;
  const orderInfo = (payload.order || {}) as Record<string, string>;
  const aggregates = (payload.aggregates || []) as AggregateBlock[];
  const recommendations = (payload.recommendations || []) as Recommendation[];
  const respondents = (payload.respondents || []) as Respondent[];
  const weeklyTrend = (payload.weekly_trend || []) as TrendPoint[];
  const topIssues = (summary.top_issues as string[] | undefined) || [];
  const allowFollowUp = payload.allow_follow_up !== false;
  const unhappyCount = Number(summary.unhappy_count || 0);
  const surveyChannel = selected?.surveyChannel || (orderInfo.channel === "whatsapp" ? "whatsapp" : orderInfo.channel === "ai_call" ? "ai_call" : null);

  const exportResults = async (kind: "pdf" | "csv" | "xlsx") => {
    const exportId = activeOrderId;
    if (!exportId) return;
    try {
      const ext = kind === "pdf" ? "pdf" : kind === "xlsx" ? "xlsx" : "csv";
      await downloadAuthenticatedFile(
        `/service-orders/${encodeURIComponent(exportId)}/survey-results/export.${ext}`,
        `survey-results-${exportId.slice(0, 8)}.${ext}`,
      );
      toast.success(`${kind === "xlsx" ? "Excel" : kind.toUpperCase()} downloaded`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Export failed");
    }
  };

  const completed = Number(summary.completed_count || 0);
  const totalRecipients = Number(summary.total_recipients || 0);
  const responseRate = Number(summary.response_rate_pct || 0);
  const avgSat5 = summary.average_satisfaction_5 != null ? Number(summary.average_satisfaction_5) : null;
  const excellentRate =
    avgSat5 != null ? Math.round((avgSat5 / 5) * 100) : responseRate > 0 ? responseRate : 0;
  const excellentDelta =
    weeklyTrend.length >= 2
      ? (weeklyTrend[weeklyTrend.length - 1]?.csat_pct ?? excellentRate) - (weeklyTrend[0]?.csat_pct ?? excellentRate)
      : undefined;

  const sentimentCounts = (summary.sentiment_counts || {}) as Record<string, number>;
  const sentimentTotal = Object.values(sentimentCounts).reduce((sum, count) => sum + Number(count || 0), 0);
  const negativePct =
    sentimentTotal > 0
      ? Math.round((Number(sentimentCounts.negative || 0) / sentimentTotal) * 100)
      : Math.round(Number(summary.nps_detractors_pct || 0));

  const completionLabel = String(summary.average_call_duration_label || "—");
  const pending = Math.max(0, totalRecipients - completed);

  const questions = aggregates.map(mapAggregateToDetailQuestion);
  const responseCards = respondents
    .map(mapRespondentToCard)
    .filter((r): r is ResponseCardData => r != null)
    .filter((r) => {
      if (!responseSearch.trim()) return true;
      const q = responseSearch.toLowerCase();
      return (
        r.quote.toLowerCase().includes(q) ||
        r.theme.toLowerCase().includes(q) ||
        r.rating.toLowerCase().includes(q)
      );
    });

  const themeItems =
    sentimentTotal > 0
      ? Object.entries(sentimentCounts)
          .sort((a, b) => Number(b[1] || 0) - Number(a[1] || 0))
          .slice(0, 4)
          .map(([label, count]) => ({
            label: label.charAt(0).toUpperCase() + label.slice(1),
            value: Math.round((Number(count) / sentimentTotal) * 100),
            sentiment: label === "negative" ? "negative" : label === "positive" ? "positive" : "mixed",
          }))
      : topIssues.slice(0, 4).map((label) => ({
          label,
          value: topIssues.length ? Math.round(100 / topIssues.length) : 0,
          sentiment: label.toLowerCase().includes("negative")
            ? "negative"
            : label.toLowerCase().includes("positive")
              ? "positive"
              : "mixed",
        }));

  const isLoading = resultsQ.isLoading;
  const hasError = resultsQ.isError;

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="Surveys · Results"
        title={orderInfo.survey_name || orderInfo.title || selected?.name || "Survey results"}
        description={
          (
            <div className="space-y-2">
              <SurveyIdentityHeader
                surveyName={orderInfo.survey_name || orderInfo.title || selected?.name || "Survey results"}
                surveyId={orderInfo.campaign_id || orderInfo.survey_id || selected?.surveyId}
                channel={selected?.surveyChannel || (orderInfo.channel === "whatsapp" ? "whatsapp" : orderInfo.channel === "ai_call" ? "ai_call" : null)}
                compact
              />
              <p className="text-sm text-muted-foreground">
                One-survey results: live responses, question analysis, themes, and anonymous response browser.
              </p>
            </div>
          ) as unknown as string
        }
        actions={
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5"
              onClick={() => void exportResults("pdf")}
              disabled={!activeOrderId}
            >
              <Download className="size-4" /> Export PDF
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5"
              onClick={() => void exportResults("xlsx")}
              disabled={!activeOrderId}
            >
              <Download className="size-4" /> Export Excel
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5"
              onClick={() => void exportResults("csv")}
              disabled={!activeOrderId}
            >
              <Download className="size-4" /> Export CSV
            </Button>
          </div>
        }
      />

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card p-3">
        <div className="flex flex-wrap items-center gap-3 min-w-0">
          <Select value={pendingOrderId} onValueChange={setPendingOrderId}>
            <SelectTrigger className="h-9 w-[21rem]">
              <SelectValue placeholder="Select survey" />
            </SelectTrigger>
            <SelectContent>
              {campaigns.map((c) => (
                <SelectItem key={c.id} value={c.id}>
                  <span className="flex items-center gap-2">
                    {c.surveyChannel === "whatsapp" ? (
                      <MessageCircle className="size-3.5 shrink-0 text-primary" />
                    ) : c.surveyChannel === "ai_call" ? (
                      <Phone className="size-3.5 shrink-0 text-primary" />
                    ) : null}
                    {c.name}
                  </span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button size="sm" disabled={showDisabled} onClick={() => pendingOrderId && setActiveOrderId(pendingOrderId)}>
            Show
          </Button>
          {pendingSelected && <StatusBadge tone={pendingSelected.status} />}
          <span className="text-sm text-muted-foreground truncate">
            {activeOrderId
              ? `${completed.toLocaleString()} / ${totalRecipients.toLocaleString()} responses · ${responseRate}% rate`
              : "Select a survey and click Show"}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Tabs value={activeTab} onValueChange={setActiveTab}>
            <TabsList className="h-9">
              <TabsTrigger value="overview" className="text-xs">Overview</TabsTrigger>
              <TabsTrigger value="questions" className="text-xs">Questions</TabsTrigger>
              <TabsTrigger value="responses" className="text-xs">Responses</TabsTrigger>
              {allowFollowUp ? (
                <TabsTrigger value="details" className="relative gap-1 text-xs">
                  <PanelRightOpen className="size-3.5" />
                  More details
                  {unhappyCount > 0 ? (
                    <span className="absolute -right-1 -top-1 flex size-4 items-center justify-center rounded-full bg-destructive text-[10px] font-semibold text-destructive-foreground">
                      {unhappyCount > 9 ? "9+" : unhappyCount}
                    </span>
                  ) : null}
                </TabsTrigger>
              ) : null}
            </TabsList>
          </Tabs>
        </div>
      </div>

      {hasError ? (
        <Card className="border-destructive/40">
          <CardContent className="flex items-center gap-3 p-6 text-sm text-destructive">
            <AlertCircle className="size-5 shrink-0" />
            Could not load survey results. Try selecting another survey or refresh the page.
          </CardContent>
        </Card>
      ) : null}

      {isLoading ? (
        <div className="grid gap-4 grid-cols-2 md:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
      ) : (
        <div className="grid gap-4 grid-cols-2 md:grid-cols-4">
          <Kpi
            title="Excellent rate"
            value={`${excellentRate}%`}
            sub={
              excellentDelta != null && excellentDelta !== 0
                ? `${excellentDelta > 0 ? "+" : ""}${excellentDelta} vs previous`
                : avgSat5 != null
                  ? `avg ${avgSat5} / 5`
                  : "satisfaction"
            }
            icon={<TrendingUp className="size-4" />}
          />
          <Kpi
            title="Response rate"
            value={`${responseRate}%`}
            sub={`${completed.toLocaleString()} of ${totalRecipients.toLocaleString()}`}
            icon={<Users className="size-4" />}
          />
          <Kpi
            title="Completion"
            value={`${responseRate}%`}
            sub={completionLabel !== "—" ? `avg. ${completionLabel}` : `${completed} completed`}
            icon={<MessageSquareText className="size-4" />}
          />
          <Kpi
            title="Poor rating"
            value={`${negativePct}%`}
            sub={`${Number(sentimentCounts.negative || summary.nps_detractors || 0)} responses`}
            tone="destructive"
            icon={<Sparkles className="size-4" />}
          />
        </div>
      )}

      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
        <TabsContent value="overview" className="space-y-6">
          {isLoading ? (
            <Skeleton className="h-64 w-full" />
          ) : (
            <>
              <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">Question-level results</CardTitle>
                  </CardHeader>
                  <CardContent className="grid gap-4 grid-cols-1 sm:grid-cols-2 xl:grid-cols-3">
                    {questions.length === 0 ? (
                      <p className="col-span-full text-sm text-muted-foreground">No question aggregates yet.</p>
                    ) : (
                      questions.slice(0, 3).map((q) => <QuestionCard key={q.id} {...q} />)
                    )}
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">Drop-off funnel</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <Funnel
                      label="Invited"
                      value={totalRecipients ? 100 : 0}
                      count={totalRecipients.toLocaleString()}
                    />
                    <Funnel
                      label="In progress"
                      value={totalRecipients ? Math.round((pending / totalRecipients) * 100) : 0}
                      count={pending.toLocaleString()}
                    />
                    <Funnel
                      label="Completed"
                      value={responseRate}
                      count={completed.toLocaleString()}
                    />
                  </CardContent>
                </Card>
              </div>

              <div className="grid gap-4 grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">AI themes</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {themeItems.length === 0 ? (
                      <p className="text-sm text-muted-foreground">Themes appear after enough responses are analysed.</p>
                    ) : (
                      themeItems.map((t) => (
                        <Theme key={t.label} label={t.label} value={t.value} sentiment={t.sentiment} />
                      ))
                    )}
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">Response breakdown</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <Segment label="Completed" excellent={`${responseRate}%`} rate={`${completed} responses`} />
                    <Segment label="Pending" excellent={`${totalRecipients ? Math.round((pending / totalRecipients) * 100) : 0}%`} rate={`${pending} waiting`} />
                    {orderInfo.channel ? (
                      <Segment label={`${orderInfo.channel} channel`} excellent={`${excellentRate}%`} rate={`${responseRate}% response`} />
                    ) : null}
                  </CardContent>
                </Card>

                <Card className="md:col-span-2 lg:col-span-1">
                  <CardHeader className="flex flex-row items-center gap-2">
                    <Sparkles className="size-4 text-primary" />
                    <CardTitle className="text-base">AI recommended actions</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3 text-sm">
                    {recommendations.length === 0 ? (
                      <p className="text-muted-foreground">Recommendations appear after enough responses are analysed.</p>
                    ) : (
                      recommendations.slice(0, 3).map((r, i) => (
                        <Action
                          key={i}
                          text={String(r.text || r.title || "")}
                          impact={String(r.impact || "Medium")}
                          source={r.source}
                        />
                      ))
                    )}
                  </CardContent>
                </Card>
              </div>
            </>
          )}
        </TabsContent>

        <TabsContent value="questions" className="space-y-6">
          {isLoading ? (
            <Skeleton className="h-48 w-full" />
          ) : questions.length === 0 ? (
            <Card>
              <CardContent className="p-6 text-sm text-muted-foreground">No question aggregates yet.</CardContent>
            </Card>
          ) : (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="secondary" className="gap-1">
                  <BarChart3 className="size-3" /> {questions.filter((q) => q.type === "Rating").length} Rating
                </Badge>
                <Badge variant="secondary" className="gap-1">
                  <HelpCircle className="size-3" /> {questions.filter((q) => q.type === "Yes / No").length} Yes / No
                </Badge>
                <Badge variant="secondary" className="gap-1">
                  <MessageCircle className="size-3" /> {questions.filter((q) => q.type === "Open text").length} Open text
                </Badge>
              </div>

              <div className="grid gap-5 grid-cols-1 sm:grid-cols-2 xl:grid-cols-3">
                {questions.map((q, idx) => (
                  <QuestionDetailCard key={q.id} index={idx + 1} {...q} />
                ))}
              </div>

              <Card>
                <CardHeader>
                  <CardTitle className="text-base flex items-center gap-2">
                    <ArrowUpDown className="size-4 text-primary" /> Question comparison
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="overflow-x-auto -mx-4 px-4">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-border">
                          <th className="py-3 pr-4 text-left font-semibold text-muted-foreground text-xs uppercase tracking-wider">#</th>
                          <th className="py-3 pr-4 text-left font-semibold text-muted-foreground text-xs uppercase tracking-wider">Question</th>
                          <th className="py-3 pr-4 text-left font-semibold text-muted-foreground text-xs uppercase tracking-wider">Type</th>
                          <th className="py-3 pr-4 text-right font-semibold text-muted-foreground text-xs uppercase tracking-wider">Responses</th>
                          <th className="py-3 pr-4 text-right font-semibold text-muted-foreground text-xs uppercase tracking-wider">Top answer</th>
                          <th className="py-3 text-right font-semibold text-muted-foreground text-xs uppercase tracking-wider">Avg time</th>
                        </tr>
                      </thead>
                      <tbody>
                        {questions.map((q, idx) => {
                          const topOption = q.options.reduce((a, b) => (b.count > a.count ? b : a), q.options[0]);
                          return (
                            <tr key={q.id} className="border-b border-border/50 last:border-0">
                              <td className="py-3 pr-4 text-muted-foreground">{idx + 1}</td>
                              <td className="py-3 pr-4 font-medium max-w-[200px] truncate">{q.title}</td>
                              <td className="py-3 pr-4">
                                <QuestionTypeBadge type={q.type} />
                              </td>
                              <td className="py-3 pr-4 text-right tabular-nums">{q.totalResponses.toLocaleString()}</td>
                              <td className="py-3 pr-4 text-right">
                                <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium", toneToColor(topOption.tone))}>
                                  {topOption.label} ({topOption.count.toLocaleString()} · {topOption.pct}%)
                                </span>
                              </td>
                              <td className="py-3 text-right tabular-nums text-muted-foreground">{q.avgTime}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </CardContent>
              </Card>

              <div className="grid gap-4 grid-cols-1 md:grid-cols-2">
                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">Yes / No breakdown</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    {questions.filter((q) => q.type === "Yes / No").length === 0 ? (
                      <p className="text-sm text-muted-foreground">No yes/no questions in this survey.</p>
                    ) : (
                      questions
                        .filter((q) => q.type === "Yes / No")
                        .map((q) => {
                          const yes = q.options.find((o) => o.label.toLowerCase() === "yes");
                          const no = q.options.find((o) => o.label.toLowerCase() === "no");
                          const yesPct = yes?.pct ?? 0;
                          return (
                            <div key={q.id} className="space-y-2">
                              <div className="flex items-center justify-between text-sm">
                                <span className="font-medium truncate pr-2">{q.title}</span>
                                <span className="shrink-0 tabular-nums text-xs text-muted-foreground">
                                  Yes {yes?.count.toLocaleString() ?? 0} · No {no?.count.toLocaleString() ?? 0}
                                </span>
                              </div>
                              <div className="flex h-3 overflow-hidden rounded-full bg-border">
                                <div
                                  className="bg-success transition-all"
                                  style={{ width: `${yesPct}%` }}
                                  title={`Yes: ${yes?.count ?? 0}`}
                                />
                                <div
                                  className="bg-destructive transition-all"
                                  style={{ width: `${100 - yesPct}%` }}
                                  title={`No: ${no?.count ?? 0}`}
                                />
                              </div>
                              <div className="flex justify-between text-[11px] text-muted-foreground">
                                <span>Yes {yesPct}%</span>
                                <span>No {no?.pct ?? 0}%</span>
                              </div>
                            </div>
                          );
                        })
                    )}
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">Rating distribution</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    {questions.filter((q) => q.type === "Rating").length === 0 ? (
                      <p className="text-sm text-muted-foreground">No rating questions in this survey.</p>
                    ) : (
                      questions
                        .filter((q) => q.type === "Rating")
                        .map((q) => (
                          <div key={q.id} className="space-y-2">
                            <p className="text-sm font-medium">{q.title}</p>
                            <div className="flex h-8 overflow-hidden rounded-full bg-border">
                              {q.options.map((option) => (
                                <div
                                  key={option.label}
                                  className={cn(
                                    "flex items-center justify-center px-1 text-[10px] font-bold text-white transition-all",
                                    toneToBar(option.tone),
                                  )}
                                  style={{ width: `${Math.max(option.pct, option.count > 0 ? 8 : 0)}%` }}
                                  title={`${option.label}: ${option.count}`}
                                >
                                  {option.count > 0 ? option.count : ""}
                                </div>
                              ))}
                            </div>
                            <div className="flex flex-wrap gap-3">
                              {q.options.map((option) => (
                                <span key={option.label} className="flex items-center gap-1 text-xs text-muted-foreground">
                                  <span className={cn("size-2 rounded-full", toneToDot(option.tone))} />
                                  {option.label} ({option.count.toLocaleString()} · {option.pct}%)
                                </span>
                              ))}
                            </div>
                          </div>
                        ))
                    )}
                  </CardContent>
                </Card>
              </div>
            </>
          )}
        </TabsContent>

        <TabsContent value="responses" className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-sm text-muted-foreground">
                {responseCards.length} responses · sorted by survey order
              </p>
              {allowFollowUp && unhappyCount > 0 ? (
                <Badge variant="destructive" className="gap-1">
                  <AlertTriangle className="size-3" /> {unhappyCount} unhappy
                </Badge>
              ) : null}
            </div>
            <div className="flex gap-2">
              <div className="relative">
                <Search className="absolute left-2 top-2.5 size-4 text-muted-foreground" />
                <Input
                  placeholder="Search responses"
                  className="h-9 w-full pl-8 sm:w-48"
                  value={responseSearch}
                  onChange={(e) => {
                    setResponseSearch(e.target.value);
                    setVisibleResponses(12);
                  }}
                />
              </div>
              <Button variant="outline" size="sm" className="gap-1.5" disabled>
                <Filter className="size-4" /> Filter
              </Button>
            </div>
          </div>

          {isLoading ? (
            <div className="grid gap-3 grid-cols-1 md:grid-cols-2 xl:grid-cols-3">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-40" />
              ))}
            </div>
          ) : responseCards.length === 0 ? (
            <Card>
              <CardContent className="p-6 text-sm text-muted-foreground">No responses to show yet.</CardContent>
            </Card>
          ) : (
            <>
              <div className="grid gap-3 grid-cols-1 md:grid-cols-2 xl:grid-cols-3">
                {responseCards.slice(0, visibleResponses).map((r) => (
                  <ResponseCard key={r.id} {...r} />
                ))}
              </div>
              {visibleResponses < responseCards.length ? (
                <div className="flex justify-center">
                  <Button variant="outline" size="sm" onClick={() => setVisibleResponses((n) => n + 12)}>
                    Load more responses
                  </Button>
                </div>
              ) : null}
            </>
          )}
        </TabsContent>

        {allowFollowUp ? (
          <TabsContent value="details" className="space-y-4">
            {isLoading ? (
              <Skeleton className="h-64 w-full" />
            ) : (
              <SurveyResultsRespondentsTab
                respondents={respondents}
                unhappyCount={unhappyCount}
                onOpenRespondent={(row) => setDetailRespondent(row as Respondent)}
              />
            )}
          </TabsContent>
        ) : null}
      </Tabs>

      <p className="text-center text-[11px] text-muted-foreground">
        Results are for one selected survey. Reports compare many surveys over time.
      </p>

      <RespondentDetailSheet
        respondent={detailRespondent}
        channel={surveyChannel}
        onClose={() => setDetailRespondent(null)}
      />
    </div>
  );
}

function completedAgoLabel(completedAt: string | null | undefined) {
  if (!completedAt) return "Completed recently";
  try {
    const diffMs = Date.now() - new Date(completedAt).getTime();
    const hours = Math.max(1, Math.round(diffMs / (1000 * 60 * 60)));
    if (hours < 24) return `Completed ${hours}h ago`;
    const days = Math.round(hours / 24);
    return `Completed ${days}d ago`;
  } catch {
    return "Completed recently";
  }
}

function RespondentDetailSheet({
  respondent,
  channel,
  onClose,
}: {
  respondent: Respondent | null;
  channel: string | null;
  onClose: () => void;
}) {
  const open = Boolean(respondent);
  const waAnswers = respondent?.wa_answers || [];
  const extracted = respondent?.extracted_answers || [];
  const openFeedback = respondent?.open_feedback || [];

  const unhappyReason =
    waAnswers.find((row) => {
      const label = String(row.answer_text || row.answer || "").toLowerCase();
      return label.includes("poor") || label === "no";
    })?.question ||
    extracted.find((row) => String(row.answer || "").toLowerCase().includes("poor"))?.question ||
    "Negative feedback on survey answers";

  return (
    <Sheet open={open} onOpenChange={(v) => !v && onClose()}>
      <SheetContent side="right" className="w-full sm:max-w-xl overflow-y-auto">
        {respondent ? (
          <>
            <Button variant="ghost" size="sm" className="mb-2 gap-1.5 px-0" onClick={onClose}>
              <ArrowLeft className="size-4" /> Back to list
            </Button>
            <SheetHeader>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <SheetTitle>{respondent.name || "Respondent"}</SheetTitle>
                  <SheetDescription>
                    {[respondent.phone, respondent.email].filter(Boolean).join(" · ") || "No contact details"}
                  </SheetDescription>
                  <p className="mt-1 text-xs text-muted-foreground">{completedAgoLabel(respondent.completed_at)}</p>
                </div>
                {respondent.is_unhappy ? <Badge variant="destructive">Unhappy</Badge> : null}
              </div>
            </SheetHeader>
            <div className="mt-6 space-y-4 text-sm">
              {respondent.is_unhappy ? (
                <Card className="border-destructive/40 bg-destructive/5">
                  <CardContent className="space-y-1 p-4">
                    <p className="font-medium text-destructive">Recommended: call within 24h</p>
                    <p className="text-muted-foreground">{unhappyReason}</p>
                  </CardContent>
                </Card>
              ) : null}
              {channel === "ai_call" && extracted.length > 0
                ? extracted.map((row, i) => (
                    <Card key={`call-${i}`}>
                      <CardContent className="space-y-2 p-4">
                        <p className="text-xs font-medium text-muted-foreground">{row.question}</p>
                        <div className="flex items-center gap-2">
                          <Badge variant="outline">{row.answer || "—"}</Badge>
                        </div>
                      </CardContent>
                    </Card>
                  ))
                : null}
              {waAnswers.length > 0
                ? waAnswers.map((row, i) => {
                    const answer = String(row.answer_text || row.answer || "—");
                    const tone = toneForAnswer(answer);
                    return (
                      <Card key={`wa-${i}`}>
                        <CardContent className="space-y-2 p-4">
                          <p className="text-xs font-medium text-muted-foreground">{row.question}</p>
                          <Badge className={cn(toneToColor(tone))}>{answer}</Badge>
                        </CardContent>
                      </Card>
                    );
                  })
                : null}
              {openFeedback.length > 0
                ? openFeedback.map((row, i) => (
                    <Card key={`open-${i}`}>
                      <CardContent className="space-y-2 p-4">
                        <p className="text-xs font-medium text-muted-foreground">{row.question}</p>
                        <blockquote className="rounded-lg border border-border bg-muted/30 px-3 py-2 text-muted-foreground">
                          {row.translated_text || row.transcript || row.text || "—"}
                        </blockquote>
                        {row.original_text && row.translated_text && row.original_text !== row.translated_text ? (
                          <p className="text-xs text-muted-foreground">Original: {row.original_text}</p>
                        ) : null}
                      </CardContent>
                    </Card>
                  ))
                : null}
            </div>
          </>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}

function toneToColor(tone: string) {
  if (tone === "success") return "bg-success/15 text-success";
  if (tone === "info") return "bg-info/15 text-info";
  if (tone === "warning") return "bg-warning/15 text-warning";
  if (tone === "destructive") return "bg-destructive/15 text-destructive";
  return "bg-accent text-accent-foreground";
}

function toneToBar(tone: string) {
  if (tone === "success") return "bg-success";
  if (tone === "info") return "bg-info";
  if (tone === "warning") return "bg-warning";
  if (tone === "destructive") return "bg-destructive";
  return "bg-primary";
}

function toneToDot(tone: string) {
  if (tone === "success") return "bg-success";
  if (tone === "info") return "bg-info";
  if (tone === "warning") return "bg-warning";
  if (tone === "destructive") return "bg-destructive";
  return "bg-primary";
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
        <div className={tone === "destructive" ? "text-destructive" : "text-primary"}>{icon}</div>
        <p className="mt-3 text-xs uppercase tracking-wider text-muted-foreground">{title}</p>
        <p className="text-2xl font-semibold tracking-tight md:text-3xl">{value}</p>
        <p className="text-xs text-muted-foreground">{sub}</p>
      </CardContent>
    </Card>
  );
}

function QuestionCard({
  title,
  type,
  options,
  totalResponses,
}: {
  title: string;
  type: string;
  options: OptionRow[];
  totalResponses: number;
}) {
  return (
    <div className="rounded-xl border border-border bg-background p-4">
      <div className="mb-4 flex items-start justify-between gap-2">
        <p className="text-sm font-semibold">{title}</p>
        <span className="shrink-0 rounded-full bg-accent px-2 py-0.5 text-[11px] font-medium text-accent-foreground">{type}</span>
      </div>
      <p className="mb-3 text-[11px] text-muted-foreground">{totalResponses.toLocaleString()} responses</p>
      <div className="space-y-3">
        {options.map((option) => (
          <BarLine key={option.label} {...option} />
        ))}
      </div>
    </div>
  );
}

function BarLine({ label, count, pct, tone }: OptionRow) {
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs">
        <span className="font-medium text-foreground">{label}</span>
        <span className="tabular-nums">
          <span className="font-semibold">{count.toLocaleString()}</span>
          <span className="text-muted-foreground"> · {pct}%</span>
        </span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-border">
        <div className={cn("h-full rounded-full transition-all", toneToBar(tone))} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function Funnel({ label, value, count }: { label: string; value: number; count: string }) {
  return (
    <div>
      <div className="mb-1 flex justify-between text-sm">
        <span>{label}</span>
        <span className="text-muted-foreground">{count}</span>
      </div>
      <Progress value={value} className="h-2" />
    </div>
  );
}

function Theme({ label, value, sentiment }: { label: string; value: number; sentiment: string }) {
  const icon =
    sentiment === "positive" ? (
      <ThumbsUp className="size-3 text-success" />
    ) : sentiment === "negative" ? (
      <ThumbsDown className="size-3 text-destructive" />
    ) : (
      <AlertTriangle className="size-3 text-warning" />
    );
  return (
    <div className="rounded-lg border border-border bg-background p-3">
      <div className="flex items-center justify-between text-sm">
        <span className="flex items-center gap-1.5 font-medium">
          {icon} {label}
        </span>
        <span className="tabular-nums text-muted-foreground">{value}%</span>
      </div>
      <p className="mt-1 text-xs capitalize text-muted-foreground">{sentiment} sentiment cluster</p>
    </div>
  );
}

function Segment({ label, excellent, rate }: { label: string; excellent: string; rate: string }) {
  return (
    <div className="flex items-center justify-between rounded-lg border border-border bg-background p-3 text-sm">
      <span>{label}</span>
      <span className="text-right">
        <b>{excellent}</b>
        <br />
        <span className="text-xs text-muted-foreground">{rate}</span>
      </span>
    </div>
  );
}

function Action({ text, impact, source }: { text: string; impact: string; source?: string }) {
  const impactCls = impact === "High" ? "text-success" : "text-warning";
  return (
    <div className="rounded-lg border border-border bg-background p-3">
      {source === "negative_feedback" ? (
        <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-destructive">
          From respondent feedback
        </p>
      ) : null}
      <p>{text}</p>
      <p className={`mt-1 text-xs ${impactCls}`}>{impact} impact</p>
    </div>
  );
}

function QuestionTypeBadge({ type }: { type: string }) {
  const icon =
    type === "Rating" ? (
      <BarChart3 className="size-3" />
    ) : type === "Yes / No" ? (
      <HelpCircle className="size-3" />
    ) : (
      <MessageCircle className="size-3" />
    );
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary ring-1 ring-primary/20">
      {icon} {type}
    </span>
  );
}

function QuestionDetailCard({
  index,
  title,
  type,
  options,
  totalResponses,
  avgTime,
}: {
  index: number;
  title: string;
  type: string;
  options: OptionRow[];
  totalResponses: number;
  avgTime: string;
}) {
  return (
    <Card className="overflow-hidden">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-start gap-2">
            <span className="grid size-6 shrink-0 place-items-center rounded-full bg-primary text-[11px] font-bold text-primary-foreground">
              {index}
            </span>
            <CardTitle className="text-sm leading-snug">{title}</CardTitle>
          </div>
          <QuestionTypeBadge type={type} />
        </div>
        <div className="flex items-center gap-3 text-xs text-muted-foreground">
          <span className="flex items-center gap-1">
            <Users className="size-3" /> {totalResponses.toLocaleString()} responses
          </span>
          <span className="flex items-center gap-1">
            <Clock className="size-3" /> avg {avgTime}
          </span>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {options.map((option) => (
          <div key={option.label} className="space-y-1.5">
            <div className="flex items-center justify-between text-sm">
              <span className="font-medium">{option.label}</span>
              <span className="flex items-center gap-2">
                <span className="text-xs font-semibold tabular-nums text-foreground">
                  {option.count.toLocaleString()}
                </span>
                <span className={cn("rounded-full px-2 py-0.5 text-xs font-semibold tabular-nums", toneToColor(option.tone))}>
                  {option.pct}%
                </span>
              </span>
            </div>
            <div className="h-2.5 overflow-hidden rounded-full bg-border">
              <div
                className={cn("h-full rounded-full transition-all", toneToBar(option.tone))}
                style={{ width: `${option.pct}%` }}
              />
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function ResponseCard({
  date,
  rating,
  answers,
  theme,
  quote,
  duration,
  isUnhappy,
  responseType,
}: {
  date: string;
  rating: string;
  answers: { question: string; answer: string }[];
  theme: string;
  quote: string;
  duration: string;
  isUnhappy: boolean;
  responseType: "text" | "voice" | null;
}) {
  const ratingCls =
    rating === "Excellent"
      ? "bg-success/15 text-success"
      : rating === "Good"
        ? "bg-info/15 text-info"
        : rating === "Poor"
          ? "bg-destructive/15 text-destructive"
          : "bg-muted text-muted-foreground";
  return (
    <Card className={cn("overflow-hidden", isUnhappy && "ring-1 ring-destructive/30")}>
      <CardContent className="space-y-3 p-4">
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-1.5">
            {isUnhappy ? <span className="size-2 rounded-full bg-destructive" title="Unhappy" /> : null}
            <span className={cn("rounded-full px-2.5 py-0.5 text-xs font-semibold", ratingCls)}>{rating}</span>
          </span>
          <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
            {responseType === "voice" ? (
              <Mic className="size-4 text-muted-foreground" aria-label="Voice response" />
            ) : responseType === "text" ? (
              <MessageSquareText className="size-4 text-muted-foreground" aria-label="Text response" />
            ) : null}
            <span className="flex items-center gap-1">
              <Clock className="size-3" /> {duration}
            </span>
            <span>{date}</span>
          </div>
        </div>
        {answers.length > 0 ? (
          <div className="flex flex-wrap gap-1.5">
            {answers.map((a) => (
              <MiniBadge key={`${a.question}-${a.answer}`} label={a.question} value={a.answer} />
            ))}
          </div>
        ) : null}
        {quote ? <p className="text-sm leading-relaxed text-muted-foreground">&ldquo;{quote}&rdquo;</p> : null}
        <Badge variant="outline" className="text-[10px]">
          {theme}
        </Badge>
      </CardContent>
    </Card>
  );
}

function MiniBadge({ label, value }: { label: string; value: string }) {
  const isYes = value.toLowerCase() === "yes";
  const isNo = value.toLowerCase() === "no";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-medium",
        isYes && "bg-success/10 text-success",
        isNo && "bg-destructive/10 text-destructive",
        !isYes && !isNo && "bg-muted text-muted-foreground",
      )}
    >
      {isYes ? <CheckCircle2 className="size-3" /> : isNo ? <XCircle className="size-3" /> : null} {label}
    </span>
  );
}
