import { useEffect, useRef, useState, createContext, useContext, useCallback } from "react";
import { X, PhoneCall, Loader2, ShieldCheck, PhoneOff } from "lucide-react";
import { toast } from "sonner";
import { completeTalkToUsCall, fetchTalkToUsConfig, loadTelnyxRtc, loadVapi, startTalkToUsCall } from "@/lib/talkToUs";

type Ctx = { open: () => void; close: () => void; isOpen: boolean };
const TalkCtx = createContext<Ctx>({ open: () => {}, close: () => {}, isOpen: false });
export const useTalkModal = () => useContext(TalkCtx);

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
  const [inCall, setInCall] = useState(false);
  const [agentReady, setAgentReady] = useState<boolean | null>(null);
  const [callId, setCallId] = useState<string | null>(null);
  const startedAt = useRef<number | null>(null);
  const vapiRef = useRef<{ stop?: () => void; start?: (...args: unknown[]) => Promise<unknown> } | null>(null);
  const telnyxRef = useRef<{ disconnect?: () => void } | null>(null);
  const telnyxCallRef = useRef<{ hangup?: () => void; id?: string } | null>(null);
  const transcriptRef = useRef<string[]>([]);
  const remoteAudioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    setAgentReady(null);
    void fetchTalkToUsConfig()
      .then((cfg) => {
        if (cancelled) return;
        setAgentReady(Boolean(cfg.telnyx?.configured || cfg.vapi?.configured));
      })
      .catch(() => {
        if (!cancelled) setAgentReady(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const cleanupCall = useCallback(async (opts?: { providerCallId?: string }) => {
    try {
      vapiRef.current?.stop?.();
    } catch {
      /* ignore */
    }
    try {
      telnyxCallRef.current?.hangup?.();
      telnyxRef.current?.disconnect?.();
    } catch {
      /* ignore */
    }
    vapiRef.current = null;
    telnyxRef.current = null;
    telnyxCallRef.current = null;
    setInCall(false);
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
  }, [callId]);

  useEffect(() => () => {
    void cleanupCall();
  }, [cleanupCall]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name || !email || !mobile) {
      toast.error("Please fill in name, email and mobile number.");
      return;
    }
    setLoading(true);
    try {
      const session = await startTalkToUsCall({
        contact_name: name,
        company_name: company,
        email,
        phone: mobile,
      });
      setCallId(session.call_id);
      startedAt.current = Date.now();
      setInCall(true);

      if (session.voice_provider === "telnyx" && session.telnyx?.configured && session.telnyx.agent_id) {
        const TelnyxRTC = await loadTelnyxRtc();
        const client = new TelnyxRTC({
          anonymous_login: {
            target_type: "ai_assistant",
            target_id: session.telnyx.agent_id,
          },
        });
        telnyxRef.current = client;
        await new Promise<void>((resolve, reject) => {
          client.on("telnyx.ready", () => resolve());
          client.on("telnyx.error", (err: { message?: string }) => reject(new Error(err?.message || "Telnyx connection failed")));
          client.connect();
        });
        const codecs = RTCRtpReceiver.getCapabilities("audio")?.codecs || [];
        const opus = codecs.find((c) => c.mimeType.toLowerCase().includes("opus"));
        const call = client.newCall({
          destinationNumber: "",
          remoteElement: remoteAudioRef.current || undefined,
          preferred_codecs: opus ? [opus] : undefined,
          customHeaders: session.telnyx.custom_headers || {},
        });
        telnyxCallRef.current = call;
        call.on("callUpdate", (state: { call?: { state?: string } }) => {
          if (state?.call?.state === "hangup" || state?.call?.state === "destroy") {
            void cleanupCall({ providerCallId: call.id });
            toast.success("Call ended — thanks for speaking with VoxBulk.");
            onClose();
          }
        });
      } else if (session.vapi?.configured && session.vapi.public_key && session.vapi.assistant_id) {
        const Vapi = await loadVapi();
        const vapi = new Vapi(session.vapi.public_key);
        vapiRef.current = vapi;
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
      } else {
        throw new Error("Voice agent is not configured yet. Please use the contact form instead.");
      }
      toast.success("Connecting you with a VoxBulk AI agent…");
    } catch (err) {
      await cleanupCall();
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

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 animate-fade-in">
      <div className="absolute inset-0 bg-navy/55 backdrop-blur-md" onClick={inCall ? undefined : onClose} />
      <audio ref={remoteAudioRef} autoPlay playsInline className="hidden" />
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
                {inCall ? "You're connected — speak with our AI agent." : "A VoxBulk AI agent will call you back instantly."}
              </p>
            </div>
          </div>
        </div>

        {inCall ? (
          <div className="p-7 space-y-4 text-center">
            <div className="mx-auto w-16 h-16 rounded-full bg-teal/10 text-teal flex items-center justify-center">
              <PhoneCall size={28} className="animate-pulse" />
            </div>
            <p className="text-[14px] text-body">Call in progress. Use your microphone and speakers.</p>
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
                Live voice agent is not configured yet. Set it up in Admin → Marketing → Front page call leads, or use the contact form instead.
              </p>
            )}
            {agentReady === null && (
              <p className="text-center text-[12.5px] text-muted-text">Checking voice agent…</p>
            )}
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
  label, value, onChange, type = "text", placeholder, required,
}: {
  label: string; value: string; onChange: (v: string) => void;
  type?: string; placeholder?: string; required?: boolean;
}) {
  return (
    <label className="block">
      <span className="block text-[12.5px] font-semibold text-heading mb-1.5">
        {label}{required && <span className="text-primary"> *</span>}
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
