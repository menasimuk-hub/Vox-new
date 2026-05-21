import { useEffect, useState } from "react";
import { Link } from "@tanstack/react-router";
import { ArrowRight } from "lucide-react";
import logoNormal from "@/assets/logonormal.svg";
import logoLight from "@/assets/logolight.svg";
import { useAuthModal } from "@/components/AuthModal";

const navLinks = [
  { label: "How it works", href: "/#how-it-works" },
  { label: "Features", href: "/#features" },
  { label: "Pricing", href: "/#pricing" },
  { label: "ROI", href: "/#results" },
  { label: "Industries", href: "/#industries" },
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
    ? {
        backgroundColor: "rgba(10,10,15,0.92)",
        backdropFilter: "saturate(160%) blur(20px)",
        WebkitBackdropFilter: "saturate(160%) blur(20px)",
      }
    : {
        backgroundColor: "rgba(10,10,15,0.75)",
        backdropFilter: "saturate(160%) blur(18px)",
        WebkitBackdropFilter: "saturate(160%) blur(18px)",
      };

  const linkColor = "text-white/65 hover:text-white hover:bg-white/[0.06]";
  const borderClass = scrolled
    ? "border-white/[0.10] shadow-[0_10px_40px_-12px_rgba(0,0,0,0.55)]"
    : "border-white/[0.07] shadow-[0_8px_30px_-12px_rgba(0,0,0,0.4)]";

  return (
    <>
      <header
        className={`fixed top-3 inset-x-3 md:inset-x-6 z-50 transition-all duration-300 rounded-full border ${borderClass}`}
        style={headerStyle}
      >
        <div className="max-w-[1320px] mx-auto h-[60px] md:h-[64px] flex items-center justify-between pl-5 pr-2 md:pl-6 md:pr-2.5">
          <Link to="/" className="flex items-center">
            <img src={logoLight} alt="VOXBULK" className="h-7 md:h-[28px] w-auto object-contain" />
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
              className="w-9 h-9 inline-flex items-center justify-center rounded-lg border border-white/[0.10] bg-white/[0.04] text-white/80 hover:text-white hover:bg-white/[0.10] transition-colors"
            >
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4" />
                <polyline points="10 17 15 12 10 7" />
                <line x1="15" y1="12" x2="3" y2="12" />
              </svg>
            </button>
            <a
              href="/#demo"
              className="inline-flex items-center justify-center gap-1.5 rounded-full px-4 h-9 text-[13.5px] font-semibold text-white transition-all"
              style={{
                background: "linear-gradient(180deg, #FB923C 0%, #F97316 100%)",
                boxShadow:
                  "0 1px 0 rgba(255,255,255,0.18) inset, 0 8px 22px -8px rgba(249,115,22,0.55)",
              }}
            >
              Get Started
            </a>
          </div>

          <button
            className="md:hidden p-2 text-white"
            aria-label="Open menu"
            onClick={() => setOpen(true)}
          >
            <svg
              width="22"
              height="22"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
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
            <img src={logoNormal} alt="VOXBULK" className="h-7 w-auto" />
            <button
              onClick={() => setOpen(false)}
              aria-label="Close menu"
              className="p-2 text-heading"
            >
              <svg
                width="24"
                height="24"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <line x1="6" y1="6" x2="18" y2="18" />
                <line x1="18" y1="6" x2="6" y2="18" />
              </svg>
            </button>
          </div>
          <div className="flex-1 px-5 py-4">
            {navLinks.map((l) => (
              <a
                key={l.href}
                href={l.href}
                onClick={() => setOpen(false)}
                className="flex items-center justify-between h-14 border-b border-border text-[17px] font-medium text-heading"
              >
                {l.label}
                <ArrowRight size={18} className="text-muted-text" />
              </a>
            ))}
            <button
              onClick={() => {
                setOpen(false);
                auth.open();
              }}
              className="flex items-center h-14 text-[17px] font-medium text-body w-full text-left"
            >
              Sign in
            </button>
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
  {
    title: "Product",
    links: [
      ["How it works", "/#how-it-works"],
      ["Pricing", "/#pricing"],
      ["ROI calculator", "/#results"],
      ["Book a demo", "/#demo"],
    ],
  },
  {
    title: "Industries",
    links: [
      ["VB Dental", "/#industries"],
      ["VB Opticians (soon)", null],
      ["VB Beauty (soon)", null],
      ["VB Wellness (soon)", null],
    ],
  },
  {
    title: "Legal",
    links: [
      ["Legal & policies", "/legal-policies"],
      ["Contact us", "/contact"],
    ],
  },
];

export function SiteFooter() {
  return (
    <footer className="bg-dark text-white pt-20 pb-10">
      <div className="max-w-[1180px] mx-auto px-5 md:px-10">
        <div className="grid md:grid-cols-4 grid-cols-2 gap-10">
          <div className="col-span-2 md:col-span-1">
            <img src={logoLight} alt="VOXBULK" className="h-8 w-auto" />
            <p className="mt-4 text-[14px] text-white/60 leading-[1.7] max-w-[260px]">
              Intelligent Voice Calls at Scale.
            </p>
            <p className="mt-5 text-[13px] text-white/40">
              © 2026 VOXBULK LTD. All rights reserved.
            </p>
          </div>
          {footerCols.map((c) => (
            <div key={c.title}>
              <div className="text-[12px] font-semibold uppercase tracking-[0.1em] text-white mb-4">
                {c.title}
              </div>
              <ul className="space-y-2.5">
                {c.links.map(([label, href]) => (
                  <li key={label}>
                    {!href ? (
                      <span className="text-[14px] text-white/30">{label}</span>
                    ) : href.startsWith("/") && !href.startsWith("/#") ? (
                      <Link
                        to={href}
                        className="text-[14px] text-white/60 hover:text-white transition-colors"
                      >
                        {label}
                      </Link>
                    ) : (
                      <a
                        href={href}
                        className="text-[14px] text-white/60 hover:text-white transition-colors"
                      >
                        {label}
                      </a>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="my-10 h-px bg-white/10" />
        <div className="flex flex-wrap items-center justify-between gap-3 text-[12px] text-white/40">
          <div>VOXBULK LTD · Registered in England &amp; Wales</div>
          <div>ICO Registered · OFCOM Compliant · GDPR Compliant</div>
        </div>
      </div>
    </footer>
  );
}

export function PageShell({
  title,
  eyebrow,
  children,
}: {
  title: string;
  eyebrow?: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="bg-background text-body antialiased min-h-screen flex flex-col">
      <SiteHeader />
      <main className="flex-1 pt-[100px] md:pt-[120px] pb-24">
        <div className="max-w-[860px] mx-auto px-5 md:px-10">
          {eyebrow && <span className="eyebrow">{eyebrow}</span>}
          <h1 className="mt-3 text-[34px] md:text-[52px] font-bold tracking-[-0.03em] text-heading leading-[1.05]">
            {title}
          </h1>
          <div className="mt-10 prose prose-slate max-w-none text-body leading-[1.75]">
            {children ?? (
              <p className="text-muted-text italic">
                Content coming soon. This page is reserved for {title}. Replace this placeholder
                with your final copy.
              </p>
            )}
          </div>
        </div>
      </main>
      <SiteFooter />
    </div>
  );
}
