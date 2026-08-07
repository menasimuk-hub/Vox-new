import * as React from "react";

import {
  getSmartCardThemeTokens,
  SmartCardThemeArt,
  type SmartCardThemeId,
  type SmartCardThemeTokens,
} from "@/components/smart-card/smart-card-themes";

export type SmartCardData = {
  companyName: string;
  companyLogo: string;
  personName: string;
  personPhoto: string;
  jobTitle: string;
  tagline: string;
  phone: string;
  email: string;
  website: string;
  location: string;
  instagram: string;
  linkedin: string;
  facebook: string;
  x: string;
  tiktok: string;
};

export type SmartCardTemplateActions = {
  whatsappHref?: string | null;
  onWhatsApp?: () => void;
  onWebSurvey?: () => void;
  webSurveyLabel?: string;
  previewBanner?: React.ReactNode;
  hideFeedback?: boolean;
};

const isSet = (v: string) => !!v && !v.startsWith("{{") && v.trim().length > 0;

const initials = (name: string) =>
  isSet(name)
    ? name
        .split(" ")
        .map((w) => w[0])
        .join("")
        .slice(0, 2)
        .toUpperCase()
    : "AB";

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

const socialIcons: Record<string, React.ReactNode> = {
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

export function SmartCardTemplate({
  card,
  themeId,
  tokens: tokensProp,
  actions,
}: {
  card: SmartCardData;
  themeId?: SmartCardThemeId | string;
  tokens?: SmartCardThemeTokens;
  actions?: SmartCardTemplateActions;
}) {
  const [saved, setSaved] = React.useState(false);
  const tokens = tokensProp || getSmartCardThemeTokens(themeId);
  const { ink, sub, border, surface, accent, accent2, accent3, onAccent, radius, bgClass, surveyNote, id } = tokens;

  const socials = [
    { href: card.instagram, label: "Instagram", glow: alpha(accent3, 0.55) },
    { href: card.linkedin, label: "LinkedIn", glow: alpha(accent, 0.55) },
    { href: card.facebook, label: "Facebook", glow: alpha(accent2, 0.55) },
    { href: card.x, label: "X", glow: alpha(accent, 0.4) },
    { href: card.tiktok, label: "TikTok", glow: alpha(accent2, 0.5) },
  ].filter((s) => isSet(s.href));

  const saveContact = () => {
    const vcard = [
      "BEGIN:VCARD",
      "VERSION:3.0",
      `FN:${card.personName}`,
      `ORG:${card.companyName}`,
      `TITLE:${card.jobTitle}`,
      `TEL;TYPE=CELL:${card.phone}`,
      `EMAIL:${card.email}`,
      `URL:${card.website}`,
      `ADR;TYPE=WORK:;;${card.location};;;;`,
      "END:VCARD",
    ].join("\n");
    const blob = new Blob([vcard], { type: "text/vcard" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${(card.personName || "contact").replace(/\s+/g, "-")}.vcf`;
    a.click();
    URL.revokeObjectURL(url);
    setSaved(true);
    setTimeout(() => setSaved(false), 2500);
  };

  const share = async () => {
    if (typeof navigator !== "undefined" && navigator.share) {
      try {
        await navigator.share({ title: card.companyName, url: window.location.href });
      } catch {
        /* dismissed */
      }
    }
  };

  const IconLink = ({
    href,
    label,
    glow,
    children,
  }: {
    href: string;
    label: string;
    glow: string;
    children: React.ReactNode;
  }) => {
    if (!isSet(href) || href === "#") {
      return (
        <span className="flex flex-col items-center gap-1.5 opacity-40">
          <span
            className="flex h-12 w-12 items-center justify-center rounded-2xl"
            style={{ background: alpha(accent, 0.06), border: `1px solid ${border}`, color: ink }}
          >
            {children}
          </span>
          <span className="text-[10.5px] font-medium tracking-wide" style={{ color: sub }}>
            {label}
          </span>
        </span>
      );
    }
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
            background: `linear-gradient(140deg, ${glow}, ${alpha(accent, 0.03)})`,
            border: `1px solid ${border}`,
            color: ink,
          }}
        >
          {children}
        </span>
        <span className="text-[10.5px] font-medium tracking-wide" style={{ color: sub }}>
          {label}
        </span>
      </a>
    );
  };

  const waHref = actions?.whatsappHref;
  const webLabel = actions?.webSurveyLabel || "Web survey";

  return (
    <main className={`smartcard-root ${bgClass} relative min-h-dvh w-full overflow-hidden`}>
      <link
        rel="stylesheet"
        href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600;9..144,700&display=swap"
      />
      <SmartCardThemeArt themeId={id} />
      <div className="relative mx-auto flex min-h-dvh w-full max-w-md flex-col px-5 pb-6 pt-6">
        <section
          className="animate-rise relative overflow-hidden px-5 pb-5 pt-6"
          style={{
            borderRadius: radius,
            background: `linear-gradient(160deg, ${surface}, ${alpha(accent, 0.04)})`,
            border: `1px solid ${border}`,
            boxShadow: `0 30px 70px -40px ${alpha(accent, 0.6)}`,
            backdropFilter: "blur(10px)",
          }}
        >
          <div className="flex items-center gap-2.5">
            {isSet(card.companyLogo) ? (
              <img
                src={card.companyLogo}
                alt={`${card.companyName} logo`}
                className="h-9 w-auto max-w-[160px] shrink-0 object-contain"
              />
            ) : (
              <div
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-[13px] font-bold"
                style={{ background: `linear-gradient(135deg, ${accent}, ${accent2})`, color: onAccent }}
              >
                ✦
              </div>
            )}
            <span className="min-w-0 truncate text-[13px] font-semibold tracking-wide" style={{ color: ink }}>
              {card.companyName}
            </span>
          </div>

          <div className="mt-5 flex items-center gap-4">
            <div className="relative shrink-0">
              <span
                className="animate-pulse-ring absolute -inset-1 rounded-full"
                style={{ border: `1px solid ${alpha(accent, 0.4)}` }}
              />
              <div
                className="flex h-[86px] w-[86px] items-center justify-center overflow-hidden rounded-full text-[26px] font-semibold"
                style={{
                  background: `linear-gradient(140deg, ${alpha(accent, 0.35)}, ${alpha(accent2, 0.35)})`,
                  border: `2px solid ${alpha(accent, 0.5)}`,
                  color: ink,
                  boxShadow: `0 18px 44px -20px ${alpha(accent, 0.9)}`,
                }}
              >
                {isSet(card.personPhoto) ? (
                  <img src={card.personPhoto} alt={card.personName} className="h-full w-full object-cover" />
                ) : (
                  initials(card.personName)
                )}
              </div>
            </div>
            <div className="min-w-0">
              <h1 className="font-display truncate text-[22px] font-semibold leading-tight" style={{ color: ink }}>
                {card.personName}
              </h1>
              {isSet(card.jobTitle) ? (
                <p className="mt-0.5 text-[12.5px] font-medium tracking-wide" style={{ color: accent }}>
                  {card.jobTitle}
                </p>
              ) : null}
              {isSet(card.tagline) ? (
                <p className="mt-1.5 text-[12px] leading-relaxed" style={{ color: sub }}>
                  {card.tagline}
                </p>
              ) : null}
            </div>
          </div>

          {actions?.previewBanner}

          <div className="mt-5 grid grid-cols-4 gap-2 border-t pt-4" style={{ borderColor: border }}>
            <IconLink href={isSet(card.phone) ? `tel:${card.phone}` : "#"} label="Call" glow={alpha(accent, 0.16)}>
              <svg width="19" height="19" viewBox="0 0 24 24" fill="none">
                <path d="M6.5 3h3l1.5 4-2 1.5a12 12 0 006.5 6.5l1.5-2 4 1.5v3a2 2 0 01-2.2 2A17 17 0 014.5 5.2 2 2 0 016.5 3z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
              </svg>
            </IconLink>
            <IconLink href={isSet(card.email) ? `mailto:${card.email}` : "#"} label="Email" glow={alpha(accent2, 0.16)}>
              <svg width="19" height="19" viewBox="0 0 24 24" fill="none">
                <rect x="3" y="5" width="18" height="14" rx="2.5" stroke="currentColor" strokeWidth="1.6" />
                <path d="M4 7l8 6 8-6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
              </svg>
            </IconLink>
            <IconLink href={isSet(card.website) ? card.website : "#"} label="Website" glow={alpha(accent3, 0.16)}>
              <svg width="19" height="19" viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.6" />
                <path d="M3 12h18M12 3a15 15 0 010 18M12 3a15 15 0 000 18" stroke="currentColor" strokeWidth="1.4" />
              </svg>
            </IconLink>
            <IconLink
              href={isSet(card.location) ? `https://maps.google.com/?q=${encodeURIComponent(card.location)}` : "#"}
              label="Location"
              glow={alpha(accent3, 0.2)}
            >
              <svg width="19" height="19" viewBox="0 0 24 24" fill="none">
                <path d="M12 21s7-5.5 7-11a7 7 0 10-14 0c0 5.5 7 11 7 11z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
                <circle cx="12" cy="10" r="2.4" stroke="currentColor" strokeWidth="1.6" />
              </svg>
            </IconLink>
          </div>
        </section>

        <div className="animate-rise mt-4 grid grid-cols-2 gap-3" style={{ animationDelay: "80ms" }}>
          <button
            type="button"
            onClick={saveContact}
            className="px-4 py-3 text-[14px] font-semibold transition-transform active:scale-[0.98]"
            style={{
              borderRadius: "16px",
              background: `linear-gradient(135deg, ${accent}, ${accent2})`,
              color: onAccent,
              boxShadow: `0 10px 28px -12px ${alpha(accent2, 0.8)}`,
            }}
          >
            {saved ? "Saved ✓" : "Save contact"}
          </button>
          <button
            type="button"
            onClick={() => void share()}
            className="px-4 py-3 text-[14px] font-semibold transition-transform active:scale-[0.98]"
            style={{ borderRadius: "16px", background: surface, border: `1px solid ${border}`, color: ink }}
          >
            Share card
          </button>
        </div>

        {!actions?.hideFeedback ? (
          <div className="animate-rise mt-4" style={{ animationDelay: "120ms" }}>
            <p className="mb-2.5 text-center text-[11px] font-semibold uppercase tracking-[0.18em]" style={{ color: sub }}>
              Share your feedback
            </p>
            <div className="grid grid-cols-2 gap-3">
              {waHref || actions?.onWhatsApp ? (
                waHref && !actions?.onWhatsApp ? (
                  <a
                    href={waHref}
                    target="_blank"
                    rel="noreferrer"
                    className="group flex flex-col items-center justify-center gap-2 rounded-3xl px-4 py-6 text-center transition-all duration-300 hover:-translate-y-1 active:scale-[0.98]"
                    style={{
                      background: "linear-gradient(150deg, rgba(37,211,102,0.22), rgba(255,255,255,0.03))",
                      border: "1px solid rgba(37,211,102,0.4)",
                      color: ink,
                      boxShadow: "0 18px 40px -26px rgba(37,211,102,0.9)",
                    }}
                  >
                    <span className="transition-transform duration-300 group-hover:scale-110">{WaIcon}</span>
                    <span className="text-[15px] font-semibold">WhatsApp</span>
                    <span className="text-[11.5px]" style={{ color: sub }}>
                      Chat with us
                    </span>
                  </a>
                ) : (
                  <button
                    type="button"
                    onClick={actions?.onWhatsApp}
                    className="group flex flex-col items-center justify-center gap-2 rounded-3xl px-4 py-6 text-center transition-all duration-300 hover:-translate-y-1 active:scale-[0.98]"
                    style={{
                      background: "linear-gradient(150deg, rgba(37,211,102,0.22), rgba(255,255,255,0.03))",
                      border: "1px solid rgba(37,211,102,0.4)",
                      color: ink,
                      boxShadow: "0 18px 40px -26px rgba(37,211,102,0.9)",
                    }}
                  >
                    <span className="transition-transform duration-300 group-hover:scale-110">{WaIcon}</span>
                    <span className="text-[15px] font-semibold">WhatsApp</span>
                    <span className="text-[11.5px]" style={{ color: sub }}>
                      Chat with us
                    </span>
                  </button>
                )
              ) : null}
              {actions?.onWebSurvey ? (
                <button
                  type="button"
                  onClick={actions.onWebSurvey}
                  className="group flex flex-col items-center justify-center gap-2 rounded-3xl px-4 py-6 text-center transition-all duration-300 hover:-translate-y-1 active:scale-[0.98]"
                  style={{
                    background: `linear-gradient(150deg, ${alpha(accent, 0.22)}, ${alpha(accent2, 0.05)})`,
                    border: `1px solid ${alpha(accent, 0.4)}`,
                    color: ink,
                    boxShadow: `0 18px 40px -26px ${alpha(accent, 0.9)}`,
                  }}
                >
                  <span className="transition-transform duration-300 group-hover:scale-110">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.6" />
                      <path d="M3 12h18M12 3a15 15 0 010 18M12 3a15 15 0 000 18" stroke="currentColor" strokeWidth="1.4" />
                    </svg>
                  </span>
                  <span className="text-[15px] font-semibold">{webLabel}</span>
                  <span className="text-[11.5px]" style={{ color: sub }}>
                    {surveyNote}
                  </span>
                </button>
              ) : null}
            </div>
          </div>
        ) : null}

        {socials.length ? (
          <div className="animate-rise mt-4 flex items-center justify-center gap-2.5" style={{ animationDelay: "200ms" }}>
            {socials.map((s) => (
              <a
                key={s.label}
                href={s.href}
                target="_blank"
                rel="noreferrer"
                aria-label={s.label}
                className="group flex h-10 w-10 items-center justify-center rounded-full transition-all duration-300 hover:-translate-y-0.5 active:scale-95"
                style={{ background: surface, border: `1px solid ${border}`, color: ink }}
              >
                <span className="transition-transform duration-300 group-hover:scale-110">{socialIcons[s.label]}</span>
              </a>
            ))}
          </div>
        ) : null}

        <footer className="mt-auto pt-5 text-center text-[11px]" style={{ color: sub }}>
          Smart card by {card.companyName}
        </footer>
      </div>
    </main>
  );
}

export const PLACEHOLDER_CARD: SmartCardData = {
  companyName: "Acme Ltd",
  companyLogo: "",
  personName: "Alex Morgan",
  personPhoto: "",
  jobTitle: "Business Development",
  tagline: "Happy to connect — scan, save, and say hello.",
  phone: "+447700900123",
  email: "alex@acme.example",
  website: "https://voxbulk.com",
  location: "London, UK",
  instagram: "",
  linkedin: "",
  facebook: "",
  x: "",
  tiktok: "",
};
