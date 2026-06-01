import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { z } from "zod";
import { SiteHeader, SiteFooter } from "@/components/SiteShell";
import { toast } from "sonner";
import {
  Building2, Phone, Globe, Mail, MapPin, Image as ImageIcon,
  Loader2, ArrowRight, ArrowLeft, Check, Upload, X,
  Briefcase, MessageSquare, PhoneCall, FileText, BarChart3, Headphones,
} from "lucide-react";
import { useAuth } from "@/lib/auth";
import { apiFetch, apiUpload, getPostLoginHandoffUrl, hasPlatformAdminAccess } from "@/lib/api";
import {
  marketingSelectionToEnabled,
  MARKETING_SERVICES,
  type MarketingServiceId,
} from "@/lib/services";

export const Route = createFileRoute("/onboarding")({
  head: () => ({
    meta: [
      { title: "Set up your company — VoxBulk" },
      { name: "description", content: "Tell us about your company so we can tailor your VoxBulk workspace — name, contact details, country and services." },
      { property: "og:title", content: "Set up your company — VoxBulk" },
      { property: "og:description", content: "Quick company setup to tailor your VoxBulk workspace." },
      { property: "og:url", content: "https://voxbulk.com/onboarding" },
    ],
    links: [{ rel: "canonical", href: "https://voxbulk.com/onboarding" }],
  }),
  component: CompanyWizard,
});

type ServiceId = MarketingServiceId;

const ICONS: Record<ServiceId, typeof Briefcase> = {
  recruitment: Briefcase,
  ai_interviews: PhoneCall,
  whatsapp_surveys: MessageSquare,
  ai_calling: Headphones,
  ats: FileText,
  customer_success: BarChart3,
};

const SERVICES = MARKETING_SERVICES.map((s) => ({ ...s, Icon: ICONS[s.id] }));

const COUNTRIES = [
  "United Kingdom", "United States", "Australia", "Canada", "Ireland",
  "Germany", "France", "Spain", "Netherlands", "Sweden", "United Arab Emirates",
  "Saudi Arabia", "South Africa", "India", "Singapore", "New Zealand", "Other",
];

const schema = z.object({
  name: z.string().trim().min(2, "Company name is required").max(120),
  phone: z.string().trim().min(5, "Phone is required").max(40),
  website: z.string().trim().max(200).optional().or(z.literal("")),
  contact_email: z.string().trim().email("Enter a valid contact email").max(255).optional().or(z.literal("")),
  country: z.string().trim().min(2, "Pick a country"),
  services: z.array(z.string()).min(1, "Pick at least one service"),
});

function CompanyWizard() {
  const navigate = useNavigate();
  const auth = useAuth();
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [userEmail, setUserEmail] = useState<string>("");
  const [saving, setSaving] = useState(false);
  const [allowedServices, setAllowedServices] = useState<Record<string, boolean> | null>(null);
  const availableServices = SERVICES.filter(
    (s) => !allowedServices || allowedServices[s.backendKey] !== false,
  );

  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [website, setWebsite] = useState("");
  const [contactEmail, setContactEmail] = useState("");
  const [country, setCountry] = useState("");
  const [services, setServices] = useState<ServiceId[]>([]);
  const [logoFile, setLogoFile] = useState<File | null>(null);
  const [logoPreview, setLogoPreview] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const redirecting = useRef(false);

  useEffect(() => {
    if (auth.loading || redirecting.current) return;
    if (!auth.user) {
      redirecting.current = true;
      navigate({ to: "/signin" });
      return;
    }
    setUserEmail(auth.user.email || "");
    setContactEmail((prev) => prev || auth.user?.email || "");
    if (hasPlatformAdminAccess(auth.user)) {
      redirecting.current = true;
      window.location.href = getPostLoginHandoffUrl(auth.user);
      return;
    }
    if (!auth.needsOnboarding()) {
      redirecting.current = true;
      window.location.href = getPostLoginHandoffUrl(auth.user);
      return;
    }
    void apiFetch<{ name?: string; allowed_services?: Record<string, boolean> }>("/organisations/me")
      .then((org) => {
        if (org?.name) setName(org.name);
        setAllowedServices(org?.allowed_services || null);
      })
      .catch(() => {});
  }, [
    auth.loading,
    auth.user?.user_id,
    auth.user?.email,
    auth.user?.onboarding_complete,
    auth.user?.dashboard_setup_complete,
    navigate,
  ]);

  const toggleService = (id: ServiceId) =>
    setServices((prev) => prev.includes(id) ? prev.filter((s) => s !== id) : [...prev, id]);

  const onLogoPick = (file: File | null) => {
    setLogoFile(file);
    if (file) setLogoPreview(URL.createObjectURL(file));
    else setLogoPreview(null);
  };

  const next = () => {
    if (step === 1) {
      if (!name.trim() || name.trim().length < 2) return toast.error("Company name is required");
      if (!phone.trim() || phone.trim().length < 5) return toast.error("Phone is required");
      if (!country) return toast.error("Pick a country");
      setStep(2);
    } else if (step === 2) {
      if (services.length === 0) return toast.error("Pick at least one service");
      setStep(3);
    }
  };
  const back = () => setStep((s) => (s === 1 ? 1 : ((s - 1) as 1 | 2 | 3)));

  const submit = async () => {
    const parsed = schema.safeParse({
      name, phone, website, contact_email: contactEmail, country, services,
    });
    if (!parsed.success) { toast.error(parsed.error.issues[0].message); return; }
    setSaving(true);
    try {
      await apiFetch("/organisations/me", {
        method: "PATCH",
        body: JSON.stringify({
          name: name.trim(),
          contact_phone: phone.trim(),
          website: website.trim() || null,
          contact_email: contactEmail.trim() || null,
          country,
        }),
      });

      const enabled = marketingSelectionToEnabled(services, allowedServices);
      await apiFetch("/organisations/me/enabled-services", {
        method: "PATCH",
        body: JSON.stringify(enabled),
      });

      if (logoFile) {
        const form = new FormData();
        form.append("file", logoFile);
        await apiUpload("/organisations/me/logo", form);
      }

      await apiFetch("/auth/me/dashboard-setup", {
        method: "POST",
        body: JSON.stringify({
          profile: {
            company_name: name.trim(),
            country,
            services,
            website: website.trim() || null,
            contact_email: contactEmail.trim() || null,
            contact_phone: phone.trim(),
          },
        }),
      });

      await auth.refresh();
      toast.success("Company saved. Welcome to VoxBulk!");
      window.location.href = getPostLoginHandoffUrl(auth.user);
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Could not save your company");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="bg-beige text-body antialiased min-h-screen flex flex-col relative overflow-hidden">
      <SiteHeader />

      {/* Background illustration */}
      <BgIllustration />

      <main className="flex-1 pt-[110px] md:pt-[130px] pb-16 relative">
        <div className="max-w-[980px] mx-auto px-4 sm:px-6 md:px-10">
          <div className="text-center max-w-[640px] mx-auto">
            <span className="eyebrow">Welcome{userEmail && `, ${userEmail.split("@")[0]}`}</span>
            <h1 className="mt-3 text-[28px] sm:text-[34px] md:text-[42px] font-bold tracking-[-0.03em] text-heading leading-[1.1]">
              Set up your <span className="serif-italic text-primary">company</span>
            </h1>
            <p className="mt-3 text-body text-[14.5px] sm:text-[15.5px]">
              A few quick details so we can tailor your workspace.
            </p>
          </div>

          {/* Stepper */}
          <ol className="mt-8 flex items-center justify-center gap-2 sm:gap-4">
            {[
              { n: 1, label: "Company" },
              { n: 2, label: "Services" },
              { n: 3, label: "Branding" },
            ].map((s, i, arr) => {
              const active = step === s.n;
              const done = step > s.n;
              return (
                <li key={s.n} className="flex items-center gap-2 sm:gap-3">
                  <span className={`w-8 h-8 rounded-full inline-flex items-center justify-center text-[12.5px] font-bold border transition-colors ${
                    done ? "bg-primary text-white border-primary" :
                    active ? "bg-navy text-gold border-navy" :
                    "bg-white text-muted-text border-border"
                  }`}>{done ? <Check size={14} /> : s.n}</span>
                  <span className={`hidden sm:inline text-[13px] font-semibold ${active || done ? "text-heading" : "text-muted-text"}`}>{s.label}</span>
                  {i < arr.length - 1 && <span className={`w-6 sm:w-10 h-px ${done ? "bg-primary" : "bg-border"}`} />}
                </li>
              );
            })}
          </ol>

          {/* Card */}
          <div className="mt-8 bg-white border border-border rounded-2xl shadow-elegant p-5 sm:p-8 md:p-10 relative">
            {step === 1 && (
              <div className="space-y-5">
                <h2 className="text-[18px] sm:text-[20px] font-bold text-heading">Company details</h2>
                <div className="grid sm:grid-cols-2 gap-4">
                  <Field icon={<Building2 size={16} />} label="Company name" required value={name} onChange={setName} placeholder="Acme Ltd" />
                  <Field icon={<Phone size={16} />} label="Phone" required type="tel" value={phone} onChange={setPhone} placeholder="+44 7…" />
                  <Field icon={<Globe size={16} />} label="Website" value={website} onChange={setWebsite} placeholder="https://acme.com" />
                  <Field icon={<Mail size={16} />} label="Contact email" type="email" value={contactEmail} onChange={setContactEmail} placeholder="hello@acme.com" />
                  <div className="sm:col-span-2">
                    <label className="block text-[12.5px] font-semibold text-heading mb-1.5">
                      Country <span className="text-primary">*</span>
                    </label>
                    <div className="relative">
                      <MapPin size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-text pointer-events-none" />
                      <select
                        value={country}
                        onChange={(e) => setCountry(e.target.value)}
                        className="w-full pl-10 pr-3 py-3 rounded-xl border border-border bg-secondary/40 text-[14.5px] focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary appearance-none"
                      >
                        <option value="">Select a country…</option>
                        {COUNTRIES.map((c) => <option key={c} value={c}>{c}</option>)}
                      </select>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {step === 2 && (
              <div>
                <h2 className="text-[18px] sm:text-[20px] font-bold text-heading">What will you use VoxBulk for?</h2>
                <p className="mt-1 text-[13.5px] text-muted-text">Pick one or more — you can change this later.</p>
                <div className="mt-5 grid sm:grid-cols-2 gap-3">
                  {availableServices.map((s) => {
                    const active = services.includes(s.id);
                    const ServiceIcon = s.Icon ?? Briefcase;
                    return (
                      <button
                        key={s.id}
                        type="button"
                        onClick={() => toggleService(s.id)}
                        className={`relative text-left rounded-2xl p-4 border transition-all ${
                          active
                            ? "bg-primary/[0.06] border-primary shadow-[0_8px_20px_-12px_rgba(30,111,217,0.45)]"
                            : "bg-white border-border hover:border-primary/40"
                        }`}
                      >
                        <div className="flex items-start gap-3">
                          <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${active ? "bg-primary text-white" : "bg-secondary text-heading"}`}>
                            <ServiceIcon size={18} />
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-1.5">
                              <h3 className="text-[14.5px] font-bold text-heading truncate">{s.label}</h3>
                              {active && <Check size={14} className="text-primary shrink-0" strokeWidth={3} />}
                            </div>
                            <p className="mt-0.5 text-[12.5px] text-body leading-snug">{s.desc}</p>
                          </div>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            {step === 3 && (
              <div>
                <h2 className="text-[18px] sm:text-[20px] font-bold text-heading">Add your logo</h2>
                <p className="mt-1 text-[13.5px] text-muted-text">Optional — appears in your dashboard and reports.</p>

                <div className="mt-6 flex flex-col sm:flex-row items-center gap-5">
                  <div className="w-28 h-28 rounded-2xl border border-border bg-secondary/40 flex items-center justify-center overflow-hidden shrink-0">
                    {logoPreview ? (
                      <img src={logoPreview} alt="Logo preview" className="w-full h-full object-contain" />
                    ) : (
                      <ImageIcon size={26} className="text-muted-text" />
                    )}
                  </div>
                  <div className="flex-1 w-full">
                    <input
                      ref={fileRef}
                      type="file"
                      accept="image/png,image/jpeg,image/webp,image/svg+xml"
                      onChange={(e) => onLogoPick(e.target.files?.[0] ?? null)}
                      className="hidden"
                    />
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={() => fileRef.current?.click()}
                        className="inline-flex items-center gap-2 h-10 px-4 rounded-xl bg-navy text-white text-[13.5px] font-semibold hover:bg-navy/90 transition-colors"
                      >
                        <Upload size={14} /> {logoPreview ? "Change logo" : "Upload logo"}
                      </button>
                      {logoPreview && (
                        <button
                          type="button"
                          onClick={() => onLogoPick(null)}
                          className="inline-flex items-center gap-1.5 h-10 px-3 rounded-xl border border-border text-[13px] font-semibold text-heading hover:bg-secondary transition-colors"
                        >
                          <X size={14} /> Remove
                        </button>
                      )}
                    </div>
                    <p className="mt-2 text-[12px] text-muted-text">PNG, JPG, WebP or SVG · up to ~2 MB.</p>
                  </div>
                </div>

                {/* Summary */}
                <div className="mt-8 rounded-2xl bg-beige/70 border border-border p-5">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-text mb-3">Review</div>
                  <dl className="grid sm:grid-cols-2 gap-x-6 gap-y-2 text-[13.5px]">
                    <SummaryRow label="Company" value={name || "—"} />
                    <SummaryRow label="Phone" value={phone || "—"} />
                    <SummaryRow label="Website" value={website || "—"} />
                    <SummaryRow label="Contact email" value={contactEmail || "—"} />
                    <SummaryRow label="Country" value={country || "—"} />
                    <SummaryRow label="Services" value={services.length ? services.map(id => availableServices.find(s => s.id === id)?.label).filter(Boolean).join(", ") : "—"} />
                  </dl>
                </div>
              </div>
            )}

            {/* Nav buttons */}
            <div className="mt-8 flex items-center justify-between gap-3">
              {step > 1 ? (
                <button onClick={back} className="inline-flex items-center gap-1.5 h-11 px-4 rounded-xl border border-border text-[13.5px] font-semibold text-heading hover:bg-secondary transition-colors">
                  <ArrowLeft size={14} /> Back
                </button>
              ) : <span />}
              {step < 3 ? (
                <button onClick={next} className="btn-primary !px-6 !py-3 !text-[14px]">
                  Continue <ArrowRight size={15} />
                </button>
              ) : (
                <button onClick={submit} disabled={saving} className="btn-primary !px-6 !py-3 !text-[14px] disabled:opacity-60">
                  {saving ? <Loader2 size={15} className="animate-spin" /> : <>Finish setup <Check size={15} /></>}
                </button>
              )}
            </div>
          </div>
        </div>
      </main>

      <SiteFooter />
    </div>
  );
}

function Field({
  icon, label, value, onChange, placeholder, type = "text", required,
}: {
  icon: React.ReactNode; label: string; value: string; onChange: (v: string) => void;
  placeholder?: string; type?: string; required?: boolean;
}) {
  return (
    <label className="block">
      <span className="block text-[12.5px] font-semibold text-heading mb-1.5">
        {label}{required && <span className="text-primary"> *</span>}
      </span>
      <div className="relative">
        <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-text">{icon}</span>
        <input
          type={type}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          required={required}
          className="w-full pl-10 pr-3 py-3 rounded-xl border border-border bg-secondary/40 text-[14.5px] focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
        />
      </div>
    </label>
  );
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-3 border-b border-border/60 pb-1.5">
      <dt className="text-muted-text">{label}</dt>
      <dd className="font-semibold text-heading text-right truncate max-w-[60%]">{value}</dd>
    </div>
  );
}

/* Subtle moving background — beige with gentle drifting blurs */
function BgIllustration() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      <div className="absolute -top-40 -left-32 w-[520px] h-[520px] rounded-full blur-3xl opacity-50 float-a"
           style={{ background: "radial-gradient(circle, rgba(30,111,217,0.18), transparent 65%)" }} />
      <div className="absolute top-1/3 -right-32 w-[460px] h-[460px] rounded-full blur-3xl opacity-50 float-b"
           style={{ background: "radial-gradient(circle, rgba(79,179,169,0.20), transparent 65%)" }} />
      <div className="absolute -bottom-40 left-1/3 w-[520px] h-[520px] rounded-full blur-3xl opacity-40 float-a"
           style={{ background: "radial-gradient(circle, rgba(212,169,58,0.18), transparent 65%)", animationDelay: "1.6s" }} />
      <div className="absolute inset-0 bg-grid opacity-[0.08]" />
      {/* drifting dots */}
      <span className="absolute top-[18%] left-[8%] w-2 h-2 rounded-full bg-primary/40 float-a" />
      <span className="absolute top-[28%] right-[12%] w-1.5 h-1.5 rounded-full bg-teal/50 float-b" />
      <span className="absolute bottom-[22%] left-[14%] w-2 h-2 rounded-full bg-gold/50 float-b" style={{ animationDelay: "0.8s" }} />
      <span className="absolute bottom-[30%] right-[18%] w-1.5 h-1.5 rounded-full bg-primary/40 float-a" style={{ animationDelay: "1.2s" }} />
    </div>
  );
}
