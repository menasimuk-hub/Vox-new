import type {
  FeedbackAggregateBlock,
  FeedbackOpenComment,
  FeedbackRespondent,
  FeedbackResultsInsightsPayload,
  FeedbackResultsPayload,
} from "@/lib/queries";

export type RatingQ = {
  id: string;
  title: string;
  type: "Rating";
  responses: number;
  scale: "PGE";
  breakdown: { poor: number; good: number; excellent: number };
  delta?: number;
};

export type YesNoQ = {
  id: string;
  title: string;
  type: "Yes/No";
  responses: number;
  scale: "YN";
  breakdown: { yes: number; no: number };
  delta?: number;
};

export type OpenQ = {
  id: string;
  title: string;
  type: "Open text" | "Voice";
  responses: number;
  scale: "OPEN";
  samples: number;
};

export type Question = RatingQ | YesNoQ | OpenQ;

export type Respondent = {
  id: string;
  name: string;
  type: "mobile" | "web";
  mobile: string;
  completedAt: string;
  completedAtTs: number;
  sentiment: "happy" | "neutral" | "unhappy";
  flagged: boolean;
  answers: Array<
    | { qid: string; type: "Rating"; value: "poor" | "good" | "excellent" }
    | { qid: string; type: "Yes/No"; value: "yes" | "no" }
    | { qid: string; type: "Voice"; value: string; original?: string; translationPending?: true }
  >;
};

export type VoiceComment = {
  id: string;
  name: string;
  tone: "destructive" | "success";
  transcript: string;
  originalTranscript?: string;
  translationPending?: boolean;
  reason: string;
  question: string;
};

const TRANSLATION_UNAVAILABLE = "[Translation unavailable]";

export type TextComment = {
  quote: string;
  rating: "excellent" | "good" | "poor";
  theme: string;
};

export type WeeklyTrendPoint = {
  week: string;
  satisfaction: number | null;
  positive: number | null;
  responses: number;
};

export type SentimentSlice = { name: string; value: number; color: string };

export type FeedbackSurveyResultsData = {
  pageTitle: string;
  metaLine: string;
  weeklyImprovementBadge: string | null;
  weeklyTrend: WeeklyTrendPoint[];
  sentimentDistribution: SentimentSlice[];
  questions: Question[];
  voiceComments: VoiceComment[];
  textComments: TextComment[];
  respondents: Respondent[];
  themes: Array<{ label: string; value: number; sentiment: string }>;
  recommendations: Array<{ title: string; text: string; impact: string }>;
  kpi: {
    satisfaction: string;
    satisfactionSub: string;
    satisfactionDelta?: number;
    recommend: string;
    recommendSub: string;
    recommendDelta?: number;
    responseRate: string;
    responseRateSub: string;
    responseRateDelta?: number;
    unhappy: string;
    unhappySub: string;
    unhappyDelta?: number;
  };
};

function classifyPge(text: string): "poor" | "good" | "excellent" | null {
  const t = text.trim().toLowerCase();
  if (!t) return null;
  if (t.includes("excellent") || t === "5") return "excellent";
  if (t.includes("good") || t === "4" || t === "3") return "good";
  if (t.includes("poor") || t === "bad" || t === "1" || t === "2") return "poor";
  return null;
}

function classifyYn(text: string): "yes" | "no" | null {
  const t = text.trim().toLowerCase();
  if (t === "yes" || t.startsWith("yes")) return "yes";
  if (t === "no" || t.startsWith("no")) return "no";
  return null;
}

function respondentType(phone: string | null | undefined): "mobile" | "web" {
  return String(phone || "").startsWith("web:") ? "web" : "mobile";
}

function displayName(phone: string | null | undefined): string {
  const p = String(phone || "").trim();
  if (!p) return "Customer";
  const digits = p.replace(/\D/g, "");
  const tail = digits.slice(-4) || digits;
  return `Customer · ${tail}`;
}

function formatRelative(iso: string | null | undefined): string {
  if (!iso) return "Recently";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "Recently";
  const diffMs = Date.now() - d.getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 60) return `${Math.max(1, mins)}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days === 1) return "yesterday";
  if (days < 7) return `${days}d ago`;
  return d.toLocaleDateString();
}

function aggregateToQuestion(block: FeedbackAggregateBlock, id: string, voiceSamples: number): Question {
  const breakdown = block.breakdown || [];
  const poor = breakdown.find((b) => b.key === "poor")?.pct ?? 0;
  const good = breakdown.find((b) => b.key === "good")?.pct ?? 0;
  const excellent = breakdown.find((b) => b.key === "excellent")?.pct ?? 0;
  const yes = breakdown.find((b) => b.key === "yes")?.pct ?? 0;
  const no = breakdown.find((b) => b.key === "no")?.pct ?? 0;
  const role = String(block.step_role || "").toLowerCase();
  const title = block.question || block.question_key || "Question";
  const responses = block.total || 0;

  if (yes || no || role.includes("yes") || role.includes("recommend")) {
    return {
      id,
      title,
      type: "Yes/No",
      scale: "YN",
      responses,
      breakdown: { yes, no },
    };
  }
  if (excellent || good || poor || role === "rating") {
    return {
      id,
      title,
      type: "Rating",
      scale: "PGE",
      responses,
      breakdown: { poor, good, excellent },
    };
  }
  const isVoice = role.includes("voice") || role.includes("open");
  return {
    id,
    title,
    type: isVoice ? "Voice" : "Open text",
    scale: "OPEN",
    responses,
    samples: voiceSamples || responses,
  };
}

function mapRespondentAnswers(
  r: FeedbackRespondent,
  questionByTitle: Map<string, string>,
  questions: Question[],
): Respondent["answers"] {
  const answers: Respondent["answers"] = [];
  for (const a of r.answers || []) {
    const title = String(a.question || "").trim();
    let qid = questionByTitle.get(title);
    if (!qid) {
      const q = questions.find((x) => x.title === title);
      qid = q?.id;
    }
    if (!qid) continue;
    const q = questions.find((x) => x.id === qid);
    const raw = String(a.answer || "").trim();
    const role = String(a.step_role || "").toLowerCase();
    if (a.answer_source === "voice" || role.includes("voice") || role.includes("open") || q?.scale === "OPEN") {
      if (raw) {
        const original = String((a as { original_text?: string }).original_text || "").trim();
        const translationPending = raw === TRANSLATION_UNAVAILABLE && Boolean(original);
        answers.push({
          qid,
          type: "Voice",
          value: translationPending ? TRANSLATION_UNAVAILABLE : raw,
          ...(original && original !== raw ? { original } : {}),
          ...(translationPending ? { translationPending: true as const } : {}),
        });
      }
      continue;
    }
    const yn = classifyYn(raw);
    if (yn || q?.scale === "YN") {
      answers.push({ qid, type: "Yes/No", value: yn || "no" });
      continue;
    }
    const pge = classifyPge(raw);
    if (pge) answers.push({ qid, type: "Rating", value: pge });
  }
  return answers;
}

function ratingFromSentiment(sentiment: string | null | undefined): "excellent" | "good" | "poor" {
  if (sentiment === "positive") return "excellent";
  if (sentiment === "negative") return "poor";
  return "good";
}

export function mapFeedbackResults(
  data: FeedbackResultsPayload,
  insights: FeedbackResultsInsightsPayload | undefined,
): FeedbackSurveyResultsData {
  const summary = data.summary || {};
  const aggregates = data.aggregates || [];
  const openComments = insights?.open_comments?.length ? insights.open_comments : data.open_comments || [];
  const voiceCountByQuestion = new Map<string, number>();
  for (const c of openComments) {
    if (c.answer_source !== "voice") continue;
    const key = String(c.theme || "voice");
    voiceCountByQuestion.set(key, (voiceCountByQuestion.get(key) || 0) + 1);
  }

  const questions: Question[] = aggregates.map((block, i) => {
    const id = `q${i + 1}`;
    const samples = openComments.filter((c) => c.answer_source === "voice").length;
    return aggregateToQuestion(block, id, samples);
  });

  const questionByTitle = new Map(questions.map((q) => [q.title, q.id]));

  const respondents: Respondent[] = (data.respondents || []).map((r) => {
    const sentiment = (r.sentiment_label as Respondent["sentiment"]) || "neutral";
    const completedTs = r.completed_at ? new Date(r.completed_at).getTime() : 0;
    return {
      id: String(r.id || ""),
      name: displayName(r.phone),
      type: respondentType(r.phone),
      mobile: String(r.phone || "—"),
      completedAt: formatRelative(r.completed_at),
      completedAtTs: Number.isNaN(completedTs) ? 0 : completedTs,
      sentiment,
      flagged: Boolean(r.flagged || r.is_unhappy),
      answers: mapRespondentAnswers(r, questionByTitle, questions),
    };
  });

  const voiceComments: VoiceComment[] = openComments
    .filter((c) => c.answer_source === "voice")
    .slice(0, 24)
    .map((c, i) => ({
      id: String(c.id || `v${i}`),
      name: c.sentiment === "negative" ? "Anonymous · Unhappy" : "Anonymous · Excellent",
      tone: c.sentiment === "negative" ? "destructive" : "success",
      transcript: String(c.text || ""),
      originalTranscript:
        c.original_text && String(c.original_text).trim() !== String(c.text || "").trim()
          ? String(c.original_text)
          : undefined,
      translationPending:
        String(c.text || "").trim() === TRANSLATION_UNAVAILABLE &&
        Boolean(c.original_text && String(c.original_text).trim()),
      reason: String(c.theme || "Feedback"),
      question: c.sentiment === "negative" ? "Why poor?" : "Anything else?",
    }));

  const textComments: TextComment[] = openComments
    .filter((c) => c.answer_source !== "voice")
    .slice(0, 32)
    .map((c) => ({
      quote: String(c.text || ""),
      rating: ratingFromSentiment(c.sentiment),
      theme: String(c.theme || "General"),
    }));

  const counts = summary.sentiment_counts || { unhappy: 0, neutral: 0, happy: 0 };
  const sentimentDistribution: SentimentSlice[] = [
    { name: "Unhappy", value: counts.unhappy || 0, color: "#ef4444" },
    { name: "Neutral", value: counts.neutral || 0, color: "#f59e0b" },
    { name: "Happy", value: counts.happy || 0, color: "#22c55e" },
  ].filter((d) => d.value > 0);

  const weeklyRaw = data.weekly_trend || [];
  const weeklyTrend: WeeklyTrendPoint[] = weeklyRaw.map((w) => ({
    week: w.week,
    satisfaction: w.satisfaction ?? null,
    positive: "positive" in w ? (w.positive ?? w.satisfaction ?? null) : (w.satisfaction ?? null),
    responses: w.responses ?? 0,
  }));

  let weeklyImprovementBadge: string | null = null;
  const withSat = weeklyTrend.filter((w) => w.satisfaction != null);
  if (withSat.length >= 2) {
    const first = withSat[0].satisfaction!;
    const last = withSat[withSat.length - 1].satisfaction!;
    const delta = last - first;
    if (delta !== 0) {
      weeklyImprovementBadge = `${delta > 0 ? "+" : ""}${delta} pts in ${withSat.length} weeks`;
    }
  }

  const completed = summary.completed_sessions ?? 0;
  const scans = summary.total_scans ?? 0;
  const locName = data.location_name || "All locations";

  const themes = (insights?.ai?.themes || []).map((t) => ({
    label: t.label,
    value: t.value,
    sentiment: t.sentiment,
  }));

  const recommendations = (insights?.ai?.recommendations || []).map((r) => ({
    title: r.title || "Recommendation",
    text: r.text || "",
    impact: r.impact || "Medium",
  }));

  return {
    pageTitle: locName === "All locations" ? "Customer feedback results" : locName,
    metaLine: `${completed.toLocaleString()} / ${Math.max(scans, completed).toLocaleString()} responses · ${data.rows?.length ?? 0} recent answers`,
    weeklyImprovementBadge,
    weeklyTrend,
    sentimentDistribution,
    questions,
    voiceComments,
    textComments,
    respondents,
    themes,
    recommendations,
    kpi: {
      satisfaction: summary.satisfaction_pct != null ? `${summary.satisfaction_pct}%` : "—",
      satisfactionSub: "good + excellent",
      recommend: summary.recommend_pct != null ? `${summary.recommend_pct}%` : "—",
      recommendSub: "yes / no question",
      responseRate:
        summary.completion_rate_pct != null ? `${summary.completion_rate_pct}%` : `${completed.toLocaleString()} sessions`,
      responseRateSub:
        summary.completion_rate_pct != null
          ? `${completed.toLocaleString()} of ${scans.toLocaleString()}`
          : `${completed.toLocaleString()} completed`,
      unhappy: String(summary.unhappy_count ?? counts.unhappy ?? 0),
      unhappySub: "needs follow up",
    },
  };
}
