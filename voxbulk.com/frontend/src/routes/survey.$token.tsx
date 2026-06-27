import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useMemo, useRef, useState } from "react";
import { MessageCircle, Sparkles, Mic, Square, RotateCcw, ArrowRight } from "lucide-react";
import { apiFetch, apiUpload } from "@/lib/api";
import { BrandLogo } from "@/components/BrandLogo";
import "./survey.css";

export const Route = createFileRoute("/survey/$token")({
  head: () => ({
    meta: [
      { title: "Quick survey — Your feedback" },
      { name: "description", content: "A 60-second survey. Tap or talk." },
    ],
  }),
  component: PublicFeedbackSurvey,
});

type SurveyQuestion = {
  kind: string;
  title: string;
  body: string;
  input: "choice" | "text";
  options: { label: string; value: string }[];
  allow_voice?: boolean;
  is_rating?: boolean;
  low_values?: string[];
  reason_options?: string[];
  reason_prompt?: string;
};

type SurveyPayload = {
  company_name: string;
  branch_name?: string;
  wa_url?: string;
  step_count: number;
  questions: SurveyQuestion[];
};

type AdvanceResponse = {
  completed?: boolean;
  step_index?: number;
  step_count?: number;
  question?: SurveyQuestion;
};

type Phase = "choose" | "survey" | "thanks";

function PublicFeedbackSurvey() {
  const { token } = Route.useParams();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [payload, setPayload] = useState<SurveyPayload | null>(null);
  const [phase, setPhase] = useState<Phase>("choose");
  const [sessionId, setSessionId] = useState("");
  const [stepIndex, setStepIndex] = useState(0);
  const [question, setQuestion] = useState<SurveyQuestion | null>(null);
  const [stepCount, setStepCount] = useState(0);
  const [textAnswer, setTextAnswer] = useState("");
  const [busy, setBusy] = useState(false);

  // Low-rating "why poor?" interstitial state.
  const [pendingLow, setPendingLow] = useState<string | null>(null);
  const [reasonChips, setReasonChips] = useState<string[]>([]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError("");
      try {
        const data = await apiFetch<{ ok?: boolean } & SurveyPayload>(`/public/feedback/survey/${encodeURIComponent(token)}`);
        if (!cancelled) setPayload(data);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Survey not found");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  const inReason = pendingLow !== null;
  const progress = useMemo(() => {
    if (!stepCount) return 0;
    return ((stepIndex + 1) / stepCount) * 100;
  }, [stepIndex, stepCount]);

  const applyAdvance = (data: AdvanceResponse) => {
    if (data.completed) {
      setPhase("thanks");
      return;
    }
    setStepIndex(Number(data.step_index ?? stepIndex + 1));
    setStepCount(Number(data.step_count ?? stepCount));
    setQuestion(data.question || null);
    setTextAnswer("");
    setPendingLow(null);
    setReasonChips([]);
  };

  const startWeb = async () => {
    setBusy(true);
    setError("");
    try {
      const data = await apiFetch<{ ok?: boolean } & AdvanceResponse>(
        `/public/feedback/survey/${encodeURIComponent(token)}/sessions`,
        { method: "POST" },
      );
      setSessionId(String((data as { session_id?: string }).session_id || ""));
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

  const submitAnswer = async (answer: string, opts?: { reason?: string; reasonSource?: string }) => {
    if (!sessionId) return;
    setBusy(true);
    setError("");
    try {
      const data = await apiFetch<{ ok?: boolean } & AdvanceResponse>(
        `/public/feedback/survey/sessions/${encodeURIComponent(sessionId)}/answer`,
        {
          method: "POST",
          body: JSON.stringify({ answer, reason: opts?.reason, reason_source: opts?.reasonSource || "text" }),
        },
      );
      applyAdvance(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save answer");
    } finally {
      setBusy(false);
    }
  };

  const uploadVoice = async (blob: Blob, mode: "answer" | "reason") => {
    if (!sessionId) return;
    setBusy(true);
    setError("");
    try {
      const form = new FormData();
      form.append("file", blob, "voice.webm");
      form.append("mode", mode);
      const data = await apiUpload<{ ok?: boolean; transcript?: string } & AdvanceResponse>(
        `/public/feedback/survey/sessions/${encodeURIComponent(sessionId)}/voice`,
        form,
      );
      if (data.transcript && mode === "reason") {
        setTextAnswer((prev) => (prev.trim() ? `${prev.trim()} — ${data.transcript}` : String(data.transcript)));
      }
      if (mode === "answer") {
        applyAdvance(data);
      }
      return data;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save voice note");
      throw e;
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <main className="fb-survey-page">
        <div className="fb-survey-shell muted">Loading survey…</div>
      </main>
    );
  }

  if (error && !payload) {
    return (
      <main className="fb-survey-page">
        <div className="fb-survey-shell">
          <p className="fb-error">{error}</p>
          <Link to="/" className="fb-link">Back to VoxBulk</Link>
        </div>
      </main>
    );
  }

  if (!payload) return null;

  if (phase === "thanks") return <ThankYou companyName={payload.company_name} />;

  if (phase === "choose") {
    return (
      <main className="fb-survey-page">
        <div className="fb-blobs" aria-hidden />
        <div className="fb-survey-shell">
          <div className="fb-top">
            <Link to="/" className="fb-brand">
              <BrandLogo icon className="fb-brand-icon" />
              <span>VoxBulk Feedback</span>
            </Link>
          </div>
          <div className="fb-hero">
            <p className="fb-kicker">{payload.company_name}</p>
            <h1 className="fb-title fb-title-lg">
              We'd love your <span className="fb-italic">feedback</span><span className="fb-dot">.</span>
            </h1>
            {payload.branch_name ? <p className="fb-sub">{payload.branch_name}</p> : null}
            <p className="fb-lead">Under a minute — voice or tap. Choose how you'd like to respond.</p>
            <div className="fb-pill">🌍 WhatsApp = all languages · Web = English</div>
          </div>
          <div className="fb-choices">
            {payload.wa_url ? (
              <a href={payload.wa_url} className="fb-choice fb-choice-wa" target="_blank" rel="noreferrer">
                <span className="fb-choice-badge fb-choice-badge-wa">
                  <MessageCircle className="fb-choice-icon" />
                </span>
                <div className="fb-choice-text">
                  <strong>Continue on WhatsApp</strong>
                  <span>💬 Reply in your own language</span>
                </div>
                <ArrowRight className="fb-choice-arrow" />
              </a>
            ) : null}
            <button type="button" className="fb-choice" onClick={startWeb} disabled={busy}>
              <span className="fb-choice-badge fb-choice-badge-dark">
                <Sparkles className="fb-choice-icon" />
              </span>
              <div className="fb-choice-text">
                <strong>Complete here</strong>
                <span>Quick on-page survey · English</span>
              </div>
              <ArrowRight className="fb-choice-arrow" />
            </button>
          </div>
          {error ? <p className="fb-error">{error}</p> : null}
          <footer className="fb-foot">Your reply is private and only shared with {payload.company_name}.</footer>
        </div>
      </main>
    );
  }

  const q = question;
  const isText = q?.input === "text";

  return (
    <main className="fb-survey-page">
      <div className="fb-blobs" aria-hidden />
      <div className="fb-survey-shell fb-survey-flow">
        <div className="fb-top">
          <span className="fb-brand">
            <BrandLogo icon className="fb-brand-icon" />
            <span>{payload.company_name}</span>
          </span>
          <span className="fb-step-count">{stepIndex + 1} / {stepCount}</span>
        </div>
        <div className="fb-progress">
          <div className="fb-progress-bar" style={{ width: `${progress}%` }} />
        </div>

        {inReason ? (
          <ReasonScreen
            question={q}
            chips={reasonChips}
            onToggleChip={(c) =>
              setReasonChips((prev) => (prev.includes(c) ? prev.filter((x) => x !== c) : [...prev, c]))
            }
            text={textAnswer}
            onText={setTextAnswer}
            busy={busy}
            onUploadVoice={(blob) => uploadVoice(blob, "reason")}
            onSkip={() => submitAnswer(pendingLow as string)}
            onSubmit={() => {
              const reason = [reasonChips.join(", "), textAnswer.trim()].filter(Boolean).join(" — ");
              submitAnswer(pendingLow as string, reason ? { reason } : undefined);
            }}
          />
        ) : (
          <div className="fb-body" key={`${stepIndex}-${q?.kind}`}>
            <p className="fb-kicker">{isText ? "Optional" : `Question ${stepIndex + 1}`}</p>
            <h1 className="fb-title">{q?.title || "Your feedback"}</h1>
            {q?.body ? <p className="fb-sub">{q.body}</p> : null}

            {isText ? (
              <TextStep
                text={textAnswer}
                onText={setTextAnswer}
                allowVoice={Boolean(q?.allow_voice)}
                busy={busy}
                onUploadVoice={(blob) => uploadVoice(blob, "answer")}
              />
            ) : (
              <div className="fb-options">
                {(q?.options || []).map((opt) => {
                  const isLow = (q?.low_values || []).includes(opt.value);
                  return (
                    <button
                      key={opt.value}
                      type="button"
                      className="fb-option"
                      disabled={busy}
                      onClick={() => {
                        if (isLow) {
                          setPendingLow(opt.value);
                          setTextAnswer("");
                          setReasonChips([]);
                        } else {
                          submitAnswer(opt.value);
                        }
                      }}
                    >
                      {opt.label}
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {isText && !inReason ? (
          <div className="fb-footer">
            <button type="button" className="fb-btn ghost" disabled={busy} onClick={() => submitAnswer("skip")}>
              Skip
            </button>
            <button
              type="button"
              className="fb-btn primary"
              disabled={busy || !textAnswer.trim()}
              onClick={() => submitAnswer(textAnswer.trim())}
            >
              {busy ? "Saving…" : "Next"}
              <ArrowRight className="fb-btn-icon" />
            </button>
          </div>
        ) : null}

        {error ? <p className="fb-error">{error}</p> : null}
      </div>
    </main>
  );
}

function ReasonScreen({
  question,
  chips,
  onToggleChip,
  text,
  onText,
  busy,
  onUploadVoice,
  onSkip,
  onSubmit,
}: {
  question: SurveyQuestion | null;
  chips: string[];
  onToggleChip: (c: string) => void;
  text: string;
  onText: (v: string) => void;
  busy: boolean;
  onUploadVoice: (blob: Blob) => Promise<unknown>;
  onSkip: () => void;
  onSubmit: () => void;
}) {
  const [voiceSaved, setVoiceSaved] = useState(false);
  return (
    <div className="fb-body fb-rise">
      <p className="fb-kicker">We hear you</p>
      <h1 className="fb-title">{question?.reason_prompt || "What went wrong?"}</h1>
      <p className="fb-sub">Tell us what to fix — tap, type, or record. Or skip.</p>

      {(question?.reason_options || []).length ? (
        <div className="fb-chips">
          {(question?.reason_options || []).map((c) => (
            <button
              key={c}
              type="button"
              className={`fb-chip ${chips.includes(c) ? "active" : ""}`}
              disabled={busy}
              onClick={() => onToggleChip(c)}
            >
              {c}
            </button>
          ))}
        </div>
      ) : null}

      <textarea
        className="fb-textarea"
        rows={3}
        value={text}
        onChange={(e) => onText(e.target.value)}
        placeholder="Type what could be better…"
      />

      <VoiceRecorder
        busy={busy}
        onRecorded={async (blob) => {
          try {
            const res = await onUploadVoice(blob);
            if (res) setVoiceSaved(true);
          } catch {
            setVoiceSaved(false);
          }
        }}
      />
      {voiceSaved ? <p className="fb-voice-saved">Voice note saved ✓</p> : null}

      <div className="fb-footer">
        <button type="button" className="fb-btn ghost" disabled={busy} onClick={onSkip}>
          Skip
        </button>
        <button type="button" className="fb-btn primary" disabled={busy} onClick={onSubmit}>
          {busy ? "Saving…" : "Next"}
          <ArrowRight className="fb-btn-icon" />
        </button>
      </div>
    </div>
  );
}

function TextStep({
  text,
  onText,
  allowVoice,
  busy,
  onUploadVoice,
}: {
  text: string;
  onText: (v: string) => void;
  allowVoice: boolean;
  busy: boolean;
  onUploadVoice: (blob: Blob) => Promise<unknown>;
}) {
  return (
    <div className="fb-rise">
      <textarea
        className="fb-textarea"
        rows={4}
        value={text}
        onChange={(e) => onText(e.target.value)}
        placeholder="Type your answer…"
      />
      {allowVoice ? (
        <>
          <div className="fb-or">or record a voice note — we'll transcribe it</div>
          <VoiceRecorder busy={busy} onRecorded={onUploadVoice} />
        </>
      ) : null}
    </div>
  );
}

type RecState = "idle" | "recording" | "recorded" | "uploading";

function VoiceRecorder({ busy, onRecorded }: { busy: boolean; onRecorded: (blob: Blob) => Promise<unknown> }) {
  const [recState, setRecState] = useState<RecState>("idle");
  const [elapsed, setElapsed] = useState(0);
  const [supported, setSupported] = useState(true);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const timerRef = useRef<number | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  useEffect(() => {
    if (typeof navigator === "undefined" || !navigator.mediaDevices || typeof MediaRecorder === "undefined") {
      setSupported(false);
    }
    return () => {
      if (timerRef.current) window.clearInterval(timerRef.current);
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  const fmt = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

  const start = async () => {
    if (recState === "recording" || busy) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      chunksRef.current = [];
      const rec = new MediaRecorder(stream);
      rec.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) chunksRef.current.push(e.data);
      };
      rec.onstop = async () => {
        const blob = new Blob(chunksRef.current, { type: rec.mimeType || "audio/webm" });
        streamRef.current?.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
        setRecState("uploading");
        try {
          await onRecorded(blob);
          setRecState("recorded");
        } catch {
          setRecState("idle");
          setElapsed(0);
        }
      };
      recorderRef.current = rec;
      rec.start();
      setRecState("recording");
      setElapsed(0);
      timerRef.current = window.setInterval(() => setElapsed((e) => e + 1), 1000);
    } catch {
      setSupported(false);
    }
  };

  const stop = () => {
    if (recState !== "recording") return;
    if (timerRef.current) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
    recorderRef.current?.stop();
  };

  const reset = () => {
    setRecState("idle");
    setElapsed(0);
  };

  if (!supported) {
    return <p className="fb-voice-hint">Voice notes aren't supported on this browser — please type instead.</p>;
  }

  if (recState === "recorded") {
    return (
      <div className="fb-rec-done">
        <span className="fb-rec-check">Voice note ready ✓</span>
        <button type="button" className="fb-rec-reset" onClick={reset} disabled={busy}>
          <RotateCcw className="fb-btn-icon" /> Re-record
        </button>
      </div>
    );
  }

  return (
    <div className="fb-rec">
      <button
        type="button"
        className={`fb-mic ${recState === "recording" ? "rec" : ""}`}
        onClick={recState === "recording" ? stop : start}
        disabled={busy || recState === "uploading"}
        aria-label={recState === "recording" ? "Stop recording" : "Record voice note"}
      >
        {recState === "recording" ? <Square className="fb-mic-icon" /> : <Mic className="fb-mic-icon" />}
        {recState === "recording" ? <span className="fb-mic-ring" aria-hidden /> : null}
      </button>
      <span className="fb-rec-label">
        {recState === "uploading" ? "Transcribing…" : recState === "recording" ? fmt(elapsed) : "Tap to record"}
      </span>
    </div>
  );
}

function ThankYou({ companyName }: { companyName: string }) {
  return (
    <main className="fb-survey-page">
      <div className="fb-blobs" aria-hidden />
      <div className="fb-survey-shell fb-thanks">
        <div className="fb-tick">
          <svg viewBox="0 0 24 24" className="fb-tick-svg" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M5 12l5 5L20 7" />
          </svg>
        </div>
        <h1 className="fb-title">Thank you<span className="fb-dot">.</span></h1>
        <p className="fb-sub">Your feedback helps {companyName} get better. We read every reply.</p>
        <Link to="/" className="fb-btn ghost fb-thanks-btn">Back to start</Link>
      </div>
    </main>
  );
}
