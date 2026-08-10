import { createFileRoute, Link } from "@tanstack/react-router";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { SiteHeader, SiteFooter } from "@/components/SiteShell";
import { Loader2, PhoneOff, QrCode, ExternalLink } from "lucide-react";
import { toast } from "sonner";
import {
  completeDemoSession,
  DEMO_SERVICES,
  loadTelnyxRtc,
  pollDemoEvents,
  startDemoSession,
  verifyDemoToken,
  type AiDemoUiEvent,
  type AiDemoVerifyResponse,
} from "@/lib/aiDemo";

const REMOTE_AUDIO_ID = "voxbulk-demo-remote-audio";

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
  const callRef = useRef<{ hangup?: () => void } | null>(null);
  const clientRef = useRef<{ disconnect?: () => void } | null>(null);
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
    if (softCapTimerRef.current) window.clearTimeout(softCapTimerRef.current);
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
      try {
        await navigator.mediaDevices.getUserMedia({ audio: true });
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
      clientRef.current = client as { disconnect?: () => void };

      await new Promise<void>((resolve, reject) => {
        const t = window.setTimeout(() => reject(new Error("Telnyx connect timeout")), 25000);
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

      const attachRemoteAudio = (call: { remoteStream?: MediaStream | null } | null | undefined) => {
        const el = document.getElementById(REMOTE_AUDIO_ID) as HTMLAudioElement | null;
        const stream = call?.remoteStream ?? null;
        if (!el || !stream) return;
        if (el.srcObject !== stream) el.srcObject = stream;
        el.muted = false;
        el.volume = 1;
        void el.play().catch(() => {});
      };

      client.on("telnyx.notification", (notification: { type?: string; call?: { remoteStream?: MediaStream | null; state?: string } }) => {
        if (notification?.type !== "callUpdate" || !notification.call) return;
        attachRemoteAudio(notification.call);
      });

      const codecs = RTCRtpReceiver.getCapabilities("audio")?.codecs || [];
      const opus = codecs.find((c) => c.mimeType.toLowerCase().includes("opus"));
      const call = client.newCall({
        destinationNumber: "",
        audio: true,
        video: false,
        remoteElement: REMOTE_AUDIO_ID,
        preferred_codecs: opus ? [opus] : undefined,
        customHeaders: started.telnyx?.custom_headers || {},
      });
      callRef.current = call;
      attachRemoteAudio(call as { remoteStream?: MediaStream | null });
      startedAtRef.current = Date.now();

      const minutes = started.soft_cap_minutes || verified.soft_cap_minutes || 7;
      softCapTimerRef.current = window.setTimeout(() => {
        void finish("Soft time limit reached");
      }, minutes * 60 * 1000);

      toast.success("Connected — speak when ready");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start demo call");
      setPhase("error");
      toast.error("Connection failed — use Resend demo link in your email");
    }
  }, [finish, verified]);

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
