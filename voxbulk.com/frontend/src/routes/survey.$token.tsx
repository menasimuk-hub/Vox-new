import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useMemo, useRef, useState } from "react";
import { MessageSquareText, Mic, Square, RotateCcw, ArrowRight } from "lucide-react";
import { apiFetch, apiUpload, getApiBaseUrl } from "@/lib/api";
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
  logo_url?: string;
  step_count: number;
  questions: SurveyQuestion[];
};

function WhatsAppIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor" aria-hidden>
      <path d="M19.05 4.91A9.82 9.82 0 0 0 12.04 2C6.58 2 2.13 6.45 2.13 11.91c0 1.75.46 3.45 1.32 4.95L2 22l5.25-1.38a9.86 9.86 0 0 0 4.79 1.22h.01c5.46 0 9.91-4.45 9.91-9.91 0-2.65-1.03-5.14-2.91-7.02ZM12.05 20.15h-.01a8.2 8.2 0 0 1-4.18-1.14l-.3-.18-3.12.82.83-3.04-.2-.31a8.2 8.2 0 0 1-1.26-4.39c0-4.54 3.7-8.23 8.24-8.23 2.2 0 4.27.86 5.83 2.42a8.2 8.2 0 0 1 2.41 5.82c0 4.54-3.69 8.23-8.23 8.23Zm4.52-6.16c-.25-.12-1.47-.72-1.69-.81-.23-.08-.39-.12-.56.13-.16.25-.64.81-.78.97-.14.17-.29.19-.54.06-.25-.12-1.05-.39-1.99-1.23-.74-.66-1.23-1.47-1.38-1.72-.14-.25-.01-.38.11-.51.11-.11.25-.29.37-.43.12-.14.16-.25.25-.41.08-.17.04-.31-.02-.43-.06-.12-.56-1.34-.76-1.84-.2-.48-.41-.42-.56-.43h-.48c-.17 0-.43.06-.66.31-.23.25-.86.85-.86 2.07 0 1.22.89 2.4 1.01 2.56.12.17 1.75 2.67 4.23 3.74.59.26 1.05.41 1.41.52.59.19 1.13.16 1.56.1.48-.07 1.47-.6 1.68-1.18.21-.58.21-1.07.14-1.18-.06-.11-.22-.17-.47-.29Z" />
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
            {payload.logo_url ? (
              <img
                src={`${getApiBaseUrl().replace(/\/+$/, "")}${payload.logo_url}`}
                alt={payload.company_name}
                className="fb-company-logo"
              />
            ) : null}
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

type RecState = "idle" | "recording" | "recorded" | "uploading" | "sent";

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

function PlaybackBar({
  playing,
  onToggle,
  duration,
  onReset,
  onSend,
  busy,
  uploading,
}: {
  playing: boolean;
  onToggle: () => void;
  duration: number;
  onReset: () => void;
  onSend: () => void;
  busy: boolean;
  uploading: boolean;
}) {
  const fmt = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  return (
    <div className="fb-playback">
      <div className="fb-playback-bar">
        <button type="button" className="fb-playback-play" onClick={onToggle} disabled={busy || uploading} aria-label={playing ? "Pause" : "Play"}>
          {playing ? (
            <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden>
              <rect x="6" y="5" width="4" height="14" rx="1" />
              <rect x="14" y="5" width="4" height="14" rx="1" />
            </svg>
          ) : (
            <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden>
              <path d="M7 5v14l12-7z" />
            </svg>
          )}
        </button>
        <div className="fb-playback-static" aria-hidden>
          {Array.from({ length: 28 }).map((_, i) => (
            <span key={i} style={{ height: `${30 + Math.abs(Math.sin(i * 1.3)) * 70}%` }} />
          ))}
        </div>
        <span className="fb-playback-time">{fmt(duration)}</span>
      </div>
      <div className="fb-playback-actions">
        <button type="button" className="fb-playback-send" onClick={onSend} disabled={busy || uploading}>
          {uploading ? "Transcribing…" : "Send voice note"}
          {!uploading ? <ArrowRight className="fb-btn-icon" /> : null}
        </button>
        <button type="button" className="fb-rec-reset" onClick={onReset} disabled={busy || uploading}>
          <RotateCcw className="fb-btn-icon" /> Re-record
        </button>
      </div>
    </div>
  );
}

function VoiceRecorder({ busy, onRecorded }: { busy: boolean; onRecorded: (blob: Blob) => Promise<unknown> }) {
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

  const clearTimer = () => {
    if (timerRef.current) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
  };

  const revokeAudioUrl = () => {
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
          setRecState("recorded");
        } else {
          setRecError("Recording was empty. Try again and speak clearly.");
          setRecState("idle");
          setElapsed(0);
        }
        recorderRef.current = null;
      };
      recorderRef.current = rec;
      rec.start(250);
      isRecordingRef.current = true;
      setRecState("recording");
      setElapsed(0);
      timerRef.current = window.setInterval(() => setElapsed((e) => e + 1), 1000);
    } catch (err) {
      holdActiveRef.current = false;
      isRecordingRef.current = false;
      stopStream();
      setRecError(micErrorMessage(err));
      setRecState("idle");
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
    setRecState("idle");
    setElapsed(0);
    setRecError("");
  };

  const togglePlayback = () => {
    const blob = blobRef.current;
    if (!blob) return;
    if (!audioRef.current) {
      const url = URL.createObjectURL(blob);
      objectUrlRef.current = url;
      const audio = new Audio(url);
      audio.onended = () => setPlaying(false);
      audioRef.current = audio;
    }
    const audio = audioRef.current;
    if (playing) {
      audio.pause();
      setPlaying(false);
    } else {
      void audio.play();
      setPlaying(true);
    }
  };

  const sendRecording = async () => {
    const blob = blobRef.current;
    if (!blob || busy) return;
    setRecError("");
    setRecState("uploading");
    revokeAudioUrl();
    try {
      await onRecorded(blob);
      setRecState("sent");
    } catch (err) {
      setRecState("recorded");
      setRecError(err instanceof Error ? err.message : "Could not send voice note");
    }
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

  if (recState === "sent") {
    return (
      <div className="fb-rec-done">
        <span className="fb-rec-check">Voice note sent ✓</span>
        <button type="button" className="fb-rec-reset" onClick={reset} disabled={busy}>
          <RotateCcw className="fb-btn-icon" /> Re-record
        </button>
      </div>
    );
  }

  if (recState === "recorded" || recState === "uploading") {
    return (
      <div className="fb-rec">
        <PlaybackBar
          playing={playing}
          onToggle={togglePlayback}
          duration={elapsed}
          onReset={reset}
          onSend={() => void sendRecording()}
          busy={busy}
          uploading={recState === "uploading"}
        />
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
