import { createFileRoute } from "@tanstack/react-router";
import * as React from "react";
import { Loader2, Mic, MicOff, PhoneOff, ShieldCheck } from "lucide-react";
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
  custom_headers?: Record<string, string>;
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
const ACTIVE_TIMEOUT_MS = 25_000;

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

function InterviewMeetingRoomPage() {
  const { token } = Route.useParams();
  const remoteAudioRef = React.useRef<HTMLAudioElement | null>(null);
  const telnyxRef = React.useRef<{ disconnect?: () => void; off?: (event: string, handler: (...args: unknown[]) => void) => void } | null>(null);
  const telnyxCallRef = React.useRef<TelnyxCall | null>(null);
  const telnyxNotificationRef = React.useRef<((notification: TelnyxNotification) => void) | null>(null);
  const localStreamRef = React.useRef<MediaStream | null>(null);
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
  } | null>(null);
  const [nowMs, setNowMs] = React.useState(() => Date.now());

  const EARLY_JOIN_MS = 60_000;
  const slotMs = booking?.booked_start_at ? new Date(booking.booked_start_at).getTime() : null;
  const msUntilOpen = slotMs != null ? slotMs - EARLY_JOIN_MS - nowMs : 0;
  const canJoin = slotMs == null || msUntilOpen <= 0;

  const aiLevel = useAudioLevel(remoteStream, phase === "live" || phase === "aiJoining");
  const userLevel = useAudioLevel(localMeterStream, (phase === "live" || phase === "aiJoining") && !muted);

  React.useEffect(() => {
    let cancelled = false;
    void publicApiFetch<{
      candidate_name?: string;
      role?: string;
      booked_start_at?: string | null;
      channel?: string | null;
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
    if (phase !== "idle" || canJoin) return;
    const id = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [phase, canJoin]);

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

  React.useEffect(() => () => cleanupRtc(), [cleanupRtc]);

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
    setStatusLine("Requesting microphone…");
    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error("Your browser does not support microphone access — try Chrome or Edge on desktop.");
      }
      let micStream: MediaStream;
      try {
        micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        localStreamRef.current = micStream;
        setLocalMeterStream(micStream);
      } catch {
        throw new Error(
          "Microphone access is required — click Allow when your browser asks for the mic, then try again.",
        );
      }

      setStatusLine("Starting interview room…");
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

      setStatusLine("Connecting to Telnyx…");
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
          setError(
            notification.errorMessage ||
              "Microphone error — allow mic access for this site in browser settings and try again",
          );
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
          setStatusLine("AI interviewer is joining…");
        }
        if (state === "active" && !wentLive) {
          wentLive = true;
          clearActiveTimer();
          setAiPresent(true);
          setPhase("live");
          setStatusLine("AI is here — you can speak now");
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
      setStatusLine("Calling AI interviewer…");

      const codecs = RTCRtpReceiver.getCapabilities("audio")?.codecs || [];
      const opus = codecs.find((c) => c.mimeType.toLowerCase().includes("opus"));
      const call = client.newCall({
        destinationNumber: "",
        audio: true,
        video: false,
        remoteElement: REMOTE_AUDIO_ID,
        preferred_codecs: opus ? [opus] : undefined,
        customHeaders: start.custom_headers || {},
      }) as TelnyxCall;
      telnyxCallRef.current = call;
      attachRemoteAudio(call);
      if (call.localStream) setLocalMeterStream(call.localStream);

      activeTimerRef.current = setTimeout(() => {
        if (!wentLive) {
          webrtcLog("active timeout");
          cleanupRtc();
          setPhase("error");
          setError("The AI interviewer did not answer — please try again. Check your mic and speakers.");
        }
      }, ACTIVE_TIMEOUT_MS);
    } catch (e) {
      cleanupRtc();
      setPhase("error");
      setError(e instanceof Error ? e.message : "Could not start the meeting");
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
  const name = meta?.candidate_name || booking?.candidate_name || "Candidate";
  const userInitials = initialsFromName(name);

  const waitTotal = Math.max(0, Math.ceil(msUntilOpen / 1000));
  const waitMins = String(Math.floor(waitTotal / 60)).padStart(2, "0");
  const waitSecs = String(waitTotal % 60).padStart(2, "0");
  const slotTimeLabel = slotMs != null ? new Date(slotMs).toLocaleString() : "";

  const inCallUi = phase === "live" || phase === "aiJoining";

  return (
    <div className="min-h-screen bg-[#0a0e17] text-[#eef2f6]">
      <audio id={REMOTE_AUDIO_ID} ref={remoteAudioRef} autoPlay playsInline className="hidden" />
      <div className="mx-auto flex min-h-screen max-w-3xl flex-col px-4 py-6 sm:px-6">
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 pb-4">
          <div className="flex items-center gap-3">
            <img src="/brand/logo-white.svg" alt="VoxBulk" className="h-7 w-auto" />
            <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-slate-400">
              Audio interview
            </span>
          </div>
          {phase === "live" ? (
            <span className="flex items-center gap-2 rounded-full border border-emerald-500/20 bg-emerald-500/10 px-3 py-1 text-xs text-emerald-400">
              <span className="size-2 rounded-full bg-emerald-400 animate-pulse" />
              Live · {mins}:{secs}
            </span>
          ) : null}
        </header>

        <main className="flex flex-1 flex-col items-center justify-center py-10 text-center">
          <div className="w-full max-w-md rounded-2xl border border-white/10 bg-white/[0.03] p-8 shadow-2xl shadow-black/40">
            <p className="text-xs font-medium uppercase tracking-wider text-slate-400">VoxBulk AI interview</p>
            <h1 className="mt-2 text-2xl font-semibold tracking-tight text-white">{role}</h1>
            <p className="mt-2 text-sm text-slate-400">Hi {name} — this is an audio-only interview in your browser.</p>

            {phase === "idle" ? (
              <div className="mt-8 space-y-4">
                <div className="flex items-center justify-center gap-2 text-xs text-slate-400">
                  <ShieldCheck className="size-4 text-violet-400" />
                  No camera required · secure browser audio
                </div>
                {!canJoin ? (
                  <div className="rounded-xl border border-white/10 bg-white/[0.04] px-4 py-5">
                    <p className="text-xs uppercase tracking-wider text-slate-400">Waiting room</p>
                    <p className="mt-2 text-3xl font-semibold tabular-nums text-white">
                      {waitMins}:{waitSecs}
                    </p>
                    <p className="mt-2 text-xs text-slate-400">
                      Your interview starts at {slotTimeLabel}. The room opens 1 minute before — keep this page open.
                    </p>
                  </div>
                ) : null}
                <button
                  type="button"
                  onClick={() => void joinMeeting()}
                  disabled={!canJoin}
                  className="w-full rounded-xl bg-violet-600 px-4 py-3 text-sm font-semibold text-white transition hover:bg-violet-500 disabled:cursor-not-allowed disabled:bg-white/10 disabled:text-slate-400"
                >
                  {canJoin ? "Join interview room" : "Room opens soon…"}
                </button>
                <p className="text-xs text-slate-500">Use headphones if possible for the clearest conversation.</p>
              </div>
            ) : null}

            {phase === "connecting" ? (
              <div className="mt-10 flex flex-col items-center gap-3 text-slate-300">
                <Loader2 className="size-8 animate-spin text-violet-400" />
                <p className="text-sm">{statusLine || "Connecting…"}</p>
              </div>
            ) : null}

            {inCallUi ? (
              <div className="mt-8 space-y-5">
                <VoiceCallAvatars
                  aiLabel="AI Interviewer"
                  aiLevel={aiLevel}
                  aiPresent={aiPresent}
                  userLabel={name.split(" ")[0] || "You"}
                  userInitials={userInitials}
                  userLevel={userLevel}
                  micOn={!muted}
                />
                <p className="text-sm text-slate-300">
                  {phase === "live"
                    ? meta?.greeting
                      ? "The AI will greet you shortly — speak naturally after you hear the welcome."
                      : "Speak naturally — the AI interviewer is listening."
                    : statusLine || "Waiting for the AI interviewer…"}
                </p>
                {phase === "live" ? (
                  <div className="flex flex-wrap justify-center gap-3">
                    <button
                      type="button"
                      onClick={toggleMute}
                      className="inline-flex items-center gap-2 rounded-xl border border-white/15 bg-white/5 px-4 py-2.5 text-sm font-medium hover:bg-white/10"
                    >
                      {muted ? <MicOff className="size-4" /> : <Mic className="size-4" />}
                      {muted ? "Unmute" : "Mute"}
                    </button>
                    <button
                      type="button"
                      onClick={() => void endMeeting()}
                      className="inline-flex items-center gap-2 rounded-xl bg-red-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-red-500"
                    >
                      <PhoneOff className="size-4" />
                      End interview
                    </button>
                  </div>
                ) : (
                  <Loader2 className="mx-auto size-6 animate-spin text-violet-400" />
                )}
              </div>
            ) : null}

            {phase === "ended" ? (
              <div className="mt-8 space-y-3">
                <p className="text-lg font-medium text-white">Thank you — interview complete</p>
                <p className="text-sm text-slate-400">
                  You can close this page. The hiring team will review your interview shortly.
                </p>
              </div>
            ) : null}

            {phase === "error" || error ? (
              <div className="mt-8 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
                {error || "Something went wrong"}
                <button
                  type="button"
                  className="mt-3 block w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs font-medium text-white hover:bg-white/10"
                  onClick={() => {
                    setPhase("idle");
                    setError(null);
                    setStatusLine("");
                  }}
                >
                  Try again
                </button>
              </div>
            ) : null}
          </div>
        </main>

        <footer className="pb-4 text-center text-[11px] text-slate-500">
          Powered by VoxBulk · audio interview room
        </footer>
      </div>
    </div>
  );
}
