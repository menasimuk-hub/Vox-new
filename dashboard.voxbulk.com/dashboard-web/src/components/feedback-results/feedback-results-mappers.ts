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
  audioUrl?: string | null;
};

function voiceAudioUrl(row: {
  audio_url?: string | null;
  voice_note_job_id?: string | null;
}): string | null {
  const direct = String(row.audio_url || "").trim();
  if (direct) return direct;
  const jobId = String(row.voice_note_job_id || "").trim();
  if (!jobId) return null;
  return `/customer-feedback/results/voice-notes/${jobId}/audio`;
}

export type Respondent = {
  id: string;
  name: string;
  /** Survey entry channel shown in results */
  type: "whatsapp" | "web";
  mobile: string;
  callbackConsent?: boolean | null;
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
  audioUrl?: string | null;
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

function respondentType(
  phone: string | null | undefined,
  entryChannel?: string | null,
): "whatsapp" | "web" {
  const channel = String(entryChannel || "").trim().toLowerCase();
  if (channel === "web") return "web";
  if (channel === "whatsapp") return "whatsapp";
  return String(phone || "").startsWith("web:") ? "web" : "whatsapp";
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

function followUpBaseKey(questionKey: string): string | null {
  const qk = String(questionKey || "");
  if (qk.endsWith("__tell_us_more")) return qk.slice(0, -"__tell_us_more".length);
  if (qk.endsWith("__low_reason")) return qk.slice(0, -"__low_reason".length);
  return null;
}

function answerMergeKey(a: NonNullable<FeedbackRespondent["answers"]>[number]): string {
  const qk = String(a.question_key || "");
  const st = String((a as { survey_type_id?: string }).survey_type_id || "");
  return st ? `${st}::${qk}` : qk;
}

function toFollowUp(
  followRaw: NonNullable<FeedbackRespondent["answers"]>[number],
): BilingualAnswer {
  const fEn = String(followRaw.answer || "").trim();
  const fOrig = String(followRaw.original_text || "").trim();
  return {
    ...normalizeBilingual(fEn, fOrig, {
      transcriptionStatus: followRaw.transcription_status,
      translationStatus: followRaw.translation_status,
    }),
    source: followRaw.answer_source,
    audioUrl: voiceAudioUrl(followRaw),
  };
}

function mapRespondentAnswers(r: FeedbackRespondent): RespondentAnswerRow[] {
  const items = r.answers || [];
  // Attach tell-us-more / low-reason rows to parents; never drop unmatched voices.
  // Key by survey_type_id + base question_key so three topics don't collapse into one.
  const lowReasons = new Map<string, (typeof items)[number]>();
  const attachedFollowUpIds = new Set<string>();

  for (const a of items) {
    const base = followUpBaseKey(String(a.question_key || ""));
    if (!base) continue;
    const st = String((a as { survey_type_id?: string }).survey_type_id || "");
    const key = st ? `${st}::${base}` : base;
    // Prefer tell_us_more over low_reason when both exist for the same parent.
    const qk = String(a.question_key || "");
    if (qk.endsWith("__tell_us_more") || !lowReasons.has(key)) {
      lowReasons.set(key, a);
    }
  }

  const rows: RespondentAnswerRow[] = [];
  for (const a of items) {
    const qk = String(a.question_key || "");
    if (followUpBaseKey(qk)) continue;

    const question = String(a.question || qk || "Question").trim() || "Question";
    const raw = String(a.answer || "").trim();
    const original = String(a.original_text || "").trim();
    const role = String(a.step_role || "").toLowerCase();
    const source = String(a.answer_source || "text").toLowerCase();
    const isVoice = source === "voice" || source === "voice_note";
    const bilingualOpts = {
      transcriptionStatus: a.transcription_status,
      translationStatus: a.translation_status,
    };
    const parentKey = answerMergeKey(a);
    const followRaw = lowReasons.get(parentKey) || lowReasons.get(qk);
    const followUp = followRaw ? toFollowUp(followRaw) : undefined;
    if (followRaw) {
      const fid = String((followRaw as { id?: string }).id || followRaw.question_key || "");
      if (fid) attachedFollowUpIds.add(fid);
      // Also mark by question_key so unmatched pass can skip.
      attachedFollowUpIds.add(String(followRaw.question_key || ""));
    }

    if (role === "final_feedback_text" || qk === "open_question" || role.includes("open")) {
      rows.push({
        question,
        type: "open",
        openText: {
          ...normalizeBilingual(raw, original, bilingualOpts),
          source: a.answer_source,
          audioUrl: voiceAudioUrl(a),
        },
      });
      continue;
    }

    // Never classify voice transcripts as rating / yes-no — that strips audio.
    if (!isVoice) {
      const yn = classifyYn(raw);
      if (yn || role.includes("recommend") || role === "yes_no" || role.includes("marketing")) {
        rows.push({ question, type: "yes_no", yesNo: yn || "no", followUp });
        continue;
      }

      const pge = classifyPge(raw);
      if (pge || role === "rating") {
        rows.push({ question, type: "rating", rating: pge || "poor", followUp });
        continue;
      }
    }

    if (raw || original || String(a.transcription_status || "") === "pending" || voiceAudioUrl(a)) {
      rows.push({
        question,
        type: "open",
        openText: {
          ...normalizeBilingual(raw, original, bilingualOpts),
          source: a.answer_source,
          audioUrl: voiceAudioUrl(a),
        },
        followUp,
      });
    }
  }

  // Emit any tell-us-more / low-reason rows that were not attached to a parent.
  for (const a of items) {
    const qk = String(a.question_key || "");
    const base = followUpBaseKey(qk);
    if (!base) continue;
    const id = String((a as { id?: string }).id || "");
    if ((id && attachedFollowUpIds.has(id)) || attachedFollowUpIds.has(qk)) continue;
    const question = String(a.question || base || "Tell us more").trim() || "Tell us more";
    const raw = String(a.answer || "").trim();
    const original = String(a.original_text || "").trim();
    rows.push({
      question: `${question} — tell us more`,
      type: "open",
      openText: {
        ...normalizeBilingual(raw, original, {
          transcriptionStatus: a.transcription_status,
          translationStatus: a.translation_status,
        }),
        source: a.answer_source,
        audioUrl: voiceAudioUrl(a),
      },
    });
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
    const qk = String(block.question_key || "");
    const qLabel = String(block.question || "");
    const samples = openComments.filter((c) => {
      if (c.answer_source !== "voice") return false;
      const cqk = String(c.question_key || "");
      const cq = String(c.question || "");
      return (qk && cqk === qk) || (qLabel && cq === qLabel) || (c.theme && c.theme === qLabel);
    }).length;
    return aggregateToQuestion(block, id, samples);
  });

  const respondents: Respondent[] = (data.respondents || []).map((r) => {
    const sentiment = (r.sentiment_label as Respondent["sentiment"]) || "neutral";
    const completedTs = r.completed_at ? new Date(r.completed_at).getTime() : 0;
    const answerRows = mapRespondentAnswers(r);
    return {
      id: String(r.id || ""),
      name: displayName(r.phone),
      type: respondentType(r.phone, r.entry_channel),
      mobile: String(r.phone || "—"),
      callbackConsent:
        typeof r.callback_consent === "boolean" ? r.callback_consent : r.callback_consent == null ? null : Boolean(r.callback_consent),
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
        question: String(c.question || c.question_key || "Voice answer").trim() || "Voice answer",
        audioUrl: c.audio_url || (c.voice_note_job_id ? `/customer-feedback/results/voice-notes/${c.voice_note_job_id}/audio` : null),
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
