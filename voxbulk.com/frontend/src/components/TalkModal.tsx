import { useEffect, useRef, useState, createContext, useContext, useCallback } from "react";
import { X, PhoneCall, Loader2, ShieldCheck, PhoneOff } from "lucide-react";
import { toast } from "sonner";
import { VoiceCallAvatars } from "@/components/VoiceCallAvatars";
import { useAudioLevel } from "@/hooks/useAudioLevel";
import { completeTalkToUsCall, fetchTalkToUsConfig, loadTelnyxRtc, loadVapi, startTalkToUsCall } from "@/lib/talkToUs";

type Ctx = { open: () => void; close: () => void; isOpen: boolean };
const TalkCtx = createContext<Ctx>({ open: () => {}, close: () => {}, isOpen: false });
export const useTalkModal = () => useContext(TalkCtx);

const REMOTE_AUDIO_ID = "voxbulk-talk-remote-audio";
const ACTIVE_TIMEOUT_MS = 25_000;

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

type CallPhase = "form" | "connecting" | "aiJoining" | "live";

function webrtcLog(msg: string, detail?: unknown) {
  console.info("[webrtc]", msg, detail ?? "");
}

function initialsFromName(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export function TalkModalProvider({ children }: { children: React.ReactNode }) {
  const [isOpen, setIsOpen] = useState(false);
  const open = useCallback(() => setIsOpen(true), []);
  const close = useCallback(() => setIsOpen(false), []);

  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = "";
      window.removeEventListener("keydown", onKey);
    };
  }, [isOpen, close]);

  return (
    <TalkCtx.Provider value={{ open, close, isOpen }}>
      {children}
      {isOpen && <TalkModal onClose={close} />}
    </TalkCtx.Provider>
  );
}

function TalkModal({ onClose }: { onClose: () => void }) {
  const [name, setName] = useState("");
  const [company, setCompany] = useState("");
  const [email, setEmail] = useState("");
  const [mobile, setMobile] = useState("");
  const [loading, setLoading] = useState(false);
  const [callPhase, setCallPhase] = useState<CallPhase>("form");
  const [statusLine, setStatusLine] = useState("");
  const [agentReady, setAgentReady] = useState<boolean | null>(null);
  const [callId, setCallId] = useState<string | null>(null);
  const [aiPresent, setAiPresent] = useState(false);
  const [remoteStream, setRemoteStream] = useState<MediaStream | null>(null);
  const [localMeterStream, setLocalMeterStream] = useState<MediaStream | null>(null);

  const startedAt = useRef<number | null>(null);
  const vapiRef = useRef<{ stop?: () => void; start?: (...args: unknown[]) => Promise<unknown> } | null>(null);
  const telnyxRef = useRef<{ disconnect?: () => void; off?: (event: string, handler: (...args: unknown[]) => void) => void } | null>(null);
  const telnyxCallRef = useRef<TelnyxCall | null>(null);
  const telnyxNotificationRef = useRef<((n: TelnyxNotification) => void) | null>(null);
  const localStreamRef = useRef<MediaStream | null>(null);
  const activeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const transcriptRef = useRef<string[]>([]);

  const aiLevel = useAudioLevel(remoteStream, callPhase === "live" || callPhase === "aiJoining");
  const userLevel = useAudioLevel(localMeterStream, callPhase === "live" || callPhase === "aiJoining");

  useEffect(() => {
    let cancelled = false;
    setAgentReady(null);
    void fetchTalkToUsConfig()
      .then((cfg) => {
        if (!cancelled) setAgentReady(Boolean(cfg.telnyx?.configured || cfg.vapi?.configured));
      })
      .catch(() => {
        if (!cancelled) setAgentReady(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const clearActiveTimer = useCallback(() => {
    if (activeTimerRef.current) {
      clearTimeout(activeTimerRef.current);
      activeTimerRef.current = null;
    }
  }, []);

  const stopLocalStream = useCallback(() => {
    localStreamRef.current?.getTracks().forEach((t) => t.stop());
    localStreamRef.current = null;
    setLocalMeterStream(null);
  }, []);

  const attachRemoteAudio = useCallback((call: TelnyxCall | null | undefined) => {
    const el = document.getElementById(REMOTE_AUDIO_ID) as HTMLAudioElement | null;
    const stream = call?.remoteStream ?? null;
    if (stream) setRemoteStream(stream);
    if (!el || !stream) return;
    if (el.srcObject !== stream) el.srcObject = stream;
    el.muted = false;
    el.volume = 1;
    void el.play().catch(() => {});
  }, []);

  const cleanupCall = useCallback(
    async (opts?: { providerCallId?: string; silent?: boolean }) => {
      clearActiveTimer();
      try {
        vapiRef.current?.stop?.();
      } catch {
        /* ignore */
      }
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
      vapiRef.current = null;
      telnyxRef.current = null;
      telnyxCallRef.current = null;
      setRemoteStream(null);
      setAiPresent(false);
      stopLocalStream();
      setCallPhase("form");
      setStatusLine("");
      if (callId) {
        const duration = startedAt.current ? Math.max(1, Math.round((Date.now() - startedAt.current) / 1000)) : undefined;
        try {
          await completeTalkToUsCall(callId, {
            transcript_text: transcriptRef.current.join("\n"),
            duration_seconds: duration,
            provider_call_id: opts?.providerCallId,
          });
        } catch {
          /* best effort */
        }
      }
      startedAt.current = null;
      setCallId(null);
      transcriptRef.current = [];
    },
    [callId, clearActiveTimer, stopLocalStream],
  );

  useEffect(
    () => () => {
      void cleanupCall({ silent: true });
    },
    [cleanupCall],
  );

  const startTelnyxCall = async (session: Awaited<ReturnType<typeof startTalkToUsCall>>) => {
    if (!session.telnyx?.agent_id) throw new Error("Telnyx agent is not configured");

    setStatusLine("Requesting microphone…");
    let micStream: MediaStream;
    try {
      micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      localStreamRef.current = micStream;
      setLocalMeterStream(micStream);
    } catch {
      throw new Error("Microphone access is required — allow mic access and try again.");
    }

    const TelnyxRTC = await loadTelnyxRtc();
    const client = new TelnyxRTC({
      anonymous_login: { target_type: "ai_assistant", target_id: session.telnyx.agent_id },
    });
    telnyxRef.current = client;

    setStatusLine("Connecting to Telnyx…");
    await new Promise<void>((resolve, reject) => {
      const t = window.setTimeout(() => reject(new Error("Connection timed out — check your network and try again")), 30_000);
      client.on("telnyx.ready", () => {
        window.clearTimeout(t);
        webrtcLog("telnyx.ready");
        resolve();
      });
      client.on("telnyx.error", (err: { message?: string }) => {
        window.clearTimeout(t);
        webrtcLog("telnyx.error", err);
        reject(new Error(err?.message || "Telnyx connection failed"));
      });
      client.connect();
    });

    let wentLive = false;
    const onNotification = (notification: TelnyxNotification) => {
      webrtcLog("notification", notification);
      if (notification?.type === "userMediaError") {
        throw new Error(notification.errorMessage || "Microphone error");
      }
      if (notification?.type !== "callUpdate" || !notification.call) return;
      const call = notification.call;
      telnyxCallRef.current = call;
      attachRemoteAudio(call);
      if (call.localStream) setLocalMeterStream(call.localStream);

      if (call.state === "ringing" || call.state === "new" || call.state === "answering") {
        setCallPhase("aiJoining");
        setStatusLine("AI agent is joining…");
      }
      if (call.state === "active" && !wentLive) {
        wentLive = true;
        clearActiveTimer();
        setAiPresent(true);
        setCallPhase("live");
        setStatusLine("AI is here — speak now");
        startedAt.current = Date.now();
        attachRemoteAudio(call);
        toast.success("Connected — you're speaking with our AI agent.");
      }
      if (call.state === "hangup" || call.state === "destroy" || call.state === "destroyed") {
        void cleanupCall({ providerCallId: call.id });
        toast.success("Call ended — thanks for speaking with VoxBulk.");
        onClose();
      }
    };
    telnyxNotificationRef.current = onNotification;
    client.on("telnyx.notification", onNotification);

    setCallPhase("aiJoining");
    setStatusLine("Calling AI agent…");

    const codecs = RTCRtpReceiver.getCapabilities("audio")?.codecs || [];
    const opus = codecs.find((c) => c.mimeType.toLowerCase().includes("opus"));
    const call = client.newCall({
      destinationNumber: "",
      audio: true,
      video: false,
      remoteElement: REMOTE_AUDIO_ID,
      preferred_codecs: opus ? [opus] : undefined,
      customHeaders: session.telnyx.custom_headers || {},
    }) as TelnyxCall;
    telnyxCallRef.current = call;
    attachRemoteAudio(call);
    if (call.localStream) setLocalMeterStream(call.localStream);

    activeTimerRef.current = setTimeout(() => {
      if (!wentLive) {
        webrtcLog("active timeout");
        void cleanupCall();
        toast.error("The AI agent did not answer — please try again.");
        setCallPhase("form");
      }
    }, ACTIVE_TIMEOUT_MS);
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name || !email || !mobile) {
      toast.error("Please fill in name, email and mobile number.");
      return;
    }
    setLoading(true);
    setCallPhase("connecting");
    try {
      const session = await startTalkToUsCall({
        contact_name: name,
        company_name: company,
        email,
        phone: mobile,
      });
      setCallId(session.call_id);

      if (session.voice_provider === "telnyx" && session.telnyx?.configured && session.telnyx.agent_id) {
        await startTelnyxCall(session);
      } else if (session.vapi?.configured && session.vapi.public_key && session.vapi.assistant_id) {
        const Vapi = await loadVapi();
        const vapi = new Vapi(session.vapi.public_key);
        vapiRef.current = vapi;
        setCallPhase("live");
        startedAt.current = Date.now();
        vapi.on("message", (message: { role?: string; transcript?: string; content?: string }) => {
          const role = message?.role;
          const content = message?.transcript || message?.content || "";
          if (content && (role === "user" || role === "assistant")) {
            transcriptRef.current.push(`${role}: ${content}`);
          }
        });
        vapi.on("call-end", () => {
          void cleanupCall();
          toast.success("Call ended — thanks for speaking with VoxBulk.");
          onClose();
        });
        vapi.on("error", (err: { message?: string }) => {
          toast.error(err?.message || "Call failed");
        });
        await vapi.start(session.vapi.assistant_id, {
          variableValues: session.vapi.variable_values,
          firstMessage: session.vapi.first_message,
        });
        toast.success("Connected — speak with our AI agent.");
      } else {
        throw new Error("Voice agent is not configured yet. Please use the contact form instead.");
      }
    } catch (err) {
      await cleanupCall();
      setCallPhase("form");
      toast.error(err instanceof Error ? err.message : "Could not start call");
    } finally {
      setLoading(false);
    }
  };

  const endCall = () => {
    void cleanupCall();
    toast.message("Call ended");
    onClose();
  };

  const inCall = callPhase !== "form";
  const userInitials = initialsFromName(name);

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 animate-fade-in">
      <div className="absolute inset-0 bg-navy/55 backdrop-blur-md" onClick={inCall ? undefined : onClose} />
      <audio id={REMOTE_AUDIO_ID} autoPlay playsInline className="hidden" />
      <div className="relative w-full max-w-[460px] bg-white rounded-3xl shadow-elevated border border-border overflow-hidden animate-scale-in">
        <button
          onClick={inCall ? endCall : onClose}
          aria-label="Close"
          className="absolute top-4 right-4 z-10 w-9 h-9 rounded-full hover:bg-secondary text-muted-text hover:text-heading flex items-center justify-center transition-colors"
        >
          <X size={18} />
        </button>

        <div className="relative px-7 pt-7 pb-4 border-b border-border">
          <div className="flex items-center gap-3">
            <div className="w-11 h-11 rounded-2xl bg-navy text-gold flex items-center justify-center">
              <PhoneCall size={20} />
            </div>
            <div>
              <h2 className="text-[20px] font-bold text-heading tracking-[-0.01em]">Talk to us</h2>
              <p className="text-[13px] text-muted-text">
                {callPhase === "live"
                  ? "AI agent is here — speak naturally."
                  : inCall
                    ? statusLine || "Connecting…"
                    : "Speak with a VoxBulk AI agent in your browser."}
              </p>
            </div>
          </div>
        </div>

        {inCall ? (
          <div className="p-7 space-y-5 text-center">
            {callPhase === "connecting" ? (
              <div className="flex flex-col items-center gap-3 py-4">
                <Loader2 className="size-8 animate-spin text-navy" />
                <p className="text-[14px] text-body">{statusLine || "Connecting…"}</p>
              </div>
            ) : (
              <>
                <VoiceCallAvatars
                  aiLabel="VoxBulk AI"
                  aiLevel={aiLevel}
                  aiPresent={aiPresent}
                  userLabel={name.split(" ")[0] || "You"}
                  userInitials={userInitials}
                  userLevel={userLevel}
                  micOn
                />
                {callPhase === "aiJoining" ? (
                  <Loader2 className="mx-auto size-6 animate-spin text-navy" />
                ) : null}
              </>
            )}
            <button
              type="button"
              onClick={endCall}
              className="w-full h-11 rounded-xl bg-red-600 text-white text-[14px] font-semibold inline-flex items-center justify-center gap-1.5 hover:bg-red-700 transition-colors"
            >
              <PhoneOff size={15} /> End call
            </button>
          </div>
        ) : (
          <form onSubmit={submit} className="p-7 space-y-3">
            {agentReady === false && (
              <p className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-3 py-2.5 text-[12.5px] text-amber-900">
                Live voice agent is not configured yet. Set it up in Admin → Marketing → Front page call leads, or use the
                contact form instead.
              </p>
            )}
            {agentReady === null && <p className="text-center text-[12.5px] text-muted-text">Checking voice agent…</p>}
            <Field label="Name" value={name} onChange={setName} placeholder="Jane Smith" required />
            <Field label="Company name" value={company} onChange={setCompany} placeholder="Acme Ltd" />
            <Field label="Email" type="email" value={email} onChange={setEmail} placeholder="you@company.com" required />
            <Field label="Mobile number" type="tel" value={mobile} onChange={setMobile} placeholder="+44 7…" required />

            <p className="flex items-start gap-2 text-[12px] text-muted-text pt-1">
              <ShieldCheck size={14} className="mt-0.5 text-teal shrink-0" />
              This call may be recorded for quality and training.
            </p>

            <div className="flex gap-2 pt-3">
              <button
                type="button"
                onClick={onClose}
                className="flex-1 h-11 rounded-xl border border-border bg-white text-[14px] font-semibold text-heading hover:bg-beige transition-colors"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={loading || agentReady !== true}
                className="flex-1 h-11 rounded-xl bg-navy text-white text-[14px] font-semibold inline-flex items-center justify-center gap-1.5 hover:bg-navy/90 transition-colors disabled:opacity-60"
              >
                {loading ? <Loader2 size={16} className="animate-spin" /> : <><PhoneCall size={15} /> Talk to us</>}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  type = "text",
  placeholder,
  required,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  placeholder?: string;
  required?: boolean;
}) {
  return (
    <label className="block">
      <span className="block text-[12.5px] font-semibold text-heading mb-1.5">
        {label}
        {required && <span className="text-primary"> *</span>}
      </span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        required={required}
        className="w-full px-3.5 py-2.5 rounded-xl border border-border bg-secondary/40 text-[14.5px] focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
      />
    </label>
  );
}
