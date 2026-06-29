import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useMemo, useRef, useState } from "react";
import { MessageSquareText, Mic, Square, ArrowRight, ChevronLeft, Play, Pause } from "lucide-react";
import { apiFetch, apiUpload, getApiBaseUrl } from "@/lib/api";
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
  logo_url?: string;
  step_count: number;
  questions: SurveyQuestion[];
};

function WhatsAppIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor" aria-hidden>
      <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 0 1-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 0 1-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 0 1 2.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0 0 12.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 0 0 5.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 0 0-3.48-8.413Z" />
    </svg>
  );
}

type AdvanceResponse = {
  completed?: boolean;
  step_index?: number;
  step_count?: number;
  question?: SurveyQuestion;
};

type Phase = "choose" | "survey" | "thanks";

type ReasonOverlay = {
  reason_options?: string[];
  reason_prompt?: string;
};

type VoiceRecState = "idle" | "recording" | "recorded" | "uploading" | "sent";

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

  // Low-rating "why poor?" overlay (rating is saved before overlay opens).
  const [reasonOverlay, setReasonOverlay] = useState<ReasonOverlay | null>(null);
  const [reasonChips, setReasonChips] = useState<string[]>([]);
  const [reasonText, setReasonText] = useState("");
  const [voiceRecState, setVoiceRecState] = useState<VoiceRecState>("idle");
  // Background, strictly-ordered send queue so the visitor never waits on uploads.
  const [pendingSends, setPendingSends] = useState(0);
  const sendQueueRef = useRef<Promise<unknown>>(Promise.resolve());

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

  const inReasonOverlay = reasonOverlay !== null;
  const questions = payload?.questions ?? [];
  const progress = useMemo(() => {
    if (!stepCount) return 0;
    return ((stepIndex + 1) / stepCount) * 100;
  }, [stepIndex, stepCount]);

  // Append a task to the strict-order background queue. The UI never awaits it, so
  // answers and voice notes upload (and transcribe) while the visitor keeps moving.
  const enqueue = (task: () => Promise<unknown>) => {
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
  };

  const drainQueue = () => sendQueueRef.current.catch(() => undefined);

  // Move the local view to a step (or finish). Navigation is client-driven from the
  // full question list, so the visitor never waits on a network round-trip.
  const goToStep = (idx: number, opts?: { reasonAfter?: ReasonOverlay | null }) => {
    setTextAnswer("");
    setReasonChips([]);
    setReasonText("");
    if (idx >= stepCount) {
      setReasonOverlay(null);
      setPhase("thanks");
      return;
    }
    setStepIndex(idx);
    setQuestion(questions[idx] || null);
    setReasonOverlay(opts?.reasonAfter ?? null);
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

  const postAnswer = (answer: string, opts?: { reason?: string; reasonSource?: string }) =>
    apiFetch(`/public/feedback/survey/sessions/${encodeURIComponent(sessionId)}/answer`, {
      method: "POST",
      body: JSON.stringify({ answer, reason: opts?.reason, reason_source: opts?.reasonSource || "text" }),
    });

  const postVoice = (blob: Blob, mode: string, answer?: string) => {
    const form = new FormData();
    form.append("file", blob, "voice.webm");
    form.append("mode", mode);
    if (answer != null) form.append("answer", answer);
    return apiUpload(`/public/feedback/survey/sessions/${encodeURIComponent(sessionId)}/voice`, form);
  };

  const postReason = (reason: string, reasonSource = "text") =>
    apiFetch(`/public/feedback/survey/sessions/${encodeURIComponent(sessionId)}/reason`, {
      method: "POST",
      body: JSON.stringify({ reason, reason_source: reasonSource }),
    });

  // Answer the current step (choice / typed text / skip) and advance instantly.
  const answerStep = (answer: string, opts?: { showReasonAfter?: ReasonOverlay }) => {
    if (!sessionId) return;
    setError("");
    enqueue(() => postAnswer(answer));
    goToStep(stepIndex + 1, { reasonAfter: opts?.showReasonAfter ?? null });
  };

  // Submit a recorded voice note as the current step's answer and advance instantly.
  const voiceAnswerStep = (blob: Blob) => {
    if (!sessionId) return;
    setError("");
    enqueue(() => postVoice(blob, "answer"));
    goToStep(stepIndex + 1);
  };

  // Low-rating reason (chips/text) for the step we just answered — sent in background.
  const submitReason = (reason: string, reasonSource = "text") => {
    const clean = reason.trim();
    setReasonOverlay(null);
    setReasonChips([]);
    setReasonText("");
    if (!sessionId || !clean || clean.toLowerCase() === "skip") return;
    enqueue(() => postReason(clean, reasonSource));
  };

  // Low-rating reason recorded as a voice note — sent in background, overlay closes.
  const voiceReason = (blob: Blob) => {
    setReasonOverlay(null);
    setReasonChips([]);
    setReasonText("");
    if (!sessionId) return;
    enqueue(() => postVoice(blob, "reason_prev"));
  };

  const dismissReasonOverlay = () => {
    setReasonOverlay(null);
    setReasonChips([]);
    setReasonText("");
  };

  const goBack = async () => {
    if (inReasonOverlay) {
      dismissReasonOverlay();
      return;
    }
    if (stepIndex <= 0 || !sessionId) return;
    setBusy(true);
    setError("");
    try {
      // Let queued sends finish so the server's step pointer matches before we step back.
      await drainQueue();
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

  if (phase === "thanks") return <ThankYou companyName={payload.company_name} logoUrl={payload.logo_url} />;

  if (phase === "choose") {
    return (
      <main className="fb-survey-page">
        <div className="fb-blobs" aria-hidden />
        <div className="fb-survey-shell">
          <div className="fb-top">
            <span className="fb-brand">
              {payload.logo_url ? (
                <img
                  src={`${getApiBaseUrl().replace(/\/+$/, "")}${payload.logo_url}`}
                  alt=""
                  className="fb-brand-logo"
                />
              ) : null}
              <span>{payload.company_name}</span>
            </span>
          </div>
          <div className="fb-hero">
            <p className="fb-company">{payload.company_name}</p>
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
                  <WhatsAppIcon className="fb-choice-icon" />
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
                <MessageSquareText className="fb-choice-icon" />
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
  const isLast = stepIndex >= stepCount - 1;
  const voicePending = voiceRecState === "recording" || voiceRecState === "recorded" || voiceRecState === "uploading";

  return (
    <main className="fb-survey-page">
      <div className="fb-blobs" aria-hidden />
      <div className="fb-survey-shell fb-survey-flow">
        <div className="fb-top">
          <span className="fb-brand">
            {(inReasonOverlay || stepIndex > 0) ? (
              <button type="button" className="fb-back" onClick={goBack} disabled={busy} aria-label="Go back">
                <ChevronLeft className="fb-back-icon" />
              </button>
            ) : null}
            {payload.logo_url ? (
              <img
                src={`${getApiBaseUrl().replace(/\/+$/, "")}${payload.logo_url}`}
                alt=""
                className="fb-brand-logo"
              />
            ) : null}
            <span>{payload.company_name}</span>
          </span>
          <span className="fb-step-count">
            {pendingSends > 0 ? <span className="fb-saving" title="Saving in the background">Saving…</span> : null}
            {stepIndex + 1} / {stepCount}
          </span>
        </div>
        <div className="fb-progress">
          <div className="fb-progress-bar" style={{ width: `${progress}%` }} />
        </div>

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
              onSubmitVoice={voiceAnswerStep}
              onRecStateChange={setVoiceRecState}
              voicePrimaryLabel={isLast ? "Submit" : "Next"}
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
                    disabled={inReasonOverlay}
                    onClick={() => {
                      if (isLow) {
                        answerStep(opt.value, {
                          showReasonAfter: {
                            reason_options: q?.reason_options,
                            reason_prompt: q?.reason_prompt,
                          },
                        });
                      } else {
                        answerStep(opt.value);
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

        {isText && !voicePending ? (
          <div className="fb-footer">
            <button type="button" className="fb-btn ghost" onClick={() => answerStep("skip")}>
              Skip
            </button>
            <button
              type="button"
              className="fb-btn primary"
              disabled={!textAnswer.trim()}
              onClick={() => answerStep(textAnswer.trim())}
            >
              {isLast ? "Submit" : "Next"}
              <ArrowRight className="fb-btn-icon" />
            </button>
          </div>
        ) : null}

        {inReasonOverlay ? (
          <div className="fb-reason-overlay" role="dialog" aria-modal="true">
            <ReasonScreen
              overlay={reasonOverlay}
              chips={reasonChips}
              onToggleChip={(c) =>
                setReasonChips((prev) => (prev.includes(c) ? prev.filter((x) => x !== c) : [...prev, c]))
              }
              text={reasonText}
              onText={setReasonText}
              busy={busy}
              onSubmitVoice={voiceReason}
              onSkip={dismissReasonOverlay}
              onSubmit={() => {
                const reason = [reasonChips.join(", "), reasonText.trim()].filter(Boolean).join(" — ");
                submitReason(reason);
              }}
            />
          </div>
        ) : null}

        {error ? <p className="fb-error">{error}</p> : null}
      </div>
    </main>
  );
}

function ReasonScreen({
  overlay,
  chips,
  onToggleChip,
  text,
  onText,
  busy,
  onSubmitVoice,
  onSkip,
  onSubmit,
}: {
  overlay: ReasonOverlay;
  chips: string[];
  onToggleChip: (c: string) => void;
  text: string;
  onText: (v: string) => void;
  busy: boolean;
  onSubmitVoice: (blob: Blob) => void;
  onSkip: () => void;
  onSubmit: () => void;
}) {
  const [voiceRecState, setVoiceRecState] = useState<VoiceRecState>("idle");
  const voicePending = voiceRecState === "recording" || voiceRecState === "recorded" || voiceRecState === "uploading";
  const canSubmitText = Boolean(chips.length || text.trim());

  return (
    <div className="fb-body fb-rise fb-reason-panel">
      <p className="fb-kicker">We hear you</p>
      <h1 className="fb-title">{overlay.reason_prompt || "What went wrong?"}</h1>
      <p className="fb-sub">Tell us what to fix — tap, type, or record. Or skip.</p>

      {(overlay.reason_options || []).length ? (
        <div className="fb-chips">
          {(overlay.reason_options || []).map((c) => (
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
        onSubmit={onSubmitVoice}
        onRecStateChange={setVoiceRecState}
        primaryLabel="Submit"
      />

      {!voicePending ? (
        <div className="fb-footer">
          <button type="button" className="fb-btn ghost" disabled={busy} onClick={onSkip}>
            Skip
          </button>
          <button type="button" className="fb-btn primary" disabled={busy || !canSubmitText} onClick={onSubmit}>
            Submit
            <ArrowRight className="fb-btn-icon" />
          </button>
        </div>
      ) : null}
    </div>
  );
}

function TextStep({
  text,
  onText,
  allowVoice,
  busy,
  onSubmitVoice,
  onRecStateChange,
  voicePrimaryLabel = "Next",
}: {
  text: string;
  onText: (v: string) => void;
  allowVoice: boolean;
  busy: boolean;
  onSubmitVoice: (blob: Blob) => void;
  onRecStateChange?: (state: VoiceRecState) => void;
  voicePrimaryLabel?: string;
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
          <div className="fb-or">or record a voice note instead</div>
          <VoiceRecorder
            busy={busy}
            onSubmit={onSubmitVoice}
            onRecStateChange={onRecStateChange}
            primaryLabel={voicePrimaryLabel}
          />
        </>
      ) : null}
    </div>
  );
}

type RecState = VoiceRecState;

const MIME_CANDIDATES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/mp4",
  "audio/ogg;codecs=opus",
  "audio/ogg",
];

function pickMimeType(): string | undefined {
  if (typeof MediaRecorder === "undefined") return undefined;
  for (const mime of MIME_CANDIDATES) {
    if (MediaRecorder.isTypeSupported(mime)) return mime;
  }
  return undefined;
}

function micErrorMessage(err: unknown): string {
  const name = err instanceof DOMException ? err.name : "";
  if (name === "NotAllowedError" || name === "PermissionDeniedError") {
    return "Microphone access was blocked. Allow the mic in your browser settings and try again.";
  }
  if (name === "NotFoundError" || name === "DevicesNotFoundError") {
    return "No microphone found on this device.";
  }
  if (err instanceof Error && err.message) return err.message;
  return "Could not start recording. Please type your answer instead.";
}

function Waveform() {
  return (
    <div className="fb-waveform" aria-hidden>
      {Array.from({ length: 18 }).map((_, i) => (
        <span
          key={i}
          className="fb-waveform-bar"
          style={{ animationDelay: `${i * 0.06}s` }}
        />
      ))}
    </div>
  );
}

function VoiceRecorder({
  busy,
  onSubmit,
  onRecStateChange,
  primaryLabel = "Next",
}: {
  busy: boolean;
  onSubmit: (blob: Blob) => void;
  onRecStateChange?: (state: RecState) => void;
  primaryLabel?: string;
}) {
  const [recState, setRecState] = useState<RecState>("idle");
  const [elapsed, setElapsed] = useState(0);
  const [recError, setRecError] = useState("");
  const [playing, setPlaying] = useState(false);
  const [supported] = useState(() => {
    if (typeof navigator === "undefined") return false;
    return Boolean(navigator.mediaDevices && typeof MediaRecorder !== "undefined");
  });

  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const timerRef = useRef<number | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const blobRef = useRef<Blob | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const objectUrlRef = useRef<string | null>(null);
  const holdActiveRef = useRef(false);
  const isRecordingRef = useRef(false);
  const skipClickRef = useRef(false);

  const setState = (state: RecState) => {
    setRecState(state);
    onRecStateChange?.(state);
  };

  const clearTimer = () => {
    if (timerRef.current) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
  };

  const revokeAudioUrl = () => {
    if (audioRef.current) {
      try {
        audioRef.current.pause();
      } catch {
        /* ignore */
      }
    }
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = null;
    }
    audioRef.current = null;
    setPlaying(false);
  };

  const stopStream = () => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  };

  useEffect(() => {
    return () => {
      clearTimer();
      stopStream();
      revokeAudioUrl();
    };
  }, []);

  const fmt = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

  const start = async () => {
    if (isRecordingRef.current || recState === "uploading" || busy) return;
    setRecError("");
    revokeAudioUrl();
    blobRef.current = null;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (!holdActiveRef.current) {
        stream.getTracks().forEach((t) => t.stop());
        return;
      }
      streamRef.current = stream;
      chunksRef.current = [];
      const mimeType = pickMimeType();
      const rec = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
      rec.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) chunksRef.current.push(e.data);
      };
      rec.onstop = () => {
        isRecordingRef.current = false;
        clearTimer();
        stopStream();
        const blob = new Blob(chunksRef.current, { type: rec.mimeType || mimeType || "audio/webm" });
        if (blob.size > 0) {
          blobRef.current = blob;
          // Don't auto-send: let the visitor play it back and re-record before sending.
          const url = URL.createObjectURL(blob);
          objectUrlRef.current = url;
          const audio = new Audio(url);
          audio.onended = () => setPlaying(false);
          audioRef.current = audio;
          setState("recorded");
        } else {
          setRecError("Recording was empty. Try again and speak clearly.");
          setState("idle");
          setElapsed(0);
        }
        recorderRef.current = null;
      };
      recorderRef.current = rec;
      rec.start(250);
      isRecordingRef.current = true;
      setState("recording");
      setElapsed(0);
      timerRef.current = window.setInterval(() => setElapsed((e) => e + 1), 1000);
    } catch (err) {
      holdActiveRef.current = false;
      isRecordingRef.current = false;
      stopStream();
      setRecError(micErrorMessage(err));
      setState("idle");
    }
  };

  const stop = () => {
    if (!isRecordingRef.current) return;
    holdActiveRef.current = false;
    clearTimer();
    const rec = recorderRef.current;
    if (rec && rec.state !== "inactive") rec.stop();
  };

  const reset = () => {
    holdActiveRef.current = false;
    isRecordingRef.current = false;
    skipClickRef.current = false;
    clearTimer();
    stopStream();
    revokeAudioUrl();
    blobRef.current = null;
    if (recorderRef.current && recorderRef.current.state !== "inactive") {
      recorderRef.current.stop();
    }
    recorderRef.current = null;
    setState("idle");
    setElapsed(0);
    setRecError("");
  };

  const togglePlayback = () => {
    const audio = audioRef.current;
    if (!audio) return;
    if (playing) {
      audio.pause();
      setPlaying(false);
    } else {
      void audio.play();
      setPlaying(true);
    }
  };

  // Hand the recording to the parent (which uploads it in the background) and let the
  // parent advance the flow — the visitor does not wait for the upload/transcription.
  const submitRecording = () => {
    const blob = blobRef.current;
    if (!blob || busy) return;
    setRecError("");
    revokeAudioUrl();
    onSubmit(blob);
  };

  const handleMicDown = (e: React.MouseEvent | React.TouchEvent) => {
    e.preventDefault();
    if (isRecordingRef.current || busy) return;
    holdActiveRef.current = true;
    skipClickRef.current = false;
    void start();
  };

  const handleMicUp = (e: React.MouseEvent | React.TouchEvent) => {
    e.preventDefault();
    if (isRecordingRef.current) {
      skipClickRef.current = true;
      stop();
    } else {
      holdActiveRef.current = false;
    }
  };

  const handleMicClick = () => {
    if (skipClickRef.current) {
      skipClickRef.current = false;
      return;
    }
    if (busy) return;
    if (isRecordingRef.current) stop();
    else if (recState === "idle") {
      holdActiveRef.current = true;
      void start();
    }
  };

  if (!supported) {
    return <p className="fb-voice-hint">Voice notes aren't supported on this browser — please type instead.</p>;
  }

  if (recState === "recorded") {
    return (
      <div className="fb-rec-preview">
        <div className="fb-rec-preview-row">
          <button
            type="button"
            className="fb-rec-play"
            onClick={togglePlayback}
            disabled={busy}
            aria-label={playing ? "Pause" : "Play"}
          >
            {playing ? <Pause className="fb-btn-icon" /> : <Play className="fb-btn-icon" />}
            {playing ? "Pause" : "Play"}
          </button>
          <span className="fb-rec-len">{fmt(elapsed)}</span>
        </div>
        <button
          type="button"
          className="fb-btn primary fb-rec-submit-only"
          onClick={submitRecording}
          disabled={busy}
        >
          {primaryLabel}
          <ArrowRight className="fb-btn-icon" />
        </button>
        <button type="button" className="fb-rec-redo-link" onClick={reset} disabled={busy}>
          Re-record
        </button>
        {recError ? <p className="fb-rec-error">{recError}</p> : null}
      </div>
    );
  }

  return (
    <div className="fb-rec">
      <button
        type="button"
        className={`fb-mic ${recState === "recording" ? "rec" : ""}`}
        onMouseDown={handleMicDown}
        onMouseUp={handleMicUp}
        onMouseLeave={() => {
          if (isRecordingRef.current) stop();
        }}
        onTouchStart={handleMicDown}
        onTouchEnd={handleMicUp}
        onClick={handleMicClick}
        disabled={busy}
        aria-label={recState === "recording" ? "Stop recording" : "Hold or tap to record"}
      >
        {recState === "recording" ? (
          <>
            <span className="fb-mic-ring" aria-hidden />
            <span className="fb-mic-ring fb-mic-ring-delay" aria-hidden />
            <Square className={`fb-mic-icon ${recState === "recording" ? "fb-mic-icon-pulse" : ""}`} />
          </>
        ) : (
          <Mic className="fb-mic-icon" />
        )}
      </button>

      {recState === "recording" ? (
        <div className="fb-rec-live">
          <Waveform />
          <span className="fb-rec-timer">{fmt(elapsed)}</span>
        </div>
      ) : (
        <span className="fb-rec-label">Hold or tap to record</span>
      )}

      {recError ? <p className="fb-rec-error">{recError}</p> : null}
    </div>
  );
}

function ThankYou({ companyName, logoUrl }: { companyName: string; logoUrl?: string }) {
  return (
    <main className="fb-survey-page">
      <div className="fb-blobs" aria-hidden />
      <div className="fb-survey-shell fb-thanks">
        {logoUrl ? (
          <img
            src={`${getApiBaseUrl().replace(/\/+$/, "")}${logoUrl}`}
            alt={companyName}
            className="fb-thanks-logo"
          />
        ) : null}
        <p className="fb-thanks-company">{companyName}</p>
        <div className="fb-tick">
          <svg viewBox="0 0 24 24" className="fb-tick-svg" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M5 12l5 5L20 7" />
          </svg>
        </div>
        <h1 className="fb-title">Thank you<span className="fb-dot">.</span></h1>
        <p className="fb-sub">Your feedback helps {companyName} get better. We read every reply.</p>
        <Link to="/" className="fb-thanks-btn">Back to start</Link>
      </div>
    </main>
  );
}
