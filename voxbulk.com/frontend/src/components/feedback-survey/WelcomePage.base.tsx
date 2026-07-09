import { createFileRoute, Link } from "@tanstack/react-router";
import iconAsset from "@/assets/icon-dark.png.asset.json";

const COMPANY_NAME = "{{company_name}}";
const WHATSAPP_NUMBER = "{{whatsapp_number}}";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "We'd love your feedback" },
      { name: "description", content: "Tell us how it went — voice or quick reply, in any language." },
    ],
  }),
  component: Welcome,
});

function Welcome() {
  return (
    <main className="relative h-[100svh] overflow-hidden bg-warm-gradient">
      {/* Floating background shapes */}
      <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="animate-float-blob absolute -left-24 top-10 h-72 w-72 rounded-full bg-gold/15 blur-3xl" />
        <div className="animate-float-blob-2 absolute -right-20 bottom-10 h-80 w-80 rounded-full bg-accent/30 blur-3xl" />
        {/* subtle orbit ring */}
        <svg className="animate-orbit-slow absolute -right-20 top-24 h-64 w-64 opacity-10" viewBox="0 0 200 200" fill="none">
          <circle cx="100" cy="100" r="80" stroke="currentColor" strokeDasharray="2 8" className="text-foreground" />
        </svg>
      </div>

      <div className="relative mx-auto flex h-[100svh] w-full max-w-md flex-col px-5 pb-5 pt-4 sm:max-w-lg sm:px-6 sm:pt-6">
        {/* Brand — logo + company name */}
        <header className="animate-rise flex flex-col items-center gap-2 text-center" style={{ animationDelay: "60ms" }}>
          <img
            src={iconAsset.url}
            alt=""
            className="animate-tilt-hover h-10 w-10 rounded-xl bg-card p-1 shadow-lift ring-1 ring-border"
          />
          <span className="font-display text-[15px] tracking-tight text-foreground">{COMPANY_NAME}</span>
        </header>

        {/* Heading */}
        <div className="mt-5 sm:mt-8">
          <h1 className="animate-rise mt-2 font-display text-[34px] leading-[1.05] text-foreground sm:text-5xl" style={{ animationDelay: "300ms" }}>
            We'd love your<br />
            <span className="italic text-foreground/90">feedback</span>
            <span className="text-gold">.</span>
          </h1>
          <p className="animate-rise mt-3 max-w-sm text-[13.5px] leading-relaxed text-muted-foreground" style={{ animationDelay: "400ms" }}>
            Two minutes. Voice or tap, in any language — your honest words help us get better.
          </p>
        </div>

        {/* Info pill */}
        <div className="animate-rise mt-4" style={{ animationDelay: "480ms" }}>
          <div className="inline-flex items-start gap-2 rounded-full border border-border bg-card/70 px-3 py-1.5 text-[11.5px] leading-snug text-muted-foreground shadow-soft backdrop-blur">
            <span aria-hidden>🌍</span>
            <span>WhatsApp = all languages · Web = English only</span>
          </div>
        </div>

        {/* CTAs — free-floating icons, no inner circles */}
        <div className="mt-5 grid gap-3">
          <a
            href={`https://wa.me/${WHATSAPP_NUMBER}`}
            target="_blank"
            rel="noopener noreferrer"
            className="animate-rise group relative overflow-hidden rounded-2xl bg-whatsapp p-4 text-left text-whatsapp-foreground shadow-lift transition-transform active:scale-[0.98] hover:-translate-y-0.5"
            style={{ animationDelay: "560ms" }}
          >
            <div className="flex items-center gap-3.5">
              <span className="animate-float-icon shrink-0 text-whatsapp-foreground drop-shadow-[0_4px_8px_rgba(0,0,0,0.25)]" style={{ animationDelay: "0s" }}>
                <WhatsAppGlyph />
              </span>
              <div className="min-w-0 flex-1">
                <div className="text-[15.5px] font-semibold tracking-tight">Continue on WhatsApp</div>
                <div className="mt-0.5 text-[11.5px] text-whatsapp-foreground/85">💬 Reply in your own language</div>
              </div>
              <ArrowGlyph />
            </div>
            <span aria-hidden className="absolute -right-10 -top-10 h-32 w-32 rounded-full bg-white/10 blur-2xl transition-transform group-hover:scale-125" />
          </a>

          <Link
            to="/survey-temp"
            className="animate-rise group relative overflow-hidden rounded-2xl border border-border bg-card p-4 text-left text-card-foreground shadow-soft transition-transform active:scale-[0.98] hover:-translate-y-0.5"
            style={{ animationDelay: "640ms" }}
          >
            <div className="flex items-center gap-3.5">
              <span className="animate-float-icon shrink-0 text-foreground drop-shadow-[0_4px_10px_rgba(180,140,60,0.35)]" style={{ animationDelay: "0.7s" }}>
                <SparkGlyph />
              </span>
              <div className="min-w-0 flex-1">
                <div className="text-[15.5px] font-semibold tracking-tight">Complete here</div>
                <div className="mt-0.5 text-[11.5px] text-muted-foreground">Quick on-page survey · English</div>
              </div>
              <ArrowGlyph className="text-foreground/60" />
            </div>
            <span aria-hidden className="absolute -left-10 -bottom-10 h-32 w-32 rounded-full bg-gold/40 blur-2xl transition-transform group-hover:scale-125" />
          </Link>
        </div>

        <footer className="animate-rise mt-auto pt-4 text-center text-[10.5px] text-muted-foreground/80" style={{ animationDelay: "780ms" }}>
          Your reply is private and only shared with {COMPANY_NAME}.
        </footer>
      </div>
    </main>
  );
}

function WhatsAppGlyph() {
  return (
    <svg viewBox="0 0 32 32" className="h-9 w-9" fill="currentColor" aria-hidden>
      <path d="M16 3C8.82 3 3 8.82 3 16c0 2.29.6 4.43 1.66 6.29L3 29l6.9-1.62A12.94 12.94 0 0 0 16 29c7.18 0 13-5.82 13-13S23.18 3 16 3Zm7.4 18.46c-.31.87-1.82 1.66-2.5 1.71-.66.05-1.31.27-4.4-.93-3.71-1.45-6.07-5.27-6.25-5.52-.18-.25-1.5-1.99-1.5-3.8 0-1.81.95-2.69 1.28-3.07.34-.37.74-.46.99-.46.25 0 .49 0 .71.01.23.01.53-.09.83.64.31.74 1.05 2.55 1.14 2.73.09.18.15.4.03.65-.12.25-.18.4-.37.61-.18.21-.39.47-.55.63-.18.18-.37.39-.16.74.21.34.94 1.55 2.02 2.5 1.39 1.23 2.56 1.6 2.9 1.78.34.18.55.15.74-.09.21-.25.86-1 1.09-1.34.22-.34.46-.28.77-.17.31.12 1.97.93 2.31 1.1.34.17.56.25.65.39.09.13.09.74-.22 1.61Z" />
    </svg>
  );
}

function SparkGlyph() {
  return (
    <svg viewBox="0 0 24 24" className="h-9 w-9" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M12 2l1.8 5.4L19 9l-5.2 1.6L12 16l-1.8-5.4L5 9l5.2-1.6L12 2z" fill="currentColor" fillOpacity="0.15" />
      <path d="M19 15l.9 2.6L22 18.5l-2.1.9L19 22l-.9-2.6L16 18.5l2.1-.9L19 15z" fill="currentColor" fillOpacity="0.25" />
    </svg>
  );
}

function ArrowGlyph({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={`h-5 w-5 shrink-0 transition-transform group-hover:translate-x-0.5 ${className}`} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M5 12h14M13 5l7 7-7 7" />
    </svg>
  );
}
