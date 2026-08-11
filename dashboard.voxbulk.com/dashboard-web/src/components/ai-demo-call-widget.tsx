import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useRouterState } from "@tanstack/react-router";
import { Loader2, PhoneOff } from "lucide-react";
import { toast } from "sonner";

import {
  clearCachedDemoStart,
  completeDemoSession,
  loadTelnyxRtc,
  normalizeTelnyxCustomHeaders,
  pollDemoEvents,
  readCachedDemoStart,
  startDemoSession,
  type AiDemoUiEvent,
} from "@/lib/ai-demo";

const REMOTE_AUDIO_ID = "voxbulk-ai-demo-remote-audio";
const ACTIVE_TIMEOUT_MS = 45_000;

type TelnyxCall = {
  id?: string;
  state?: string;
  hangup?: () => void;
  remoteStream?: MediaStream | null;
  localStream?: MediaStream | null;
};

function demoSessionFromLocation(): string {
  if (typeof window === "undefined") return "";
  try {
    const q = new URLSearchParams(window.location.search);
    return String(q.get("demo_session") || "").trim();
  } catch {
    return "";
  }
}

function stripDemoSessionQuery() {
  try {
    const url = new URL(window.location.href);
    if (!url.searchParams.has("demo_session")) return;
    url.searchParams.delete("demo_session");
    window.history.replaceState(window.history.state, "", url.pathname + url.search + url.hash);
  } catch {
    /* ignore */
  }
}

export function AiDemoCallWidget() {
  const navigate = useNavigate();
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const [sessionId, setSessionId] = useState(() => demoSessionFromLocation());
  const [phase, setPhase] = useState<"idle" | "connecting" | "live" | "ended">("idle");
  const [statusLine, setStatusLine] = useState("AI demo call");
  const callRef = useRef<TelnyxCall | null>(null);
  const clientRef = useRef<{
    disconnect?: () => void;
    off?: (ev: string, fn: (...args: unknown[]) => void) => void;
  } | null>(null);
  const notificationHandlerRef = useRef<((...args: unknown[]) => void) | null>(null);
  const localStreamRef = useRef<MediaStream | null>(null);
  const afterEventIdRef = useRef<string | null>(null);
  const activeTimerRef = useRef<number | null>(null);
  const softCapTimerRef = useRef<number | null>(null);
  const startedAtRef = useRef<number>(0);
  const startedRef = useRef(false);

  const navigateRoute = useCallback(
    (route: string) => {
      const path = route.startsWith("/") ? route : `/${route}`;
      if (pathname === path) return;
      void navigate({ to: path as never });
    },
    [navigate, pathname],
  );

  const applyEvents = useCallback(
    (events: AiDemoUiEvent[]) => {
      for (const ev of events) {
        if (ev.id) afterEventIdRef.current = ev.id;
        const route = String(ev.route || "").trim();
        if (route && (ev.type === "highlight_dashboard" || ev.type === "switch_kb" || ev.type === "show_pricing")) {
          const delay = typeof ev.delay_ms === "number" ? ev.delay_ms : 200;
          window.setTimeout(() => navigateRoute(route), delay);
        }
        if (ev.type === "request_sales_offer") {
          toast.message("Sales will follow up with the best offer");
        }
        if (ev.type === "end_demo") {
          setPhase("ended");
          setStatusLine("Demo ended");
        }
      }
    },
    [navigateRoute],
  );

  const hangup = useCallback(async () => {
    if (activeTimerRef.current) {
      window.clearTimeout(activeTimerRef.current);
      activeTimerRef.current = null;
    }
    if (softCapTimerRef.current) {
      window.clearTimeout(softCapTimerRef.current);
      softCapTimerRef.current = null;
    }
    try {
      const client = clientRef.current;
      const handler = notificationHandlerRef.current;
      if (client && handler) client.off?.("telnyx.notification", handler);
    } catch {
      /* ignore */
    }
    notificationHandlerRef.current = null;
    try {
      callRef.current?.hangup?.();
    } catch {
      /* ignore */
    }
    try {
      clientRef.current?.disconnect?.();
    } catch {
      /* ignore */
    }
    callRef.current = null;
    clientRef.current = null;
    try {
      localStreamRef.current?.getTracks().forEach((t) => t.stop());
    } catch {
      /* ignore */
    }
    localStreamRef.current = null;
  }, []);

  const finish = useCallback(
    async (note?: string) => {
      if (!sessionId) return;
      const duration = startedAtRef.current
        ? Math.max(1, Math.round((Date.now() - startedAtRef.current) / 1000))
        : undefined;
      try {
        await completeDemoSession({
          session_id: sessionId,
          summary: note || "Demo session ended",
          duration_seconds: duration,
        });
      } catch {
        /* still end UI */
      }
      await hangup();
      clearCachedDemoStart(sessionId);
      stripDemoSessionQuery();
      setPhase("ended");
      setStatusLine("Demo ended");
    },
    [hangup, sessionId],
  );

  useEffect(() => {
    const id = demoSessionFromLocation();
    if (id) setSessionId(id);
  }, []);

  useEffect(() => {
    if (!sessionId || startedRef.current) return;
    startedRef.current = true;
    let cancelled = false;

    (async () => {
      setPhase("connecting");
      setStatusLine("Connecting AI demo…");
      try {
        const cached = readCachedDemoStart(sessionId);
        const started =
          cached?.telnyx?.agent_id
            ? cached
            : await startDemoSession(sessionId, cached?.selected_services || []);
        if (cancelled) return;
        const agentId = started.telnyx?.agent_id;
        if (!agentId) throw new Error("Demo voice agent is not configured.");

        let micStream: MediaStream;
        try {
          micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
          localStreamRef.current = micStream;
        } catch {
          throw new Error("Microphone access is required for the AI demo call.");
        }

        const TelnyxRTC = await loadTelnyxRtc();
        const client = new TelnyxRTC({
          anonymous_login: { target_type: "ai_assistant", target_id: agentId },
        });
        clientRef.current = client as {
          disconnect?: () => void;
          off?: (ev: string, fn: (...args: unknown[]) => void) => void;
        };

        await new Promise<void>((resolve, reject) => {
          const t = window.setTimeout(() => reject(new Error("Telnyx connect timeout")), 30000);
          client.on("telnyx.ready", () => {
            window.clearTimeout(t);
            resolve();
          });
          client.on("telnyx.error", (err: unknown) => {
            window.clearTimeout(t);
            reject(err instanceof Error ? err : new Error("Telnyx error"));
          });
          client.connect();
        });

        const attachRemoteAudio = (call: TelnyxCall | null | undefined) => {
          const el = document.getElementById(REMOTE_AUDIO_ID) as HTMLAudioElement | null;
          const stream = call?.remoteStream ?? null;
          if (!el || !stream) return;
          if (el.srcObject !== stream) el.srcObject = stream;
          el.muted = false;
          el.volume = 1;
          void el.play().catch(() => {});
        };

        let wentLive = false;
        const onNotification = (notification: {
          type?: string;
          errorMessage?: string;
          call?: TelnyxCall;
        }) => {
          if (notification?.type === "userMediaError") {
            void finish("Microphone error");
            toast.error(notification.errorMessage || "Microphone error");
            return;
          }
          if (notification?.type !== "callUpdate" || !notification.call) return;
          const call = notification.call;
          callRef.current = call;
          attachRemoteAudio(call);
          const state = String(call.state || "").toLowerCase();
          if ((state === "active" || state === "answered" || state === "held") && !wentLive) {
            wentLive = true;
            if (activeTimerRef.current) {
              window.clearTimeout(activeTimerRef.current);
              activeTimerRef.current = null;
            }
            startedAtRef.current = Date.now();
            setPhase("live");
            setStatusLine("Live with AI — speak naturally");
            toast.success("AI demo connected");
          }
          if (state === "hangup" || state === "destroy" || state === "destroyed") {
            void finish("Call ended");
          }
        };
        notificationHandlerRef.current = onNotification as (...args: unknown[]) => void;
        client.on("telnyx.notification", onNotification);

        const codecs = RTCRtpReceiver.getCapabilities("audio")?.codecs || [];
        const opus = codecs.find((c) => c.mimeType.toLowerCase().includes("opus"));
        const call = client.newCall({
          destinationNumber: "",
          audio: true,
          video: false,
          customHeaders: normalizeTelnyxCustomHeaders(started.telnyx?.custom_headers),
          preferredCodecs: opus ? [opus] : undefined,
          localStream: micStream,
        });
        callRef.current = call as TelnyxCall;

        activeTimerRef.current = window.setTimeout(() => {
          if (!wentLive) {
            toast.error("AI did not join in time");
            void finish("AI join timeout");
          }
        }, ACTIVE_TIMEOUT_MS);

        const softCap = Math.max(3, Number(started.soft_cap_minutes || 7)) * 60 * 1000;
        softCapTimerRef.current = window.setTimeout(() => {
          toast.message("Wrapping up the demo");
          void finish("Soft cap reached");
        }, softCap);
      } catch (e) {
        startedRef.current = false;
        setPhase("ended");
        const msg = e instanceof Error ? e.message : "Could not start AI demo call";
        setStatusLine(msg);
        toast.error(msg);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [finish, sessionId]);

  useEffect(() => {
    if (!sessionId || phase === "ended" || phase === "idle") return;
    let cancelled = false;
    const tick = async () => {
      try {
        const res = await pollDemoEvents(sessionId, afterEventIdRef.current);
        if (cancelled) return;
        if (res.events?.length) applyEvents(res.events);
      } catch {
        /* ignore poll blips */
      }
    };
    void tick();
    const id = window.setInterval(() => void tick(), 1500);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [applyEvents, phase, sessionId]);

  if (!sessionId || phase === "idle") return null;
  if (phase === "ended") return null;

  return (
    <div className="fixed bottom-4 right-4 z-[80] flex max-w-sm flex-col gap-2 rounded-2xl border border-border bg-background/95 p-3 shadow-xl backdrop-blur">
      <audio id={REMOTE_AUDIO_ID} autoPlay playsInline className="hidden" />
      <div className="flex items-center gap-2">
        {phase === "connecting" ? (
          <Loader2 className="h-4 w-4 animate-spin text-primary" />
        ) : (
          <span className="relative flex h-2.5 w-2.5">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
            <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-500" />
          </span>
        )}
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">AI Demo</p>
          <p className="truncate text-xs text-muted-foreground">{statusLine}</p>
        </div>
        <button
          type="button"
          className="inline-flex h-9 items-center gap-1 rounded-full bg-destructive px-3 text-xs font-medium text-destructive-foreground"
          onClick={() => void finish("Visitor hung up")}
        >
          <PhoneOff className="h-3.5 w-3.5" />
          End
        </button>
      </div>
      <p className="text-[11px] text-muted-foreground">
        You are in the real Voxbulk Demo workspace. The agent will open Services, Packages, and Feedback pages as it talks.
      </p>
    </div>
  );
}
