import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
  type CSSProperties,
} from "react";
import type { Theme } from "./types";

export type VoiceDetailHandle = {
  getBlob: () => Blob | null;
  getText: () => string;
  hasVoicePending: () => boolean;
};

type RecState = "idle" | "recording" | "recorded";

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

function MicGlyph() {
  return (
    <svg viewBox="0 0 24 24" className="h-7 w-7" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <rect x="9" y="3" width="6" height="12" rx="3" />
      <path d="M5 11a7 7 0 0 0 14 0M12 18v3M8 21h8" />
    </svg>
  );
}

function Waveform({ color }: { color: string }) {
  const style = (i: number): CSSProperties => ({
    background: color,
    height: "100%",
    animation: `wave 0.9s ease-in-out ${i * 0.06}s infinite`,
    transformOrigin: "center",
  });
  return (
    <div className="flex h-7 items-center gap-1">
      {Array.from({ length: 16 }).map((_, i) => (
        <span key={i} className="w-1 rounded-full" style={style(i)} />
      ))}
    </div>
  );
}

function PlaybackBar({
  theme,
  duration,
  playing,
  onToggle,
  onReset,
}: {
  theme: Theme;
  duration: number;
  playing: boolean;
  onToggle: () => void;
  onReset: () => void;
}) {
  const fmt = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  return (
    <div className="w-full max-w-sm">
      <div
        className="flex items-center gap-3 rounded-full border p-2 pr-4 shadow-soft"
        style={{ background: theme.card, borderColor: theme.border }}
      >
        <button
          type="button"
          onClick={onToggle}
          className="grid h-10 w-10 shrink-0 place-items-center rounded-full text-white transition-transform active:scale-95"
          style={{ background: theme.gradientButton }}
          aria-label={playing ? "Pause" : "Play"}
        >
          {playing ? (
            <svg viewBox="0 0 24 24" className="h-4 w-4" fill="currentColor" aria-hidden>
              <rect x="6" y="5" width="4" height="14" rx="1" />
              <rect x="14" y="5" width="4" height="14" rx="1" />
            </svg>
          ) : (
            <svg viewBox="0 0 24 24" className="h-4 w-4" fill="currentColor" aria-hidden>
              <path d="M7 5v14l12-7z" />
            </svg>
          )}
        </button>
        <div className="flex h-5 flex-1 items-center gap-[3px]">
          {Array.from({ length: 24 }).map((_, i) => (
            <span
              key={i}
              className="flex-1 rounded-full"
              style={{ background: theme.accent, opacity: 0.6, height: `${30 + Math.abs(Math.sin(i * 1.3)) * 70}%` }}
            />
          ))}
        </div>
        <span className="font-display text-sm tabular-nums">{fmt(duration)}</span>
      </div>
      <button
        type="button"
        onClick={onReset}
        className="mt-2 w-full text-center text-[11px] font-medium underline-offset-4 hover:underline"
        style={{ color: theme.sub }}
      >
        Re-record
      </button>
    </div>
  );
}

export type VoiceDetailProps = {
  theme: Theme;
  eyebrow: string;
  title: string;
  hint: string;
  text: string;
  onTextChange: (value: string) => void;
  placeholder?: string;
  allowVoice?: boolean;
  reasonOptions?: string[];
  selectedChips?: string[];
  onToggleChip?: (chip: string) => void;
  disabled?: boolean;
  onVoicePendingChange?: (pending: boolean) => void;
};

export const VoiceDetail = forwardRef<VoiceDetailHandle, VoiceDetailProps>(function VoiceDetail(
  {
    theme,
    eyebrow,
    title,
    hint,
    text,
    onTextChange,
    placeholder = "Write your thoughts…",
    allowVoice = true,
    reasonOptions,
    selectedChips = [],
    onToggleChip,
    disabled = false,
    onVoicePendingChange,
  },
  ref,
) {
  const [recState, setRecState] = useState<RecState>("idle");
  const [recSeconds, setRecSeconds] = useState(0);
  const [recError, setRecError] = useState("");
  const [playing, setPlaying] = useState(false);
  const [supported] = useState(() => {
    if (typeof navigator === "undefined") return false;
    return Boolean(navigator.mediaDevices && typeof MediaRecorder !== "undefined");
  });

  const textRef = useRef(text);
  const recStateRef = useRef(recState);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const timerRef = useRef<number | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const blobRef = useRef<Blob | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const objectUrlRef = useRef<string | null>(null);
  const isRecordingRef = useRef(false);

  textRef.current = text;
  recStateRef.current = recState;

  useEffect(() => {
    onVoicePendingChange?.(recState === "recording" || recState === "recorded");
  }, [recState, onVoicePendingChange]);

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

  const resetRecording = () => {
    isRecordingRef.current = false;
    clearTimer();
    stopStream();
    revokeAudioUrl();
    blobRef.current = null;
    if (recorderRef.current && recorderRef.current.state !== "inactive") {
      recorderRef.current.stop();
    }
    recorderRef.current = null;
    setRecState("idle");
    setRecSeconds(0);
    setRecError("");
  };

  useEffect(() => () => {
    clearTimer();
    stopStream();
    revokeAudioUrl();
  }, []);

  useImperativeHandle(ref, () => ({
    getBlob: () => blobRef.current,
    getText: () => textRef.current,
    hasVoicePending: () => recStateRef.current === "recording" || recStateRef.current === "recorded",
  }));

  const start = async () => {
    if (disabled || isRecordingRef.current || recState === "recorded") return;
    setRecError("");
    revokeAudioUrl();
    blobRef.current = null;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
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
          const url = URL.createObjectURL(blob);
          objectUrlRef.current = url;
          const audio = new Audio(url);
          audio.onended = () => setPlaying(false);
          audioRef.current = audio;
          setRecState("recorded");
        } else {
          setRecError("Recording was empty. Try again and speak clearly.");
          setRecState("idle");
          setRecSeconds(0);
        }
        recorderRef.current = null;
      };
      recorderRef.current = rec;
      rec.start(250);
      isRecordingRef.current = true;
      setRecState("recording");
      setRecSeconds(0);
      timerRef.current = window.setInterval(() => setRecSeconds((s) => s + 1), 1000);
    } catch (err) {
      isRecordingRef.current = false;
      stopStream();
      setRecError(micErrorMessage(err));
      setRecState("idle");
    }
  };

  const stop = () => {
    if (!isRecordingRef.current) return;
    clearTimer();
    const rec = recorderRef.current;
    if (rec && rec.state !== "inactive") rec.stop();
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

  const fmt = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

  return (
    <div className="animate-rise">
      <p className="text-[11px] font-medium uppercase tracking-[0.2em]" style={{ color: theme.sub }}>
        {eyebrow}
      </p>
      <h1 className="mt-2 font-display text-[26px] leading-[1.15] sm:text-[30px]">{title}</h1>
      <p className="mt-2 text-[12.5px] leading-relaxed" style={{ color: theme.sub }}>{hint}</p>

      {(reasonOptions || []).length > 0 ? (
        <div className="mt-4 flex flex-wrap gap-2">
          {(reasonOptions || []).map((chip) => {
            const active = selectedChips.includes(chip);
            return (
              <button
                key={chip}
                type="button"
                disabled={disabled}
                onClick={() => onToggleChip?.(chip)}
                className="rounded-full border px-3 py-1.5 text-[13px] font-medium transition-all active:scale-[0.98]"
                style={
                  active
                    ? { background: theme.gradientButton, color: "#fff", borderColor: "transparent" }
                    : { background: theme.card, borderColor: theme.border, color: theme.ink }
                }
              >
                {chip}
              </button>
            );
          })}
        </div>
      ) : null}

      <textarea
        value={text}
        onChange={(e) => onTextChange(e.target.value)}
        placeholder={placeholder}
        rows={3}
        disabled={disabled}
        className="mt-4 w-full resize-none rounded-2xl border px-4 py-3 text-[14px] leading-relaxed shadow-soft outline-none transition-all"
        style={{ background: theme.card, borderColor: theme.border, color: theme.ink }}
      />

      {allowVoice ? (
        <>
          <div
            className="my-4 flex items-center gap-3 text-[10.5px] font-medium uppercase tracking-[0.2em]"
            style={{ color: theme.sub }}
          >
            <span className="h-px flex-1" style={{ background: theme.border }} />
            or record
            <span className="h-px flex-1" style={{ background: theme.border }} />
          </div>

          {!supported ? (
            <p className="text-center text-[11px]" style={{ color: theme.sub }}>
              Voice notes aren&apos;t supported on this browser — please type instead.
            </p>
          ) : (
            <div className="flex flex-col items-center">
              {recState !== "recorded" ? (
                <button
                  type="button"
                  disabled={disabled}
                  onClick={() => (recState === "recording" ? stop() : void start())}
                  className="relative grid h-16 w-16 place-items-center rounded-full text-white shadow-lift transition-transform active:scale-95 disabled:opacity-50"
                  style={{ background: theme.gradientButton }}
                  aria-label={recState === "recording" ? "Stop recording" : "Start recording"}
                >
                  {recState === "recording" && (
                    <>
                      <span aria-hidden className="animate-pulse-ring absolute inset-0 rounded-full" style={{ background: theme.ringA }} />
                      <span
                        aria-hidden
                        className="animate-pulse-ring absolute inset-0 rounded-full"
                        style={{ background: theme.ringB, animationDelay: "0.6s" }}
                      />
                    </>
                  )}
                  <span className={recState === "recording" ? "animate-mic-pulse" : ""}>
                    <MicGlyph />
                  </span>
                </button>
              ) : (
                <PlaybackBar
                  theme={theme}
                  duration={recSeconds}
                  playing={playing}
                  onToggle={togglePlayback}
                  onReset={resetRecording}
                />
              )}
              {recState === "recording" && (
                <div className="mt-3 flex flex-col items-center gap-1.5">
                  <Waveform color={theme.accent} />
                  <div className="font-display text-sm tabular-nums">{fmt(recSeconds)}</div>
                </div>
              )}
              {recState === "idle" && (
                <p className="mt-2 text-[11px]" style={{ color: theme.sub }}>Tap to record</p>
              )}
              {recError ? (
                <p className="mt-2 text-center text-[11px] text-red-600">{recError}</p>
              ) : null}
            </div>
          )}
        </>
      ) : null}
    </div>
  );
});
