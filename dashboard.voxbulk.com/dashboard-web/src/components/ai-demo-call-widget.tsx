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
  bindDemoCallControl,
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
import {
  enqueueDemoAgentMessage,
  flushDemoAgentMessages,
  readCallControlId,
  type DemoAgentCall,
} from "@/lib/ai-demo-agent-send";

const REMOTE_AUDIO_ID = "voxbulk-ai-demo-remote-audio";
const ACTIVE_TIMEOUT_MS = 45_000;
const POS_KEY = "voxbulk_ai_demo_widget_pos";

type TelnyxCall = DemoAgentCall & {
  id?: string;
  hangup?: () => void;
  remoteStream?: MediaStream | null;
  localStream?: MediaStream | null;
};

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
  const callControlIdRef = useRef<string | null>(null);
  const missingCcidLoggedRef = useRef(false);
  const ccidPollRef = useRef<number | null>(null);

  const beatIndexRef = useRef(-1);
  const tourStartedRef = useRef(false);
  const wizardPauseRef = useRef<number | null>(null);
  const startTourRef = useRef<() => void>(() => undefined);

  const flushAgentMessages = useCallback(async () => {
    const result = await flushDemoAgentMessages(callRef.current, pendingAgentMsgsRef.current);
    if (!result.ok && result.reason === "missing_method") {
      console.warn("[ai-demo] call.sendConversationMessage missing — Next/Click will not reach Leo", result);
    } else if (!result.ok && result.reason === "threw") {
      console.warn("[ai-demo] sendConversationMessage threw", result.error);
    } else if (result.ok) {
      console.info("[ai-demo] agent inject ok", {
        via: result.via,
        reason: result.reason,
        preview: result.preview,
        callControlId: result.callControlId,
      });
    } else if (!result.ok && result.reason === "not_live") {
      console.warn("[ai-demo] agent inject queued — call not live yet", result);
    }
    return result;
  }, []);

  const sendToAgent = useCallback(
    (msg: string) => {
      enqueueDemoAgentMessage(pendingAgentMsgsRef.current, msg);
      void flushAgentMessages();
    },
    [flushAgentMessages],
  );

  /** Sync spotlight to API memory only — Leo continues when the visitor speaks (done/clicked). */
  const syncBeatMemory = useCallback(
    async (opts: {
      target: string;
      beat: DemoTourBeat;
      beatIndex: number;
      agentMessage?: string;
    }) => {
      const sid = demoSessionFromLocation() || sessionId;
      if (!sid) return;
      const ccid = readCallControlId(callRef.current) || callControlIdRef.current;
      try {
        await reportDemoUserClick(sid, opts.target, {
          beat_id: opts.beat.id,
          label: opts.beat.label,
          talk: opts.beat.talk,
          intent: opts.beat.intent,
          beat_index: opts.beatIndex,
          call_control_id: ccid,
          agent_message: opts.agentMessage,
          notify_agent: false,
        });
      } catch (err) {
        console.warn("[ai-demo] beat memory sync failed", err);
      }
    },
    [sessionId],
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
      /* UI moves immediately; Leo sells after the visitor says done/clicked on the call. */
      void syncBeatMemory({
        target: clicked,
        beat: nextBeat,
        beatIndex: next,
        agentMessage: demoTourAdvanceMessage(nextBeat),
      });
    },
    [applyBeatAt, syncBeatMemory],
  );
  advanceFromRef.current = advanceFrom;

  const startTour = useCallback(() => {
    if (tourStartedRef.current && beatIndexRef.current >= 0) return;
    tourStartedRef.current = true;
    const first = DEMO_TOUR_BEATS[0];
    applyBeatAt(0);
    if (first) {
      void syncBeatMemory({
        target: first.target,
        beat: first,
        beatIndex: 0,
        agentMessage: demoTourStartMessage(first),
      });
    }
  }, [applyBeatAt, syncBeatMemory]);
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
    if (ccidPollRef.current) {
      window.clearInterval(ccidPollRef.current);
      ccidPollRef.current = null;
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
        if (cancelled) {
          micStream.getTracks().forEach((t) => t.stop());
          return;
        }

        const TelnyxRTC = await loadTelnyxRtc();
        if (cancelled) {
          micStream.getTracks().forEach((t) => t.stop());
          return;
        }
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
        if (cancelled) {
          try {
            client.disconnect?.();
          } catch {
            /* ignore */
          }
          micStream.getTracks().forEach((t) => t.stop());
          return;
        }

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
          if (cancelled || exitingRef.current) return;
          if (notification?.type === "userMediaError") {
            void finish("Microphone error");
            toast.error(notification.errorMessage || "Microphone error");
            return;
          }
          if (notification?.type !== "callUpdate" || !notification.call) return;
          const call = notification.call;
          callRef.current = call;
          attachRemoteAudio(call);
          const tryBindCcid = () => {
            const ccid = readCallControlId(callRef.current);
            if (!ccid || ccid === callControlIdRef.current) return Boolean(callControlIdRef.current);
            callControlIdRef.current = ccid;
            missingCcidLoggedRef.current = false;
            const sid = demoSessionFromLocation() || sessionId;
            if (sid) {
              void bindDemoCallControl(sid, ccid).catch(() => undefined);
            }
            console.info("[ai-demo] bound call_control_id", ccid.slice(0, 24));
            return true;
          };
          tryBindCcid();
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
            /* Poll until Telnyx fills call_control_id (often late on anonymous AI). */
            if (ccidPollRef.current) window.clearInterval(ccidPollRef.current);
            let polls = 0;
            ccidPollRef.current = window.setInterval(() => {
              polls += 1;
              if (cancelled || exitingRef.current || tryBindCcid() || polls > 40) {
                if (ccidPollRef.current) {
                  window.clearInterval(ccidPollRef.current);
                  ccidPollRef.current = null;
                }
                if (!callControlIdRef.current && !missingCcidLoggedRef.current) {
                  missingCcidLoggedRef.current = true;
                  console.info(
                    "[ai-demo] no call_control_id yet — voice-gated tour (Leo waits for spoken done)",
                  );
                }
              }
            }, 500);
            window.setTimeout(() => {
              if (!cancelled && !exitingRef.current) startTourRef.current();
            }, 400);
          }
          /* Ignore hangup/destroy until we were live — early Telnyx states
             used to wipe the demo to /thanks before Leo joined. */
          if (wentLive && (state === "hangup" || state === "destroy" || state === "destroyed")) {
            if (ccidPollRef.current) {
              window.clearInterval(ccidPollRef.current);
              ccidPollRef.current = null;
            }
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
          if (!wentLive && !cancelled && !exitingRef.current) {
            toast.error("AI did not join in time");
            void finish("AI join timeout");
          }
        }, ACTIVE_TIMEOUT_MS);

        const softMinutes = Number(started.soft_cap_minutes);
        const softCap =
          (Number.isFinite(softMinutes) && softMinutes > 0 ? Math.max(3, softMinutes) : 7) * 60 * 1000;
        softCapTimerRef.current = window.setTimeout(() => {
          if (cancelled || exitingRef.current) return;
          toast.message("Wrapping up the demo");
          sendToAgent(DEMO_WRAP_MESSAGE);
          wrapTimerRef.current = window.setTimeout(() => {
            void finish("Soft cap reached");
          }, 12_000);
        }, Math.max(5_000, softCap - 12_000));
      } catch (e) {
        /* Strict-mode remount / navigation must not bounce visitors to /thanks. */
        if (cancelled || exitingRef.current) return;
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
