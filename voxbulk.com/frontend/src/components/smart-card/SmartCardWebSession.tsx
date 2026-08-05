import * as React from "react";

import { VoiceDetail, type VoiceDetailHandle } from "@/components/feedback-survey/VoiceDetail";
import type { Theme } from "@/components/feedback-survey/types";
import "@/components/feedback-survey/survey-themes.css";

const API = (import.meta as any).env?.VITE_API_URL || "https://api.voxbulk.com";

/** Theme tuned to SoT smartcard dark UI for VoiceDetail / Expo-style steps. */
const SC_THEME: Theme = {
  bgClass: "bg-smartcard-gradient",
  ink: "#eaf2ff",
  sub: "rgba(234,242,255,0.6)",
  card: "rgba(255,255,255,0.06)",
  border: "rgba(234,242,255,0.14)",
  accent: "#38bdf8",
  accent2: "#6366f1",
  cool: "#7dd3fc",
  gradientButton: "linear-gradient(135deg,#38bdf8,#6366f1)",
  gradientProgress: "linear-gradient(90deg,#38bdf8,#6366f1)",
  selectedShadow: "0 10px 28px -12px rgba(99,102,241,0.8)",
  ringA: "rgba(56,189,248,0.45)",
  ringB: "rgba(99,102,241,0.4)",
};

type Props = {
  token: string;
  companyName: string;
  onDone: (message: string) => void;
  onBlocked: (status: string, message?: string) => void;
  onBack: () => void;
};

export function SmartCardWebSession({ token, companyName, onDone, onBlocked, onBack }: Props) {
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [sessionId, setSessionId] = React.useState<string | null>(null);
  const [prompt, setPrompt] = React.useState("");
  const [stepKey, setStepKey] = React.useState("contact");
  const [stepIndex, setStepIndex] = React.useState(0);
  const [stepTotal, setStepTotal] = React.useState(1);
  const [allowVoice, setAllowVoice] = React.useState(false);
  const [contactCapture, setContactCapture] = React.useState("offer_both");
  const [answer, setAnswer] = React.useState("");
  const [contact, setContact] = React.useState({ name: "", company: "", email: "", mobile: "" });
  const [cardPreview, setCardPreview] = React.useState<string | null>(null);
  const cardInputRef = React.useRef<HTMLInputElement>(null);
  const voiceRef = React.useRef<VoiceDetailHandle>(null);

  const isContact = stepKey.startsWith("contact");

  const applyAdvance = (data: any) => {
    if (data.done) {
      onDone(data.message || "Thank you — we appreciate your feedback.");
      return;
    }
    setPrompt(data.prompt || "");
    setStepKey(String(data.step || ""));
    if (typeof data.step_index === "number") setStepIndex(data.step_index);
    else setStepIndex((i) => i + 1);
    if (typeof data.step_total === "number") setStepTotal(data.step_total);
    setAllowVoice(Boolean(data.allow_voice));
    setAnswer("");
  };

  React.useEffect(() => {
    void (async () => {
      setBusy(true);
      setError(null);
      try {
        const res = await fetch(`${API}/public/smart-card/${encodeURIComponent(token)}/start`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({}),
        });
        const data = await res.json();
        if (!res.ok) {
          const detail = typeof data?.detail === "string" ? data.detail : "Could not start";
          if (detail === "preview_exhausted" || detail === "expired") {
            onBlocked(detail);
            return;
          }
          throw new Error(detail);
        }
        setSessionId(data.session_id);
        setPrompt(data.prompt || "Please continue.");
        setStepKey(String(data.step || "contact"));
        setContactCapture(String(data.contact_capture || "offer_both"));
        const steps: string[] = Array.isArray(data.steps) ? data.steps : [];
        setStepTotal(Math.max(1, data.step_total || steps.length || 1));
        setStepIndex(typeof data.step_index === "number" ? data.step_index : 0);
        setAllowVoice(Boolean(data.allow_voice));
      } catch (e: any) {
        setError(e?.message || "Could not start");
      } finally {
        setBusy(false);
      }
    })();
    // Fresh mount (keyed by parent) starts a new session once.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const sendAnswer = async (text: string, answerSource = "text") => {
    if (!sessionId) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`${API}/public/smart-card/${encodeURIComponent(token)}/answer`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, answer: text, answer_source: answerSource }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data?.detail === "string" ? data.detail : "Answer failed");
      applyAdvance(data);
    } catch (e: any) {
      setError(e?.message || "Answer failed");
    } finally {
      setBusy(false);
    }
  };

  const submitContact = async () => {
    const packed = [contact.name, contact.company, contact.email, contact.mobile]
      .map((s) => s.trim())
      .filter(Boolean)
      .join(" | ");
    if (!packed && contactCapture !== "card_only") {
      setError("Please enter your details or upload a business card.");
      return;
    }
    if (!packed && contactCapture === "card_only") {
      setError("Please upload a photo of your business card.");
      return;
    }
    await sendAnswer(packed || contact.name || "card");
  };

  const onCardPicked = async (file: File | null) => {
    if (!file || !sessionId) return;
    setBusy(true);
    setError(null);
    try {
      setCardPreview(URL.createObjectURL(file));
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch(
        `${API}/public/smart-card/${encodeURIComponent(token)}/card?session_id=${encodeURIComponent(sessionId)}`,
        { method: "POST", body: fd },
      );
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data?.detail === "string" ? data.detail : "OCR failed");
      const ex = data.extracted || {};
      setContact((c) => ({
        name: String(ex.name || c.name || ""),
        company: String(ex.company || c.company || ""),
        email: String(ex.email || c.email || ""),
        mobile: String(ex.phone || c.mobile || ""),
      }));
      if (data.prompt) setPrompt(data.prompt);
    } catch (e: any) {
      setError(e?.message || "Could not read card");
    } finally {
      setBusy(false);
      if (cardInputRef.current) cardInputRef.current.value = "";
    }
  };

  const submitVoiceOrText = async () => {
    const blob = voiceRef.current?.getBlob() || null;
    const typed = (voiceRef.current?.getText() || answer).trim();
    if (blob && sessionId) {
      setBusy(true);
      setError(null);
      try {
        const form = new FormData();
        form.append("file", blob, "voice.webm");
        const res = await fetch(
          `${API}/public/smart-card/${encodeURIComponent(token)}/sessions/${encodeURIComponent(sessionId)}/voice`,
          { method: "POST", body: form },
        );
        const data = await res.json();
        if (!res.ok) {
          throw new Error(
            typeof data?.detail === "string"
              ? data.detail
              : "Could not process voice note",
          );
        }
        applyAdvance(data);
      } catch (e: any) {
        setError(e?.message || "Could not process voice note");
      } finally {
        setBusy(false);
      }
      return;
    }
    if (!typed) {
      setError(allowVoice ? "Record a voice note or type your answer." : "Please type your answer.");
      return;
    }
    await sendAnswer(typed);
  };

  const progressPct = Math.round(((stepIndex + 1) / Math.max(1, stepTotal)) * 100);

  return (
    <main className="bg-smartcard-gradient relative min-h-dvh overflow-hidden">
      <div className="relative mx-auto flex min-h-dvh w-full max-w-md flex-col px-5 pb-8 pt-6">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-[11px] font-medium uppercase tracking-[0.18em]" style={{ color: SC_THEME.sub }}>
              Feedback
            </p>
            <p className="text-[14px] font-semibold" style={{ color: SC_THEME.ink }}>
              {companyName}
            </p>
          </div>
          <button
            type="button"
            onClick={onBack}
            className="text-[12px]"
            style={{ color: SC_THEME.sub }}
          >
            Back
          </button>
        </div>
        <div className="mt-1 flex justify-end">
          <span className="text-[11px]" style={{ color: SC_THEME.sub }}>
            {Math.min(stepIndex + 1, stepTotal)} / {stepTotal}
          </span>
        </div>
        <div className="mt-3 h-1 w-full overflow-hidden rounded-full" style={{ background: SC_THEME.border }}>
          <div
            className="h-full rounded-full transition-all duration-500"
            style={{ width: `${progressPct}%`, background: SC_THEME.gradientProgress }}
          />
        </div>

        <div className="mt-6 flex flex-1 flex-col">
          {error ? <p className="mb-3 text-[13px] text-rose-300">{error}</p> : null}

          {isContact ? (
            <div className="animate-rise space-y-4">
              <p className="text-[11px] font-medium uppercase tracking-[0.2em]" style={{ color: SC_THEME.sub }}>
                Contact
              </p>
              <h1 className="text-[22px] font-semibold leading-snug" style={{ color: SC_THEME.ink }}>
                {prompt ||
                  (contactCapture === "card_only"
                    ? "Please upload a photo of your business card."
                    : "Upload a business card, or enter your details.")}
              </h1>
              <input
                ref={cardInputRef}
                type="file"
                accept="image/*"
                capture="environment"
                className="hidden"
                onChange={(e) => void onCardPicked(e.target.files?.[0] || null)}
              />
              {contactCapture !== "manual_only" ? (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => cardInputRef.current?.click()}
                  className="flex w-full flex-col items-center gap-1 rounded-2xl border-2 border-dashed px-4 py-6 text-[14px] font-semibold disabled:opacity-60"
                  style={{
                    borderColor: "rgba(56,189,248,0.35)",
                    color: SC_THEME.ink,
                    background: "rgba(56,189,248,0.08)",
                  }}
                >
                  <span className="text-2xl" aria-hidden>
                    📷
                  </span>
                  {cardPreview ? "Retake / change business card" : "Take photo of business card"}
                  <span className="text-[11px] font-normal" style={{ color: SC_THEME.sub }}>
                    Camera or upload — we read the details for you
                  </span>
                </button>
              ) : null}
              {cardPreview ? (
                <img
                  src={cardPreview}
                  alt="Business card preview"
                  className="h-36 w-full rounded-xl object-cover"
                />
              ) : null}
              {contactCapture !== "card_only" ? (
                <div className="grid gap-2.5">
                  {(
                    [
                      ["name", "Name"],
                      ["company", "Company"],
                      ["mobile", "Mobile"],
                      ["email", "Email"],
                    ] as const
                  ).map(([key, label]) => (
                    <label key={key} className="block">
                      <span className="mb-1 block text-[11px] uppercase tracking-wide" style={{ color: SC_THEME.sub }}>
                        {label}
                      </span>
                      <input
                        value={contact[key]}
                        onChange={(e) => setContact((c) => ({ ...c, [key]: e.target.value }))}
                        className="w-full rounded-xl px-3 py-2.5 text-[14px] outline-none"
                        style={{
                          background: SC_THEME.card,
                          border: `1px solid ${SC_THEME.border}`,
                          color: SC_THEME.ink,
                        }}
                        autoComplete={key === "email" ? "email" : key === "mobile" ? "tel" : "off"}
                      />
                    </label>
                  ))}
                </div>
              ) : null}
              <button
                type="button"
                disabled={busy}
                onClick={() => void submitContact()}
                className="mt-2 w-full rounded-2xl px-4 py-3 text-[14px] font-semibold disabled:opacity-60"
                style={{ background: SC_THEME.gradientButton, color: "#06121f" }}
              >
                {busy ? "Sending…" : "Continue"}
              </button>
            </div>
          ) : (
            <div className="animate-rise flex flex-1 flex-col">
              <VoiceDetail
                key={`sc-voice-${stepKey}-${stepIndex}`}
                ref={voiceRef}
                theme={SC_THEME}
                eyebrow="Question"
                title={prompt || "Please continue."}
                hint={
                  allowVoice
                    ? "Type in English, or record a voice note in any language — we keep the recording and translate for the team."
                    : "Type your answer."
                }
                text={answer}
                onTextChange={setAnswer}
                allowVoice={allowVoice}
                disabled={busy}
                placeholder="Your answer…"
              />
              <button
                type="button"
                disabled={busy}
                onClick={() => void submitVoiceOrText()}
                className="mt-4 w-full rounded-2xl px-4 py-3 text-[14px] font-semibold disabled:opacity-60"
                style={{ background: SC_THEME.gradientButton, color: "#06121f" }}
              >
                {busy ? "Sending…" : "Continue"}
              </button>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
