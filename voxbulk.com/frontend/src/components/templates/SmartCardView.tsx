import { useState, type ReactNode } from "react";
import logoDark from "@/assets/voxbulk-logo-dark.svg";
import portrait from "@/assets/smartcard-portrait.jpg";

export type SmartCardData = {
  companyName: string;
  personName: string;
  jobTitle: string;
  tagline: string;
  phone: string;
  whatsapp: string;
  email: string;
  website: string;
  location: string;
};

export type SmartCardTheme = {
  id: string;
  name: string;
  blurb: string;
  bgClass: string;
  ink: string;
  sub: string;
  border: string;
  surface: string;
  accent: string;
  accent2: string;
  accent3: string;
  onAccent: string;
  radius: string;
  surveyNote: string;
  logoPlate?: "light" | "dark";
};


const alpha = (hex: string, a: number) => {
  const h = hex.replace("#", "");
  const n = parseInt(h.length === 3 ? h.split("").map((c) => c + c).join("") : h, 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
};

const WaIcon = (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
    <path d="M12.04 2A9.9 9.9 0 002.1 11.9c0 1.75.46 3.45 1.32 4.95L2 22l5.3-1.38a9.9 9.9 0 0014.74-8.72A9.9 9.9 0 0012.04 2zm5.8 14.05c-.24.68-1.4 1.3-1.94 1.34-.5.04-1.12.06-1.81-.11a15.5 15.5 0 01-6.6-4.6c-.44-.58-1.17-1.68-1.17-3.2 0-1.52.8-2.27 1.08-2.58.28-.31.6-.39.8-.39l.58.01c.19 0 .44-.07.68.52.25.6.85 2.08.93 2.23.07.15.12.33.02.53-.1.2-.15.32-.3.5l-.44.51c-.15.15-.3.32-.13.62.17.3.76 1.25 1.63 2.03 1.12 1 2.07 1.31 2.37 1.46.3.15.47.13.65-.08.17-.2.75-.87.95-1.17.2-.3.4-.25.67-.15.27.1 1.72.81 2.02.96.3.15.5.22.57.35.07.13.07.74-.17 1.42z" />
  </svg>
);

const socialIcons: Record<string, ReactNode> = {
  Instagram: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
      <rect x="3" y="3" width="18" height="18" rx="5" stroke="currentColor" strokeWidth="1.6" />
      <circle cx="12" cy="12" r="4" stroke="currentColor" strokeWidth="1.6" />
      <circle cx="17.2" cy="6.8" r="1.1" fill="currentColor" />
    </svg>
  ),
  LinkedIn: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
      <path d="M4.98 3.5a2.5 2.5 0 11-.02 5 2.5 2.5 0 01.02-5zM3 9h4v12H3V9zm7 0h3.8v1.7h.05c.53-.95 1.83-1.95 3.77-1.95 4.03 0 4.78 2.5 4.78 5.75V21h-4v-5.6c0-1.34-.02-3.07-1.9-3.07-1.9 0-2.2 1.45-2.2 2.97V21h-4V9z" />
    </svg>
  ),
  Facebook: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
      <path d="M13.5 21v-8h2.7l.4-3.1h-3.1V7.9c0-.9.25-1.5 1.55-1.5H16.7V3.6c-.3-.04-1.3-.13-2.47-.13-2.45 0-4.13 1.5-4.13 4.25V9.9H7.4V13h2.7v8h3.4z" />
    </svg>
  ),
  X: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
      <path d="M17.5 3h3.1l-6.8 7.8L21.8 21h-6.1l-4.8-6.2L5.4 21H2.3l7.3-8.3L2.4 3h6.3l4.3 5.7L17.5 3zm-1.1 16.1h1.7L7.7 4.8H5.9l10.5 14.3z" />
    </svg>
  ),
  TikTok: (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="currentColor">
      <path d="M16.5 3c.35 1.9 1.55 3.3 3.5 3.55v2.6c-1.3.06-2.5-.3-3.6-1.02v5.9c0 3.5-2.6 5.97-5.9 5.97A5.7 5.7 0 015 14.2a5.7 5.7 0 015.7-5.7c.33 0 .65.03.95.09v2.8a3 3 0 00-.95-.16 2.98 2.98 0 100 5.96c1.64 0 2.98-1.3 2.98-3V3h2.82z" />
    </svg>
  ),
};

function Art({ accent, accent2, accent3 }: { accent: string; accent2: string; accent3: string }) {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      <div className="tpl-blob-a absolute -left-24 -top-24 h-80 w-80 rounded-full blur-3xl" style={{ background: alpha(accent, 0.18) }} />
      <div className="tpl-blob-b absolute -right-24 bottom-0 h-80 w-80 rounded-full blur-3xl" style={{ background: alpha(accent2, 0.16) }} />
      <svg className="tpl-orbit-slow absolute -right-16 top-20 h-64 w-64 opacity-20" viewBox="0 0 200 200" fill="none">
        <circle cx="100" cy="100" r="72" stroke={accent} strokeWidth="0.7" strokeDasharray="2 10" />
        <circle cx="100" cy="28" r="3" fill={accent3} />
      </svg>
      <svg className="tpl-orbit-rev absolute -left-20 bottom-12 h-56 w-56 opacity-20" viewBox="0 0 200 200" fill="none">
        <circle cx="100" cy="100" r="80" stroke={accent2} strokeWidth="0.7" strokeDasharray="3 10" />
        <circle cx="180" cy="100" r="3" fill={accent} />
      </svg>
    </div>
  );
}

/** Live mobile smart-card template — the screen a customer sees after scanning the QR. */
export function SmartCardView({ card, theme }: { card: SmartCardData; theme: SmartCardTheme }) {
  const [saved, setSaved] = useState(false);
  const { ink, sub, border, surface, accent, accent2, accent3, onAccent, radius } = theme;
  const logoPlate = theme.logoPlate ?? "light";

  const socials = [
    { label: "Instagram", glow: alpha(accent3, 0.55) },
    { label: "LinkedIn", glow: alpha(accent, 0.55) },
    { label: "Facebook", glow: alpha(accent2, 0.55) },
    { label: "X", glow: alpha(accent, 0.4) },
    { label: "TikTok", glow: alpha(accent2, 0.5) },
  ];

  const IconTile = ({ label, glow, children }: { label: string; glow: string; children: ReactNode }) => (
    <div className="flex flex-col items-center gap-1.5">
      <span
        className="flex h-12 w-12 items-center justify-center rounded-2xl"
        style={{ background: `linear-gradient(140deg, ${glow}, ${alpha(accent, 0.03)})`, border: `1px solid ${border}`, color: ink }}
      >
        {children}
      </span>
      <span className="text-[10.5px] font-medium tracking-wide" style={{ color: sub }}>{label}</span>
    </div>
  );

  return (
    <div className={`${theme.bgClass} relative h-full w-full overflow-y-auto`}>
      <Art accent={accent} accent2={accent2} accent3={accent3} />
      <div className="relative mx-auto flex min-h-full w-full max-w-md flex-col px-5 pb-8 pt-11">
        <section
          className="tpl-rise relative overflow-hidden px-5 pb-5 pt-6"
          style={{
            borderRadius: radius,
            background: `linear-gradient(160deg, ${surface}, ${alpha(accent, 0.04)})`,
            border: `1px solid ${border}`,
            boxShadow: `0 30px 70px -40px ${alpha(accent, 0.6)}`,
            backdropFilter: "blur(10px)",
          }}
        >
          <div className="flex items-center gap-2.5">
            <div
              className="flex h-8 w-[112px] shrink-0 items-center justify-start overflow-hidden rounded-lg px-2 py-1"
              style={{
                background: logoPlate === "dark" ? "rgba(17,20,28,0.92)" : "rgba(255,255,255,0.94)",
                border: `1px solid ${logoPlate === "dark" ? "rgba(255,255,255,0.18)" : "rgba(15,23,42,0.12)"}`,
                boxShadow: `0 6px 18px -10px ${alpha(accent, 0.9)}`,
              }}
            >
              <img src={logoDark} alt={`${card.companyName} logo`} className="h-full w-auto object-contain" />
            </div>
          </div>

          <div className="mt-5 flex items-center gap-4">
            <div className="relative shrink-0">
              <span className="tpl-pulse-ring absolute -inset-1 rounded-full" style={{ border: `1px solid ${alpha(accent, 0.4)}` }} />
              <div
                className="h-[86px] w-[86px] overflow-hidden rounded-full"
                style={{
                  border: `2px solid ${alpha(accent, 0.5)}`,
                  boxShadow: `0 18px 44px -20px ${alpha(accent, 0.9)}`,
                }}
              >
                <img src={portrait} alt={card.personName} loading="lazy" width={86} height={86} className="h-full w-full object-cover" />
              </div>
            </div>
            <div className="min-w-0">
              <h3 className="truncate text-[20px] font-semibold leading-tight" style={{ color: ink }}>{card.personName}</h3>
              <p className="mt-0.5 text-[12px] font-medium tracking-wide" style={{ color: accent }}>{card.jobTitle}</p>
              <p className="mt-1.5 text-[11.5px] leading-relaxed" style={{ color: sub }}>{card.tagline}</p>
            </div>
          </div>


          <div className="mt-5 grid grid-cols-4 gap-2 border-t pt-4" style={{ borderColor: border }}>
            <IconTile label="Call" glow={alpha(accent, 0.16)}>
              <svg width="19" height="19" viewBox="0 0 24 24" fill="none"><path d="M6.5 3h3l1.5 4-2 1.5a12 12 0 006.5 6.5l1.5-2 4 1.5v3a2 2 0 01-2.2 2A17 17 0 014.5 5.2 2 2 0 016.5 3z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" /></svg>
            </IconTile>
            <IconTile label="Email" glow={alpha(accent2, 0.16)}>
              <svg width="19" height="19" viewBox="0 0 24 24" fill="none"><rect x="3" y="5" width="18" height="14" rx="2.5" stroke="currentColor" strokeWidth="1.6" /><path d="M4 7l8 6 8-6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" /></svg>
            </IconTile>
            <IconTile label="Website" glow={alpha(accent3, 0.16)}>
              <svg width="19" height="19" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.6" /><path d="M3 12h18M12 3a15 15 0 010 18M12 3a15 15 0 000 18" stroke="currentColor" strokeWidth="1.4" /></svg>
            </IconTile>
            <IconTile label="Location" glow={alpha(accent3, 0.2)}>
              <svg width="19" height="19" viewBox="0 0 24 24" fill="none"><path d="M12 21s7-5.5 7-11a7 7 0 10-14 0c0 5.5 7 11 7 11z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" /><circle cx="12" cy="10" r="2.4" stroke="currentColor" strokeWidth="1.6" /></svg>
            </IconTile>
          </div>
        </section>

        <div className="tpl-rise mt-4 grid grid-cols-2 gap-3" style={{ animationDelay: "80ms" }}>
          <button
            onClick={() => { setSaved(true); window.setTimeout(() => setSaved(false), 2000); }}
            className="px-4 py-3 text-[14px] font-semibold transition-transform active:scale-[0.98]"
            style={{ borderRadius: "16px", background: `linear-gradient(135deg, ${accent}, ${accent2})`, color: onAccent, boxShadow: `0 10px 28px -12px ${alpha(accent2, 0.8)}` }}
          >
            {saved ? "Saved ✓" : "Save contact"}
          </button>
          <button
            className="px-4 py-3 text-[14px] font-semibold transition-transform active:scale-[0.98]"
            style={{ borderRadius: "16px", background: surface, border: `1px solid ${border}`, color: ink }}
          >
            Share card
          </button>
        </div>

        <div className="tpl-rise mt-4" style={{ animationDelay: "120ms" }}>
          <p className="mb-2.5 text-center text-[11px] font-semibold uppercase tracking-[0.18em]" style={{ color: sub }}>Share your feedback</p>
          <div className="grid grid-cols-2 gap-3">
            <div
              className="flex flex-col items-center justify-center gap-2 rounded-3xl px-4 py-6 text-center"
              style={{ background: "linear-gradient(150deg, rgba(37,211,102,0.22), rgba(255,255,255,0.03))", border: "1px solid rgba(37,211,102,0.4)", color: ink, boxShadow: "0 18px 40px -26px rgba(37,211,102,0.9)" }}
            >
              <span>{WaIcon}</span>
              <span className="text-[15px] font-semibold">WhatsApp</span>
              <span className="text-[11.5px]" style={{ color: sub }}>Chat with us</span>
            </div>
            <div
              className="flex flex-col items-center justify-center gap-2 rounded-3xl px-4 py-6 text-center"
              style={{ background: `linear-gradient(150deg, ${alpha(accent, 0.22)}, ${alpha(accent2, 0.05)})`, border: `1px solid ${alpha(accent, 0.4)}`, color: ink, boxShadow: `0 18px 40px -26px ${alpha(accent, 0.9)}` }}
            >
              <span>
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.6" /><path d="M3 12h18M12 3a15 15 0 010 18M12 3a15 15 0 000 18" stroke="currentColor" strokeWidth="1.4" /></svg>
              </span>
              <span className="text-[15px] font-semibold">Web survey</span>
              <span className="text-[11.5px]" style={{ color: sub }}>{theme.surveyNote}</span>
            </div>
          </div>
        </div>

        <div className="tpl-rise mt-4 flex items-center justify-center gap-2.5" style={{ animationDelay: "200ms" }}>
          {socials.map((s) => (
            <span key={s.label} aria-label={s.label} className="flex h-10 w-10 items-center justify-center rounded-full" style={{ background: surface, border: `1px solid ${border}`, color: ink }}>
              {socialIcons[s.label]}
            </span>
          ))}
        </div>

        <footer className="mt-auto pt-5 text-center text-[11px]" style={{ color: sub }}>Smart card by {card.companyName}</footer>
      </div>
    </div>
  );
}

export const VOXBULK_CARD: SmartCardData = {
  companyName: "VoxBulk",
  personName: "James Whitfield",
  jobTitle: "Sales Manager",
  tagline: "Intelligent screening. Instant results.",
  phone: "+44 7954 823445",
  whatsapp: "447954823445",
  email: "james@voxbulk.com",
  website: "https://voxbulk.com",
  location: "London, UK",
};

export const SMARTCARD_THEMES: SmartCardTheme[] = [
  {
    id: "smartcard",
    name: "Azure",
    blurb: "Cool blue and indigo — corporate, consulting and B2B teams.",
    bgClass: "bg-smartcard-gradient",
    ink: "#eaf2ff",
    sub: "rgba(234,242,255,0.62)",
    border: "rgba(234,242,255,0.14)",
    surface: "rgba(255,255,255,0.06)",
    accent: "#38bdf8",
    accent2: "#6366f1",
    accent3: "#a78bfa",
    onAccent: "#06121f",
    radius: "28px",
    surveyNote: "60 seconds",
  },
  {
    id: "smartcard1",
    name: "Emerald",
    blurb: "Emerald and gold — consultants, law and finance.",
    bgClass: "bg-smartcard1-gradient",
    ink: "#ecfdf5",
    sub: "rgba(236,253,245,0.6)",
    border: "rgba(212,175,55,0.24)",
    surface: "rgba(255,255,255,0.06)",
    accent: "#34d399",
    accent2: "#d4af37",
    accent3: "#a3e635",
    onAccent: "#04231a",
    radius: "22px",
    surveyNote: "Under a minute",
  },
  {
    id: "smartcard2",
    name: "Blush",
    blurb: "Light rose and lilac — salons, spas, studios and creatives.",
    bgClass: "bg-smartcard2-gradient",
    ink: "#3b2135",
    sub: "rgba(59,33,53,0.6)",
    border: "rgba(59,33,53,0.12)",
    surface: "rgba(255,255,255,0.65)",
    accent: "#e0648f",
    accent2: "#a78bfa",
    accent3: "#f0a2b8",
    onAccent: "#ffffff",
    radius: "30px",
    surveyNote: "Takes 60 seconds",
  },
  {
    id: "smartcard3",
    name: "Amber",
    blurb: "Warm amber and charcoal — restaurants, cafés and hotels.",
    bgClass: "bg-smartcard3-gradient",
    ink: "#fdf3e3",
    sub: "rgba(253,243,227,0.62)",
    border: "rgba(253,243,227,0.16)",
    surface: "rgba(255,255,255,0.07)",
    accent: "#fbbf24",
    accent2: "#f97316",
    accent3: "#ef7c5a",
    onAccent: "#2a1405",
    radius: "20px",
    surveyNote: "Quick 1 min",
  },
  {
    id: "smartcard4",
    name: "Neon",
    blurb: "Bold lime and violet — tech, startups and creative agencies.",
    bgClass: "bg-smartcard4-gradient",
    ink: "#eef0ff",
    sub: "rgba(238,240,255,0.6)",
    border: "rgba(238,240,255,0.14)",
    surface: "rgba(255,255,255,0.05)",
    accent: "#a3e635",
    accent2: "#c084fc",
    accent3: "#67e8f9",
    onAccent: "#12190a",
    radius: "16px",
    surveyNote: "60 second survey",
  },
];
