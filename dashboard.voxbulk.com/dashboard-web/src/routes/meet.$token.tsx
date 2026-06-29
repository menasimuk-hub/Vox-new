import { createFileRoute } from "@tanstack/react-router";
import * as React from "react";
import { Loader2, Mic, MicOff, PhoneOff, ShieldCheck } from "lucide-react";
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

type CallPhase = "idle" | "connecting" | "live" | "ended" | "error";

type TelnyxNotification = {
  type?: string;
  call?: { state?: string; id?: string };
  errorMessage?: string;
};

async function loadTelnyxRtc() {
  const mod = await import("@telnyx/webrtc");
  return mod.TelnyxRTC;
}

function InterviewMeetingRoomPage() {
  const { token } = Route.useParams();
  const remoteAudioRef = React.useRef<HTMLAudioElement | null>(null);
  const telnyxRef = React.useRef<{ disconnect?: () => void; off?: (event: string, handler: (...args: unknown[]) => void) => void } | null>(null);
  const telnyxCallRef = React.useRef<{ hangup?: () => void; id?: string } | null>(null);
  const telnyxNotificationRef = React.useRef<((notification: TelnyxNotification) => void) | null>(null);
  const startedAtRef = React.useRef<number | null>(null);

  const [phase, setPhase] = React.useState<CallPhase>("idle");
  const [error, setError] = React.useState<string | null>(null);
  const [meta, setMeta] = React.useState<MeetingStartResponse | null>(null);
  const [muted, setMuted] = React.useState(false);
  const [elapsed, setElapsed] = React.useState(0);
  const [booking, setBooking] = React.useState<{
    candidate_name?: string;
    role?: string;
    booked_start_at?: string | null;
    channel?: string | null;
  } | null>(null);
  const [nowMs, setNowMs] = React.useState(() => Date.now());

  // Room opens 1 minute before the booked slot (matches backend early-join window).
  const EARLY_JOIN_MS = 60_000;
  const slotMs = booking?.booked_start_at ? new Date(booking.booked_start_at).getTime() : null;
  const msUntilOpen = slotMs != null ? slotMs - EARLY_JOIN_MS - nowMs : 0;
  const canJoin = slotMs == null || msUntilOpen <= 0;

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
      .catch(() => {
        /* waiting area still works; join will surface any error */
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  React.useEffect(() => {
    if (phase !== "idle" || canJoin) return;
    const id = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [phase, canJoin]);

  const cleanupRtc = React.useCallback(() => {
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
  }, []);

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
    await completeMeeting(callId);
  }, [cleanupRtc, completeMeeting]);

  React.useEffect(() => {
    return () => {
      cleanupRtc();
    };
  }, [cleanupRtc]);

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
    try {
      const start = await publicApiFetch<MeetingStartResponse>(
        `/public/interview-booking/${encodeURIComponent(token)}/meeting/start`,
        { method: "POST", body: "{}" },
      );
      if (!start?.agent_id) {
        throw new Error("Interview agent is not available right now");
      }
      setMeta(start);

      const TelnyxRTC = await loadTelnyxRtc();
      const client = new TelnyxRTC({
        anonymous_login: {
          target_type: "ai_assistant",
          target_id: start.agent_id,
        },
      });
      telnyxRef.current = client;

      await new Promise<void>((resolve, reject) => {
        client.on("telnyx.ready", () => resolve());
        client.on("telnyx.error", (err: { message?: string }) =>
          reject(new Error(err?.message || "Could not connect to the interview room")),
        );
        client.connect();
      });

      const codecs = RTCRtpReceiver.getCapabilities("audio")?.codecs || [];
      const opus = codecs.find((c) => c.mimeType.toLowerCase().includes("opus"));
      const call = client.newCall({
        destinationNumber: "",
        remoteElement: remoteAudioRef.current || undefined,
        preferred_codecs: opus ? [opus] : undefined,
        customHeaders: start.custom_headers || {},
      });
      telnyxCallRef.current = call;

      await new Promise<void>((resolve, reject) => {
        const timeout = window.setTimeout(() => {
          reject(new Error("Connection timed out — check your microphone permission and try again"));
        }, 45_000);

        const onNotification = (notification: TelnyxNotification) => {
          if (notification?.type === "userMediaError") {
            window.clearTimeout(timeout);
            reject(
              new Error(
                notification.errorMessage ||
                  "Microphone access is required — allow the browser to use your mic and try again",
              ),
            );
            return;
          }
          if (notification?.type !== "callUpdate" || !notification.call) return;
          const state = notification.call.state;
          // AI assistants auto-answer; ringing means media path is up.
          if (state === "active" || state === "ringing") {
            window.clearTimeout(timeout);
            startedAtRef.current = Date.now();
            setPhase("live");
            setElapsed(0);
            resolve();
            return;
          }
          if (state === "hangup" || state === "destroy" || state === "destroyed") {
            window.clearTimeout(timeout);
            void endMeeting();
          }
        };

        telnyxNotificationRef.current = onNotification;
        client.on("telnyx.notification", onNotification);
      });
    } catch (e) {
      cleanupRtc();
      setPhase("error");
      setError(e instanceof Error ? e.message : "Could not start the meeting");
    }
  };

  const toggleMute = () => {
    const call = telnyxCallRef.current as { muteAudio?: () => void; unmuteAudio?: () => void } | null;
    if (!call) return;
    if (muted) {
      call.unmuteAudio?.();
    } else {
      call.muteAudio?.();
    }
    setMuted((m) => !m);
  };

  const mins = String(Math.floor(elapsed / 60)).padStart(2, "0");
  const secs = String(elapsed % 60).padStart(2, "0");
  const role = meta?.role || booking?.role || "Interview";
  const name = meta?.candidate_name || booking?.candidate_name || "Candidate";

  const waitTotal = Math.max(0, Math.ceil(msUntilOpen / 1000));
  const waitMins = String(Math.floor(waitTotal / 60)).padStart(2, "0");
  const waitSecs = String(waitTotal % 60).padStart(2, "0");
  const slotTimeLabel = slotMs != null ? new Date(slotMs).toLocaleString() : "";

  return (
    <div className="min-h-screen bg-[#0a0e17] text-[#eef2f6]">
      <audio ref={remoteAudioRef} autoPlay playsInline className="hidden" />
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
                <p className="text-sm">Connecting you to your AI interviewer…</p>
              </div>
            ) : null}

            {phase === "live" ? (
              <div className="mt-8 space-y-4">
                <div className="mx-auto flex size-24 items-center justify-center rounded-full bg-violet-500/15 ring-2 ring-violet-500/30">
                  <div className="size-16 rounded-full bg-violet-500/25 animate-pulse" />
                </div>
                <p className="text-sm text-slate-300">Speak naturally — the AI interviewer is listening.</p>
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
