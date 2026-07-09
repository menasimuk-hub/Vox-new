import { Link } from "@tanstack/react-router";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiFetch, apiUpload, getApiBaseUrl } from "@/lib/api";
import { buildCopy, getThemePack, resolveThemeId } from "./theme-registry";
import type { Copy, SurveyPayload, SurveyQuestion, Theme, ThemePack } from "./types";
import { VoiceDetail, type VoiceDetailHandle } from "./VoiceDetail";
import "./survey-themes.css";

type AdvanceResponse = {
  completed?: boolean;
  step_index?: number;
  step_count?: number;
  question?: SurveyQuestion;
  pending_tell_us_more?: boolean;
  deadline_at?: string | null;
};

type SessionStatusResponse = AdvanceResponse & {
  ok?: boolean;
  session_status?: string;
};

type Phase = "loading" | "error" | "choose" | "survey" | "thanks";

type ReasonOverlay = {
  reason_options?: string[];
  reason_prompt?: string;
};

export type PublicFeedbackSurveyProps = {
  token: string;
  previewThemeId?: string;
  previewCompanyName?: string;
};

function logoSrc(logoUrl?: string) {
  if (!logoUrl) return "";
  return `${getApiBaseUrl().replace(/\/+$/, "")}${logoUrl}`;
}

function WhatsAppGlyph() {
  return (
    <svg viewBox="0 0 32 32" className="h-9 w-9" fill="currentColor" aria-hidden>
      <path d="M16 3C8.82 3 3 8.82 3 16c0 2.29.6 4.43 1.66 6.29L3 29l6.9-1.62A12.94 12.94 0 0 0 16 29c7.18 0 13-5.82 13-13S23.18 3 16 3Zm7.4 18.46c-.31.87-1.82 1.66-2.5 1.71-.66.05-1.31.27-4.4-.93-3.71-1.45-6.07-5.27-6.25-5.52-.18-.25-1.5-1.99-1.5-3.8 0-1.81.95-2.69 1.28-3.07.34-.37.74-.46.99-.46.25 0 .49 0 .71.01.23.01.53-.09.83.64.31.74 1.05 2.55 1.14 2.73.09.18.15.4.03.65-.12.25-.18.4-.37.61-.18.21-.39.47-.55.63-.18.18-.37.39-.16.74.21.34.94 1.55 2.02 2.5 1.39 1.23 2.56 1.6 2.9 1.78.34.18.55.15.74-.09.21-.25.86-1 1.09-1.34.22-.34.46-.28.77-.17.31.12 1.97.93 2.31 1.1.34.17.56.25.65.39.09.13.09.74-.22 1.61Z" />
    </svg>
  );
}

function SparkGlyph() {
  return (
    <svg viewBox="0 0 24 24" className="h-9 w-9" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M12 2l1.8 5.4L19 9l-5.2 1.6L12 16l-1.8-5.4L5 9l5.2-1.6L12 2z" fill="currentColor" fillOpacity="0.15" />
      <path d="M19 15l.9 2.6L22 18.5l-2.1.9L19 22l-.9-2.6L16 18.5l2.1-.9L19 15z" fill="currentColor" fillOpacity="0.25" />
    </svg>
  );
}

function ArrowGlyph({ className = "" }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={`h-5 w-5 shrink-0 transition-transform group-hover:translate-x-0.5 ${className}`}
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M5 12h14M13 5l7 7-7 7" />
    </svg>
  );
}

function SurveyThankYou({
  theme,
  copy,
  Art,
}: {
  theme: Theme;
  copy: Copy;
  Art: ThemePack["Art"];
}) {
  return (
    <main
      className={`relative grid h-[100svh] place-items-center overflow-hidden px-6 ${theme.bgClass}`}
      style={{ color: theme.ink }}
    >
      <Art />
      <div className="relative max-w-sm text-center">
        <div
          className="animate-tick-pop mx-auto grid h-20 w-20 place-items-center rounded-full text-white shadow-lift"
          style={{ background: theme.gradientButton }}
        >
          <svg viewBox="0 0 24 24" className="h-9 w-9" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
            <path d="M5 12l5 5L20 7" />
          </svg>
        </div>
        <h1 className="animate-confetti-rise mt-6 font-display text-4xl" style={{ animationDelay: "120ms" }}>
          {copy.thankYouTitle}
          <span style={{ color: theme.accent }}>.</span>
        </h1>
        <p
          className="animate-confetti-rise mt-3 text-[15px] leading-relaxed"
          style={{ animationDelay: "240ms", color: theme.sub }}
        >
          {copy.thankYouSubtitle}
        </p>
        <Link
          to="/"
          className="animate-confetti-rise mt-8 inline-flex items-center gap-2 rounded-full border px-5 py-2.5 text-sm font-medium shadow-soft transition-transform hover:-translate-y-0.5"
          style={{ animationDelay: "360ms", background: theme.card, borderColor: theme.border, color: theme.ink }}
        >
          Back to start
        </Link>
      </div>
    </main>
  );
}

function WelcomeChoose({
  payload,
  theme,
  copy,
  busy,
  error,
  onStartWeb,
}: {
  payload: SurveyPayload;
  theme: Theme;
  copy: Copy;
  busy: boolean;
  error: string;
  onStartWeb: () => void;
}) {
  const bgClass = theme.bgClass || "bg-warm-gradient";
  const logo = logoSrc(payload.logo_url);

  return (
    <main className={`relative h-[100svh] overflow-hidden ${bgClass}`} style={{ color: theme.ink }}>
      <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="animate-float-blob absolute -left-24 top-10 h-72 w-72 rounded-full blur-3xl" style={{ background: `${theme.accent}26` }} />
        <div className="animate-float-blob-2 absolute -right-20 bottom-10 h-80 w-80 rounded-full blur-3xl" style={{ background: `${theme.accent2}4d` }} />
        <svg className="animate-orbit-slow absolute -right-20 top-24 h-64 w-64 opacity-10" viewBox="0 0 200 200" fill="none">
          <circle cx="100" cy="100" r="80" stroke="currentColor" strokeDasharray="2 8" style={{ color: theme.ink }} />
        </svg>
      </div>

      <div className="relative mx-auto flex h-[100svh] w-full max-w-md flex-col px-5 pb-5 pt-4 sm:max-w-lg sm:px-6 sm:pt-6">
        <header className="animate-rise flex flex-col items-center gap-2 text-center" style={{ animationDelay: "60ms" }}>
          {logo ? (
            <img
              src={logo}
              alt=""
              className="animate-tilt-hover h-10 w-10 rounded-xl p-1 shadow-lift ring-1"
              style={{ background: theme.card, borderColor: theme.border }}
            />
          ) : null}
          <span className="font-display text-[15px] tracking-tight">{copy.companyName}</span>
        </header>

        <div className="mt-5 sm:mt-8">
          <h1
            className="animate-rise mt-2 font-display text-[34px] leading-[1.05] sm:text-5xl"
            style={{ animationDelay: "300ms", color: theme.ink }}
          >
            We&apos;d love your
            <br />
            <span className="italic" style={{ color: theme.ink, opacity: 0.9 }}>feedback</span>
            <span style={{ color: theme.accent }}>.</span>
          </h1>
          {payload.branch_name ? (
            <p className="animate-rise mt-2 text-[13px]" style={{ animationDelay: "360ms", color: theme.sub }}>
              {payload.branch_name}
            </p>
          ) : null}
          <p
            className="animate-rise mt-3 max-w-sm text-[13.5px] leading-relaxed"
            style={{ animationDelay: "400ms", color: theme.sub }}
          >
            Under a minute — voice or tap. Choose how you&apos;d like to respond.
          </p>
        </div>

        <div className="animate-rise mt-4" style={{ animationDelay: "480ms" }}>
          <div
            className="inline-flex items-start gap-2 rounded-full border px-3 py-1.5 text-[11.5px] leading-snug shadow-soft backdrop-blur"
            style={{ background: `${theme.card}b3`, borderColor: theme.border, color: theme.sub }}
          >
            <span aria-hidden>🌍</span>
            <span>WhatsApp = all languages · Web = English</span>
          </div>
        </div>

        <div className="mt-5 grid gap-3">
          {payload.wa_url ? (
            <a
              href={payload.wa_url}
              target="_blank"
              rel="noopener noreferrer"
              className="animate-rise group relative overflow-hidden rounded-2xl p-4 text-left shadow-lift transition-transform active:scale-[0.98] hover:-translate-y-0.5"
              style={{ animationDelay: "560ms", background: "#25D366", color: "#fff" }}
            >
              <div className="flex items-center gap-3.5">
                <span className="animate-float-icon shrink-0 drop-shadow-[0_4px_8px_rgba(0,0,0,0.25)]" style={{ animationDelay: "0s" }}>
                  <WhatsAppGlyph />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="text-[15.5px] font-semibold tracking-tight">Continue on WhatsApp</div>
                  <div className="mt-0.5 text-[11.5px] opacity-85">💬 Reply in your own language</div>
                </div>
                <ArrowGlyph />
              </div>
              <span aria-hidden className="absolute -right-10 -top-10 h-32 w-32 rounded-full bg-white/10 blur-2xl transition-transform group-hover:scale-125" />
            </a>
          ) : null}

          <button
            type="button"
            disabled={busy}
            onClick={onStartWeb}
            className="animate-rise group relative overflow-hidden rounded-2xl border p-4 text-left shadow-soft transition-transform active:scale-[0.98] hover:-translate-y-0.5 disabled:opacity-60"
            style={{ animationDelay: "640ms", background: theme.card, borderColor: theme.border, color: theme.ink }}
          >
            <div className="flex items-center gap-3.5">
              <span
                className="animate-float-icon shrink-0 drop-shadow-[0_4px_10px_rgba(180,140,60,0.35)]"
                style={{ animationDelay: "0.7s", color: theme.ink }}
              >
                <SparkGlyph />
              </span>
              <div className="min-w-0 flex-1">
                <div className="text-[15.5px] font-semibold tracking-tight">Complete here</div>
                <div className="mt-0.5 text-[11.5px]" style={{ color: theme.sub }}>
                  Quick on-page survey · English
                </div>
              </div>
              <ArrowGlyph className="opacity-60" />
            </div>
            <span
              aria-hidden
              className="absolute -left-10 -bottom-10 h-32 w-32 rounded-full blur-2xl transition-transform group-hover:scale-125"
              style={{ background: `${theme.accent}66` }}
            />
          </button>
        </div>

        {error ? <p className="mt-3 text-center text-[13px] text-red-600">{error}</p> : null}

        <footer className="animate-rise mt-auto pt-4 text-center text-[10.5px]" style={{ animationDelay: "780ms", color: theme.sub, opacity: 0.8 }}>
          Your reply is private and only shared with {copy.companyName}.
        </footer>
      </div>
    </main>
  );
}

function QuestionView({
  theme,
  index,
  question,
  disabled,
  onSelect,
}: {
  theme: Theme;
  index: number;
  question: SurveyQuestion;
  disabled: boolean;
  onSelect: (value: string, low?: boolean) => void;
}) {
  return (
    <div className="animate-rise">
      <p className="text-[11px] font-medium uppercase tracking-[0.2em]" style={{ color: theme.sub }}>
        Question {index + 1}
      </p>
      <h1 className="mt-2 font-display text-[28px] leading-[1.15] sm:text-[32px]">{question.title}</h1>
      {question.body ? (
        <p className="mt-2 text-[13px] leading-relaxed" style={{ color: theme.sub }}>{question.body}</p>
      ) : null}
      <div className="mt-6 grid gap-2.5">
        {(question.options || []).map((opt) => {
          const isLow = (question.low_values || []).includes(opt.value);
          return (
            <button
              key={opt.value}
              type="button"
              disabled={disabled}
              onClick={() => onSelect(opt.value, isLow)}
              className="group flex items-center justify-between rounded-2xl border px-4 py-3.5 text-left text-[15px] font-medium transition-all active:scale-[0.98] disabled:opacity-50"
              style={{ background: theme.card, borderColor: theme.border, color: theme.ink }}
            >
              <span>{opt.label}</span>
              <span
                className="grid h-5 w-5 place-items-center rounded-full"
                style={{ border: `1px solid ${theme.border}` }}
              />
            </button>
          );
        })}
      </div>
    </div>
  );
}

function SurveyFooter({
  theme,
  showSkip,
  nextLabel,
  nextDisabled,
  backDisabled,
  busy,
  onBack,
  onSkip,
  onNext,
}: {
  theme: Theme;
  showSkip: boolean;
  nextLabel: string;
  nextDisabled: boolean;
  backDisabled: boolean;
  busy: boolean;
  onBack: () => void;
  onSkip: () => void;
  onNext: () => void;
}) {
  return (
    <div className="flex items-center gap-3">
      <button
        type="button"
        onClick={onBack}
        disabled={backDisabled || busy}
        className="inline-flex h-12 items-center gap-1.5 rounded-full border px-4 text-sm font-medium shadow-soft transition-all active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-40"
        style={{ background: theme.card, borderColor: theme.border, color: theme.ink }}
      >
        <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <path d="M15 18l-6-6 6-6" />
        </svg>
        Back
      </button>
      {showSkip ? (
        <button
          type="button"
          onClick={onSkip}
          disabled={busy}
          className="inline-flex h-12 items-center rounded-full px-4 text-sm font-medium transition-all hover:opacity-80 disabled:opacity-40"
          style={{ color: theme.sub }}
        >
          Skip
        </button>
      ) : null}
      <button
        type="button"
        onClick={onNext}
        disabled={nextDisabled || busy}
        className="inline-flex h-12 flex-1 items-center justify-center gap-2 rounded-full px-6 text-sm font-semibold text-white shadow-lift transition-all active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-40"
        style={{ background: theme.gradientButton }}
      >
        {nextLabel}
        <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <path d="M5 12h14M13 5l7 7-7 7" />
        </svg>
      </button>
    </div>
  );
}

export function PublicFeedbackSurvey({
  token,
  previewThemeId,
  previewCompanyName,
}: PublicFeedbackSurveyProps) {
  const [phase, setPhase] = useState<Phase>("loading");
  const [error, setError] = useState("");
  const [payload, setPayload] = useState<SurveyPayload | null>(null);
  const [sessionId, setSessionId] = useState("");
  const [stepIndex, setStepIndex] = useState(0);
  const [question, setQuestion] = useState<SurveyQuestion | null>(null);
  const [stepCount, setStepCount] = useState(0);
  const [busy, setBusy] = useState(false);
  const [pendingSends, setPendingSends] = useState(0);

  const [reasonOverlay, setReasonOverlay] = useState<ReasonOverlay | null>(null);
  const [reasonChips, setReasonChips] = useState<string[]>([]);
  const [reasonText, setReasonText] = useState("");
  const [textAnswer, setTextAnswer] = useState("");

  const [tellUsMorePending, setTellUsMorePending] = useState(false);
  const [deadlineAt, setDeadlineAt] = useState<string | null>(null);
  const [detailVoicePending, setDetailVoicePending] = useState(false);
  const [reasonVoicePending, setReasonVoicePending] = useState(false);

  const sendQueueRef = useRef<Promise<unknown>>(Promise.resolve());
  const navEpochRef = useRef(0);
  const stepIndexRef = useRef(0);
  const detailRef = useRef<VoiceDetailHandle>(null);
  const reasonRef = useRef<VoiceDetailHandle>(null);
  const isPreview = Boolean(previewThemeId);

  const themePack = useMemo(() => {
    if (!payload) return getThemePack("survey-temp", "Your business");
    const themeId = resolveThemeId(payload.theme_id, payload.industry_slug, payload.web_theme);
    return getThemePack(themeId, payload.company_name, payload.industry_name);
  }, [payload]);

  const copy = useMemo(() => {
    if (!payload) return buildCopy(themePack, "Your business");
    return buildCopy(themePack, payload.company_name, payload.industry_name);
  }, [payload, themePack]);

  const theme = themePack.theme;
  const Art = themePack.Art;
  const questions = payload?.questions ?? [];

  useEffect(() => {
    stepIndexRef.current = stepIndex;
  }, [stepIndex]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setPhase("loading");
      setError("");
      try {
        if (previewThemeId) {
          const mock: SurveyPayload = {
            company_name: previewCompanyName || "Preview business",
            branch_name: "Preview branch",
            industry_name: "Preview",
            step_count: 3,
            theme_id: previewThemeId,
            questions: [
              {
                kind: "topic",
                title: "How would you rate your overall experience?",
                body: "Tap one option",
                input: "choice",
                options: [
                  { label: "😊 Excellent", value: "Excellent" },
                  { label: "🙂 Good", value: "Good" },
                  { label: "😞 Poor", value: "Poor" },
                ],
                is_rating: true,
                low_values: ["Poor"],
                reason_prompt: "Sorry to hear that. What went wrong?",
                reason_options: ["Service", "Speed", "Staff"],
              },
              {
                kind: "topic",
                title: "Would you recommend us?",
                body: "",
                input: "choice",
                options: [
                  { label: "👍 Yes", value: "yes" },
                  { label: "🤔 Maybe", value: "maybe" },
                  { label: "👎 No", value: "no" },
                ],
              },
              {
                kind: "open_question",
                title: "Anything else to share?",
                body: "Optional — type or record a voice note.",
                input: "text",
                options: [],
                allow_voice: true,
              },
            ],
          };
          if (!cancelled) {
            setPayload(mock);
            setPhase("choose");
          }
          return;
        }
        const data = await apiFetch<{ ok?: boolean } & SurveyPayload>(
          `/public/feedback/survey/${encodeURIComponent(token)}`,
        );
        if (!cancelled) {
          setPayload(data);
          setPhase("choose");
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Survey not found");
          setPhase("error");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token, previewThemeId, previewCompanyName]);

  const progress = useMemo(() => {
    if (!stepCount) return 0;
    return ((stepIndex + 1) / stepCount) * 100;
  }, [stepIndex, stepCount]);

  const enqueue = useCallback((task: () => Promise<unknown>) => {
    setPendingSends((n) => n + 1);
    const next = sendQueueRef.current
      .catch(() => undefined)
      .then(() => task())
      .catch((e) => {
        setError(e instanceof Error ? e.message : "Some answers could not be saved");
      })
      .finally(() => setPendingSends((n) => Math.max(0, n - 1)));
    sendQueueRef.current = next;
    return next;
  }, []);

  const bumpNavEpoch = () => {
    navEpochRef.current += 1;
    return navEpochRef.current;
  };

  const goToStep = useCallback(
    (
      idx: number,
      opts?: { reasonAfter?: ReasonOverlay | null; question?: SurveyQuestion | null },
    ) => {
      bumpNavEpoch();
      setTextAnswer("");
      setReasonChips([]);
      setReasonText("");
      if (idx >= stepCount) {
        setReasonOverlay(null);
        setPhase("thanks");
        return;
      }
      setStepIndex(idx);
      setQuestion(opts?.question ?? questions[idx] ?? null);
      setReasonOverlay(opts?.reasonAfter ?? null);
    },
    [questions, stepCount],
  );

  const applyAdvance = useCallback(
    (epoch: number, data: AdvanceResponse, fallbackNext: number) => {
      if (epoch !== navEpochRef.current) return;
      if (data.completed) {
        setTellUsMorePending(false);
        setDeadlineAt(null);
        setReasonOverlay(null);
        setPhase("thanks");
        return;
      }
      if (data.pending_tell_us_more) {
        setTellUsMorePending(true);
        setDeadlineAt(data.deadline_at ?? null);
        if (data.question) setQuestion(data.question);
        return;
      }
      setTellUsMorePending(false);
      setDeadlineAt(null);
      if (typeof data.step_index === "number") {
        goToStep(data.step_index, { question: data.question ?? null });
        return;
      }
      goToStep(fallbackNext);
    },
    [goToStep],
  );

  const postAnswer = (answer: string, opts?: { reason?: string; reasonSource?: string }) =>
    apiFetch(`/public/feedback/survey/sessions/${encodeURIComponent(sessionId)}/answer`, {
      method: "POST",
      body: JSON.stringify({
        answer,
        reason: opts?.reason,
        reason_source: opts?.reasonSource || "text",
      }),
    });

  const postVoice = (blob: Blob, mode: string, answer?: string) => {
    const form = new FormData();
    form.append("file", blob, "voice.webm");
    form.append("mode", mode);
    if (answer != null) form.append("answer", answer);
    return apiUpload(`/public/feedback/survey/sessions/${encodeURIComponent(sessionId)}/voice`, form);
  };

  const answerStep = (answer: string, opts?: { showReasonAfter?: ReasonOverlay }) => {
    if (!sessionId && !isPreview) return;
    setError("");
    const epoch = navEpochRef.current;
    if (isPreview) {
      if (opts?.showReasonAfter) {
        setReasonOverlay(opts.showReasonAfter);
        return;
      }
      goToStep(stepIndex + 1);
      return;
    }
    if (opts?.showReasonAfter) {
      enqueue(async () => {
        const data = (await postAnswer(answer)) as AdvanceResponse;
        if (epoch !== navEpochRef.current) return;
        if (data.pending_tell_us_more) {
          setTellUsMorePending(true);
          setDeadlineAt(data.deadline_at ?? null);
          if (data.question) setQuestion(data.question);
          setReasonOverlay(opts.showReasonAfter ?? null);
          return;
        }
        setReasonOverlay(opts.showReasonAfter);
      });
      return;
    }
    enqueue(async () => {
      const data = (await postAnswer(answer)) as AdvanceResponse;
      applyAdvance(epoch, data, stepIndex + 1);
    });
  };

  const submitDetailStep = async (mode: "answer" | "reason") => {
    if (!sessionId && !isPreview) return;
    const ref = mode === "reason" ? reasonRef : detailRef;
    const voiceBlob = ref.current?.getBlob();
    const text = (ref.current?.getText() || (mode === "reason" ? reasonText : textAnswer)).trim();
    const chips = mode === "reason" ? reasonChips : [];
    const combinedText = [chips.join(", "), text].filter(Boolean).join(" — ");

    if (mode === "reason") {
      setReasonOverlay(null);
      setReasonChips([]);
      setReasonText("");
      setTellUsMorePending(false);
      setDeadlineAt(null);
    }

    if (isPreview) {
      goToStep(stepIndexRef.current + 1);
      return;
    }

    const epoch = navEpochRef.current;

    if (voiceBlob) {
      if (mode === "reason") {
        setBusy(true);
        try {
          const voiceRes = (await postVoice(voiceBlob, "transcribe")) as { transcript?: string };
          const transcript = String(voiceRes.transcript || "").trim();
          if (!transcript) {
            setError("Could not transcribe your voice note. Please try again or type your answer.");
            return;
          }
          const data = (await postAnswer("skip", {
            reason: transcript,
            reasonSource: "voice",
          })) as AdvanceResponse;
          applyAdvance(epoch, data, stepIndexRef.current + 1);
        } catch (e) {
          setError(e instanceof Error ? e.message : "Could not save voice answer");
        } finally {
          setBusy(false);
        }
        return;
      }
      setBusy(true);
      try {
        const data = (await postVoice(voiceBlob, "answer")) as AdvanceResponse & { saved?: boolean };
        if (data.saved === false) {
          setError("Could not save your voice answer. Please try again.");
          return;
        }
        applyAdvance(epoch, data, stepIndexRef.current + 1);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Could not save voice answer");
      } finally {
        setBusy(false);
      }
      return;
    }

    if (mode === "reason") {
      const reason = combinedText || "skip";
      enqueue(async () => {
        const data = (await postAnswer("skip", {
          reason: reason.toLowerCase() === "skip" ? "skip" : reason,
          reasonSource: "text",
        })) as AdvanceResponse;
        applyAdvance(epoch, data, stepIndex + 1);
      });
      return;
    }

    if (combinedText) {
      enqueue(async () => {
        const data = (await postAnswer(combinedText)) as AdvanceResponse;
        applyAdvance(epoch, data, stepIndex + 1);
      });
    }
  };

  const skipDetailStep = (mode: "answer" | "reason") => {
    if (isPreview) {
      goToStep(stepIndex + 1);
      return;
    }
    if (mode === "reason") {
      setReasonOverlay(null);
      setReasonChips([]);
      setReasonText("");
      const epoch = navEpochRef.current;
      enqueue(async () => {
        const data = (await postAnswer("skip", { reason: "skip", reasonSource: "text" })) as AdvanceResponse;
        applyAdvance(epoch, data, stepIndex + 1);
      });
      return;
    }
    answerStep("skip");
  };

  const startWeb = async () => {
    setBusy(true);
    setError("");
    try {
      if (isPreview && payload) {
        setSessionId("preview");
        setStepIndex(0);
        setStepCount(payload.questions.length);
        setQuestion(payload.questions[0] ?? null);
        setPhase("survey");
        return;
      }
      const data = await apiFetch<{ ok?: boolean; session_id?: string } & AdvanceResponse>(
        `/public/feedback/survey/${encodeURIComponent(token)}/sessions`,
        { method: "POST" },
      );
      setSessionId(String(data.session_id || ""));
      setStepIndex(Number(data.step_index ?? 0));
      setStepCount(Number(data.step_count ?? 0));
      setQuestion(data.question || null);
      setPhase("survey");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start survey");
    } finally {
      setBusy(false);
    }
  };

  const goBack = async () => {
    if (reasonOverlay) {
      setReasonOverlay(null);
      setReasonChips([]);
      setReasonText("");
      return;
    }
    if (stepIndex <= 0 || !sessionId) return;
    setBusy(true);
    setError("");
    try {
      await sendQueueRef.current.catch(() => undefined);
      await apiFetch(`/public/feedback/survey/sessions/${encodeURIComponent(sessionId)}/back`, {
        method: "POST",
      });
      goToStep(stepIndex - 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not go back");
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    if (!tellUsMorePending || !sessionId || isPreview) return;

    let cancelled = false;
    let intervalId = 0;
    let timeoutId = 0;

    const pollStatus = async () => {
      try {
        const data = await apiFetch<SessionStatusResponse>(
          `/public/feedback/survey/sessions/${encodeURIComponent(sessionId)}/status`,
        );
        if (cancelled) return;
        const epoch = navEpochRef.current;
        if (data.completed) {
          applyAdvance(epoch, data, stepIndexRef.current + 1);
          return;
        }
        if (!data.pending_tell_us_more) {
          applyAdvance(epoch, data, stepIndexRef.current + 1);
        }
      } catch {
        /* status endpoint may be unavailable; ignore transient errors */
      }
    };

    void pollStatus();
    intervalId = window.setInterval(() => void pollStatus(), 30_000);

    if (deadlineAt) {
      const ms = new Date(deadlineAt).getTime() - Date.now();
      if (ms > 0) {
        timeoutId = window.setTimeout(() => void pollStatus(), ms);
      } else {
        void pollStatus();
      }
    }

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
      window.clearTimeout(timeoutId);
    };
  }, [tellUsMorePending, sessionId, deadlineAt, applyAdvance]);

  const q = question;
  const isText = q?.input === "text";
  const isLast = stepIndex >= stepCount - 1;
  const inReasonOverlay = reasonOverlay !== null;
  const activeDetailRef = inReasonOverlay ? reasonRef : detailRef;
  const voicePending = inReasonOverlay ? reasonVoicePending : detailVoicePending;
  const detailText = inReasonOverlay ? reasonText : textAnswer;
  const recordedBlob = activeDetailRef.current?.getBlob() ?? null;
  const isRecording = voicePending && !recordedBlob;
  const canSubmitDetail =
    !isRecording &&
    (Boolean(recordedBlob) ||
      Boolean(detailText.trim()) ||
      (inReasonOverlay && reasonChips.length > 0));

  return (
    <div className="feedback-survey-root">
      {phase === "loading" && (
        <main className={`grid h-[100svh] place-items-center ${theme.bgClass}`} style={{ color: theme.ink }}>
          <p className="text-sm" style={{ color: theme.sub }}>Loading survey…</p>
        </main>
      )}

      {phase === "error" && (
        <main className={`grid h-[100svh] place-items-center px-6 ${theme.bgClass}`} style={{ color: theme.ink }}>
          <div className="max-w-sm text-center">
            <p className="text-red-600">{error}</p>
            <Link to="/" className="mt-4 inline-block text-sm underline" style={{ color: theme.sub }}>
              Back to VoxBulk
            </Link>
          </div>
        </main>
      )}

      {phase === "choose" && payload ? (
        <WelcomeChoose
          payload={payload}
          theme={theme}
          copy={copy}
          busy={busy}
          error={error}
          onStartWeb={startWeb}
        />
      ) : null}

      {phase === "thanks" ? <SurveyThankYou theme={theme} copy={copy} Art={Art} /> : null}

      {phase === "survey" && payload && q ? (
        <main className={`relative flex h-[100svh] flex-col overflow-hidden ${theme.bgClass}`} style={{ color: theme.ink }}>
          <Art />
          <div className="relative mx-auto flex h-[100svh] w-full max-w-md flex-col px-5 pb-5 pt-4 sm:max-w-lg sm:pt-6">
            <div className="flex items-center justify-between">
              <div className="inline-flex items-center gap-2">
                {payload.logo_url ? (
                  <img
                    src={logoSrc(payload.logo_url)}
                    alt=""
                    className="h-7 w-7 rounded-md p-0.5 shadow-soft"
                    style={{ background: "#fff" }}
                  />
                ) : null}
                <div className="flex flex-col leading-tight">
                  <span className="font-display text-sm tracking-tight">{copy.companyName}</span>
                  <span className="text-[10px] font-medium uppercase tracking-[0.18em]" style={{ color: theme.sub }}>
                    {copy.serviceLabel}
                  </span>
                </div>
              </div>
              <span className="text-[11px] font-medium" style={{ color: theme.sub }}>
                {pendingSends > 0 ? (
                  <span className="mr-2 opacity-70" title="Saving in the background">Saving…</span>
                ) : null}
                {stepIndex + 1} / {stepCount}
              </span>
            </div>

            <div className="mt-3 h-1 w-full overflow-hidden rounded-full" style={{ background: theme.border }}>
              <div
                className="h-full rounded-full transition-all duration-500 ease-out"
                style={{ width: `${progress}%`, background: theme.gradientProgress }}
              />
            </div>

            <div className="flex flex-1 flex-col justify-center py-4">
              {inReasonOverlay ? (
                <VoiceDetail
                  ref={reasonRef}
                  theme={theme}
                  eyebrow="We hear you"
                  title={reasonOverlay.reason_prompt || "What went wrong?"}
                  hint="Tell us what to fix — tap, type, or record. Or skip."
                  text={reasonText}
                  onTextChange={setReasonText}
                  placeholder="Type what could be better…"
                  allowVoice
                  reasonOptions={reasonOverlay.reason_options}
                  selectedChips={reasonChips}
                  onToggleChip={(c) =>
                    setReasonChips((prev) => (prev.includes(c) ? prev.filter((x) => x !== c) : [...prev, c]))
                  }
                  disabled={busy}
                  onVoicePendingChange={setReasonVoicePending}
                />
              ) : isText ? (
                <VoiceDetail
                  ref={detailRef}
                  key={`text-${stepIndex}`}
                  theme={theme}
                  eyebrow="Optional"
                  title={q.title || "Your feedback"}
                  hint={q.body || "🎙️ Record or ✍️ write — we'll translate."}
                  text={textAnswer}
                  onTextChange={setTextAnswer}
                  placeholder="Type your answer…"
                  allowVoice={Boolean(q.allow_voice)}
                  disabled={busy}
                  onVoicePendingChange={setDetailVoicePending}
                />
              ) : (
                <QuestionView
                  theme={theme}
                  index={stepIndex}
                  question={q}
                  disabled={busy}
                  onSelect={(value, low) => {
                    if (low) {
                      answerStep(value, {
                        showReasonAfter: {
                          reason_options: q.reason_options,
                          reason_prompt: q.reason_prompt,
                        },
                      });
                    } else {
                      answerStep(value);
                    }
                  }}
                />
              )}
            </div>

            {(inReasonOverlay || isText) && (
              <SurveyFooter
                theme={theme}
                showSkip
                nextLabel={isLast && !inReasonOverlay ? "Submit" : "Next"}
                nextDisabled={!canSubmitDetail}
                backDisabled={stepIndex <= 0 && !inReasonOverlay}
                busy={busy}
                onBack={goBack}
                onSkip={() => skipDetailStep(inReasonOverlay ? "reason" : "answer")}
                onNext={() => submitDetailStep(inReasonOverlay ? "reason" : "answer")}
              />
            )}

            {!inReasonOverlay && !isText && stepIndex > 0 && (
              <SurveyFooter
                theme={theme}
                showSkip={false}
                nextLabel="Next"
                nextDisabled
                backDisabled={false}
                busy={busy}
                onBack={goBack}
                onSkip={() => undefined}
                onNext={() => undefined}
              />
            )}

            {error ? <p className="mt-2 text-center text-[13px] text-red-600">{error}</p> : null}
          </div>
        </main>
      ) : null}
    </div>
  );
}
