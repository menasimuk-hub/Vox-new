import { useCallback, useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { useNavigate, useRouterState } from "@tanstack/react-router";
import { GripVertical, Loader2, PhoneOff } from "lucide-react";
import { toast } from "sonner";

import { clearAllSessionStorage } from "@/lib/session-storage";
import {
  clearCachedDemoStart,
  completeDemoSession,
  demoThanksUrl,
  fetchDemoSessionGate,
  loadTelnyxRtc,
  markAiDemoMode,
  normalizeTelnyxCustomHeaders,
  pollDemoEvents,
  readCachedDemoStart,
  reportDemoUserClick,
  startDemoSession,
  type AiDemoUiEvent,
} from "@/lib/ai-demo";
import {
  clearDemoHighlight,
  hasDemoHighlight,
  parseDemoRoute,
  scheduleDemoHighlight,
} from "@/lib/ai-demo-highlight";
import {
  DEMO_TOUR_BEATS,
  DEMO_WRAP_MESSAGE,
  demoTourAdvanceMessage,
  demoTourBeatAt,
  demoTourStartMessage,
  nextIndexAfterClick,
  type DemoTourBeat,
} from "@/lib/ai-demo-tour";

const REMOTE_AUDIO_ID = "voxbulk-ai-demo-remote-audio";
const ACTIVE_TIMEOUT_MS = 45_000;
const POS_KEY = "voxbulk_ai_demo_widget_pos";

type TelnyxCall = {
  id?: string;
  state?: string;
  hangup?: () => void;
  remoteStream?: MediaStream | null;
  localStream?: MediaStream | null;
  /** Official JS WebRTC API — injects a user text turn into the AI assistant. */
  sendConversationMessage?: (message: string, attachments?: string[]) => Promise<unknown> | unknown;
};

function callLooksLive(call: TelnyxCall | null | undefined): boolean {
  const state = String(call?.state || "").toLowerCase();
  return state === "active" || state === "answered" || state === "held";
}

type WidgetPos = { x: number; y: number };

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

function readSavedPos(): WidgetPos {
  try {
    const raw = localStorage.getItem(POS_KEY);
    if (!raw) return { x: 12, y: 12 };
    const parsed = JSON.parse(raw) as WidgetPos;
    if (typeof parsed?.x === "number" && typeof parsed?.y === "number") {
      return {
        x: Math.max(8, Math.min(parsed.x, window.innerWidth - 160)),
        y: Math.max(8, Math.min(parsed.y, window.innerHeight - 56)),
      };
    }
  } catch {
    /* ignore */
  }
  return { x: 12, y: 12 };
}

function wipeDemoAuthAndLeave(sessionId: string, thanksUrl?: string | null) {
  clearCachedDemoStart(sessionId);
  markAiDemoMode(false);
  stripDemoSessionQuery();
  try {
    clearAllSessionStorage();
  } catch {
    /* ignore */
  }
  window.location.replace(demoThanksUrl(sessionId, thanksUrl));
}

export function AiDemoCallWidget() {
  const navigate = useNavigate();
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const [sessionId, setSessionId] = useState(() => demoSessionFromLocation());
  const [phase, setPhase] = useState<"idle" | "connecting" | "live" | "ended">("idle");
  const [statusLine, setStatusLine] = useState("AI demo call");
  const [pos, setPos] = useState<WidgetPos>(() =>
    typeof window === "undefined" ? { x: 12, y: 12 } : readSavedPos(),
  );
  const dragRef = useRef<{
    active: boolean;
    ox: number;
    oy: number;
    startX: number;
    startY: number;
  } | null>(null);
  const callRef = useRef<TelnyxCall | null>(null);
  const clientRef = useRef<{
    disconnect?: () => void;
    off?: (ev: string, fn: (...args: unknown[]) => void) => void;
  } | null>(null);
  const pendingAgentMsgsRef = useRef<string[]>([]);

  const beatIndexRef = useRef(-1);
  const tourStartedRef = useRef(false);
  const wizardPauseRef = useRef<number | null>(null);
  const startTourRef = useRef<() => void>(() => undefined);

  const flushAgentMessages = useCallback(() => {
    const call = callRef.current;
    if (!call || !callLooksLive(call)) return;
    const send = call.sendConversationMessage;
    if (typeof send !== "function") {
      if (pendingAgentMsgsRef.current.length) {
        console.warn(
          "[ai-demo] call.sendConversationMessage missing — Next/Click will not reach Leo",
          { state: call.state, keys: Object.getOwnPropertyNames(call) },
        );
      }
      return;
    }
    const queued = pendingAgentMsgsRef.current.splice(0);
    for (const text of queued) {
      try {
        const result = send.call(call, text);
        void Promise.resolve(result).then(
          () => undefined,
          (err: unknown) => {
            console.warn("[ai-demo] sendConversationMessage rejected", err);
          },
        );
      } catch (err) {
        console.warn("[ai-demo] sendConversationMessage threw", err);
      }
    }
  }, []);

  const sendToAgent = useCallback(
    (msg: string) => {
      const text = String(msg || "").trim();
      if (!text) return;
      pendingAgentMsgsRef.current.push(text);
      if (pendingAgentMsgsRef.current.length > 6) {
        pendingAgentMsgsRef.current = pendingAgentMsgsRef.current.slice(-6);
      }
      flushAgentMessages();
    },
    [flushAgentMessages],
  );

  const notifySpotlight = useCallback(
    (beat: DemoTourBeat) => {
      sendToAgent(demoTourAdvanceMessage(beat));
    },
    [sendToAgent],
  );

  const notificationHandlerRef = useRef<((...args: unknown[]) => void) | null>(null);
  const localStreamRef = useRef<MediaStream | null>(null);
  const afterEventIdRef = useRef<string | null>(null);
  const activeTimerRef = useRef<number | null>(null);
  const softCapTimerRef = useRef<number | null>(null);
  const wrapTimerRef = useRef<number | null>(null);
  const startedAtRef = useRef<number>(0);
  const startedRef = useRef(false);
  const exitingRef = useRef(false);
  const thanksUrlRef = useRef<string | null>(null);
  const advanceFromRef = useRef<(clicked: string) => void>(() => undefined);

  const applyBeatAt = useCallback(
    (index: number) => {
      if (wizardPauseRef.current != null) {
        window.clearTimeout(wizardPauseRef.current);
        wizardPauseRef.current = null;
      }
      beatIndexRef.current = index;
      const beat = demoTourBeatAt(index);
      if (!beat) {
        clearDemoHighlight();
        return;
      }
      const runHighlight = () => {
        scheduleDemoHighlight(
          {
            targetElementId: beat.target,
            pointer: beat.intent === "click",
            label: beat.label,
            warnMissing: true,
            intent: beat.intent,
            persistUntilClick: true,
            showNext: beat.showNext,
            onClicked: (clicked) => advanceFromRef.current(clicked),
          },
          80,
        );
        if (beat.intent === "view" && !beat.showNext) {
          wizardPauseRef.current = window.setTimeout(() => {
            if (beatIndexRef.current === index) advanceFromRef.current(beat.target);
          }, 2200);
        }
      };
      const { pathname: path, search } = parseDemoRoute(beat.route);
      const currentPath = typeof window !== "undefined" ? window.location.pathname : pathname;
      const currentSearch =
        typeof window !== "undefined" ? window.location.search.replace(/^\?/, "") : "";
      const nextSearch = new URLSearchParams(search).toString();
      const needsNav = path !== currentPath || (nextSearch && nextSearch !== currentSearch);
      if (needsNav) {
        void navigate({
          to: path as never,
          search: (Object.keys(search).length ? search : undefined) as never,
        }).then(() => runHighlight());
      } else {
        runHighlight();
      }
    },
    [navigate, pathname],
  );

  const advanceFrom = useCallback(
    (clicked: string) => {
      const cur = beatIndexRef.current;
      const next = nextIndexAfterClick(cur, clicked);
      const nextBeat = demoTourBeatAt(next);
      applyBeatAt(next);
      if (!nextBeat) return;
      notifySpotlight(nextBeat);
      const sid = demoSessionFromLocation() || sessionId;
      if (sid) {
        void reportDemoUserClick(sid, clicked, {
          beat_id: nextBeat.id,
          label: nextBeat.label,
          talk: nextBeat.talk,
          intent: nextBeat.intent,
          beat_index: next,
        }).catch(() => undefined);
      }
    },
    [applyBeatAt, notifySpotlight, sessionId],
  );
  advanceFromRef.current = advanceFrom;

  const startTour = useCallback(() => {
    if (tourStartedRef.current && beatIndexRef.current >= 0) return;
    tourStartedRef.current = true;
    const first = DEMO_TOUR_BEATS[0];
    applyBeatAt(0);
    if (first) sendToAgent(demoTourStartMessage(first));
    const sid = demoSessionFromLocation() || sessionId;
    if (sid && first) {
      void reportDemoUserClick(sid, first.target, {
        beat_id: first.id,
        label: first.label,
        talk: first.talk,
        intent: first.intent,
        beat_index: 0,
      }).catch(() => undefined);
    }
  }, [applyBeatAt, sendToAgent, sessionId]);
  startTourRef.current = startTour;

  const hangup = useCallback(async () => {
    if (activeTimerRef.current) {
      window.clearTimeout(activeTimerRef.current);
      activeTimerRef.current = null;
    }
    if (softCapTimerRef.current) {
      window.clearTimeout(softCapTimerRef.current);
      softCapTimerRef.current = null;
    }
    if (wrapTimerRef.current) {
      window.clearTimeout(wrapTimerRef.current);
      wrapTimerRef.current = null;
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
    pendingAgentMsgsRef.current = [];
    if (wizardPauseRef.current != null) {
      window.clearTimeout(wizardPauseRef.current);
      wizardPauseRef.current = null;
    }
    clearDemoHighlight();
    try {
      localStreamRef.current?.getTracks().forEach((t) => t.stop());
    } catch {
      /* ignore */
    }
    localStreamRef.current = null;
  }, []);

  const finish = useCallback(
    async (note?: string) => {
      if (!sessionId || exitingRef.current) return;
      exitingRef.current = true;
      setPhase("ended");
      setStatusLine("Demo ended");
      // Kill the voice call first so the agent stops speaking immediately.
      await hangup();
      const duration = startedAtRef.current
        ? Math.max(1, Math.round((Date.now() - startedAtRef.current) / 1000))
        : undefined;
      let thanks: string | null = thanksUrlRef.current;
      try {
        const res = await completeDemoSession({
          session_id: sessionId,
          summary: note || "Demo session ended",
          duration_seconds: duration,
        });
        if (res?.thanks_url) thanks = String(res.thanks_url);
      } catch {
        /* still leave dashboard — session may already be completed */
      }
      wipeDemoAuthAndLeave(sessionId, thanks);
    },
    [hangup, sessionId],
  );

  const applyEvents = useCallback(
    (events: AiDemoUiEvent[]) => {
      for (const ev of events) {
        if (ev.id) afterEventIdRef.current = ev.id;
        if (ev.type === "request_sales_offer") {
          toast.message("Sales will follow up with the best offer");
        }
        if (ev.type === "end_demo") {
          sendToAgent(DEMO_WRAP_MESSAGE);
          if (wrapTimerRef.current) window.clearTimeout(wrapTimerRef.current);
          wrapTimerRef.current = window.setTimeout(() => {
            void finish("Agent ended demo");
          }, 12_000);
          continue;
        }
        const action = String(ev.action || ev.type || "").trim().toLowerCase();
        const isHighlight =
          action === "highlight" ||
          action === "navigate" ||
          action === "open_chart" ||
          action === "restore" ||
          ev.type === "highlight_dashboard";
        if (!isHighlight || exitingRef.current) continue;
        if (beatIndexRef.current < 0) {
          startTour();
          continue;
        }
        /* Restore current box only — never skip ahead. */
        applyBeatAt(beatIndexRef.current);
      }
    },
    [applyBeatAt, finish, sendToAgent, startTour],
  );

  useEffect(() => {
    const id = demoSessionFromLocation();
    if (id) setSessionId(id);
  }, []);

  useEffect(() => {
    if (!tourStartedRef.current || beatIndexRef.current < 0) return;
    applyBeatAt(beatIndexRef.current);
  }, [pathname, applyBeatAt]);

  useEffect(() => {
    if (phase !== "live") return;
    const id = window.setInterval(() => {
      if (!tourStartedRef.current || beatIndexRef.current < 0 || exitingRef.current) return;
      if (!hasDemoHighlight()) applyBeatAt(beatIndexRef.current);
    }, 2000);
    return () => window.clearInterval(id);
  }, [phase, applyBeatAt]);

  useEffect(() => {
    if (!sessionId || startedRef.current) return;
    startedRef.current = true;
    let cancelled = false;

    (async () => {
      setPhase("connecting");
      setStatusLine("Connecting…");
      markAiDemoMode(true);
      try {
        const cached = readCachedDemoStart(sessionId);
        if (cached?.thanks_url) thanksUrlRef.current = String(cached.thanks_url);
        const started =
          cached?.telnyx?.agent_id
            ? cached
            : await startDemoSession(sessionId, cached?.selected_services || []);
        if (cancelled) return;
        if (started.thanks_url) thanksUrlRef.current = String(started.thanks_url);
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
          if (state === "active" || state === "answered" || state === "held") {
            flushAgentMessages();
          }
          if ((state === "active" || state === "answered" || state === "held") && !wentLive) {
            wentLive = true;
            if (activeTimerRef.current) {
              window.clearTimeout(activeTimerRef.current);
              activeTimerRef.current = null;
            }
            startedAtRef.current = Date.now();
            setPhase("live");
            setStatusLine("Live with Leo");
            toast.success("AI demo connected");
            /* Start the spotlight as soon as audio is live so the first
               sendConversationMessage is not racing a still-connecting call. */
            window.setTimeout(() => startTourRef.current(), 400);
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
          sendToAgent(DEMO_WRAP_MESSAGE);
          wrapTimerRef.current = window.setTimeout(() => {
            void finish("Soft cap reached");
          }, 12_000);
        }, Math.max(5_000, softCap - 12_000));
      } catch (e) {
        startedRef.current = false;
        setPhase("ended");
        const msg = e instanceof Error ? e.message : "Could not start AI demo call";
        setStatusLine(msg);
        toast.error(msg);
        // Failed start still must not leave a dangling demo JWT on the dashboard.
        wipeDemoAuthAndLeave(sessionId, thanksUrlRef.current);
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
        const [eventsRes, gate] = await Promise.all([
          pollDemoEvents(sessionId, afterEventIdRef.current),
          fetchDemoSessionGate(sessionId).catch(() => null),
        ]);
        if (cancelled || exitingRef.current) return;
        if (gate && !gate.active) {
          exitingRef.current = true;
          setPhase("ended");
          await hangup();
          wipeDemoAuthAndLeave(sessionId, gate.thanks_url || thanksUrlRef.current);
          return;
        }
        if (eventsRes.events?.length) applyEvents(eventsRes.events);
      } catch {
        /* ignore poll blips */
      }
    };
    void tick();
    const id = window.setInterval(() => void tick(), 700);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [applyEvents, hangup, phase, sessionId]);

  const onPointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    const target = e.target as HTMLElement;
    if (target.closest("button")) return;
    dragRef.current = {
      active: true,
      ox: pos.x,
      oy: pos.y,
      startX: e.clientX,
      startY: e.clientY,
    };
    e.currentTarget.setPointerCapture(e.pointerId);
  };

  const onPointerMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    if (!drag?.active) return;
    const next = {
      x: Math.max(8, Math.min(drag.ox + (e.clientX - drag.startX), window.innerWidth - 160)),
      y: Math.max(8, Math.min(drag.oy + (e.clientY - drag.startY), window.innerHeight - 56)),
    };
    setPos(next);
  };

  const onPointerUp = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (!dragRef.current?.active) return;
    dragRef.current.active = false;
    try {
      localStorage.setItem(POS_KEY, JSON.stringify(pos));
    } catch {
      /* ignore */
    }
    try {
      e.currentTarget.releasePointerCapture(e.pointerId);
    } catch {
      /* ignore */
    }
  };

  if (!sessionId || phase === "idle") return null;
  if (phase === "ended") return null;

  return (
    <div
      className="fixed z-[80] select-none touch-none"
      style={{ left: pos.x, top: pos.y }}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
    >
      <audio id={REMOTE_AUDIO_ID} autoPlay playsInline className="hidden" />
      <div className="flex items-center gap-1.5 rounded-full border border-border bg-background/95 py-1 pl-1.5 pr-1 shadow-lg backdrop-blur">
        <span
          className="inline-flex h-7 w-5 cursor-grab items-center justify-center text-muted-foreground active:cursor-grabbing"
          title="Drag"
        >
          <GripVertical className="h-3.5 w-3.5" />
        </span>
        {phase === "connecting" ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
        ) : (
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
          </span>
        )}
        <div className="min-w-0 max-w-[110px]">
          <p className="truncate text-[11px] font-semibold leading-tight">AI Demo</p>
          <p className="truncate text-[10px] leading-tight text-muted-foreground">{statusLine}</p>
        </div>
        <button
          type="button"
          className="inline-flex h-7 items-center gap-1 rounded-full bg-destructive px-2.5 text-[11px] font-medium text-destructive-foreground"
          onClick={() => void finish("Visitor hung up")}
          title="End call"
        >
          <PhoneOff className="h-3 w-3" />
          End
        </button>
      </div>
    </div>
  );
}
