import { createFileRoute } from "@tanstack/react-router";
import * as React from "react";
import { CheckCircle2, Loader2, Mic, MicOff, PhoneOff, ShieldCheck, Volume2 } from "lucide-react";
import { VoiceCallAvatars } from "@/components/VoiceCallAvatars";
import { useAudioLevel } from "@/hooks/useAudioLevel";
import { publicApiFetch } from "@/lib/api";

export const Route = createFileRoute("/meet/$token")({
  head: () => ({ meta: [{ title: "AI interview meeting — VoxBulk" }] }),
  component: InterviewMeetingRoomPage,
});

type MeetingStartResponse = {
  ok?: boolean;
  agent_id?: string;
  greeting?: string;
  custom_headers?: Record<string, string> | Array<{ name: string; value: string }>;
  web_calls_enabled?: boolean;
  meeting_url?: string;
  candidate_name?: string;
  role?: string;
};

type CallPhase = "idle" | "connecting" | "aiJoining" | "live" | "ended" | "error";

type TelnyxCall = {
  state?: string;
  id?: string;
  remoteStream?: MediaStream | null;
  localStream?: MediaStream | null;
  hangup?: () => void;
  muteAudio?: () => void;
  unmuteAudio?: () => void;
};

type TelnyxNotification = {
  type?: string;
  call?: TelnyxCall;
  errorMessage?: string;
};

const REMOTE_AUDIO_ID = "voxbulk-remote-audio";
const ACTIVE_TIMEOUT_MS = 45_000;

function normalizeTelnyxCustomHeaders(
  raw: Record<string, string> | Array<{ name: string; value: string }> | undefined,
): Array<{ name: string; value: string }> {
  if (!raw) return [];
  if (Array.isArray(raw)) {
    return raw.filter((h) => String(h?.name || "").trim() && String(h?.value || "").trim());
  }
  return Object.entries(raw)
    .map(([name, value]) => {
      const clean = String(value || "").trim();
      if (!clean) return null;
      const headerName = name.startsWith("X-") ? name : `X-${name}`;
      return { name: headerName, value: clean };
    })
    .filter((h): h is { name: string; value: string } => h != null);
}

function callLooksLive(call: TelnyxCall | null | undefined): boolean {
  const state = String(call?.state || "").toLowerCase();
  if (state === "active" || state === "held" || state === "speaking" || state === "answered") {
    return true;
  }
  const tracks = call?.remoteStream?.getAudioTracks?.() || [];
  return tracks.some((t) => t.readyState === "live" && t.enabled);
}

function webrtcLog(msg: string, detail?: unknown) {
  console.info("[webrtc]", msg, detail ?? "");
}

async function loadTelnyxRtc() {
  const mod = await import("@telnyx/webrtc");
  return mod.TelnyxRTC;
}

function initialsFromName(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function playSpeakerTestTone() {
  const AudioCtx = window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!AudioCtx) throw new Error("Audio is not supported in this browser");
  const ctx = new AudioCtx();
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.type = "sine";
  osc.frequency.value = 880;
  gain.gain.value = 0.0001;
  osc.connect(gain);
  gain.connect(ctx.destination);
  const now = ctx.currentTime;
  gain.gain.exponentialRampToValueAtTime(0.18, now + 0.05);
  gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.55);
  osc.start(now);
  osc.stop(now + 0.6);
  window.setTimeout(() => {
    void ctx.close().catch(() => {});
  }, 800);
}

type MeetLang = "en" | "ar";

const MEET_COPY = {
  en: {
    badge: "Audio interview",
    live: "Live",
    title: "VoxBulk AI interview",
    hi: (name: string) => `Hi ${name} — this is an audio-only interview in your browser.`,
    noCamera: "No camera required · secure browser audio",
    waitingRoom: "Waiting room",
    roomOpensIn: "Room opens in",
    interviewStartsIn: "Interview starts in",
    roomOpen: "Room is open — you can join now",
    startsAt: (when: string) => `Your interview starts at ${when}. The room opens 1 minute before — keep this page open.`,
    deviceTest: "Optional device check",
    deviceHint: "You can test your mic and speakers, or join straight away.",
    microphone: "Microphone",
    testMic: "Test mic",
    retestMic: "Retest mic",
    micSpeak: "Speak now — the bar should move when you talk.",
    micAllow: "Allow the mic, then speak to see the level.",
    speakers: "Speakers / headphones",
    playSound: "Play test sound",
    hearBeep: "You should hear a short beep. Turn up volume if you miss it.",
    joinSoon: "Room opens soon…",
    join: "Join interview room",
    headphones: "Use headphones if possible for the clearest conversation.",
    connecting: "Connecting…",
    requestingMic: "Requesting microphone…",
    aiLabel: "AI Interviewer",
    you: "You",
    speakNatural: "Speak naturally — the AI interviewer is listening.",
    greetSoon: "The AI will greet you shortly — speak naturally after you hear the welcome.",
    waitingAi: "Waiting for the AI interviewer…",
    mute: "Mute",
    unmute: "Unmute",
    end: "End interview",
    thanks: "Thank you — interview complete",
    closePage: "You can close this page. The hiring team will review your interview shortly.",
    tryAgain: "Try again",
    somethingWrong: "Something went wrong",
    footer: "Powered by VoxBulk · audio interview room",
    langLabel: "Interview language: English",
    micRequired: "Microphone access is required — click Allow when your browser asks, then try again.",
    speakerFail: "Could not play a test sound — check your speaker or headphone volume.",
    aiNoAnswer: "The AI interviewer did not answer — please try again. Check your mic and speakers.",
    micBrowser: "Your browser does not support microphone access — try Chrome or Edge.",
    micDesktop: "Your browser does not support microphone access — try Chrome or Edge on desktop.",
    micAllowJoin: "Microphone access is required — click Allow when your browser asks for the mic, then try again.",
  },
  ar: {
    badge: "مقابلة صوتية",
    live: "مباشر",
    title: "مقابلة VoxBulk بالذكاء الاصطناعي",
    hi: (name: string) => `مرحباً ${name} — هذه مقابلة صوتية فقط عبر المتصفح.`,
    noCamera: "لا حاجة للكاميرا · اتصال صوتي آمن",
    waitingRoom: "غرفة الانتظار",
    roomOpensIn: "تفتح الغرفة خلال",
    interviewStartsIn: "تبدأ المقابلة خلال",
    roomOpen: "الغرفة مفتوحة — يمكنك الانضمام الآن",
    startsAt: (when: string) => `تبدأ مقابلتك في ${when}. تفتح الغرفة قبل دقيقة واحدة — أبقِ هذه الصفحة مفتوحة.`,
    deviceTest: "اختبار الأجهزة (اختياري)",
    deviceHint: "يمكنك اختبار الميكروفون والسماعات، أو الانضمام مباشرة.",
    microphone: "الميكروفون",
    testMic: "اختبار الميكروفون",
    retestMic: "إعادة الاختبار",
    micSpeak: "تحدث الآن — يجب أن يتحرك الشريط عند الكلام.",
    micAllow: "اسمح بالميكروفون ثم تحدث لرؤية المستوى.",
    speakers: "السماعات / سماعة الرأس",
    playSound: "تشغيل صوت تجريبي",
    hearBeep: "يجب أن تسمع صوتاً قصيراً. ارفع الصوت إن لم تسمعه.",
    joinSoon: "الغرفة تفتح قريباً…",
    join: "انضم إلى غرفة المقابلة",
    headphones: "يفضّل استخدام سماعة رأس لأوضح محادثة.",
    connecting: "جارٍ الاتصال…",
    requestingMic: "طلب إذن الميكروفون…",
    aiLabel: "المحاور الذكي",
    you: "أنت",
    speakNatural: "تحدث بشكل طبيعي — المحاور الذكي يستمع.",
    greetSoon: "سيرحّب بك المحاور قريباً — تحدث بعد سماع الترحيب.",
    waitingAi: "بانتظار المحاور الذكي…",
    mute: "كتم الصوت",
    unmute: "إلغاء الكتم",
    end: "إنهاء المقابلة",
    thanks: "شكراً لك — انتهت المقابلة",
    closePage: "يمكنك إغلاق هذه الصفحة. سيراجع فريق التوظيف مقابلتك قريباً.",
    tryAgain: "حاول مرة أخرى",
    somethingWrong: "حدث خطأ ما",
    footer: "مدعوم من VoxBulk · غرفة مقابلة صوتية",
    langLabel: "لغة المقابلة: العربية",
    micRequired: "يلزم السماح بالميكروفون — اضغط سماح عندما يطلب المتصفح، ثم حاول مرة أخرى.",
    speakerFail: "تعذّر تشغيل الصوت التجريبي — تحقق من مستوى السماعة.",
    aiNoAnswer: "لم يرد المحاور الذكي — حاول مرة أخرى. تحقق من الميكروفون والسماعات.",
    micBrowser: "متصفحك لا يدعم الميكروفون — جرّب Chrome أو Edge.",
    micDesktop: "متصفحك لا يدعم الميكروفون — جرّب Chrome أو Edge على الكمبيوتر.",
    micAllowJoin: "يلزم السماح بالميكروفون — اضغط سماح عندما يطلب المتصفح، ثم حاول مرة أخرى.",
  },
} as const;

function formatCountdown(totalSeconds: number): string {
  const safe = Math.max(0, totalSeconds);
  const h = Math.floor(safe / 3600);
  const m = Math.floor((safe % 3600) / 60);
  const s = safe % 60;
  if (h > 0) {
    return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  }
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function InterviewMeetingRoomPage() {
  const { token } = Route.useParams();
  const remoteAudioRef = React.useRef<HTMLAudioElement | null>(null);
  const telnyxRef = React.useRef<{ disconnect?: () => void; off?: (event: string, handler: (...args: unknown[]) => void) => void } | null>(null);
  const telnyxCallRef = React.useRef<TelnyxCall | null>(null);
  const telnyxNotificationRef = React.useRef<((notification: TelnyxNotification) => void) | null>(null);
  const localStreamRef = React.useRef<MediaStream | null>(null);
  const testStreamRef = React.useRef<MediaStream | null>(null);
  const activeTimerRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  const startedAtRef = React.useRef<number | null>(null);

  const [phase, setPhase] = React.useState<CallPhase>("idle");
  const [statusLine, setStatusLine] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [meta, setMeta] = React.useState<MeetingStartResponse | null>(null);
  const [muted, setMuted] = React.useState(false);
  const [elapsed, setElapsed] = React.useState(0);
  const [aiPresent, setAiPresent] = React.useState(false);
  const [remoteStream, setRemoteStream] = React.useState<MediaStream | null>(null);
  const [localMeterStream, setLocalMeterStream] = React.useState<MediaStream | null>(null);
  const [booking, setBooking] = React.useState<{
    candidate_name?: string;
    role?: string;
    booked_start_at?: string | null;
    channel?: string | null;
    interview_language?: string | null;
  } | null>(null);
  const [nowMs, setNowMs] = React.useState(() => Date.now());
  const [deviceReady, setDeviceReady] = React.useState(false);
  const [micTesting, setMicTesting] = React.useState(false);
  const [speakerPlayed, setSpeakerPlayed] = React.useState(false);
  const [deviceError, setDeviceError] = React.useState<string | null>(null);
  const [testStream, setTestStream] = React.useState<MediaStream | null>(null);

  const lang: MeetLang = booking?.interview_language === "ar" ? "ar" : "en";
  const t = MEET_COPY[lang];
  const isRtl = lang === "ar";

  const EARLY_JOIN_MS = 60_000;
  const slotMs = booking?.booked_start_at ? new Date(booking.booked_start_at).getTime() : null;
  const msUntilOpen = slotMs != null ? slotMs - EARLY_JOIN_MS - nowMs : 0;
  const msUntilStart = slotMs != null ? slotMs - nowMs : 0;
  const canJoin = slotMs == null || msUntilOpen <= 0;
  const showCountdown = phase === "idle" && slotMs != null;

  const aiLevel = useAudioLevel(remoteStream, phase === "live" || phase === "aiJoining");
  const userLevel = useAudioLevel(localMeterStream, (phase === "live" || phase === "aiJoining") && !muted);
  const testMicLevel = useAudioLevel(testStream, phase === "idle" && micTesting);

  React.useEffect(() => {
    let cancelled = false;
    void publicApiFetch<{
      candidate_name?: string;
      role?: string;
      booked_start_at?: string | null;
      channel?: string | null;
      interview_language?: string | null;
    }>(`/public/interview-booking/${encodeURIComponent(token)}`)
      .then((res) => {
        if (!cancelled) setBooking(res);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [token]);

  React.useEffect(() => {
    if (!showCountdown) return;
    const id = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [showCountdown]);

  const clearActiveTimer = React.useCallback(() => {
    if (activeTimerRef.current) {
      clearTimeout(activeTimerRef.current);
      activeTimerRef.current = null;
    }
  }, []);

  const attachRemoteAudio = React.useCallback((call: TelnyxCall | null | undefined) => {
    const el = remoteAudioRef.current;
    const stream = call?.remoteStream ?? null;
    if (stream) setRemoteStream(stream);
    if (!el || !stream) return;
    if (el.srcObject !== stream) el.srcObject = stream;
    el.muted = false;
    el.volume = 1;
    void el.play().catch(() => {});
  }, []);

  const stopLocalStream = React.useCallback(() => {
    localStreamRef.current?.getTracks().forEach((t) => t.stop());
    localStreamRef.current = null;
    setLocalMeterStream(null);
  }, []);

  const stopTestStream = React.useCallback(() => {
    testStreamRef.current?.getTracks().forEach((t) => t.stop());
    testStreamRef.current = null;
    setTestStream(null);
    setMicTesting(false);
  }, []);

  const startMicTest = React.useCallback(async () => {
    setDeviceError(null);
    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error(t.micBrowser);
      }
      stopTestStream();
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      testStreamRef.current = stream;
      setTestStream(stream);
      setMicTesting(true);
      setDeviceReady(true);
    } catch {
      setDeviceReady(false);
      setDeviceError(t.micRequired);
    }
  }, [stopTestStream, t.micBrowser, t.micRequired]);

  const testSpeaker = React.useCallback(() => {
    setDeviceError(null);
    try {
      playSpeakerTestTone();
      setSpeakerPlayed(true);
    } catch {
      setDeviceError(t.speakerFail);
    }
  }, [t.speakerFail]);

  const cleanupRtc = React.useCallback(() => {
    clearActiveTimer();
    try {
      const client = telnyxRef.current;
      const handler = telnyxNotificationRef.current;
      if (client && handler) {
        client.off?.("telnyx.notification", handler as (...args: unknown[]) => void);
      }
      telnyxNotificationRef.current = null;
      telnyxCallRef.current?.hangup?.();
      telnyxRef.current?.disconnect?.();
    } catch {
      /* ignore */
    }
    telnyxRef.current = null;
    telnyxCallRef.current = null;
    setRemoteStream(null);
    setAiPresent(false);
    stopLocalStream();
  }, [clearActiveTimer, stopLocalStream]);

  const completeMeeting = React.useCallback(
    async (providerCallId?: string) => {
      const duration =
        startedAtRef.current != null
          ? Math.max(1, Math.round((Date.now() - startedAtRef.current) / 1000))
          : undefined;
      try {
        await publicApiFetch(`/public/interview-booking/${encodeURIComponent(token)}/meeting/complete`, {
          method: "POST",
          body: JSON.stringify({
            duration_seconds: duration,
            provider_call_id: providerCallId || telnyxCallRef.current?.id || undefined,
          }),
        });
      } catch {
        /* best effort */
      }
      startedAtRef.current = null;
    },
    [token],
  );

  const endMeeting = React.useCallback(async () => {
    const callId = telnyxCallRef.current?.id;
    cleanupRtc();
    setPhase("ended");
    setStatusLine("");
    await completeMeeting(callId);
  }, [cleanupRtc, completeMeeting]);

  React.useEffect(() => () => {
    cleanupRtc();
    stopTestStream();
  }, [cleanupRtc, stopTestStream]);

  React.useEffect(() => {
    if (phase !== "live" || startedAtRef.current == null) return;
    const id = window.setInterval(() => {
      setElapsed(Math.max(0, Math.floor((Date.now() - startedAtRef.current!) / 1000)));
    }, 1000);
    return () => window.clearInterval(id);
  }, [phase]);

  const joinMeeting = async () => {
    setError(null);
    setPhase("connecting");
    setStatusLine(t.requestingMic);
    stopTestStream();
    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error(t.micDesktop);
      }
      let micStream: MediaStream;
      try {
        micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        localStreamRef.current = micStream;
        setLocalMeterStream(micStream);
      } catch {
        throw new Error(t.micAllowJoin);
      }

      setStatusLine(t.connecting);
      const start = await publicApiFetch<MeetingStartResponse>(
        `/public/interview-booking/${encodeURIComponent(token)}/meeting/start`,
        { method: "POST", body: "{}" },
      );
      if (!start?.agent_id) throw new Error("Interview agent is not available right now");
      if (start.web_calls_enabled === false) {
        throw new Error("Online meeting is not enabled for this interview agent — contact the employer.");
      }
      setMeta(start);

      const TelnyxRTC = await loadTelnyxRtc();
      const client = new TelnyxRTC({
        anonymous_login: { target_type: "ai_assistant", target_id: start.agent_id },
      });
      telnyxRef.current = client;

      setStatusLine(t.connecting);
      await new Promise<void>((resolve, reject) => {
        const connectTimeout = window.setTimeout(() => {
          reject(new Error("Could not reach the interview server — check your connection and try again"));
        }, 30_000);
        client.on("telnyx.ready", () => {
          window.clearTimeout(connectTimeout);
          webrtcLog("telnyx.ready");
          resolve();
        });
        client.on("telnyx.error", (err: { message?: string }) => {
          window.clearTimeout(connectTimeout);
          webrtcLog("telnyx.error", err);
          reject(new Error(err?.message || "Could not connect to the interview room"));
        });
        client.connect();
      });

      let wentLive = false;
      const onNotification = (notification: TelnyxNotification) => {
        webrtcLog("notification", notification);
        if (notification?.type === "userMediaError") {
          setPhase("error");
          setError(notification.errorMessage || t.micAllowJoin);
          return;
        }
        if (notification?.type !== "callUpdate" || !notification.call) return;
        const call = notification.call;
        const state = call.state;
        telnyxCallRef.current = call;
        attachRemoteAudio(call);
        if (call.localStream) setLocalMeterStream(call.localStream);

        if (state === "ringing" || state === "new" || state === "answering") {
          setPhase("aiJoining");
          setStatusLine(t.waitingAi);
        }
        if (callLooksLive(call) && !wentLive) {
          wentLive = true;
          clearActiveTimer();
          setAiPresent(true);
          setPhase("live");
          setStatusLine(t.speakNatural);
          startedAtRef.current = Date.now();
          setElapsed(0);
          attachRemoteAudio(call);
        }
        if (state === "hangup" || state === "destroy" || state === "destroyed") {
          void endMeeting();
        }
      };
      telnyxNotificationRef.current = onNotification;
      client.on("telnyx.notification", onNotification);

      setPhase("aiJoining");
      setStatusLine(t.waitingAi);

      const codecs = RTCRtpReceiver.getCapabilities("audio")?.codecs || [];
      const opus = codecs.find((c) => c.mimeType.toLowerCase().includes("opus"));
      const call = client.newCall({
        destinationNumber: "",
        audio: true,
        video: false,
        remoteElement: REMOTE_AUDIO_ID,
        preferred_codecs: opus ? [opus] : undefined,
        customHeaders: normalizeTelnyxCustomHeaders(start.custom_headers),
      }) as TelnyxCall;
      telnyxCallRef.current = call;
      attachRemoteAudio(call);
      if (call.localStream) setLocalMeterStream(call.localStream);

      activeTimerRef.current = setTimeout(() => {
        if (!wentLive) {
          webrtcLog("active timeout");
          cleanupRtc();
          setPhase("error");
          setError(t.aiNoAnswer);
        }
      }, ACTIVE_TIMEOUT_MS);
    } catch (e) {
      cleanupRtc();
      setPhase("error");
      setError(e instanceof Error ? e.message : t.somethingWrong);
      setStatusLine("");
    }
  };

  const toggleMute = () => {
    const call = telnyxCallRef.current;
    if (!call) return;
    if (muted) call.unmuteAudio?.();
    else call.muteAudio?.();
    setMuted((m) => !m);
  };

  const mins = String(Math.floor(elapsed / 60)).padStart(2, "0");
  const secs = String(elapsed % 60).padStart(2, "0");
  const role = meta?.role || booking?.role || "Interview";
  const name = meta?.candidate_name || booking?.candidate_name || (lang === "ar" ? "المرشح" : "Candidate");
  const userInitials = initialsFromName(name);

  const openCountdown = formatCountdown(Math.ceil(msUntilOpen / 1000));
  const startCountdown = formatCountdown(Math.ceil(msUntilStart / 1000));
  const slotTimeLabel =
    slotMs != null
      ? new Date(slotMs).toLocaleString(lang === "ar" ? "ar" : "en-GB", {
          weekday: "short",
          day: "numeric",
          month: "short",
          hour: "2-digit",
          minute: "2-digit",
        })
      : "";

  const inCallUi = phase === "live" || phase === "aiJoining";

  return (
    <div
      className="h-dvh max-h-dvh overflow-hidden bg-[#0a0e17] text-[#eef2f6]"
      dir={isRtl ? "rtl" : "ltr"}
      lang={lang}
    >
      <audio id={REMOTE_AUDIO_ID} ref={remoteAudioRef} autoPlay playsInline className="hidden" />
      <div className="mx-auto flex h-full w-full max-w-lg flex-col px-4 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-[max(0.75rem,env(safe-area-inset-top))] sm:max-w-3xl sm:px-6 sm:py-6">
        <header className="flex shrink-0 items-center justify-between gap-3 pb-3 sm:border-b sm:border-white/10 sm:pb-4">
          <div className="flex items-center gap-2.5 sm:gap-3">
            <img src="/brand/logo-white.svg" alt="VoxBulk" className="h-6 w-auto sm:h-7" />
            <span className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-[11px] text-slate-400 sm:text-xs">
              {t.badge}
            </span>
          </div>
          {phase === "live" ? (
            <span className="flex items-center gap-2 rounded-full border border-emerald-500/20 bg-emerald-500/10 px-3 py-1 text-xs text-emerald-400">
              <span className="size-2 rounded-full bg-emerald-400 animate-pulse" />
              {t.live} · {mins}:{secs}
            </span>
          ) : null}
        </header>

        <main className="flex min-h-0 flex-1 flex-col text-center">
          <div className="flex min-h-0 flex-1 flex-col rounded-none border-0 bg-transparent p-0 sm:rounded-2xl sm:border sm:border-white/10 sm:bg-white/[0.03] sm:p-8 sm:shadow-2xl sm:shadow-black/40">
            <div className="shrink-0 pt-1 sm:pt-0">
              <p className="text-[11px] font-medium uppercase tracking-wider text-slate-400 sm:text-xs">{t.title}</p>
              <h1 className="mt-1.5 line-clamp-2 text-2xl font-semibold tracking-tight text-white sm:mt-2 sm:text-2xl">
                {role}
              </h1>
              <p className="mt-1.5 text-sm text-slate-400 sm:mt-2">{t.hi(name.split(" ")[0] || name)}</p>
              <p className="mt-1 text-xs text-violet-300/90 sm:mt-2">{t.langLabel}</p>
            </div>

            {phase === "idle" ? (
              <div className="mt-4 flex min-h-0 flex-1 flex-col gap-3 sm:mt-6 sm:gap-4">
                <div className="flex items-center justify-center gap-2 text-xs text-slate-400">
                  <ShieldCheck className="size-4 text-violet-400" />
                  {t.noCamera}
                </div>

                {showCountdown ? (
                  <div className="flex flex-1 flex-col items-center justify-center rounded-2xl border border-violet-500/30 bg-violet-500/10 px-4 py-6 sm:flex-none sm:py-8">
                    <p className="text-xs uppercase tracking-wider text-violet-200/80">{t.waitingRoom}</p>
                    {!canJoin ? (
                      <>
                        <p className="mt-3 text-sm text-slate-300">{t.roomOpensIn}</p>
                        <p className="mt-2 text-6xl font-semibold tabular-nums tracking-tight text-white sm:text-5xl">
                          {openCountdown}
                        </p>
                      </>
                    ) : msUntilStart > 0 ? (
                      <>
                        <p className="mt-3 text-sm text-emerald-300">{t.roomOpen}</p>
                        <p className="mt-2 text-sm text-slate-300">{t.interviewStartsIn}</p>
                        <p className="mt-2 text-6xl font-semibold tabular-nums tracking-tight text-white sm:text-5xl">
                          {startCountdown}
                        </p>
                      </>
                    ) : (
                      <>
                        <p className="mt-3 text-sm text-emerald-300">{t.roomOpen}</p>
                        <p className="mt-2 text-5xl font-semibold tabular-nums text-white">00:00</p>
                      </>
                    )}
                    <p className="mt-4 max-w-sm text-xs leading-relaxed text-slate-400">{t.startsAt(slotTimeLabel)}</p>
                  </div>
                ) : (
                  <div className="flex-1" />
                )}

                <div className="shrink-0 rounded-2xl border border-white/10 bg-white/[0.04] p-3 text-start sm:p-4">
                  <div className="flex items-baseline justify-between gap-2">
                    <p className="text-[11px] font-medium uppercase tracking-wider text-slate-400 sm:text-xs">
                      {t.deviceTest}
                    </p>
                    <p className="text-[10px] text-slate-500 sm:text-xs">{t.deviceHint}</p>
                  </div>

                  <div className="mt-3 grid grid-cols-1 gap-2.5 sm:gap-3">
                    <div className="rounded-xl border border-white/10 bg-black/20 p-3">
                      <div className="flex items-center justify-between gap-3">
                        <div className="flex min-w-0 items-center gap-2 text-sm text-slate-200">
                          <Mic className="size-4 shrink-0 text-violet-300" />
                          <span className="truncate">{t.microphone}</span>
                          {deviceReady ? <CheckCircle2 className="size-3.5 shrink-0 text-emerald-400" /> : null}
                        </div>
                        <button
                          type="button"
                          onClick={() => void startMicTest()}
                          className="shrink-0 rounded-lg border border-white/15 bg-white/5 px-3 py-2 text-xs font-medium text-white hover:bg-white/10"
                        >
                          {micTesting ? t.retestMic : t.testMic}
                        </button>
                      </div>
                      <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/10">
                        <div
                          className="h-full rounded-full bg-emerald-400 transition-[width] duration-75"
                          style={{ width: `${Math.min(100, Math.round(testMicLevel * 220))}%` }}
                        />
                      </div>
                    </div>

                    <div className="rounded-xl border border-white/10 bg-black/20 p-3">
                      <div className="flex items-center justify-between gap-3">
                        <div className="flex min-w-0 items-center gap-2 text-sm text-slate-200">
                          <Volume2 className="size-4 shrink-0 text-violet-300" />
                          <span className="truncate">{t.speakers}</span>
                          {speakerPlayed ? <CheckCircle2 className="size-3.5 shrink-0 text-emerald-400" /> : null}
                        </div>
                        <button
                          type="button"
                          onClick={testSpeaker}
                          className="shrink-0 rounded-lg border border-white/15 bg-white/5 px-3 py-2 text-xs font-medium text-white hover:bg-white/10"
                        >
                          {t.playSound}
                        </button>
                      </div>
                    </div>
                  </div>

                  {deviceError ? <p className="mt-2 text-xs text-red-300">{deviceError}</p> : null}
                </div>

                <div className="shrink-0 space-y-2 pt-1">
                  <button
                    type="button"
                    onClick={() => void joinMeeting()}
                    disabled={!canJoin}
                    className="w-full rounded-2xl bg-violet-600 px-4 py-4 text-base font-semibold text-white transition hover:bg-violet-500 disabled:cursor-not-allowed disabled:bg-white/10 disabled:text-slate-400 sm:rounded-xl sm:py-3 sm:text-sm"
                  >
                    {!canJoin ? t.joinSoon : t.join}
                  </button>
                  <p className="text-xs text-slate-500">{t.headphones}</p>
                </div>
              </div>
            ) : null}

            {phase === "connecting" ? (
              <div className="flex flex-1 flex-col items-center justify-center gap-4 text-slate-300">
                <Loader2 className="size-10 animate-spin text-violet-400" />
                <p className="text-base sm:text-sm">{statusLine || t.connecting}</p>
              </div>
            ) : null}

            {inCallUi ? (
              <div className="mt-4 flex flex-1 flex-col items-center justify-center gap-6 sm:mt-8 sm:gap-5">
                <VoiceCallAvatars
                  aiLabel={t.aiLabel}
                  aiLevel={aiLevel}
                  aiPresent={aiPresent}
                  userLabel={name.split(" ")[0] || t.you}
                  userInitials={userInitials}
                  userLevel={userLevel}
                  micOn={!muted}
                />
                <p className="max-w-sm text-sm text-slate-300">
                  {phase === "live"
                    ? meta?.greeting
                      ? t.greetSoon
                      : t.speakNatural
                    : statusLine || t.waitingAi}
                </p>
                {phase === "live" ? (
                  <div className="flex w-full max-w-sm flex-col gap-3 sm:max-w-none sm:flex-row sm:flex-wrap sm:justify-center">
                    <button
                      type="button"
                      onClick={toggleMute}
                      className="inline-flex flex-1 items-center justify-center gap-2 rounded-2xl border border-white/15 bg-white/5 px-4 py-3.5 text-base font-medium hover:bg-white/10 sm:flex-none sm:rounded-xl sm:py-2.5 sm:text-sm"
                    >
                      {muted ? <MicOff className="size-5 sm:size-4" /> : <Mic className="size-5 sm:size-4" />}
                      {muted ? t.unmute : t.mute}
                    </button>
                    <button
                      type="button"
                      onClick={() => void endMeeting()}
                      className="inline-flex flex-1 items-center justify-center gap-2 rounded-2xl bg-red-600 px-4 py-3.5 text-base font-semibold text-white hover:bg-red-500 sm:flex-none sm:rounded-xl sm:py-2.5 sm:text-sm"
                    >
                      <PhoneOff className="size-5 sm:size-4" />
                      {t.end}
                    </button>
                  </div>
                ) : (
                  <Loader2 className="size-8 animate-spin text-violet-400" />
                )}
              </div>
            ) : null}

            {phase === "ended" ? (
              <div className="flex flex-1 flex-col items-center justify-center space-y-3">
                <p className="text-xl font-medium text-white sm:text-lg">{t.thanks}</p>
                <p className="max-w-sm text-sm text-slate-400">{t.closePage}</p>
              </div>
            ) : null}

            {phase === "error" || error ? (
              <div className="mt-auto rounded-2xl border border-red-500/30 bg-red-500/10 px-4 py-4 text-sm text-red-200 sm:mt-8">
                {error || t.somethingWrong}
                <button
                  type="button"
                  className="mt-4 block w-full rounded-xl border border-white/10 bg-white/5 px-3 py-3 text-sm font-medium text-white hover:bg-white/10"
                  onClick={() => {
                    setPhase("idle");
                    setError(null);
                    setStatusLine("");
                    setDeviceReady(false);
                    setSpeakerPlayed(false);
                    setDeviceError(null);
                  }}
                >
                  {t.tryAgain}
                </button>
              </div>
            ) : null}
          </div>
        </main>

        <footer className="hidden shrink-0 pb-1 text-center text-[11px] text-slate-500 sm:block sm:pb-4">
          {t.footer}
        </footer>
      </div>
    </div>
  );
}
