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

export type RespondentAnswerRow = {
  question: string;
  type: "rating" | "yes_no" | "open";
  rating?: "poor" | "good" | "excellent";
  yesNo?: "yes" | "no";
  followUp?: BilingualAnswer;
  openText?: BilingualAnswer;
};

export type BilingualAnswer = {
  english: string;
  original?: string;
  translationPending?: boolean;
  source?: string;
};

export type Respondent = {
  id: string;
  name: string;
  type: "mobile" | "web";
  mobile: string;
  completedAt: string;
  completedAtTs: number;
  sentiment: "happy" | "neutral" | "unhappy";
  flagged: boolean;
  answers: RespondentAnswerRow[];
  answerDots: Array<
    | { type: "Rating"; value: "poor" | "good" | "excellent" }
    | { type: "Yes/No"; value: "yes" | "no" }
  >;
  aiFollowUp?: import("@/components/ai-follow-up-report").AiFollowUpReport | null;
  aiFollowUpStatus?: string | null;
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
  original?: string;
  translationPending?: boolean;
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

function hasArabicScript(text: string): boolean {
  return /[\u0600-\u06FF]/.test(text);
}

function normalizeBilingual(
  english: string,
  original?: string,
  opts?: { transcriptionStatus?: string | null; translationStatus?: string | null },
): BilingualAnswer {
  const en = english.trim();
  const orig = (original || "").trim();
  const transcriptionStatus = String(opts?.transcriptionStatus || "").toLowerCase();
  if (transcriptionStatus === "pending" || en === "Transcribing…") {
    return { english: "Transcribing…", translationPending: true };
  }
  if (transcriptionStatus === "failed" && !en && !orig) {
    return { english: "Transcription failed", translationPending: true };
  }
  if (en === TRANSLATION_UNAVAILABLE && orig) {
    return { english: TRANSLATION_UNAVAILABLE, original: orig, translationPending: true };
  }
  if (hasArabicScript(en) && orig && !hasArabicScript(orig)) {
    return { english: orig, original: en };
  }
  if (hasArabicScript(en) && !orig) {
    return { english: TRANSLATION_UNAVAILABLE, original: en, translationPending: true };
  }
  if (orig && orig !== en) {
    return { english: en || orig, original: orig };
  }
  return { english: en || orig };
}

function mapRespondentAnswers(r: FeedbackRespondent): RespondentAnswerRow[] {
  const items = r.answers || [];
  // Web CF pending flow saves `__tell_us_more`; older / reason_prev path saves `__low_reason`.
  // Prefer tell_us_more when both exist so Apple/web voice reasons show under the rating.
  const lowReasons = new Map<string, (typeof items)[number]>();
  for (const a of items) {
    const qk = String(a.question_key || "");
    if (qk.endsWith("__low_reason")) {
      const base = qk.slice(0, -"__low_reason".length);
      if (!lowReasons.has(base)) lowReasons.set(base, a);
    }
  }
  for (const a of items) {
    const qk = String(a.question_key || "");
    if (qk.endsWith("__tell_us_more")) {
      lowReasons.set(qk.slice(0, -"__tell_us_more".length), a);
    }
  }

  const rows: RespondentAnswerRow[] = [];
  for (const a of items) {
    const qk = String(a.question_key || "");
    if (qk.endsWith("__low_reason") || qk.endsWith("__tell_us_more")) continue;

    const question = String(a.question || "").trim();
    const raw = String(a.answer || "").trim();
    const original = String(a.original_text || "").trim();
    const role = String(a.step_role || "").toLowerCase();
    const bilingualOpts = {
      transcriptionStatus: a.transcription_status,
      translationStatus: a.translation_status,
    };

    if (role === "final_feedback_text" || qk === "open_question") {
      rows.push({
        question,
        type: "open",
        openText: { ...normalizeBilingual(raw, original, bilingualOpts), source: a.answer_source },
      });
      continue;
    }

    const yn = classifyYn(raw);
    if (yn || role.includes("recommend") || role === "yes_no" || role.includes("marketing")) {
      rows.push({ question, type: "yes_no", yesNo: yn || "no" });
      continue;
    }

    const pge = classifyPge(raw);
    if (pge || role === "rating") {
      const followRaw = lowReasons.get(qk);
      let followUp: BilingualAnswer | undefined;
      if (followRaw) {
        const fEn = String(followRaw.answer || "").trim();
        const fOrig = String(followRaw.original_text || "").trim();
        followUp = {
          ...normalizeBilingual(fEn, fOrig, {
            transcriptionStatus: followRaw.transcription_status,
            translationStatus: followRaw.translation_status,
          }),
          source: followRaw.answer_source,
        };
      }
      rows.push({ question, type: "rating", rating: pge || "poor", followUp });
      continue;
    }

    if (raw || original || String(a.transcription_status || "") === "pending") {
      rows.push({
        question,
        type: "open",
        openText: { ...normalizeBilingual(raw, original, bilingualOpts), source: a.answer_source },
      });
    }
  }
  return rows;
}

function mapAnswerDots(rows: RespondentAnswerRow[]): Respondent["answerDots"] {
  return rows.flatMap((row) => {
    if (row.type === "rating" && row.rating) return [{ type: "Rating" as const, value: row.rating }];
    if (row.type === "yes_no" && row.yesNo) return [{ type: "Yes/No" as const, value: row.yesNo }];
    return [];
  });
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

  const respondents: Respondent[] = (data.respondents || []).map((r) => {
    const sentiment = (r.sentiment_label as Respondent["sentiment"]) || "neutral";
    const completedTs = r.completed_at ? new Date(r.completed_at).getTime() : 0;
    const answerRows = mapRespondentAnswers(r);
    return {
      id: String(r.id || ""),
      name: displayName(r.phone),
      type: respondentType(r.phone),
      mobile: String(r.phone || "—"),
      completedAt: formatRelative(r.completed_at),
      completedAtTs: Number.isNaN(completedTs) ? 0 : completedTs,
      sentiment,
      flagged: Boolean(r.flagged || r.is_unhappy),
      answers: answerRows,
      answerDots: mapAnswerDots(answerRows),
      aiFollowUp: (r.ai_follow_up as Respondent["aiFollowUp"]) || null,
      aiFollowUpStatus: r.ai_follow_up_status || (r.ai_follow_up as { status?: string } | undefined)?.status || null,
    };
  });

  const voiceComments: VoiceComment[] = openComments
    .filter((c) => c.answer_source === "voice")
    .slice(0, 24)
    .map((c, i) => {
      const english = String(c.text || "").trim();
      const original = String(c.original_text || "").trim();
      const transcribing = String((c as { transcription_status?: string }).transcription_status || "") === "pending";
      return {
        id: String(c.id || `v${i}`),
        name: c.sentiment === "negative" ? "Anonymous · Unhappy" : "Anonymous · Excellent",
        tone: c.sentiment === "negative" ? "destructive" : "success",
        transcript: transcribing ? "Transcribing…" : english,
        originalTranscript:
          !transcribing && original && original !== english ? original : undefined,
        translationPending:
          transcribing ||
          (english === TRANSLATION_UNAVAILABLE && Boolean(original)),
        reason: String(c.theme || "Feedback"),
        question: c.sentiment === "negative" ? "Why poor?" : "Anything else?",
      };
    });

  const textComments: TextComment[] = openComments
    .filter((c) => c.answer_source !== "voice")
    .slice(0, 32)
    .map((c) => {
      const english = String(c.text || "").trim();
      const original = String(c.original_text || "").trim();
      return {
        quote: english,
        original: original && original !== english ? original : undefined,
        translationPending: english === TRANSLATION_UNAVAILABLE && Boolean(original),
        rating: ratingFromSentiment(c.sentiment),
        theme: String(c.theme || "General"),
      };
    });

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
