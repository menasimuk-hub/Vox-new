import { useEffect, useRef, useState } from "react";
import { Link } from "@tanstack/react-router";
import { ArrowRight, Globe, Check, ChevronDown, Sparkles, MessageCircle, Inbox, LayoutGrid } from "lucide-react";
import logoDark from "@/assets/voxbulk-logo-dark.svg";
import logoLight from "@/assets/voxbulk-logo-light.svg";
import { useAuthModal } from "@/components/AuthModal";
import { useCurrency, MARKETS } from "@/components/CurrencyContext";
import { CookieConsentBanner, openCookiePreferences } from "@/components/CookieConsentBanner";

const productLinks = [
  { label: "Recruitment Automation", to: "/recruitment", desc: "AI screening, scheduling & voice interviews", Icon: Sparkles, tone: "blue" as const },
  { label: "WhatsApp Surveys", to: "/surveys", desc: "WhatsApp & AI calling surveys — live dashboard", Icon: MessageCircle, tone: "teal" as const },
  { label: "Customer Feedback", to: "/feedback", desc: "QR feedback, voice notes, 50+ languages", Icon: Inbox, tone: "gold" as const },
];


export function SiteHeader() {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);
  const auth = useAuthModal();

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 40);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const headerStyle = scrolled
    ? { backgroundColor: "rgba(10,22,40,0.92)", backdropFilter: "saturate(160%) blur(20px)", WebkitBackdropFilter: "saturate(160%) blur(20px)" }
    : { backgroundColor: "rgba(255,255,255,0.92)", backdropFilter: "saturate(160%) blur(18px)", WebkitBackdropFilter: "saturate(160%) blur(18px)" };

  const linkColor = scrolled
    ? "text-white/75 hover:text-white hover:bg-white/[0.08]"
    : "text-navy/75 hover:text-navy hover:bg-navy/[0.06]";
  const borderClass = scrolled
    ? "border-white/[0.10] shadow-[0_10px_40px_-12px_rgba(0,0,0,0.55)]"
    : "border-navy/[0.08] shadow-[0_8px_30px_-12px_rgba(10,22,40,0.18)]";

  return (
    <>
      <header
        className={`fixed top-3 inset-x-3 md:inset-x-6 z-50 transition-all duration-300 rounded-xl border ${borderClass}`}
        style={headerStyle}
      >
        <div className="max-w-[1320px] mx-auto h-[64px] md:h-[72px] flex items-center justify-between pl-4 pr-2 md:pl-6 md:pr-3">
          <Link to="/" className="flex items-center">
            <img
              src={scrolled ? logoLight : logoDark}
              alt="VoxBulk Logo"
              width={140}
              height={32}
              fetchPriority="high"
              decoding="async"
              className="h-7 md:h-[32px] w-auto object-contain transition-all"
            />
          </Link>

          <nav className="hidden lg:flex items-center gap-1 absolute left-1/2 -translate-x-1/2">
            <Link
              to="/"
              hash="what-we-do"
              className={`text-[14.5px] font-semibold transition-all px-4 py-2 rounded-lg ${linkColor}`}
            >
              What we do
            </Link>
            <ProductsDropdown linkColor={linkColor} scrolled={scrolled} />
            <Link
              to="/pricing"
              className={`text-[14.5px] font-semibold transition-all px-4 py-2 rounded-lg ${linkColor}`}
            >
              Pricing
            </Link>
            <Link
              to="/contact"
              className={`text-[14.5px] font-semibold transition-all px-4 py-2 rounded-lg ${linkColor}`}
            >
              Contact
            </Link>
          </nav>

          <div className="hidden md:flex items-center gap-2.5">
            <button
              onClick={auth.open}
              className={`inline-flex items-center gap-1.5 h-9 px-3.5 rounded-lg text-[13.5px] font-semibold transition-colors ${
                scrolled
                  ? "text-white/85 hover:text-white hover:bg-white/[0.08]"
                  : "text-navy/80 hover:text-navy hover:bg-navy/[0.06]"
              }`}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4" />
                <polyline points="10 17 15 12 10 7" />
                <line x1="15" y1="12" x2="3" y2="12" />
              </svg>
              Sign in
            </button>
            <span className={`h-6 w-px ${scrolled ? "bg-white/15" : "bg-navy/15"}`} aria-hidden />
            <Link
              to="/contact"
              className="inline-flex items-center justify-center gap-1.5 rounded-lg px-4 h-9 text-[13.5px] font-semibold text-white transition-all"
              style={{ background: "linear-gradient(180deg, #2A82EB 0%, #1E6FD9 100%)", boxShadow: "0 1px 0 rgba(255,255,255,0.18) inset, 0 8px 22px -8px rgba(30,111,217,0.55)" }}
            >
              Get Started <ArrowRight size={14} />
            </Link>
          </div>

          <button className={`md:hidden p-2 ${scrolled ? "text-white" : "text-navy"}`} aria-label="Open menu" onClick={() => setOpen(true)}>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="4" y1="7" x2="20" y2="7" />
              <line x1="4" y1="12" x2="20" y2="12" />
              <line x1="4" y1="17" x2="20" y2="17" />
            </svg>
          </button>
        </div>
      </header>


      {open && (
        <div className="fixed inset-0 z-[60] bg-white md:hidden flex flex-col">
          <div className="flex items-center justify-between px-5 h-[68px] border-b border-border">
            <img src={logoDark} alt="VoxBulk Logo" className="h-7 w-auto" />
            <button onClick={() => setOpen(false)} aria-label="Close menu" className="p-2 text-heading">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="6" y1="6" x2="18" y2="18" />
                <line x1="18" y1="6" x2="6" y2="18" />
              </svg>
            </button>
          </div>
          <div className="flex-1 px-5 py-4 overflow-y-auto">
            <div className="text-[11px] font-bold uppercase tracking-[0.14em] text-muted-text mt-2 mb-1">Services</div>
            {productLinks.map((l) => (
              <Link key={l.to} to={l.to} onClick={() => setOpen(false)}
                className="flex items-center justify-between h-14 border-b border-border text-[16px] font-medium text-heading">
                {l.label}
                <ArrowRight size={18} className="text-muted-text" />
              </Link>
            ))}
            <Link to="/pricing" onClick={() => setOpen(false)} className="flex items-center justify-between h-14 border-b border-border text-[17px] font-medium text-heading">
              Pricing <ArrowRight size={18} className="text-muted-text" />
            </Link>
            <Link to="/contact" onClick={() => setOpen(false)} className="flex items-center justify-between h-14 border-b border-border text-[17px] font-medium text-heading">
              Contact <ArrowRight size={18} className="text-muted-text" />
            </Link>
            <button onClick={() => { setOpen(false); auth.open(); }} className="flex items-center h-14 text-[17px] font-medium text-body w-full text-left">Sign in</button>
          </div>
          <div className="p-5 border-t border-border">
            <Link to="/contact" onClick={() => setOpen(false)} className="btn-primary w-full">
              Get Started <ArrowRight size={16} />
            </Link>
          </div>
        </div>
      )}
    </>
  );
}

function ProductsDropdown({ linkColor, scrolled }: { linkColor: string; scrolled: boolean }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);
  return (
    <div ref={ref} className="relative" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      <button
        onClick={() => setOpen((v) => !v)}
        className={`inline-flex items-center gap-1.5 text-[14.5px] font-semibold transition-all px-4 py-2 rounded-lg ${linkColor}`}
      >
        <LayoutGrid size={14} className="opacity-80" />
        Services
        <ChevronDown size={14} className={`transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className={`absolute top-full left-1/2 -translate-x-1/2 pt-2 w-[360px]`}>
          <div className={`rounded-xl border ${scrolled ? "border-white/10 bg-[#0E1A2E]" : "border-navy/10 bg-white"} shadow-[0_20px_50px_-15px_rgba(10,22,40,0.35)] overflow-hidden`}>
            {productLinks.map((p) => {
              const toneBg =
                p.tone === "blue" ? "bg-primary/10 text-primary" :
                p.tone === "teal" ? "bg-teal/15 text-teal" :
                "bg-gold/20 text-[#8a6a1a]";
              return (
                <Link
                  key={p.to}
                  to={p.to}
                  onClick={() => setOpen(false)}
                  className={`flex items-start gap-3 px-4 py-3 transition-colors ${scrolled ? "hover:bg-white/[0.06]" : "hover:bg-navy/[0.04]"}`}
                >
                  <span className={`shrink-0 w-9 h-9 rounded-lg flex items-center justify-center ${toneBg}`}>
                    <p.Icon size={16} />
                  </span>
                  <span className="flex-1 min-w-0">
                    <span className={`block text-[14px] font-semibold ${scrolled ? "text-white" : "text-heading"}`}>{p.label}</span>
                    <span className={`block text-[12px] mt-0.5 ${scrolled ? "text-white/55" : "text-muted-text"}`}>{p.desc}</span>
                  </span>
                </Link>
              );
            })}
            <Link
              to="/pricing"
              onClick={() => setOpen(false)}
              className={`flex items-center justify-between px-4 py-3 border-t ${scrolled ? "border-white/10 bg-white/[0.03] text-white/80 hover:text-white" : "border-border bg-beige/60 text-heading hover:bg-beige"} text-[13px] font-semibold transition-colors`}
            >
              View pricing & plans <ArrowRight size={13} />
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}


const footerCols: Array<{ title: string; links: Array<[string, string | null]> }> = [
  { title: "Product", links: [["Recruitment Automation", "/recruitment"], ["WhatsApp Surveys", "/surveys"], ["Customer Feedback", "/feedback"], ["Pricing", "/pricing"]] },
  { title: "Resources", links: [["Blog", "/blog"], ["News", "/news"]] },
  { title: "Company", links: [["Legal & policies", "/legal-policies"], ["Contact us", "/contact"]] },
];



export function SiteFooter() {
  const { currency, setCurrency } = useCurrency();
  const [open, setOpen] = useState(false);
  const active = MARKETS.find((m) => m.code === currency) ?? MARKETS[0];
  return (
    <footer className="bg-dark text-white pt-20 pb-10">
      <div className="max-w-[1180px] mx-auto px-5 md:px-10">
        <div className="grid md:grid-cols-4 grid-cols-2 gap-10">
          <div className="col-span-2 md:col-span-1">
            <img src={logoLight} alt="VoxBulk Logo" width={160} height={36} loading="lazy" decoding="async" className="h-8 w-auto" />
            <p className="mt-4 text-[14px] text-white/60 leading-[1.7] max-w-[260px]">
              Intelligent screening. Instant results.
            </p>
            <p className="mt-5 text-[13px] text-white/40">© 2026 VoxBulk LTD. All rights reserved.</p>

            {/* Country / currency selector */}
            <div className="mt-6 relative inline-block">
              <div className="text-[11px] uppercase tracking-[0.1em] text-white/40 mb-2">Country</div>
              <button
                type="button"
                onClick={() => setOpen((v) => !v)}
                className="inline-flex items-center gap-2 px-3 h-9 rounded-lg border border-white/15 bg-white/[0.04] hover:bg-white/[0.08] text-[13px] text-white/85 transition-colors"
              >
                <Globe size={14} className="text-white/60" />
                <span>{active.flag}</span>
                <span>{active.country}</span>
                <span className="text-white/40">·</span>
                <span className="text-white/70 font-medium">{active.label}</span>
              </button>
              {open && (
                <div className="absolute z-20 mt-2 w-56 rounded-lg border border-white/10 bg-[#0E1A2E] shadow-2xl overflow-hidden">
                  {MARKETS.map((m) => (
                    <button
                      key={m.code}
                      onClick={() => { setCurrency(m.code); setOpen(false); }}
                      className={`w-full flex items-center gap-2 px-3 h-10 text-[13px] text-left hover:bg-white/[0.06] transition-colors ${m.code === currency ? "text-white" : "text-white/75"}`}
                    >
                      <span>{m.flag}</span>
                      <span className="flex-1">{m.country}</span>
                      <span className="text-white/50 text-[12px]">{m.label}</span>
                      {m.code === currency && <Check size={14} className="text-teal" />}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
          {footerCols.map((c) => (
            <div key={c.title}>
              <div className="text-[12px] font-semibold uppercase tracking-[0.1em] text-white mb-4">{c.title}</div>
              <ul className="space-y-2.5">
                {c.links.map(([label, href]) => (
                  <li key={label}>
                    {!href ? (
                      <span className="text-[14px] text-white/30">{label}</span>
                    ) : href.startsWith("/") && !href.startsWith("/#") ? (
                      <Link to={href} className="text-[14px] text-white/60 hover:text-white transition-colors">{label}</Link>
                    ) : (
                      <a href={href} className="text-[14px] text-white/60 hover:text-white transition-colors">{label}</a>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="my-10 h-px bg-white/10" />
        <div className="flex flex-wrap items-center justify-between gap-3 text-[12px] text-white/40">
          <div>VoxBulk LTD · Registered in England &amp; Wales</div>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <Link to="/gdpr" className="hover:text-white/70 transition-colors">GDPR</Link>
            <span aria-hidden>·</span>
            <Link to="/privacy" className="hover:text-white/70 transition-colors">Privacy</Link>
            <span aria-hidden>·</span>
            <Link to="/cookies" className="hover:text-white/70 transition-colors">Cookies</Link>
            <span aria-hidden>·</span>
            <button
              type="button"
              onClick={() => openCookiePreferences()}
              className="hover:text-white/70 transition-colors"
            >
              Cookie settings
            </button>
          </div>
        </div>
      </div>
      <CookieConsentBanner />
    </footer>
  );
}

export function PageShell({ title, eyebrow, children }: { title: string; eyebrow?: string; children?: React.ReactNode }) {
  return (
    <div className="bg-background text-body antialiased min-h-screen flex flex-col">
      <SiteHeader />
      <main className="flex-1 pt-[100px] md:pt-[120px] pb-24">
        <div className="max-w-[860px] mx-auto px-5 md:px-10">
          {eyebrow && <span className="eyebrow">{eyebrow}</span>}
          <h1 className="mt-3 text-[34px] md:text-[52px] font-bold tracking-[-0.03em] text-heading leading-[1.05]">{title}</h1>
          <div className="mt-10 prose prose-slate max-w-none text-body leading-[1.75]">
            {children ?? (
              <p className="text-muted-text italic">
                Content coming soon. This page is reserved for {title}. Replace this placeholder with your final copy.
              </p>
            )}
          </div>
        </div>
      </main>
      <SiteFooter />
    </div>
  );
}
