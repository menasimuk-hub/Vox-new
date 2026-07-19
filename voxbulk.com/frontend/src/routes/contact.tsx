import { createFileRoute } from "@tanstack/react-router";
import { useState, useRef, useEffect } from "react";
import { z } from "zod";
import { SiteHeader, SiteFooter } from "@/components/SiteShell";
import { ArrowRight, ArrowLeft, Check, Mail, User, MessageSquare } from "lucide-react";
import { frontpageApiFetch } from "@/lib/api";
import { toast } from "sonner";
import { fetchSeoSettings } from "@/lib/seo";
import { pageMeta } from "@/lib/seo-defaults";

export const Route = createFileRoute("/contact")({
  loader: async () => ({ settings: await fetchSeoSettings() }),
  head: ({ loaderData }) => ({
    meta: pageMeta("contact", { override: loaderData?.settings?.marketing_pages?.contact }),
    links: [{ rel: "canonical", href: "https://voxbulk.com/contact" }],
  }),

  component: ContactPage,
});

const schema = z.object({
  name: z.string().trim().min(2, "Please enter your name").max(100),
  email: z.string().trim().email("Enter a valid email").max(255),
  message: z.string().trim().min(10, "Please write at least 10 characters").max(2000),
});

function ContactPage() {
  const [step, setStep] = useState<0 | 1 | 2 | 3>(0);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const next = () => {
    setError(null);
    if (step === 0) {
      const r = schema.shape.name.safeParse(name);
      if (!r.success) return setError(r.error.issues[0].message);
    }
    if (step === 1) {
      const r = schema.shape.email.safeParse(email);
      if (!r.success) return setError(r.error.issues[0].message);
    }
    setStep((s) => (s + 1) as 0 | 1 | 2 | 3);
  };
  const back = () => { setError(null); setStep((s) => Math.max(0, s - 1) as 0 | 1 | 2 | 3); };

  const submit = async () => {
    setError(null);
    const parsed = schema.safeParse({ name, email, message });
    if (!parsed.success) { setError(parsed.error.issues[0].message); return; }
    setSubmitting(true);
    try {
      await frontpageApiFetch("/frontpage/contact", {
        method: "POST",
        body: JSON.stringify({
          name: parsed.data.name,
          email: parsed.data.email,
          message: parsed.data.message,
          website: "", // honeypot
        }),
      });
      setStep(3);
      toast.success("Thanks! We'll be in touch shortly.");
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Something went wrong. Please try again.";
      setError(msg);
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
            <span className="eyebrow">Contact us</span>
            <h1 className="mt-3 text-[34px] md:text-[44px] font-bold tracking-[-0.03em] text-heading leading-[1.05]">
              Contact the VoxBulk <span className="italic font-serif font-normal text-primary">Team</span>.
            </h1>
            <p className="mt-4 text-body text-[16px]">A few quick steps and we'll be in touch.</p>

            <h2 className="sr-only">Send us a message</h2>
          </div>

          {/* Progress */}
          <div className="mt-10 flex items-center justify-center gap-2">
            {[0, 1, 2].map((i) => (
              <div key={i} className={`h-1.5 rounded-full transition-all ${step >= i ? "bg-primary w-10" : "bg-border w-6"}`} />
            ))}
          </div>

          <div className="mt-10 bg-white border border-border rounded-3xl p-7 md:p-10 shadow-elegant">
            {step === 0 && (
              <Field
                id="contact-name"
                icon={<User size={18} />}
                label="What's your name?"
                value={name}
                onChange={setName}
                placeholder="Jane Smith"
                autoFocus
                onEnter={next}
              />
            )}
            {step === 1 && (
              <Field
                id="contact-email"
                icon={<Mail size={18} />}
                label="Your email address"
                type="email"
                value={email}
                onChange={setEmail}
                placeholder="jane@company.com"

                autoFocus
                onEnter={next}
              />
            )}
            {step === 2 && (
              <div>
                <label htmlFor="contact-message" className="flex items-center gap-2 text-[13px] font-semibold uppercase tracking-wider text-muted-text mb-3">
                  <MessageSquare size={16} /> Your message
                </label>
                <textarea
                  id="contact-message"
                  autoFocus
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  placeholder="Tell us a bit about your team and what you're looking to automate…"

                  rows={6}
                  className="w-full rounded-xl border border-border bg-secondary/30 px-4 py-3 text-[15px] focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary resize-none"
                />
              </div>
            )}
            {step === 3 && (
              <div className="text-center py-6">
                <div className="mx-auto w-16 h-16 rounded-full bg-success/15 text-success flex items-center justify-center">
                  <Check size={32} strokeWidth={3} />
                </div>
                <h3 className="mt-5 text-[24px] font-bold text-heading">Message sent</h3>
                <p className="mt-2 text-body">Thanks {name.split(" ")[0]}, we'll reply to {email} within one working day.</p>
              </div>
            )}

            {error && <p className="mt-4 text-[13.5px] text-destructive">{error}</p>}

            {step < 3 && (
              <div className="mt-7 flex items-center justify-between gap-3">
                <button
                  onClick={back}
                  disabled={step === 0}
                  className="inline-flex items-center gap-1.5 px-3 py-2 text-[14px] text-muted-text hover:text-heading disabled:opacity-30 disabled:cursor-not-allowed"
                >
                  <ArrowLeft size={16} /> Back
                </button>

                {step < 2 ? (
                  <button onClick={next} className="btn-primary text-[14px]">
                    Continue <ArrowRight size={15} />
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
  id, label, value, onChange, placeholder, type = "text", icon, autoFocus, onEnter,
}: {
  id: string; label: string; value: string; onChange: (v: string) => void; placeholder?: string;
  type?: string; icon?: React.ReactNode; autoFocus?: boolean; onEnter?: () => void;
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
        onKeyDown={(e) => { if (e.key === "Enter") onEnter?.(); }}
        placeholder={placeholder}
        className="w-full rounded-xl border border-border bg-secondary/30 px-4 py-3.5 text-[16px] focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
      />
    </div>
  );
}

/* ---------------- Slide-to-submit button ---------------- */
function SlideToSubmit({ onConfirm, loading }: { onConfirm: () => void; loading: boolean }) {
  const [x, setX] = useState(0);
  const [confirmed, setConfirmed] = useState(false);
  const trackRef = useRef<HTMLDivElement>(null);
  const startXRef = useRef<number | null>(null);
  const maxRef = useRef(0);

  useEffect(() => {
    const update = () => {
      if (trackRef.current) {
        maxRef.current = trackRef.current.clientWidth - 56; // knob width
      }
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
    const nx = Math.max(0, Math.min(maxRef.current, e.clientX - startXRef.current));
    setX(nx);
  };
  const onPointerUp = () => {
    if (startXRef.current === null) return;
    startXRef.current = null;
    if (x >= maxRef.current - 4) {
      setX(maxRef.current);
      setConfirmed(true);
      onConfirm();
    } else {
      setX(0);
    }
  };

  const pct = maxRef.current ? (x / maxRef.current) * 100 : 0;

  return (
    <div
      ref={trackRef}
      role="button"
      tabIndex={0}
      aria-label="Slide to send your message"
      onKeyDown={(e) => { if ((e.key === "Enter" || e.key === " ") && !confirmed && !loading) { e.preventDefault(); setConfirmed(true); onConfirm(); } }}
      className="relative flex-1 max-w-[320px] h-14 rounded-full bg-secondary border border-border overflow-hidden select-none touch-none"
    >
      {/* Filled track */}
      <div
        className="absolute inset-y-0 left-0 bg-gradient-to-r from-primary to-primary-dark transition-[width] duration-100"
        style={{ width: `${Math.max(pct, 8)}%` }}
      />
      {/* Label */}
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
        <span className={`text-[13.5px] font-semibold uppercase tracking-[0.18em] transition-colors ${pct > 50 ? "text-white/80" : "text-muted-text"}`}>
          {loading ? "Sending…" : confirmed ? "Sent" : "Slide to send"}
        </span>
      </div>
      {/* Knob */}
      <div
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        className="absolute top-1 left-1 w-12 h-12 rounded-full bg-white shadow-elevated flex items-center justify-center cursor-grab active:cursor-grabbing transition-transform"
        style={{ transform: `translateX(${x}px)` }}
      >
        {confirmed || loading ? <Check size={18} className="text-primary" /> : <ArrowRight size={18} className="text-primary" />}
      </div>
    </div>
  );
}
