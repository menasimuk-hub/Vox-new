import { useEffect, useState } from "react";
import { Link } from "@tanstack/react-router";
import { ArrowRight, Globe, Check } from "lucide-react";
import { BrandLogo } from "@/components/BrandLogo";
import { useAuthModal } from "@/components/AuthModal";
import { useCurrency, MARKETS } from "@/components/CurrencyContext";

const navLinks = [
  { label: "What we do", href: "/#what-we-do" },
  { label: "Services", href: "/#services" },
  { label: "How it works", href: "/#how-it-works" },
  { label: "Pricing", href: "/#pricing" },
  { label: "FAQ", href: "/#faq" },
];

export function SiteHeader() {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);
  const auth = useAuthModal();
  const headerSurface = scrolled ? "dark" : "light";

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
  const iconBtnClass = scrolled
    ? "border-white/[0.12] bg-white/[0.05] text-white/85 hover:text-white hover:bg-white/[0.12]"
    : "border-navy/[0.10] bg-navy/[0.04] text-navy/80 hover:text-navy hover:bg-navy/[0.08]";

  return (
    <>
      <header
        className={`fixed top-3 inset-x-3 md:inset-x-6 z-50 transition-all duration-300 rounded-xl border ${borderClass}`}
        style={headerStyle}
      >
        <div className="max-w-[1320px] mx-auto h-[60px] md:h-[64px] flex items-center justify-between pl-4 pr-2 md:pl-6 md:pr-3">
          <Link to="/" className="flex items-center" aria-label="VoxBulk home">
            <BrandLogo
              surface={headerSurface}
              width={140}
              height={32}
              fetchPriority="high"
              className="h-7 md:h-[30px] w-auto object-contain transition-opacity duration-300"
            />
          </Link>

          <nav className="hidden lg:flex items-center gap-1 absolute left-1/2 -translate-x-1/2">
            {navLinks.map((l) => (
              <a
                key={l.href}
                href={l.href}
                className={`text-[14px] font-medium transition-all px-4 py-2 rounded-full ${linkColor}`}
              >
                {l.label}
              </a>
            ))}
          </nav>

          <div className="hidden md:flex items-center gap-2">
            <button
              onClick={auth.open}
              aria-label="Sign in"
              className={`w-9 h-9 inline-flex items-center justify-center rounded-lg border transition-colors ${iconBtnClass}`}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4" />
                <polyline points="10 17 15 12 10 7" />
                <line x1="15" y1="12" x2="3" y2="12" />
              </svg>
            </button>
            <a
              href="/#demo"
              className="inline-flex items-center justify-center gap-1.5 rounded-lg px-4 h-9 text-[13.5px] font-semibold text-white transition-all btn-cta"
            >
              Get Started
            </a>
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
            <BrandLogo surface="light" className="h-7 w-auto" />
            <button onClick={() => setOpen(false)} aria-label="Close menu" className="p-2 text-heading">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="6" y1="6" x2="18" y2="18" />
                <line x1="18" y1="6" x2="6" y2="18" />
              </svg>
            </button>
          </div>
          <div className="flex-1 px-5 py-4">
            {navLinks.map((l) => (
              <a key={l.href} href={l.href} onClick={() => setOpen(false)}
                className="flex items-center justify-between h-14 border-b border-border text-[17px] font-medium text-heading">
                {l.label}
                <ArrowRight size={18} className="text-muted-text" />
              </a>
            ))}
            <button onClick={() => { setOpen(false); auth.open(); }} className="flex items-center h-14 text-[17px] font-medium text-body w-full text-left">Sign in</button>
          </div>
          <div className="p-5 border-t border-border">
            <a href="/#demo" onClick={() => setOpen(false)} className="btn-primary w-full">
              Book a demo <ArrowRight size={16} />
            </a>
          </div>
        </div>
      )}
    </>
  );
}

const footerCols: Array<{ title: string; links: Array<[string, string | null]> }> = [
  { title: "Product", links: [["What we do", "/#what-we-do"], ["Services", "/#services"], ["How it works", "/#how-it-works"], ["Pricing", "/#pricing"], ["Book a demo", "/#demo"]] },
  { title: "Services", links: [["Recruitment automation", "/#services"], ["WhatsApp surveys", "/#services"], ["Sales agents (soon)", null], ["Customer success (soon)", null]] },
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
            <BrandLogo surface="dark" width={160} height={36} loading="lazy" className="h-8 w-auto" />
            <p className="mt-4 text-[14px] text-white/60 leading-[1.7] max-w-[260px]">
              Intelligent voice &amp; messaging that runs itself.
            </p>
            <p className="mt-5 text-[13px] text-white/40">© 2026 VoxBulk LTD. All rights reserved.</p>

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
                <div className="absolute z-20 mt-2 w-56 rounded-lg border border-white/10 bg-navy-2 shadow-2xl overflow-hidden">
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
          <div>GDPR Compliant · UK / EU data centres</div>
        </div>
      </div>
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
