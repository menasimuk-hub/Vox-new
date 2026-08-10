import { createFileRoute, Link } from "@tanstack/react-router";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { SiteHeader, SiteFooter } from "@/components/SiteShell";
import { Loader2, PhoneOff, QrCode, ExternalLink } from "lucide-react";
import { toast } from "sonner";
import {
  completeDemoSession,
  DEMO_SERVICES,
  loadTelnyxRtc,
  normalizeTelnyxCustomHeaders,
  pollDemoEvents,
  startDemoSession,
  verifyDemoToken,
  type AiDemoUiEvent,
  type AiDemoVerifyResponse,
} from "@/lib/aiDemo";

const REMOTE_AUDIO_ID = "voxbulk-demo-remote-audio";
const ACTIVE_TIMEOUT_MS = 45_000;

type TelnyxCall = {
  id?: string;
  state?: string;
  hangup?: () => void;
  remoteStream?: MediaStream | null;
  localStream?: MediaStream | null;
};

export const Route = createFileRoute("/demo/session")({
  validateSearch: (search: Record<string, unknown>) => ({
    token: typeof search.token === "string" ? search.token : "",
  }),
  component: DemoSessionPage,
});

function DemoSessionPage() {
  const { token } = Route.useSearch();
  const [phase, setPhase] = useState<"loading" | "ready" | "live" | "ended" | "error">("loading");
  const [error, setError] = useState<string | null>(null);
  const [verified, setVerified] = useState<AiDemoVerifyResponse | null>(null);
  const [activeTab, setActiveTab] = useState<string | null>(null);
  const [resultPanel, setResultPanel] = useState<unknown>(null);
  const [link, setLink] = useState<{ url?: string; label?: string } | null>(null);
  const [qr, setQr] = useState<{ data?: string; label?: string } | null>(null);
  const [cta, setCta] = useState(false);
  const [summary, setSummary] = useState("");
  const callRef = useRef<TelnyxCall | null>(null);
  const clientRef = useRef<{ disconnect?: () => void; off?: (ev: string, fn: (...args: unknown[]) => void) => void } | null>(null);
  const notificationHandlerRef = useRef<((...args: unknown[]) => void) | null>(null);
  const localStreamRef = useRef<MediaStream | null>(null);
  const activeTimerRef = useRef<number | null>(null);
  const startedAtRef = useRef<number>(0);
  const afterEventIdRef = useRef<string | null>(null);
  const softCapTimerRef = useRef<number | null>(null);

  const applyEvents = useCallback((events: AiDemoUiEvent[]) => {
    for (const ev of events) {
      if (ev.id) afterEventIdRef.current = ev.id;
      if (ev.type === "switch_kb" && ev.service) setActiveTab(ev.service);
      if (ev.type === "show_result_panel") setResultPanel(ev.data ?? null);
      if (ev.type === "show_link") setLink({ url: ev.url, label: ev.label });
      if (ev.type === "show_qr_code") setQr({ data: String(ev.data || ""), label: ev.label });
      if (ev.type === "end_demo") {
        setCta(true);
        setSummary(String(ev.summary || ""));
        setPhase("ended");
      }
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!token) {
        setError("Missing demo link token.");
        setPhase("error");
        return;
      }
      try {
        const v = await verifyDemoToken(token);
        if (cancelled) return;
        setVerified(v);
        if (v.memory && typeof v.memory === "object" && (v.memory as { active_service_code?: string }).active_service_code) {
          setActiveTab(String((v.memory as { active_service_code?: string }).active_service_code));
        }
        setPhase("ready");
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : "Invalid demo link");
        setPhase("error");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

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
      if (!verified) return;
      const duration = startedAtRef.current
        ? Math.max(1, Math.round((Date.now() - startedAtRef.current) / 1000))
        : undefined;
      try {
        await completeDemoSession({
          session_id: verified.session_id,
          summary: note || summary || "Demo session ended",
          duration_seconds: duration,
        });
      } catch {
        /* still show CTA */
      }
      await hangup();
      setCta(true);
      setPhase("ended");
    },
    [hangup, summary, verified],
  );

  const startCall = useCallback(async () => {
    if (!verified) return;
    setPhase("live");
    try {
      // Mic first — same as Talk-to-us; unlocks autoplay for remote audio.
      let micStream: MediaStream;
      try {
        micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        localStreamRef.current = micStream;
      } catch {
        throw new Error("Microphone access is required — allow mic access and try again.");
      }

      const started = await startDemoSession(verified.session_id);
      const agentId = started.telnyx?.agent_id;
      if (!agentId) throw new Error("Demo voice agent is not configured yet.");

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
          attachRemoteAudio(call);
          toast.success("Connected — speak when ready");
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
        remoteElement: REMOTE_AUDIO_ID,
        preferred_codecs: opus ? [opus] : undefined,
        customHeaders: normalizeTelnyxCustomHeaders(started.telnyx?.custom_headers),
      }) as TelnyxCall;
      callRef.current = call;
      attachRemoteAudio(call);

      activeTimerRef.current = window.setTimeout(() => {
        if (!wentLive) {
          void hangup();
          setError("The AI agent did not answer — use Resend demo link and try again.");
          setPhase("error");
          toast.error("The AI agent did not answer — please try again.");
        }
      }, ACTIVE_TIMEOUT_MS);

      const minutes = started.soft_cap_minutes || verified.soft_cap_minutes || 7;
      softCapTimerRef.current = window.setTimeout(() => {
        void finish("Soft time limit reached");
      }, minutes * 60 * 1000);
    } catch (e) {
      await hangup();
      setError(e instanceof Error ? e.message : "Could not start demo call");
      setPhase("error");
      toast.error("Connection failed — use Resend demo link in your email");
    }
  }, [finish, hangup, verified]);

  useEffect(() => {
    if (phase !== "live" || !verified) return;
    let cancelled = false;
    const tick = async () => {
      try {
        const { events } = await pollDemoEvents(verified.session_id, afterEventIdRef.current);
        if (!cancelled && events?.length) applyEvents(events);
      } catch {
        /* ignore transient poll errors */
      }
    };
    void tick();
    const id = window.setInterval(() => void tick(), 1500);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [phase, verified, applyEvents]);

  useEffect(() => () => {
    void hangup();
  }, [hangup]);

  const panelText = useMemo(() => {
    if (resultPanel == null) return null;
    try {
      return typeof resultPanel === "string" ? resultPanel : JSON.stringify(resultPanel, null, 2);
    } catch {
      return String(resultPanel);
    }
  }, [resultPanel]);

  return (
    <div className="bg-background text-body antialiased min-h-screen flex flex-col">
      <SiteHeader />
      <main className="flex-1 pt-[110px] md:pt-[120px] pb-20">
        <div className="max-w-[960px] mx-auto px-5 md:px-10">
          <audio id={REMOTE_AUDIO_ID} autoPlay playsInline />

          <div className="text-center mb-8">
            <span className="eyebrow">AI demo session</span>
            <h1 className="mt-2 text-[28px] md:text-[36px] font-bold text-heading tracking-[-0.03em]">
              {verified ? `Hi ${verified.contact_name}` : "Opening your demo"}
            </h1>
            {verified?.has_memory && (
              <p className="mt-2 text-[14px] text-primary font-medium">Continuing from your previous session</p>
            )}
          </div>

          {phase === "loading" && (
            <div className="flex justify-center py-16 text-muted-text gap-2 items-center">
              <Loader2 className="animate-spin" size={20} /> Verifying link…
            </div>
          )}

          {phase === "error" && (
            <div className="rounded-3xl border border-border bg-white p-8 text-center shadow-elegant">
              <p className="text-red-600 font-medium">{error}</p>
              <p className="mt-3 text-[14px] text-body">
                If the call dropped or the link was used, open your email and tap <strong>Resend demo link</strong>.
              </p>
              <Link to="/demo" className="inline-flex mt-6 text-primary font-semibold text-[14px]">
                Request another demo
              </Link>
            </div>
          )}

          {(phase === "ready" || phase === "live" || phase === "ended") && verified && (
            <div className="grid md:grid-cols-[1fr_320px] gap-6">
              <div className="rounded-3xl border border-border bg-white p-6 md:p-8 shadow-elegant">
                <div className="flex flex-wrap gap-2 mb-6">
                  {DEMO_SERVICES.map((s) => (
                    <span
                      key={s.code}
                      className={`rounded-full px-3 py-1.5 text-[12px] font-semibold border ${
                        activeTab === s.code
                          ? "border-primary bg-primary/10 text-heading"
                          : "border-border text-muted-text"
                      }`}
                    >
                      {s.label}
                    </span>
                  ))}
                </div>

                {phase === "ready" && (
                  <div className="text-center py-8">
                    <p className="text-body text-[15px] mb-6">
                      Allow microphone access. This call may be recorded for sales follow-up.
                    </p>
                    <button type="button" className="btn-primary h-12 px-8" onClick={() => void startCall()}>
                      Start demo call
                    </button>
                  </div>
                )}

                {phase === "live" && (
                  <div className="text-center py-8">
                    <div className="inline-flex items-center gap-2 text-primary font-semibold mb-4">
                      <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" /> Live with AI
                    </div>
                    <p className="text-[14px] text-body mb-6">Ask questions or ask to switch products anytime.</p>
                    <button
                      type="button"
                      className="inline-flex items-center gap-2 h-11 px-5 rounded-full border border-border text-[14px] font-semibold"
                      onClick={() => void finish("Visitor ended the call")}
                    >
                      <PhoneOff size={16} /> End demo
                    </button>
                  </div>
                )}

                {phase === "ended" && (
                  <div className="text-center py-6">
                    <h2 className="text-[22px] font-bold text-heading">Thanks for the demo</h2>
                    {summary && <p className="mt-2 text-[14px] text-body">{summary}</p>}
                    <p className="mt-3 text-[14px] text-body">
                      Our sales team has your needs summary, transcript, and recording.
                    </p>
                    {cta && (
                      <a
                        href="/contact"
                        className="btn-primary inline-flex mt-6 h-12 px-7 items-center"
                      >
                        Book a call with sales
                      </a>
                    )}
                  </div>
                )}

                {panelText && (
                  <div className="mt-6 rounded-2xl border border-border bg-secondary/20 p-4">
                    <div className="text-[12px] font-semibold uppercase tracking-wider text-muted-text mb-2">
                      Dashboard preview
                    </div>
                    <pre className="text-[12px] whitespace-pre-wrap break-words text-heading max-h-64 overflow-auto">
                      {panelText}
                    </pre>
                  </div>
                )}
              </div>

              <aside className="space-y-4">
                <div className="rounded-3xl border border-border bg-white p-5 shadow-elegant">
                  <div className="text-[12px] font-semibold uppercase tracking-wider text-muted-text mb-2">Company</div>
                  <div className="font-semibold text-heading">{verified.company_name}</div>
                  <div className="text-[13px] text-body mt-1">{verified.email}</div>
                  <div className="text-[13px] text-body mt-1">
                    Language: {verified.language === "ar" ? "Arabic" : "English"}
                  </div>
                </div>
                {link?.url && (
                  <a
                    href={link.url}
                    target="_blank"
                    rel="noreferrer"
                    className="flex items-center gap-2 rounded-3xl border border-border bg-white p-5 shadow-elegant text-primary font-semibold"
                  >
                    <ExternalLink size={16} /> {link.label || "Open link"}
                  </a>
                )}
                {qr?.data && (
                  <div className="rounded-3xl border border-border bg-white p-5 shadow-elegant">
                    <div className="flex items-center gap-2 text-[12px] font-semibold uppercase tracking-wider text-muted-text mb-2">
                      <QrCode size={14} /> {qr.label || "QR"}
                    </div>
                    <p className="text-[12px] break-all text-body">{qr.data}</p>
                  </div>
                )}
              </aside>
            </div>
          )}
        </div>
      </main>
      <SiteFooter />
    </div>
  );
}
