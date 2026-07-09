import { Link } from "@tanstack/react-router";
import { useEffect, useMemo, useRef, useState, type ComponentType, type CSSProperties } from "react";
import iconAsset from "@/assets/icon-dark.png.asset.json";

export type Option = { label: string; value: string; low?: boolean };
export type Question = { id: string; text: string; followUpPrompt: string; options: Option[] };

export type Theme = {
  bgClass: string;
  ink: string;
  sub: string;
  card: string;
  border: string;
  accent: string;
  accent2: string;
  cool: string;
  gradientButton: string; // css gradient
  gradientProgress: string;
  selectedShadow: string;
  ringA: string;
  ringB: string;
};

export type Copy = {
  companyName: string;
  serviceLabel: string; // e.g., "Restaurants & Cafés"
  metaTitle: string;
  metaDescription: string;
  thankYouTitle: string;
  thankYouSubtitle: string;
};

type Step =
  | { kind: "question"; qIndex: number }
  | { kind: "followup"; qIndex: number }
  | { kind: "more" }
  | { kind: "optin" };

type RecState = "idle" | "recording" | "recorded";
type Detail = { text: string; recSeconds: number; recState: RecState };
const emptyDetail = (): Detail => ({ text: "", recSeconds: 0, recState: "idle" });

export function SurveyTemplate({
  theme, questions, copy, Art,
}: {
  theme: Theme;
  questions: Question[];
  copy: Copy;
  Art: ComponentType;
}) {
  const T = theme;
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [followUps, setFollowUps] = useState<Record<string, Detail>>({});
  const [more, setMore] = useState<Detail>(emptyDetail());
  const [optIn, setOptIn] = useState<{ wants: boolean; phone: string }>({ wants: false, phone: "" });
  const [cursor, setCursor] = useState(0);
  const [submitted, setSubmitted] = useState(false);

  const steps = useMemo<Step[]>(() => {
    const out: Step[] = [];
    questions.forEach((q, i) => {
      out.push({ kind: "question", qIndex: i });
      const opt = q.options.find((o) => o.value === answers[q.id]);
      if (opt?.low) out.push({ kind: "followup", qIndex: i });
    });
    out.push({ kind: "more" });
    out.push({ kind: "optin" });
    return out;
  }, [answers, questions]);

  const step = steps[Math.min(cursor, steps.length - 1)];
  const totalSteps = steps.length;
  const progress = ((cursor + 1) / totalSteps) * 100;

  const goNext = () => (cursor + 1 >= totalSteps ? setSubmitted(true) : setCursor(cursor + 1));
  const goBack = () => setCursor(Math.max(0, cursor - 1));
  const canAdvance = step.kind === "question" ? !!answers[questions[step.qIndex].id] : true;

  if (submitted) return <ThankYou T={T} copy={copy} Art={Art} />;

  return (
    <main className={`relative flex h-[100svh] flex-col overflow-hidden ${T.bgClass}`} style={{ color: T.ink }}>
      <Art />
      <div className="relative mx-auto flex h-[100svh] w-full max-w-md flex-col px-5 pb-5 pt-4 sm:max-w-lg sm:pt-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <Link to="/" className="inline-flex items-center gap-2">
            <img src={iconAsset.url} alt="" className="h-7 w-7 rounded-md bg-white p-0.5 shadow-soft" />
            <div className="flex flex-col leading-tight">
              <span className="font-display text-sm tracking-tight">{copy.companyName}</span>
              <span className="text-[10px] font-medium uppercase tracking-[0.18em]" style={{ color: T.sub }}>{copy.serviceLabel}</span>
            </div>
          </Link>
          <span className="text-[11px] font-medium" style={{ color: T.sub }}>{cursor + 1} / {totalSteps}</span>
        </div>
        {/* Progress */}
        <div className="mt-3 h-1 w-full overflow-hidden rounded-full" style={{ background: T.border }}>
          <div className="h-full rounded-full transition-all duration-500 ease-out"
               style={{ width: `${progress}%`, background: T.gradientProgress }} />
        </div>
        {/* Body */}
        <div className="flex flex-1 flex-col justify-center py-4">
          {step.kind === "question" && (
            <QuestionView T={T} key={`q-${step.qIndex}`} index={step.qIndex} question={questions[step.qIndex]}
              value={answers[questions[step.qIndex].id]}
              onChange={(v) => setAnswers((a) => ({ ...a, [questions[step.qIndex].id]: v }))} />
          )}
          {step.kind === "followup" && (
            <DetailView T={T} key={`f-${step.qIndex}`} eyebrow="Tell us more" title={questions[step.qIndex].followUpPrompt}
              hint="Type it or record a voice note — any language."
              detail={followUps[questions[step.qIndex].id] ?? emptyDetail()}
              onChange={(d) => setFollowUps((f) => ({ ...f, [questions[step.qIndex].id]: d }))} />
          )}
          {step.kind === "more" && (
            <DetailView T={T} key="more" eyebrow="Optional" title="Anything else to share?"
              hint="🎙️ Record or ✍️ write — in any language, we'll translate."
              detail={more} onChange={setMore} />
          )}
          {step.kind === "optin" && <OptInView T={T} value={optIn} onChange={setOptIn} />}
        </div>
        {/* Footer */}
        <div className="flex items-center gap-3">
          <button onClick={goBack} disabled={cursor === 0}
            className="inline-flex h-12 items-center gap-1.5 rounded-full border px-4 text-sm font-medium shadow-soft transition-all active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-40"
            style={{ background: T.card, borderColor: T.border, color: T.ink }}>
            <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M15 18l-6-6 6-6" /></svg>
            Back
          </button>
          {(step.kind === "followup" || step.kind === "more" || step.kind === "optin") && (
            <button onClick={goNext} className="inline-flex h-12 items-center rounded-full px-4 text-sm font-medium transition-all hover:opacity-80" style={{ color: T.sub }}>
              Skip
            </button>
          )}
          <button onClick={goNext} disabled={!canAdvance}
            className="inline-flex h-12 flex-1 items-center justify-center gap-2 rounded-full px-6 text-sm font-semibold text-white shadow-lift transition-all active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-40"
            style={{ background: T.gradientButton }}>
            {cursor + 1 === totalSteps ? "Submit feedback" : "Next"}
            <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14M13 5l7 7-7 7" /></svg>
          </button>
        </div>
      </div>
    </main>
  );
}

function QuestionView({ T, index, question, value, onChange }: {
  T: Theme; index: number; question: Question; value: string | undefined; onChange: (v: string) => void;
}) {
  return (
    <div className="animate-rise">
      <p className="text-[11px] font-medium uppercase tracking-[0.2em]" style={{ color: T.sub }}>Question {index + 1}</p>
      <h1 className="mt-2 font-display text-[28px] leading-[1.15] sm:text-[32px]">{question.text}</h1>
      <div className="mt-6 grid gap-2.5">
        {question.options.map((opt) => {
          const selected = value === opt.value;
          return (
            <button key={opt.value} onClick={() => onChange(opt.value)}
              className="group flex items-center justify-between rounded-2xl border px-4 py-3.5 text-left text-[15px] font-medium transition-all active:scale-[0.98]"
              style={selected
                ? { background: T.gradientButton, color: "#fff", borderColor: "transparent", boxShadow: T.selectedShadow }
                : { background: T.card, borderColor: T.border, color: T.ink }}>
              <span>{opt.label}</span>
              <span className="grid h-5 w-5 place-items-center rounded-full"
                    style={selected ? { background: "#fff", color: T.accent } : { border: `1px solid ${T.border}` }}>
                {selected && (
                  <svg viewBox="0 0 24 24" className="h-3 w-3" fill="none" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12l5 5L20 7" /></svg>
                )}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function DetailView({ T, eyebrow, title, hint, detail, onChange }: {
  T: Theme; eyebrow: string; title: string; hint: string; detail: Detail; onChange: (d: Detail) => void;
}) {
  const timerRef = useRef<number | null>(null);
  const secsRef = useRef(detail.recSeconds);
  const detailRef = useRef(detail);
  detailRef.current = detail;
  useEffect(() => () => { if (timerRef.current) window.clearInterval(timerRef.current); }, []);

  const start = () => {
    if (detailRef.current.recState === "recording") return;
    secsRef.current = 0;
    onChange({ ...detailRef.current, recState: "recording", recSeconds: 0 });
    timerRef.current = window.setInterval(() => {
      secsRef.current += 1;
      onChange({ ...detailRef.current, recState: "recording", recSeconds: secsRef.current });
    }, 1000);
  };
  const stop = () => {
    if (timerRef.current) { window.clearInterval(timerRef.current); timerRef.current = null; }
    if (detailRef.current.recState === "recording") onChange({ ...detailRef.current, recState: "recorded" });
  };
  const reset = () => { secsRef.current = 0; onChange({ ...detailRef.current, recState: "idle", recSeconds: 0 }); };
  const fmt = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

  return (
    <div className="animate-rise">
      <p className="text-[11px] font-medium uppercase tracking-[0.2em]" style={{ color: T.sub }}>{eyebrow}</p>
      <h1 className="mt-2 font-display text-[26px] leading-[1.15] sm:text-[30px]">{title}</h1>
      <p className="mt-2 text-[12.5px] leading-relaxed" style={{ color: T.sub }}>{hint}</p>

      <textarea value={detail.text} onChange={(e) => onChange({ ...detail, text: e.target.value })}
        placeholder="Write your thoughts…" rows={3}
        className="mt-4 w-full resize-none rounded-2xl border px-4 py-3 text-[14px] leading-relaxed shadow-soft outline-none transition-all"
        style={{ background: T.card, borderColor: T.border, color: T.ink }} />

      <div className="my-4 flex items-center gap-3 text-[10.5px] font-medium uppercase tracking-[0.2em]" style={{ color: T.sub }}>
        <span className="h-px flex-1" style={{ background: T.border }} />or record<span className="h-px flex-1" style={{ background: T.border }} />
      </div>

      <div className="flex flex-col items-center">
        {detail.recState !== "recorded" ? (
          <button onClick={() => (detail.recState === "recording" ? stop() : start())}
            className="relative grid h-16 w-16 place-items-center rounded-full text-white shadow-lift transition-transform active:scale-95"
            style={{ background: T.gradientButton }}
            aria-label={detail.recState === "recording" ? "Stop recording" : "Start recording"}>
            {detail.recState === "recording" && (
              <>
                <span aria-hidden className="animate-pulse-ring absolute inset-0 rounded-full" style={{ background: T.ringA }} />
                <span aria-hidden className="animate-pulse-ring absolute inset-0 rounded-full" style={{ background: T.ringB, animationDelay: "0.6s" }} />
              </>
            )}
            <span className={detail.recState === "recording" ? "animate-mic-pulse" : ""}><MicGlyph /></span>
          </button>
        ) : (
          <PlaybackBar T={T} duration={detail.recSeconds} onReset={reset} />
        )}
        {detail.recState === "recording" && (
          <div className="mt-3 flex flex-col items-center gap-1.5">
            <Waveform color={T.accent} />
            <div className="font-display text-sm tabular-nums">{fmt(detail.recSeconds)}</div>
          </div>
        )}
        {detail.recState === "idle" && <p className="mt-2 text-[11px]" style={{ color: T.sub }}>Tap to record</p>}
      </div>
    </div>
  );
}

function OptInView({ T, value, onChange }: { T: Theme; value: { wants: boolean; phone: string }; onChange: (v: { wants: boolean; phone: string }) => void }) {
  return (
    <div className="animate-rise">
      <p className="text-[11px] font-medium uppercase tracking-[0.2em]" style={{ color: T.sub }}>Stay in touch</p>
      <h1 className="mt-2 font-display text-[26px] leading-[1.15] sm:text-[30px]">Want us to follow up?</h1>
      <p className="mt-2 text-[12.5px] leading-relaxed" style={{ color: T.sub }}>
        Share your mobile number and we may reach out about your feedback. Totally optional.
      </p>
      <label className="mt-5 flex cursor-pointer items-start gap-3 rounded-2xl border p-4 shadow-soft" style={{ background: T.card, borderColor: T.border }}>
        <input type="checkbox" checked={value.wants}
          onChange={(e) => onChange({ ...value, wants: e.target.checked, phone: e.target.checked ? value.phone : "" })}
          className="mt-0.5 h-5 w-5 shrink-0" style={{ accentColor: T.accent }} />
        <div className="min-w-0 flex-1">
          <div className="text-[14px] font-medium">Yes, you can contact me</div>
          <div className="mt-0.5 text-[11.5px]" style={{ color: T.sub }}>🔒 No spam — only a follow-up about this feedback if needed.</div>
        </div>
      </label>
      {value.wants && (
        <div className="animate-rise mt-3">
          <label className="mb-1.5 block text-[11px] font-medium uppercase tracking-[0.15em]" style={{ color: T.sub }}>Mobile number</label>
          <div className="flex items-center gap-2 rounded-2xl border px-4 py-3 shadow-soft" style={{ background: T.card, borderColor: T.border }}>
            <span className="text-[15px]">📱</span>
            <input type="tel" inputMode="tel" placeholder="+1 555 123 4567" value={value.phone}
              onChange={(e) => onChange({ ...value, phone: e.target.value })}
              className="w-full bg-transparent text-[15px] outline-none" style={{ color: T.ink }} />
          </div>
          <p className="mt-2 text-[11px]" style={{ color: T.sub }}>Used once — only to follow up. Never shared, never marketed.</p>
        </div>
      )}
    </div>
  );
}

function MicGlyph() {
  return (
    <svg viewBox="0 0 24 24" className="h-7 w-7" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <rect x="9" y="3" width="6" height="12" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3M8 21h8" />
    </svg>
  );
}

function Waveform({ color }: { color: string }) {
  const style = (i: number): CSSProperties => ({ background: color, height: "100%", animation: `wave 0.9s ease-in-out ${i * 0.06}s infinite`, transformOrigin: "center" });
  return (
    <div className="flex h-7 items-center gap-1">
      {Array.from({ length: 16 }).map((_, i) => (
        <span key={i} className="w-1 rounded-full" style={style(i)} />
      ))}
    </div>
  );
}

function PlaybackBar({ T, duration, onReset }: { T: Theme; duration: number; onReset: () => void }) {
  const [playing, setPlaying] = useState(false);
  const fmt = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  return (
    <div className="w-full max-w-sm">
      <div className="flex items-center gap-3 rounded-full border p-2 pr-4 shadow-soft" style={{ background: T.card, borderColor: T.border }}>
        <button onClick={() => setPlaying((p) => !p)}
          className="grid h-10 w-10 shrink-0 place-items-center rounded-full text-white transition-transform active:scale-95"
          style={{ background: T.gradientButton }}>
          {playing ? (
            <svg viewBox="0 0 24 24" className="h-4 w-4" fill="currentColor"><rect x="6" y="5" width="4" height="14" rx="1" /><rect x="14" y="5" width="4" height="14" rx="1" /></svg>
          ) : (
            <svg viewBox="0 0 24 24" className="h-4 w-4" fill="currentColor"><path d="M7 5v14l12-7z" /></svg>
          )}
        </button>
        <div className="flex h-5 flex-1 items-center gap-[3px]">
          {Array.from({ length: 24 }).map((_, i) => (
            <span key={i} className="flex-1 rounded-full" style={{ background: T.accent, opacity: 0.6, height: `${30 + Math.abs(Math.sin(i * 1.3)) * 70}%` }} />
          ))}
        </div>
        <span className="font-display text-sm tabular-nums">{fmt(duration)}</span>
      </div>
      <button onClick={onReset} className="mt-2 w-full text-center text-[11px] font-medium underline-offset-4 hover:underline" style={{ color: T.sub }}>Re-record</button>
    </div>
  );
}

function ThankYou({ T, copy, Art }: { T: Theme; copy: Copy; Art: ComponentType }) {
  return (
    <main className={`relative grid h-[100svh] place-items-center overflow-hidden px-6 ${T.bgClass}`} style={{ color: T.ink }}>
      <Art />
      <div className="relative max-w-sm text-center">
        <div className="animate-tick-pop mx-auto grid h-20 w-20 place-items-center rounded-full text-white shadow-lift"
             style={{ background: T.gradientButton }}>
          <svg viewBox="0 0 24 24" className="h-9 w-9" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12l5 5L20 7" /></svg>
        </div>
        <h1 className="animate-confetti-rise mt-6 font-display text-4xl" style={{ animationDelay: "120ms" }}>
          {copy.thankYouTitle}<span style={{ color: T.accent }}>.</span>
        </h1>
        <p className="animate-confetti-rise mt-3 text-[15px] leading-relaxed" style={{ animationDelay: "240ms", color: T.sub }}>
          {copy.thankYouSubtitle}
        </p>
        <Link to="/" className="animate-confetti-rise mt-8 inline-flex items-center gap-2 rounded-full border px-5 py-2.5 text-sm font-medium shadow-soft transition-transform hover:-translate-y-0.5"
              style={{ animationDelay: "360ms", background: T.card, borderColor: T.border, color: T.ink }}>
          Back to start
        </Link>
      </div>
    </main>
  );
}

// Default question set — shared across most themes; individual routes can override.
export const DEFAULT_QUESTIONS: Question[] = [
  {
    id: "experience",
    text: "How was your overall experience?",
    followUpPrompt: "Sorry to hear that. What went wrong?",
    options: [
      { label: "Loved it", value: "great" },
      { label: "It was okay", value: "okay" },
      { label: "Not great", value: "poor", low: true },
    ],
  },
  {
    id: "recommend",
    text: "Would you recommend us to a friend?",
    followUpPrompt: "Got it — what's holding you back?",
    options: [
      { label: "Absolutely", value: "yes" },
      { label: "Maybe", value: "maybe", low: true },
      { label: "Not really", value: "no", low: true },
    ],
  },
  {
    id: "speed",
    text: "How did our speed feel?",
    followUpPrompt: "Thanks — where did we lose time?",
    options: [
      { label: "Quick", value: "fast" },
      { label: "Fine", value: "avg" },
      { label: "Too slow", value: "slow", low: true },
    ],
  },
];
