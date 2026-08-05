import * as React from "react";

import { SmartCardWebSession } from "@/components/smart-card/SmartCardWebSession";

const API = (import.meta as any).env?.VITE_API_URL || "https://api.voxbulk.com";

const INK = "#eaf2ff";
const SUB = "rgba(234,242,255,0.62)";
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
    photo_url?: string | null;
  };
  company?: {
    name?: string;
    website?: string;
    description?: string;
    tagline?: string | null;
    location?: string | null;
    logo_url?: string | null;
  };
};

type Phase = "card" | "web" | "done" | "blocked";

type AspectKind = "square" | "landscape" | "portrait";

function Art() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      <div
        className="animate-float-blob absolute -left-28 -top-24 h-96 w-96 rounded-full blur-3xl"
        style={{ background: "rgba(99,102,241,0.16)" }}
      />
      <div
        className="animate-float-blob-2 absolute -right-24 bottom-0 h-96 w-96 rounded-full blur-3xl"
        style={{ background: "rgba(56,189,248,0.12)" }}
      />
      <svg className="absolute inset-0 h-full w-full opacity-[0.05]" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <pattern id="sc-grid" width="38" height="38" patternUnits="userSpaceOnUse">
            <path d="M 38 0 L 0 0 0 38" fill="none" stroke={INK} strokeWidth="0.6" />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#sc-grid)" />
      </svg>
      <svg
        className="animate-drift-slow absolute left-6 top-[16%] h-9 w-9 opacity-[0.13]"
        viewBox="0 0 24 24"
        fill="none"
        style={{ color: "#7dd3fc" }}
      >
        <path
          d="M3 17l5-6 4 3 5-7 4 4"
          stroke="currentColor"
          strokeWidth="1.4"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <svg
        className="animate-drift-slower absolute right-8 top-[38%] h-8 w-8 opacity-[0.12]"
        viewBox="0 0 24 24"
        fill="none"
        style={{ color: "#a78bfa" }}
      >
        <rect x="3" y="7" width="18" height="12" rx="2.5" stroke="currentColor" strokeWidth="1.3" />
        <path d="M9 7V5.5A1.5 1.5 0 0110.5 4h3A1.5 1.5 0 0115 5.5V7" stroke="currentColor" strokeWidth="1.3" />
      </svg>
      <svg
        className="animate-drift-slower absolute right-10 bottom-[14%] h-8 w-8 opacity-[0.11]"
        viewBox="0 0 24 24"
        fill="none"
        style={{ color: "#f472b6", animationDelay: "2s" }}
      >
        <path d="M4 19V9M10 19V5M16 19v-7M22 19H2" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
      </svg>
      <svg className="animate-orbit-slow absolute -right-16 top-20 h-64 w-64 opacity-[0.16]" viewBox="0 0 200 200" fill="none">
        <circle cx="100" cy="100" r="70" stroke="#38bdf8" strokeWidth="0.7" strokeDasharray="4 8" />
        <circle cx="100" cy="30" r="3.5" fill="#a78bfa" />
      </svg>
      <svg className="animate-orbit-rev absolute -left-20 bottom-12 h-56 w-56 opacity-[0.14]" viewBox="0 0 200 200" fill="none">
        <circle cx="100" cy="100" r="80" stroke="#a78bfa" strokeWidth="0.7" strokeDasharray="3 10" />
        <circle cx="180" cy="100" r="3" fill="#38bdf8" />
      </svg>
    </div>
  );
}

function mediaUrl(path?: string | null): string | null {
  if (!path) return null;
  if (/^https?:\/\//i.test(path)) return path;
  return `${API}${path}`;
}

function classifyAspect(w: number, h: number): AspectKind {
  if (!w || !h) return "square";
  const r = w / h;
  if (r > 1.12) return "landscape";
  if (r < 0.88) return "portrait";
  return "square";
}

/** Renders image in its natural shape: square → square, otherwise rectangular. */
function AdaptiveImg({
  src,
  alt,
  kind,
  className,
  style,
}: {
  src: string;
  alt: string;
  kind: "logo" | "photo";
  className?: string;
  style?: React.CSSProperties;
}) {
  const [aspect, setAspect] = React.useState<AspectKind>("square");

  const box =
    kind === "logo"
      ? aspect === "landscape"
        ? { height: 36, width: 56 }
        : aspect === "portrait"
          ? { height: 48, width: 32 }
          : { height: 36, width: 36 }
      : aspect === "landscape"
        ? { height: 72, width: 110 }
        : aspect === "portrait"
          ? { height: 110, width: 78 }
          : { height: 86, width: 86 };

  const radius =
    kind === "logo"
      ? aspect === "square"
        ? "rounded-xl"
        : "rounded-lg"
      : aspect === "square"
        ? "rounded-[22px]"
        : "rounded-2xl";

  return (
    <div
      className={`flex items-center justify-center overflow-hidden ${radius} ${className || ""}`}
      style={{
        width: box.width,
        height: box.height,
        ...style,
      }}
    >
      <img
        src={src}
        alt={alt}
        className="h-full w-full object-cover"
        onLoad={(e) => {
          const img = e.currentTarget;
          setAspect(classifyAspect(img.naturalWidth, img.naturalHeight));
        }}
      />
    </div>
  );
}

function initials(name: string) {
  const parts = name
    .split(/\s+/)
    .map((w) => w[0])
    .filter(Boolean);
  return (parts.join("").slice(0, 2) || "AB").toUpperCase();
}

function IconLink({
  href,
  label,
  glow,
  children,
}: {
  href: string;
  label: string;
  glow: string;
  children: React.ReactNode;
}) {
  return (
    <a
      href={href}
      target={href.startsWith("http") ? "_blank" : undefined}
      rel="noreferrer"
      aria-label={label}
      title={label}
      className="group flex flex-col items-center gap-1.5"
    >
      <span
        className="flex h-12 w-12 items-center justify-center rounded-2xl transition-all duration-300 group-hover:-translate-y-0.5 group-active:scale-95"
        style={{
          background: `linear-gradient(140deg, ${glow.replace("0.55", "0.16").replace("0.5", "0.16")}, rgba(255,255,255,0.04))`,
          border: `1px solid ${BORDER}`,
          color: INK,
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.borderColor = glow;
          e.currentTarget.style.boxShadow = `0 12px 26px -14px ${glow}`;
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.borderColor = BORDER;
          e.currentTarget.style.boxShadow = "none";
        }}
      >
        {children}
      </span>
      <span className="text-[10.5px] font-medium tracking-wide" style={{ color: SUB }}>
        {label}
      </span>
    </a>
  );
}

const WaIcon = (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
    <path d="M12.04 2A9.9 9.9 0 002.1 11.9c0 1.75.46 3.45 1.32 4.95L2 22l5.3-1.38a9.9 9.9 0 0014.74-8.72A9.9 9.9 0 0012.04 2zm5.8 14.05c-.24.68-1.4 1.3-1.94 1.34-.5.04-1.12.06-1.81-.11a15.5 15.5 0 01-6.6-4.6c-.44-.58-1.17-1.68-1.17-3.2 0-1.52.8-2.27 1.08-2.58.28-.31.6-.39.8-.39l.58.01c.19 0 .44-.07.68.52.25.6.85 2.08.93 2.23.07.15.12.33.02.53-.1.2-.15.32-.3.5l-.44.51c-.15.15-.3.32-.13.62.17.3.76 1.25 1.63 2.03 1.12 1 2.07 1.31 2.37 1.46.3.15.47.13.65-.08.17-.2.75-.87.95-1.17.2-.3.4-.25.67-.15.27.1 1.72.81 2.02.96.3.15.5.22.57.35.07.13.07.74-.17 1.42z" />
  </svg>
);

function ensureHttp(url: string): string {
  const t = url.trim();
  if (!t) return t;
  if (/^https?:\/\//i.test(t)) return t;
  return `https://${t}`;
}

const SOCIAL_DEFS: {
  key: keyof SocialLinks | string;
  label: string;
  glow: string;
  icon: React.ReactNode;
}[] = [
  {
    key: "instagram",
    label: "Instagram",
    glow: "rgba(244,114,182,0.55)",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
        <rect x="3" y="3" width="18" height="18" rx="5" stroke="currentColor" strokeWidth="1.6" />
        <circle cx="12" cy="12" r="4" stroke="currentColor" strokeWidth="1.6" />
        <circle cx="17.2" cy="6.8" r="1.1" fill="currentColor" />
      </svg>
    ),
  },
  {
    key: "linkedin",
    label: "LinkedIn",
    glow: "rgba(56,189,248,0.55)",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
        <path d="M4.98 3.5a2.5 2.5 0 11-.02 5 2.5 2.5 0 01.02-5zM3 9h4v12H3V9zm7 0h3.8v1.7h.05c.53-.95 1.83-1.95 3.77-1.95 4.03 0 4.78 2.5 4.78 5.75V21h-4v-5.6c0-1.34-.02-3.07-1.9-3.07-1.9 0-2.2 1.45-2.2 2.97V21h-4V9z" />
      </svg>
    ),
  },
  {
    key: "facebook",
    label: "Facebook",
    glow: "rgba(99,102,241,0.55)",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
        <path d="M13.5 21v-8h2.7l.4-3.1h-3.1V7.9c0-.9.25-1.5 1.55-1.5H16.7V3.6c-.3-.04-1.3-.13-2.47-.13-2.45 0-4.13 1.5-4.13 4.25V9.9H7.4V13h2.7v8h3.4z" />
      </svg>
    ),
  },
  {
    key: "x",
    label: "X",
    glow: "rgba(234,242,255,0.45)",
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
        <path d="M17.5 3h3.1l-6.8 7.8L21.8 21h-6.1l-4.8-6.2L5.4 21H2.3l7.3-8.3L2.4 3h6.3l4.3 5.7L17.5 3zm-1.1 16.1h1.7L7.7 4.8H5.9l10.5 14.3z" />
      </svg>
    ),
  },
  {
    key: "tiktok",
    label: "TikTok",
    glow: "rgba(167,139,250,0.55)",
    icon: (
      <svg width="17" height="17" viewBox="0 0 24 24" fill="currentColor">
        <path d="M16.5 3c.35 1.9 1.55 3.3 3.5 3.55v2.6c-1.3.06-2.5-.3-3.6-1.02v5.9c0 3.5-2.6 5.97-5.9 5.97A5.7 5.7 0 015 14.2a5.7 5.7 0 015.7-5.7c.33 0 .65.03.95.09v2.8a3 3 0 00-.95-.16 2.98 2.98 0 100 5.96c1.64 0 2.98-1.3 2.98-3V3h2.82z" />
      </svg>
    ),
  },
];

export function PublicSmartCardLanding({ token }: { token: string }) {
  const [meta, setMeta] = React.useState<CardMeta | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [phase, setPhase] = React.useState<Phase>("card");
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
  const photoSrc = mediaUrl(rep?.photo_url);
  const logoSrc = mediaUrl(company?.logo_url);
  const waHref =
    meta?.feedback_whatsapp_url ||
    meta?.whatsapp_url ||
    (phone
      ? `https://wa.me/${phone.replace(/\D/g, "")}?text=${encodeURIComponent("Hi! I'd like to share some feedback.")}`
      : null);

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
    a.download = "contact.vcf";
    a.click();
    URL.revokeObjectURL(url);
    setSaved(true);
    setTimeout(() => setSaved(false), 2500);
  };

  const share = async () => {
    if (typeof navigator !== "undefined" && navigator.share) {
      try {
        await navigator.share({ title: companyName, url: window.location.href });
      } catch {
        /* dismissed */
      }
    }
  };

  const startWeb = () => {
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

  const socialEntries = SOCIAL_DEFS.map((s) => ({
    ...s,
    href: (socials[s.key] || "").trim(),
  })).filter((s) => s.href);

  return (
    <main className="bg-smartcard-gradient relative min-h-dvh w-full overflow-hidden">
      <Art />
      <div className="relative mx-auto flex min-h-dvh w-full max-w-md flex-col px-5 pb-6 pt-6">
        {/* Card surface — feedback-flow /smartcard layout */}
        <section
          className="animate-rise relative overflow-hidden rounded-[28px] px-5 pb-5 pt-6"
          style={{
            background: "linear-gradient(160deg, rgba(255,255,255,0.09), rgba(255,255,255,0.03))",
            border: `1px solid ${BORDER}`,
            boxShadow: "0 30px 70px -40px rgba(56,189,248,0.6)",
            backdropFilter: "blur(10px)",
          }}
        >
          {/* company row */}
          <div className="flex items-center gap-2.5">
            {logoSrc ? (
              <AdaptiveImg
                src={logoSrc}
                alt={`${companyName} logo`}
                kind="logo"
                style={{
                  background: "linear-gradient(135deg,#38bdf8,#6366f1)",
                  color: "#06121f",
                }}
              />
            ) : (
              <div
                className="flex h-9 w-9 items-center justify-center overflow-hidden rounded-xl text-[13px] font-bold"
                style={{ background: "linear-gradient(135deg,#38bdf8,#6366f1)", color: "#06121f" }}
              >
                ✦
              </div>
            )}
            <span className="text-[13px] font-semibold tracking-wide" style={{ color: INK }}>
              {companyName}
            </span>
          </div>

          {/* representative */}
          <div className="mt-5 flex items-center gap-4">
            <div className="relative shrink-0">
              <span
                className="animate-pulse-ring absolute -inset-1 rounded-full"
                style={{ border: "1px solid rgba(56,189,248,0.4)" }}
              />
              {photoSrc ? (
                <AdaptiveImg
                  src={photoSrc}
                  alt={personName}
                  kind="photo"
                  style={{
                    background: "linear-gradient(140deg, rgba(56,189,248,0.35), rgba(99,102,241,0.35))",
                    border: "2px solid rgba(125,211,252,0.5)",
                    color: INK,
                    boxShadow: "0 18px 44px -20px rgba(56,189,248,0.9)",
                  }}
                />
              ) : (
                <div
                  className="flex h-[86px] w-[86px] items-center justify-center overflow-hidden rounded-full text-[26px] font-semibold"
                  style={{
                    background: "linear-gradient(140deg, rgba(56,189,248,0.35), rgba(99,102,241,0.35))",
                    border: "2px solid rgba(125,211,252,0.5)",
                    color: INK,
                    boxShadow: "0 18px 44px -20px rgba(56,189,248,0.9)",
                  }}
                >
                  {initials(personName)}
                </div>
              )}
            </div>
            <div className="min-w-0">
              <h1 className="truncate text-[22px] font-semibold leading-tight" style={{ color: INK }}>
                {personName}
              </h1>
              {jobTitle ? (
                <p className="mt-0.5 text-[12.5px] font-medium tracking-wide" style={{ color: "#7dd3fc" }}>
                  {jobTitle}
                </p>
              ) : null}
              {tagline ? (
                <p className="mt-1.5 text-[12px] leading-relaxed" style={{ color: SUB }}>
                  {tagline}
                </p>
              ) : null}
            </div>
          </div>

          {meta.status === "preview" && typeof meta.preview_tests_remaining === "number" ? (
            <p
              className="mt-4 rounded-full px-3 py-1 text-center text-[11px] font-medium"
              style={{
                background: "rgba(251,191,36,0.15)",
                color: "#fbbf24",
                border: "1px solid rgba(251,191,36,0.35)",
              }}
            >
              {meta.preview_tests_remaining} of 15 free scans left
            </p>
          ) : null}

          {/* compact contact icons */}
          <div className="mt-5 grid grid-cols-4 gap-2 border-t pt-4" style={{ borderColor: BORDER }}>
            <IconLink href={phone ? `tel:${phone}` : "#"} label="Call" glow="rgba(56,189,248,0.55)">
              <svg width="19" height="19" viewBox="0 0 24 24" fill="none">
                <path
                  d="M6.5 3h3l1.5 4-2 1.5a12 12 0 006.5 6.5l1.5-2 4 1.5v3a2 2 0 01-2.2 2A17 17 0 014.5 5.2 2 2 0 016.5 3z"
                  stroke="currentColor"
                  strokeWidth="1.6"
                  strokeLinejoin="round"
                />
              </svg>
            </IconLink>
            <IconLink href={email ? `mailto:${email}` : "#"} label="Email" glow="rgba(167,139,250,0.55)">
              <svg width="19" height="19" viewBox="0 0 24 24" fill="none">
                <rect x="3" y="5" width="18" height="14" rx="2.5" stroke="currentColor" strokeWidth="1.6" />
                <path d="M4 7l8 6 8-6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
              </svg>
            </IconLink>
            <IconLink
              href={website ? ensureHttp(website) : "#"}
              label="Website"
              glow="rgba(99,102,241,0.55)"
            >
              <svg width="19" height="19" viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.6" />
                <path
                  d="M3 12h18M12 3a15 15 0 010 18M12 3a15 15 0 000 18"
                  stroke="currentColor"
                  strokeWidth="1.4"
                />
              </svg>
            </IconLink>
            <IconLink
              href={
                location ? `https://maps.google.com/?q=${encodeURIComponent(location)}` : "#"
              }
              label="Location"
              glow="rgba(244,114,182,0.5)"
            >
              <svg width="19" height="19" viewBox="0 0 24 24" fill="none">
                <path
                  d="M12 21s7-5.5 7-11a7 7 0 10-14 0c0 5.5 7 11 7 11z"
                  stroke="currentColor"
                  strokeWidth="1.6"
                  strokeLinejoin="round"
                />
                <circle cx="12" cy="10" r="2.4" stroke="currentColor" strokeWidth="1.6" />
              </svg>
            </IconLink>
          </div>
        </section>

        {/* Primary actions */}
        <div className="animate-rise mt-4 grid grid-cols-2 gap-3" style={{ animationDelay: "80ms" }}>
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

        {/* Feedback — hero pair */}
        <div className="animate-rise mt-4" style={{ animationDelay: "120ms" }}>
          <p
            className="mb-2.5 text-center text-[11px] font-semibold uppercase tracking-[0.18em]"
            style={{ color: SUB }}
          >
            Share your feedback
          </p>
          <div className="grid grid-cols-2 gap-3">
            {waHref ? (
              <a
                href={waHref}
                target="_blank"
                rel="noreferrer"
                className="group flex flex-col items-center justify-center gap-2 rounded-3xl px-4 py-6 text-center transition-all duration-300 hover:-translate-y-1 active:scale-[0.98]"
                style={{
                  background: "linear-gradient(150deg, rgba(37,211,102,0.22), rgba(255,255,255,0.03))",
                  border: "1px solid rgba(37,211,102,0.4)",
                  color: INK,
                  boxShadow: "0 18px 40px -26px rgba(37,211,102,0.9)",
                }}
              >
                <span className="transition-transform duration-300 group-hover:scale-110">{WaIcon}</span>
                <span className="text-[15px] font-semibold">WhatsApp</span>
                <span className="text-[11.5px]" style={{ color: SUB }}>
                  Chat with us
                </span>
              </a>
            ) : (
              <div
                className="flex flex-col items-center justify-center gap-2 rounded-3xl px-4 py-6 text-center opacity-50"
                style={{
                  background: "linear-gradient(150deg, rgba(37,211,102,0.12), rgba(255,255,255,0.03))",
                  border: "1px solid rgba(37,211,102,0.25)",
                  color: INK,
                }}
              >
                <span>{WaIcon}</span>
                <span className="text-[15px] font-semibold">WhatsApp</span>
                <span className="text-[11.5px]" style={{ color: SUB }}>
                  Not available
                </span>
              </div>
            )}
            <button
              type="button"
              onClick={() => startWeb()}
              className="group flex flex-col items-center justify-center gap-2 rounded-3xl px-4 py-6 text-center transition-all duration-300 hover:-translate-y-1 active:scale-[0.98]"
              style={{
                background: "linear-gradient(150deg, rgba(56,189,248,0.22), rgba(255,255,255,0.03))",
                border: "1px solid rgba(56,189,248,0.4)",
                color: INK,
                boxShadow: "0 18px 40px -26px rgba(56,189,248,0.9)",
              }}
            >
              <span className="transition-transform duration-300 group-hover:scale-110">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                  <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.6" />
                  <path
                    d="M3 12h18M12 3a15 15 0 010 18M12 3a15 15 0 000 18"
                    stroke="currentColor"
                    strokeWidth="1.4"
                  />
                </svg>
              </span>
              <span className="text-[15px] font-semibold">Web survey</span>
              <span className="text-[11.5px]" style={{ color: SUB }}>
                60 seconds
              </span>
            </button>
          </div>
        </div>

        {error ? <p className="mt-3 text-center text-[13px] text-rose-300">{error}</p> : null}

        {/* Socials */}
        {socialEntries.length > 0 ? (
          <div
            className="animate-rise mt-4 flex items-center justify-center gap-2.5"
            style={{ animationDelay: "200ms" }}
          >
            {socialEntries.map((s) => (
              <a
                key={s.label}
                href={ensureHttp(s.href)}
                target="_blank"
                rel="noreferrer"
                aria-label={s.label}
                className="group flex h-10 w-10 items-center justify-center rounded-full transition-all duration-300 hover:-translate-y-0.5 active:scale-95"
                style={{ background: CARD_BG, border: `1px solid ${BORDER}`, color: INK }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.borderColor = s.glow;
                  e.currentTarget.style.boxShadow = `0 10px 24px -12px ${s.glow}`;
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = BORDER;
                  e.currentTarget.style.boxShadow = "none";
                }}
              >
                <span className="transition-transform duration-300 group-hover:scale-110">{s.icon}</span>
              </a>
            ))}
          </div>
        ) : null}

        <footer className="mt-auto pt-5 text-center text-[11px]" style={{ color: "rgba(234,242,255,0.4)" }}>
          Smart card by {companyName}
        </footer>
      </div>
    </main>
  );
}
