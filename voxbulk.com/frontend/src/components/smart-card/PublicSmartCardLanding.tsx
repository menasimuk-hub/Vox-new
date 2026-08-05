import * as React from "react";

import { SmartCardWebSession } from "@/components/smart-card/SmartCardWebSession";

const API = (import.meta as any).env?.VITE_API_URL || "https://api.voxbulk.com";

const INK = "#eaf2ff";
const SUB = "rgba(234,242,255,0.6)";
const CARD_BG = "rgba(255,255,255,0.06)";
const BORDER = "rgba(234,242,255,0.14)";

type SocialLinks = {
  x?: string;
  instagram?: string;
  facebook?: string;
  tiktok?: string;
  linkedin?: string;
  [key: string]: string | undefined;
};

type CardMeta = {
  status: string;
  message?: string;
  renew_url?: string;
  preview_tests_remaining?: number | null;
  whatsapp_url?: string | null;
  feedback_whatsapp_url?: string | null;
  representative?: {
    name?: string;
    email?: string;
    website?: string;
    mobile?: string;
    landline?: string;
    job_title?: string | null;
    social_links?: SocialLinks | null;
  };
  company?: {
    name?: string;
    website?: string;
    description?: string;
    tagline?: string | null;
    location?: string | null;
  };
};

type Phase = "card" | "web" | "done" | "blocked";

function Art() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      <div
        className="animate-float-blob absolute -left-28 -top-24 h-96 w-96 rounded-full blur-3xl"
        style={{ background: "rgba(99,102,241,0.18)" }}
      />
      <div
        className="animate-float-blob-2 absolute -right-24 bottom-0 h-96 w-96 rounded-full blur-3xl"
        style={{ background: "rgba(56,189,248,0.14)" }}
      />
      <svg className="absolute inset-0 h-full w-full opacity-[0.06]" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <pattern id="sc-grid" width="38" height="38" patternUnits="userSpaceOnUse">
            <path d="M 38 0 L 0 0 0 38" fill="none" stroke={INK} strokeWidth="0.6" />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#sc-grid)" />
      </svg>
      <svg className="animate-orbit-slow absolute -right-16 top-24 h-64 w-64 opacity-25" viewBox="0 0 200 200" fill="none">
        <circle cx="100" cy="100" r="70" stroke="#38bdf8" strokeWidth="0.7" strokeDasharray="4 8" />
        <circle cx="100" cy="30" r="3.5" fill="#a78bfa" />
      </svg>
      <svg className="animate-orbit-rev absolute -left-20 bottom-16 h-56 w-56 opacity-20" viewBox="0 0 200 200" fill="none">
        <circle cx="100" cy="100" r="80" stroke="#a78bfa" strokeWidth="0.7" strokeDasharray="3 10" />
        <circle cx="180" cy="100" r="3" fill="#38bdf8" />
      </svg>
    </div>
  );
}

function Action({
  href,
  label,
  sub,
  icon,
  tint,
  glow,
  delay,
}: {
  href: string;
  label: string;
  sub: string;
  icon: React.ReactNode;
  tint: string;
  glow: string;
  delay: string;
}) {
  const external = href.startsWith("http");
  return (
    <a
      href={href}
      target={external ? "_blank" : undefined}
      rel={external ? "noreferrer" : undefined}
      className="animate-rise group relative flex items-center gap-4 overflow-hidden rounded-2xl px-4 py-3.5 transition-all duration-300 hover:-translate-y-0.5 active:scale-[0.98]"
      style={{
        background: CARD_BG,
        border: `1px solid ${BORDER}`,
        animationDelay: delay,
        backdropFilter: "blur(8px)",
      }}
    >
      <span
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-300 group-hover:opacity-100"
        style={{ background: `linear-gradient(100deg, ${tint}, transparent 65%)` }}
      />
      <span
        className="relative flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl transition-all duration-300 group-hover:scale-110 group-hover:rotate-[-4deg]"
        style={{
          background: `linear-gradient(140deg, ${tint}, rgba(255,255,255,0.04))`,
          border: `1px solid ${glow}`,
          color: INK,
          boxShadow: `0 8px 22px -12px ${glow}`,
        }}
      >
        <span
          aria-hidden
          className="absolute inset-0 rounded-2xl opacity-0 blur-md transition-opacity duration-300 group-hover:opacity-70"
          style={{ background: glow }}
        />
        <span className="relative">{icon}</span>
      </span>
      <span className="relative min-w-0 flex-1">
        <span className="block text-[15px] font-semibold" style={{ color: INK }}>
          {label}
        </span>
        <span className="block truncate text-[12px]" style={{ color: SUB }}>
          {sub}
        </span>
      </span>
      <svg
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill="none"
        className="relative transition-transform duration-300 group-hover:translate-x-1"
        style={{ color: SUB }}
      >
        <path d="M9 6l6 6-6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </a>
  );
}

function ensureHttp(url: string): string {
  const t = url.trim();
  if (!t) return t;
  if (/^https?:\/\//i.test(t)) return t;
  return `https://${t}`;
}

const SOCIAL_META: Record<string, { label: string; char: string }> = {
  instagram: { label: "Instagram", char: "◎" },
  linkedin: { label: "LinkedIn", char: "in" },
  x: { label: "X", char: "𝕏" },
  facebook: { label: "Facebook", char: "f" },
  tiktok: { label: "TikTok", char: "♪" },
};

export function PublicSmartCardLanding({ token }: { token: string }) {
  const [meta, setMeta] = React.useState<CardMeta | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [phase, setPhase] = React.useState<Phase>("card");
  const [pickerOpen, setPickerOpen] = React.useState(false);
  const [saved, setSaved] = React.useState(false);
  const [doneMsg, setDoneMsg] = React.useState("Thank you");
  const [blockMessage, setBlockMessage] = React.useState<string | undefined>();
  const [webRunId, setWebRunId] = React.useState(0);

  React.useEffect(() => {
    void (async () => {
      try {
        const res = await fetch(`${API}/public/smart-card/${encodeURIComponent(token)}`);
        const data = await res.json();
        if (!res.ok) throw new Error(typeof data?.detail === "string" ? data.detail : "Not found");
        setMeta(data);
        if (data.status === "expired" || data.status === "preview_exhausted") {
          setPhase("blocked");
        }
      } catch (e: any) {
        setError(e?.message || "Failed to load");
      }
    })();
  }, [token]);

  const rep = meta?.representative;
  const company = meta?.company;
  const personName = rep?.name || "Representative";
  const companyName = company?.name || "Company";
  const jobTitle = (rep?.job_title || "").trim();
  const tagline = (company?.tagline || company?.description || "").trim();
  const location = (company?.location || "").trim();
  const phone = (rep?.mobile || rep?.landline || "").trim();
  const email = (rep?.email || "").trim();
  const website = (rep?.website || company?.website || "").trim();
  const socials = rep?.social_links || {};

  const saveContact = () => {
    const vcard = [
      "BEGIN:VCARD",
      "VERSION:3.0",
      `FN:${personName}`,
      `ORG:${companyName}`,
      ...(jobTitle ? [`TITLE:${jobTitle}`] : []),
      ...(phone ? [`TEL;TYPE=CELL:${phone}`] : []),
      ...(email ? [`EMAIL:${email}`] : []),
      ...(website ? [`URL:${ensureHttp(website)}`] : []),
      ...(location ? [`ADR;TYPE=WORK:;;${location};;;;`] : []),
      "END:VCARD",
    ].join("\n");
    const blob = new Blob([vcard], { type: "text/vcard" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${(personName || "contact").replace(/\s+/g, "-").toLowerCase()}.vcf`;
    a.click();
    URL.revokeObjectURL(url);
    setSaved(true);
    setTimeout(() => setSaved(false), 2500);
  };

  const share = async () => {
    if (typeof navigator !== "undefined" && navigator.share) {
      try {
        await navigator.share({ title: companyName, text: personName, url: window.location.href });
      } catch {
        /* dismissed */
      }
    } else if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
      try {
        await navigator.clipboard.writeText(window.location.href);
        setSaved(true);
        setTimeout(() => setSaved(false), 2000);
      } catch {
        /* ignore */
      }
    }
  };

  const startWeb = () => {
    setPickerOpen(false);
    setError(null);
    setWebRunId((n) => n + 1);
    setPhase("web");
  };

  if (error && !meta) {
    return (
      <main className="bg-smartcard-gradient relative flex min-h-dvh items-center justify-center p-6">
        <p className="text-rose-300">{error}</p>
      </main>
    );
  }

  if (!meta) {
    return (
      <main className="bg-smartcard-gradient relative flex min-h-dvh items-center justify-center p-6">
        <p style={{ color: SUB }}>Loading…</p>
      </main>
    );
  }

  if (phase === "blocked") {
    return (
      <main className="bg-smartcard-gradient relative min-h-dvh overflow-hidden">
        <Art />
        <div className="relative mx-auto flex min-h-dvh max-w-md flex-col justify-center px-5 py-10 text-center">
          <h1 className="text-[22px] font-semibold" style={{ color: INK }}>
            {companyName}
          </h1>
          <p className="mt-3 text-[14px] leading-relaxed" style={{ color: SUB }}>
            {blockMessage || meta.message || "This Smart Card QR is unavailable."}
          </p>
          {meta.renew_url ? (
            <a
              href={meta.renew_url}
              target="_blank"
              rel="noreferrer"
              className="mt-6 inline-flex items-center justify-center rounded-2xl px-4 py-3 text-[14px] font-semibold"
              style={{
                background: "linear-gradient(135deg,#38bdf8,#6366f1)",
                color: "#06121f",
              }}
            >
              Renew package
            </a>
          ) : null}
        </div>
      </main>
    );
  }

  if (phase === "done") {
    return (
      <main className="bg-smartcard-gradient relative min-h-dvh overflow-hidden">
        <Art />
        <div className="relative mx-auto flex min-h-dvh max-w-md flex-col items-center justify-center px-5 text-center">
          <div
            className="flex h-16 w-16 items-center justify-center rounded-2xl text-2xl"
            style={{ background: "linear-gradient(135deg,#38bdf8,#6366f1)", color: "#06121f" }}
          >
            ✓
          </div>
          <h1 className="mt-5 text-[24px] font-semibold" style={{ color: INK }}>
            Thank you
          </h1>
          <p className="mt-2 text-[14px] leading-relaxed" style={{ color: SUB }}>
            {doneMsg}
          </p>
          <button
            type="button"
            onClick={() => setPhase("card")}
            className="mt-8 rounded-2xl px-4 py-2.5 text-[13px] font-medium"
            style={{ background: CARD_BG, border: `1px solid ${BORDER}`, color: INK }}
          >
            Back to card
          </button>
        </div>
      </main>
    );
  }

  if (phase === "web") {
    return (
      <SmartCardWebSession
        key={webRunId}
        token={token}
        companyName={companyName}
        onDone={(msg) => {
          setDoneMsg(msg);
          setPhase("done");
        }}
        onBlocked={(status, message) => {
          setBlockMessage(
            message ||
              (status === "preview_exhausted"
                ? "Preview tests are used up (15)."
                : "This Smart Card QR is unavailable."),
          );
          setMeta((m) => (m ? { ...m, status } : m));
          setPhase("blocked");
        }}
        onBack={() => setPhase("card")}
      />
    );
  }

  /* Digital card landing */
  const socialEntries = Object.entries(socials).filter(([, v]) => (v || "").trim());

  return (
    <main className="bg-smartcard-gradient relative min-h-dvh w-full overflow-hidden">
      <Art />
      <div className="relative mx-auto flex min-h-dvh w-full max-w-md flex-col px-5 pb-8 pt-9">
        <section className="animate-rise flex flex-col items-center text-center">
          <div
            className="relative flex h-20 w-20 items-center justify-center rounded-2xl text-2xl font-semibold"
            style={{
              background: "linear-gradient(135deg,#38bdf8,#6366f1)",
              color: "#06121f",
              boxShadow: "0 14px 40px -14px rgba(56,189,248,0.7)",
            }}
          >
            <span className="animate-pulse-ring absolute inset-0 rounded-2xl" style={{ border: "1px solid rgba(56,189,248,0.45)" }} />
            {(personName || "V").slice(0, 1).toUpperCase()}
          </div>
          <h1 className="mt-4 text-[26px] font-semibold leading-tight" style={{ color: INK }}>
            {personName}
          </h1>
          <p className="mt-1 text-[13px] font-medium tracking-wide" style={{ color: "#7dd3fc" }}>
            {[jobTitle, companyName].filter(Boolean).join(" · ")}
          </p>
          {tagline ? (
            <p className="mt-2 max-w-[19rem] text-[13px] leading-relaxed" style={{ color: SUB }}>
              {tagline}
            </p>
          ) : null}
          {meta.status === "preview" && typeof meta.preview_tests_remaining === "number" ? (
            <p className="mt-3 rounded-full px-3 py-1 text-[11px] font-medium" style={{ background: "rgba(251,191,36,0.15)", color: "#fbbf24", border: "1px solid rgba(251,191,36,0.35)" }}>
              {meta.preview_tests_remaining} of 15 free scans left
            </p>
          ) : null}
        </section>

        <div className="animate-rise mt-6 grid grid-cols-2 gap-3" style={{ animationDelay: "80ms" }}>
          <button
            type="button"
            onClick={saveContact}
            className="rounded-2xl px-4 py-3 text-[14px] font-semibold transition-transform active:scale-[0.98]"
            style={{
              background: "linear-gradient(135deg,#38bdf8,#6366f1)",
              color: "#06121f",
              boxShadow: "0 10px 28px -12px rgba(99,102,241,0.8)",
            }}
          >
            {saved ? "Saved ✓" : "Save contact"}
          </button>
          <button
            type="button"
            onClick={() => void share()}
            className="rounded-2xl px-4 py-3 text-[14px] font-semibold transition-transform active:scale-[0.98]"
            style={{ background: CARD_BG, border: `1px solid ${BORDER}`, color: INK }}
          >
            Share card
          </button>
        </div>

        <nav className="mt-4 flex flex-col gap-2.5">
          {meta.whatsapp_url ? (
            <Action
              href={meta.whatsapp_url}
              label="WhatsApp"
              sub="Message on WhatsApp"
              tint="rgba(37,211,102,0.18)"
              glow="rgba(37,211,102,0.55)"
              delay="120ms"
              icon={
                <svg width="19" height="19" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12.04 2A9.9 9.9 0 002.1 11.9c0 1.75.46 3.45 1.32 4.95L2 22l5.3-1.38a9.9 9.9 0 0014.74-8.72A9.9 9.9 0 0012.04 2zm5.8 14.05c-.24.68-1.4 1.3-1.94 1.34-.5.04-1.12.06-1.81-.11a15.5 15.5 0 01-6.6-4.6c-.44-.58-1.17-1.68-1.17-3.2 0-1.52.8-2.27 1.08-2.58.28-.31.6-.39.8-.39l.58.01c.19 0 .44-.07.68.52.25.6.85 2.08.93 2.23.07.15.12.33.02.53-.1.2-.15.32-.3.5l-.44.51c-.15.15-.3.32-.13.62.17.3.76 1.25 1.63 2.03 1.12 1 2.07 1.31 2.37 1.46.3.15.47.13.65-.08.17-.2.75-.87.95-1.17.2-.3.4-.25.67-.15.27.1 1.72.81 2.02.96.3.15.5.22.57.35.07.13.07.74-.17 1.42z" />
                </svg>
              }
            />
          ) : null}
          {phone ? (
            <Action
              href={`tel:${phone}`}
              label="Call"
              sub={phone}
              tint="rgba(56,189,248,0.18)"
              glow="rgba(56,189,248,0.55)"
              delay="170ms"
              icon={
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                  <path d="M6.5 3h3l1.5 4-2 1.5a12 12 0 006.5 6.5l1.5-2 4 1.5v3a2 2 0 01-2.2 2A17 17 0 014.5 5.2 2 2 0 016.5 3z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
                </svg>
              }
            />
          ) : null}
          {email ? (
            <Action
              href={`mailto:${email}`}
              label="Email"
              sub={email}
              tint="rgba(167,139,250,0.18)"
              glow="rgba(167,139,250,0.55)"
              delay="220ms"
              icon={
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                  <rect x="3" y="5" width="18" height="14" rx="2.5" stroke="currentColor" strokeWidth="1.6" />
                  <path d="M4 7l8 6 8-6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
                </svg>
              }
            />
          ) : null}
          {website ? (
            <Action
              href={ensureHttp(website)}
              label="Website"
              sub={website.replace(/^https?:\/\//i, "")}
              tint="rgba(99,102,241,0.18)"
              glow="rgba(99,102,241,0.55)"
              delay="270ms"
              icon={
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                  <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.6" />
                  <path d="M3 12h18M12 3a15 15 0 010 18M12 3a15 15 0 000 18" stroke="currentColor" strokeWidth="1.4" />
                </svg>
              }
            />
          ) : null}
          {location ? (
            <Action
              href={`https://maps.google.com/?q=${encodeURIComponent(location)}`}
              label="Location"
              sub={location}
              tint="rgba(244,114,182,0.16)"
              glow="rgba(244,114,182,0.5)"
              delay="320ms"
              icon={
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                  <path d="M12 21s7-5.5 7-11a7 7 0 10-14 0c0 5.5 7 11 7 11z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
                  <circle cx="12" cy="10" r="2.4" stroke="currentColor" strokeWidth="1.6" />
                </svg>
              }
            />
          ) : null}
        </nav>

        {socialEntries.length > 0 ? (
          <div className="animate-rise mt-5 flex flex-wrap items-center justify-center gap-3" style={{ animationDelay: "360ms" }}>
            {socialEntries.map(([key, href]) => {
              const metaS = SOCIAL_META[key] || { label: key, char: key.slice(0, 1).toUpperCase() };
              return (
                <a
                  key={key}
                  href={ensureHttp(String(href))}
                  target="_blank"
                  rel="noreferrer"
                  aria-label={metaS.label}
                  className="flex h-11 w-11 items-center justify-center rounded-full text-[13px] font-semibold transition-all duration-300 hover:-translate-y-0.5 active:scale-95"
                  style={{ background: CARD_BG, border: `1px solid ${BORDER}`, color: INK }}
                >
                  {metaS.char}
                </a>
              );
            })}
          </div>
        ) : null}

        <button
          type="button"
          onClick={() => setPickerOpen(true)}
          className="animate-rise group mt-5 flex w-full items-center justify-between rounded-2xl px-4 py-3.5 text-left transition-all duration-300 hover:-translate-y-0.5 active:scale-[0.98]"
          style={{
            background: "rgba(56,189,248,0.08)",
            border: "1px solid rgba(56,189,248,0.28)",
            animationDelay: "400ms",
          }}
        >
          <span>
            <span className="block text-[14px] font-semibold" style={{ color: INK }}>
              Leave us feedback
            </span>
            <span className="block text-[12px]" style={{ color: SUB }}>
              60 seconds — it really helps us
            </span>
          </span>
          <span className="text-lg transition-transform duration-300 group-hover:scale-110">💬</span>
        </button>

        {error ? <p className="mt-3 text-center text-[13px] text-rose-300">{error}</p> : null}

        {pickerOpen ? (
          <div className="fixed inset-0 z-50 flex items-end justify-center px-4 pb-5 sm:items-center sm:pb-0">
            <button
              type="button"
              aria-label="Close"
              onClick={() => setPickerOpen(false)}
              className="absolute inset-0"
              style={{ background: "rgba(3,10,20,0.72)", backdropFilter: "blur(6px)" }}
            />
            <div
              className="animate-rise relative w-full max-w-md rounded-3xl p-5"
              style={{
                background: "linear-gradient(160deg, rgba(18,28,46,0.96), rgba(10,16,28,0.96))",
                border: `1px solid ${BORDER}`,
                boxShadow: "0 30px 70px -30px rgba(56,189,248,0.5)",
              }}
            >
              <div className="mx-auto mb-4 h-1 w-10 rounded-full" style={{ background: BORDER }} />
              <h2 className="text-center text-[18px] font-semibold" style={{ color: INK }}>
                How would you like to share it?
              </h2>
              <p className="mt-1 text-center text-[12.5px]" style={{ color: SUB }}>
                Pick whichever is easier for you.
              </p>
              <div className="mt-5 flex flex-col gap-3">
                {meta.feedback_whatsapp_url || meta.whatsapp_url ? (
                  <a
                    href={meta.feedback_whatsapp_url || meta.whatsapp_url || "#"}
                    target="_blank"
                    rel="noreferrer"
                    onClick={() => setPickerOpen(false)}
                    className="group flex items-center gap-4 rounded-2xl px-4 py-3.5 transition-all duration-300 hover:-translate-y-0.5 active:scale-[0.98]"
                    style={{
                      background: "linear-gradient(120deg, rgba(37,211,102,0.16), rgba(255,255,255,0.03))",
                      border: "1px solid rgba(37,211,102,0.35)",
                    }}
                  >
                    <span
                      className="flex h-11 w-11 items-center justify-center rounded-2xl"
                      style={{ background: "rgba(37,211,102,0.22)", color: INK }}
                    >
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                        <path d="M12.04 2A9.9 9.9 0 002.1 11.9c0 1.75.46 3.45 1.32 4.95L2 22l5.3-1.38a9.9 9.9 0 0014.74-8.72A9.9 9.9 0 0012.04 2zm5.8 14.05c-.24.68-1.4 1.3-1.94 1.34-.5.04-1.12.06-1.81-.11a15.5 15.5 0 01-6.6-4.6c-.44-.58-1.17-1.68-1.17-3.2 0-1.52.8-2.27 1.08-2.58.28-.31.6-.39.8-.39l.58.01c.19 0 .44-.07.68.52.25.6.85 2.08.93 2.23.07.15.12.33.02.53-.1.2-.15.32-.3.5l-.44.51c-.15.15-.3.32-.13.62.17.3.76 1.25 1.63 2.03 1.12 1 2.07 1.31 2.37 1.46.3.15.47.13.65-.08.17-.2.75-.87.95-1.17.2-.3.4-.25.67-.15.27.1 1.72.81 2.02.96.3.15.5.22.57.35.07.13.07.74-.17 1.42z" />
                      </svg>
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-[15px] font-semibold" style={{ color: INK }}>
                        Send on WhatsApp
                      </span>
                      <span className="block truncate text-[12px]" style={{ color: SUB }}>
                        Chat with us directly
                      </span>
                    </span>
                  </a>
                ) : null}
                <button
                  type="button"
                  onClick={() => startWeb()}
                  className="group flex items-center gap-4 rounded-2xl px-4 py-3.5 text-left transition-all duration-300 hover:-translate-y-0.5 active:scale-[0.98]"
                  style={{
                    background: "linear-gradient(120deg, rgba(56,189,248,0.16), rgba(255,255,255,0.03))",
                    border: "1px solid rgba(56,189,248,0.35)",
                  }}
                >
                  <span
                    className="flex h-11 w-11 items-center justify-center rounded-2xl"
                    style={{ background: "rgba(56,189,248,0.22)", color: INK }}
                  >
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.6" />
                      <path d="M3 12h18M12 3a15 15 0 010 18M12 3a15 15 0 000 18" stroke="currentColor" strokeWidth="1.4" />
                    </svg>
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-[15px] font-semibold" style={{ color: INK }}>
                      Web survey
                    </span>
                    <span className="block truncate text-[12px]" style={{ color: SUB }}>
                      Card photo · questions · voice note
                    </span>
                  </span>
                </button>
              </div>
              <button
                type="button"
                onClick={() => setPickerOpen(false)}
                className="mt-4 w-full rounded-2xl py-2.5 text-[13px] font-medium"
                style={{ background: CARD_BG, border: `1px solid ${BORDER}`, color: SUB }}
              >
                Maybe later
              </button>
            </div>
          </div>
        ) : null}

        <footer className="mt-auto pt-7 text-center text-[11px]" style={{ color: "rgba(234,242,255,0.4)" }}>
          Smart card by {companyName}
        </footer>
      </div>
    </main>
  );
}
