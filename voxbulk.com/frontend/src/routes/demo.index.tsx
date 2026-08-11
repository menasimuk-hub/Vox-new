import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { z } from "zod";
import { SiteHeader, SiteFooter } from "@/components/SiteShell";
import { ArrowRight, ArrowLeft, Check, Building2, Globe, Languages, Mail, MessageSquare, Phone, User } from "lucide-react";
import { submitDemoRequest } from "@/lib/aiDemo";
import { toast } from "sonner";
import { fetchSeoSettings } from "@/lib/seo";
import { pageMeta } from "@/lib/seo-defaults";

export const Route = createFileRoute("/demo/")({
  loader: async () => ({ settings: await fetchSeoSettings() }),
  head: ({ loaderData }) => ({
    meta: pageMeta("contact", {
      override: {
        ...(loaderData?.settings?.marketing_pages?.contact || {}),
        title: "Request an AI demo | VoxBulk",
        description: "Book a live AI product demo for Recruitment, Surveys, Feedback, Expo, or Smart Card.",
      },
    }),
    links: [{ rel: "canonical", href: "https://voxbulk.com/demo" }],
  }),
  component: DemoRequestPage,
});

const COUNTRY_CODES = [
  { code: "+44", label: "UK (+44)" },
  { code: "+966", label: "SA (+966)" },
  { code: "+971", label: "AE (+971)" },
  { code: "+1", label: "US/CA (+1)" },
  { code: "+33", label: "FR (+33)" },
  { code: "+49", label: "DE (+49)" },
  { code: "+91", label: "IN (+91)" },
];

const schema = z.object({
  contact_name: z.string().trim().min(2, "Please enter your name").max(100),
  email: z.string().trim().email("Enter a valid email").max(255),
  company_name: z.string().trim().min(2, "Company name is required").max(255),
  whatsapp_local: z.string().trim().min(6, "Enter your WhatsApp number").max(20),
  website: z.string().trim().min(3, "Company website is required").max(512),
  preferred_language: z.enum(["en", "ar"]),
  message: z.string().trim().min(10, "Please write at least 10 characters").max(2000),
});

function DemoRequestPage() {
  const [step, setStep] = useState(0);
  const [contactName, setContactName] = useState("");
  const [email, setEmail] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [countryCode, setCountryCode] = useState("+44");
  const [whatsappLocal, setWhatsappLocal] = useState("");
  const [website, setWebsite] = useState("");
  const [preferredLanguage, setPreferredLanguage] = useState<"en" | "ar">("en");
  const [message, setMessage] = useState("");
  const [callbackConsent, setCallbackConsent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const totalSteps = 6;

  const next = () => {
    setError(null);
    if (step === 0) {
      const r = schema.shape.contact_name.safeParse(contactName);
      if (!r.success) return setError(r.error.issues[0].message);
    }
    if (step === 1) {
      const r = schema.shape.email.safeParse(email);
      if (!r.success) return setError(r.error.issues[0].message);
    }
    if (step === 2) {
      const r = schema.shape.company_name.safeParse(companyName);
      if (!r.success) return setError(r.error.issues[0].message);
      const w = schema.shape.website.safeParse(website);
      if (!w.success) return setError(w.error.issues[0].message);
    }
    if (step === 3) {
      const r = schema.shape.whatsapp_local.safeParse(whatsappLocal.replace(/\s+/g, ""));
      if (!r.success) return setError(r.error.issues[0].message);
    }
    setStep((s) => Math.min(totalSteps - 1, s + 1));
  };

  const back = () => {
    setError(null);
    setStep((s) => Math.max(0, s - 1));
  };

  const submit = async () => {
    setError(null);
    if (!callbackConsent) {
      setError("Please confirm that we may call you back on your WhatsApp number.");
      return;
    }
    const local = whatsappLocal.replace(/\s+/g, "").replace(/^0+/, "");
    const parsed = schema.safeParse({
      contact_name: contactName,
      email,
      company_name: companyName,
      whatsapp_local: local,
      website,
      preferred_language: preferredLanguage,
      message,
    });
    if (!parsed.success) {
      setError(parsed.error.issues[0].message);
      return;
    }
    setSubmitting(true);
    try {
      await submitDemoRequest({
        contact_name: parsed.data.contact_name,
        email: parsed.data.email,
        company_name: parsed.data.company_name,
        whatsapp: `${countryCode}${parsed.data.whatsapp_local}`,
        website: parsed.data.website,
        preferred_language: parsed.data.preferred_language,
        message: parsed.data.message,
        callback_consent: callbackConsent,
      });
      setStep(totalSteps);
      toast.success("Request received — we'll email your demo link shortly.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="bg-background text-body antialiased min-h-screen flex flex-col">
      <SiteHeader />
      <main className="flex-1 pt-[110px] md:pt-[130px] pb-24">
        <div className="max-w-[640px] mx-auto px-5 md:px-10">
          <div className="text-center">
            <span className="eyebrow">Live AI demo</span>
            <h1 className="mt-3 text-[34px] md:text-[44px] font-bold tracking-[-0.03em] text-heading leading-[1.05]">
              Request your VoxBulk <span className="italic font-serif font-normal text-primary">AI demo</span>.
            </h1>
            <p className="mt-4 text-body text-[16px]">
              Tell us about your company. After approval we email a one-time demo link (valid 7 days) and WhatsApp you to check your inbox.
            </p>
          </div>

          {step < totalSteps && (
            <div className="mt-10 flex items-center justify-center gap-2">
              {Array.from({ length: totalSteps }).map((_, i) => (
                <div
                  key={i}
                  className={`h-1.5 rounded-full transition-all ${step >= i ? "bg-primary w-8" : "bg-border w-5"}`}
                />
              ))}
            </div>
          )}

          <div className="mt-10 bg-white border border-border rounded-3xl p-7 md:p-10 shadow-elegant">
            {step === 0 && (
              <Field
                id="demo-name"
                icon={<User size={18} />}
                label="Your name"
                value={contactName}
                onChange={setContactName}
                placeholder="Full name"
                autoFocus
                onEnter={next}
              />
            )}
            {step === 1 && (
              <Field
                id="demo-email"
                icon={<Mail size={18} />}
                label="Work email"
                type="email"
                value={email}
                onChange={setEmail}
                placeholder="you@company.com"
                autoFocus
                onEnter={next}
              />
            )}
            {step === 2 && (
              <div className="space-y-5">
                <Field
                  id="demo-company"
                  icon={<Building2 size={18} />}
                  label="Company name"
                  value={companyName}
                  onChange={setCompanyName}
                  placeholder="Company Ltd"
                  autoFocus
                />
                <Field
                  id="demo-website"
                  icon={<Globe size={18} />}
                  label="Company website"
                  value={website}
                  onChange={setWebsite}
                  placeholder="https://company.com"
                  onEnter={next}
                />
              </div>
            )}
            {step === 3 && (
              <div>
                <label className="flex items-center gap-2 text-[13px] font-semibold uppercase tracking-wider text-muted-text mb-3">
                  <Phone size={18} /> WhatsApp number
                </label>
                <div className="flex gap-2">
                  <select
                    value={countryCode}
                    onChange={(e) => setCountryCode(e.target.value)}
                    className="w-[140px] rounded-xl border border-border bg-secondary/30 px-3 py-3.5 text-[15px]"
                  >
                    {COUNTRY_CODES.map((c) => (
                      <option key={c.code} value={c.code}>
                        {c.label}
                      </option>
                    ))}
                  </select>
                  <input
                    value={whatsappLocal}
                    onChange={(e) => setWhatsappLocal(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && next()}
                    placeholder="7123 456789"
                    className="flex-1 rounded-xl border border-border bg-secondary/30 px-4 py-3.5 text-[16px] focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
                    autoFocus
                  />
                </div>
              </div>
            )}
            {step === 4 && (
              <div>
                <label className="flex items-center gap-2 text-[13px] font-semibold uppercase tracking-wider text-muted-text mb-3">
                  <Languages size={18} /> Preferred demo language
                </label>
                <div className="grid grid-cols-2 gap-3">
                  {[
                    { id: "en" as const, label: "English" },
                    { id: "ar" as const, label: "Arabic" },
                  ].map((opt) => (
                    <button
                      key={opt.id}
                      type="button"
                      onClick={() => setPreferredLanguage(opt.id)}
                      className={`rounded-xl border px-4 py-4 text-[15px] font-semibold transition-all ${
                        preferredLanguage === opt.id
                          ? "border-primary bg-primary/10 text-heading"
                          : "border-border bg-secondary/30 text-body"
                      }`}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {step === 5 && (
              <div className="space-y-4">
                <div>
                  <label htmlFor="demo-message" className="flex items-center gap-2 text-[13px] font-semibold uppercase tracking-wider text-muted-text mb-3">
                    <MessageSquare size={18} /> Your message
                  </label>
                  <textarea
                    id="demo-message"
                    value={message}
                    onChange={(e) => setMessage(e.target.value)}
                    rows={5}
                    placeholder="What would you like to see in the demo?"
                    className="w-full rounded-xl border border-border bg-secondary/30 px-4 py-3.5 text-[16px] focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
                    autoFocus
                  />
                </div>
                <label className="flex items-start gap-2.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={callbackConsent}
                    onChange={(e) => setCallbackConsent(e.target.checked)}
                    className="mt-0.5 w-4 h-4 rounded border-border text-primary focus:ring-2 focus:ring-primary/30"
                  />
                  <span className="text-[13.5px] text-body leading-snug">
                    I agree that VoxBulk may call me back on the WhatsApp number I provided about this demo. <span className="text-primary">*</span>
                  </span>
                </label>
              </div>
            )}
            {step === totalSteps && (
              <div className="text-center py-6">
                <div className="mx-auto w-14 h-14 rounded-full bg-primary/10 flex items-center justify-center mb-4">
                  <Check className="text-primary" size={28} />
                </div>
                <h2 className="text-[22px] font-bold text-heading">Request received</h2>
                <p className="mt-3 text-body text-[15px]">
                  Our team will review and email your demo link. Watch for a WhatsApp note to check your inbox (and spam).
                </p>
                <Link to="/" className="inline-flex mt-6 text-primary font-semibold text-[14px]">
                  Back to home
                </Link>
              </div>
            )}

            {error && step < totalSteps && (
              <p className="mt-4 text-[14px] text-red-600" role="alert">
                {error}
              </p>
            )}

            {step < totalSteps && (
              <div className="mt-8 flex items-center gap-3">
                {step > 0 && (
                  <button type="button" onClick={back} className="h-12 w-12 rounded-full border border-border flex items-center justify-center">
                    <ArrowLeft size={18} />
                  </button>
                )}
                {step < 5 ? (
                  <button type="button" onClick={next} className="btn-primary h-12 px-6 flex-1 max-w-[280px]">
                    Continue <ArrowRight size={16} />
                  </button>
                ) : (
                  <SlideToSubmit onConfirm={submit} loading={submitting} />
                )}
              </div>
            )}
          </div>
        </div>
      </main>
      <SiteFooter />
    </div>
  );
}

function Field({
  id,
  label,
  value,
  onChange,
  placeholder,
  type = "text",
  icon,
  autoFocus,
  onEnter,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: string;
  icon?: React.ReactNode;
  autoFocus?: boolean;
  onEnter?: () => void;
}) {
  return (
    <div>
      <label htmlFor={id} className="flex items-center gap-2 text-[13px] font-semibold uppercase tracking-wider text-muted-text mb-3">
        {icon} {label}
      </label>
      <input
        id={id}
        autoFocus={autoFocus}
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") onEnter?.();
        }}
        placeholder={placeholder}
        className="w-full rounded-xl border border-border bg-secondary/30 px-4 py-3.5 text-[16px] focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
      />
    </div>
  );
}

function SlideToSubmit({ onConfirm, loading }: { onConfirm: () => void; loading: boolean }) {
  const [x, setX] = useState(0);
  const [confirmed, setConfirmed] = useState(false);
  const trackRef = useRef<HTMLDivElement>(null);
  const startXRef = useRef<number | null>(null);
  const maxRef = useRef(0);

  useEffect(() => {
    const update = () => {
      if (trackRef.current) maxRef.current = trackRef.current.clientWidth - 56;
    };
    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, []);

  const onPointerDown = (e: React.PointerEvent) => {
    if (confirmed || loading) return;
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
    startXRef.current = e.clientX - x;
  };
  const onPointerMove = (e: React.PointerEvent) => {
    if (startXRef.current === null) return;
    setX(Math.max(0, Math.min(maxRef.current, e.clientX - startXRef.current)));
  };
  const onPointerUp = () => {
    if (startXRef.current === null) return;
    startXRef.current = null;
    if (x >= maxRef.current - 4) {
      setX(maxRef.current);
      setConfirmed(true);
      onConfirm();
    } else setX(0);
  };
  const pct = maxRef.current ? (x / maxRef.current) * 100 : 0;

  return (
    <div
      ref={trackRef}
      role="button"
      tabIndex={0}
      aria-label="Slide to send your demo request"
      onKeyDown={(e) => {
        if ((e.key === "Enter" || e.key === " ") && !confirmed && !loading) {
          e.preventDefault();
          setConfirmed(true);
          onConfirm();
        }
      }}
      className="relative flex-1 max-w-[320px] h-14 rounded-full bg-secondary border border-border overflow-hidden select-none touch-none"
    >
      <div className="absolute inset-y-0 left-0 bg-gradient-to-r from-primary to-primary-dark" style={{ width: `${Math.max(pct, 8)}%` }} />
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
        <span className={`text-[13.5px] font-semibold uppercase tracking-[0.18em] ${pct > 50 ? "text-white/80" : "text-muted-text"}`}>
          {loading ? "Sending…" : confirmed ? "Sent" : "Slide to send"}
        </span>
      </div>
      <div
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        className="absolute top-1 left-1 w-12 h-12 rounded-full bg-white shadow-elevated flex items-center justify-center cursor-grab"
        style={{ transform: `translateX(${x}px)` }}
      >
        {confirmed || loading ? <Check size={18} className="text-primary" /> : <ArrowRight size={18} className="text-primary" />}
      </div>
    </div>
  );
}
