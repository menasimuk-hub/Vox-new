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
  address?: string;
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

/** Dual-tone plate: readable for both white and dark logos without canvas sampling. */
function CompanyLogoBadge({ src, companyName }: { src: string; companyName: string }) {
  return (
    <div
      className="flex h-6 max-w-[104px] shrink-0 items-center justify-center rounded-md px-1 py-0.5"
      style={{
        background:
          "linear-gradient(145deg, rgba(255,255,255,0.9) 0%, rgba(248,250,252,0.7) 50%, rgba(15,23,42,0.22) 100%)",
        border: "1px solid rgba(255,255,255,0.4)",
        boxShadow: "0 0 12px rgba(255,255,255,0.28), 0 4px 12px -8px rgba(0,0,0,0.35)",
      }}
    >
      <img
        src={src}
        alt={`${companyName} logo`}
        width={96}
        height={20}
        decoding="async"
        fetchPriority="high"
        className="h-4 w-auto max-w-[96px] object-contain"
      />
    </div>
  );
}

const WaIcon = (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
    <path d="M12.04 2A9.9 9.9 0 002.1 11.9c0 1.75.46 3.45 1.32 4.95L2 22l5.3-1.38a9.9 9.9 0 0014.74-8.72A9.9 9.9 0 0012.04 2zm5.8 14.05c-.24.68-1.4 1.3-1.94 1.34-.5.04-1.12.06-1.81-.11a15.5 15.5 0 01-6.6-4.6c-.44-.58-1.17-1.68-1.17-3.2 0-1.52.8-2.27 1.08-2.58.28-.31.6-.39.8-.39l.58.01c.19 0 .44-.07.68.52.25.6.85 2.08.93 2.23.07.15.12.33.02.53-.1.2-.15.32-.3.5l-.44.51c-.15.15-.3.32-.13.62.17.3.76 1.25 1.63 2.03 1.12 1 2.07 1.31 2.37 1.46.3.15.47.13.65-.08.17-.2.75-.87.95-1.17.2-.3.4-.25.67-.15.27.1 1.72.81 2.02.96.3.15.5.22.57.35.07.13.07.74-.17 1.42z" />
  </svg>
);

const socialIcons: Record<string, React.ReactNode> = {
  Instagram: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
      <rect x="3" y="3" width="18" height="18" rx="5" stroke="currentColor" strokeWidth="1.6" />
      <circle cx="12" cy="12" r="4" stroke="currentColor" strokeWidth="1.6" />
      <circle cx="17.2" cy="6.8" r="1.1" fill="currentColor" />
    </svg>
  ),
  LinkedIn: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
      <path d="M4.98 3.5a2.5 2.5 0 11-.02 5 2.5 2.5 0 01.02-5zM3 9h4v12H3V9zm7 0h3.8v1.7h.05c.53-.95 1.83-1.95 3.77-1.95 4.03 0 4.78 2.5 4.78 5.75V21h-4v-5.6c0-1.34-.02-3.07-1.9-3.07-1.9 0-2.2 1.45-2.2 2.97V21h-4V9z" />
    </svg>
  ),
  Facebook: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
      <path d="M13.5 21v-8h2.7l.4-3.1h-3.1V7.9c0-.9.25-1.5 1.55-1.5H16.7V3.6c-.3-.04-1.3-.13-2.47-.13-2.45 0-4.13 1.5-4.13 4.25V9.9H7.4V13h2.7v8h3.4z" />
    </svg>
  ),
  X: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
      <path d="M17.5 3h3.1l-6.8 7.8L21.8 21h-6.1l-4.8-6.2L5.4 21H2.3l7.3-8.3L2.4 3h6.3l4.3 5.7L17.5 3zm-1.1 16.1h1.7L7.7 4.8H5.9l10.5 14.3z" />
    </svg>
  ),
  TikTok: (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor">
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
  const { ink, sub, border, surface, accent, accent2, accent3, onAccent, radius, bgClass, id } = tokens;

  const socials = [
    { label: "Instagram", href: card.instagram },
    { label: "LinkedIn", href: card.linkedin },
    { label: "Facebook", href: card.facebook },
    { label: "X", href: card.x },
    { label: "TikTok", href: card.tiktok },
  ].filter((s) => isSet(s.href));

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
    const enabled = href && href !== "#";
    return (
      <a
        href={enabled ? href : undefined}
        onClick={(e) => {
          if (!enabled) e.preventDefault();
        }}
        className="flex flex-col items-center gap-1 rounded-xl px-1 py-2 text-center transition active:scale-[0.98]"
        style={{
          color: ink,
          background: enabled ? glow : "transparent",
          opacity: enabled ? 1 : 0.4,
          pointerEvents: enabled ? "auto" : "none",
        }}
        aria-disabled={!enabled}
      >
        <span
          className="flex h-9 w-9 items-center justify-center rounded-full"
          style={{ background: surface, border: `1px solid ${border}` }}
        >
          {children}
        </span>
        <span className="text-[10px] font-medium tracking-wide" style={{ color: sub }}>
          {label}
        </span>
      </a>
    );
  };

  const saveContact = () => {
    const lines = [
      "BEGIN:VCARD",
      "VERSION:3.0",
      `FN:${card.personName}`,
      `ORG:${card.companyName}`,
      isSet(card.jobTitle) ? `TITLE:${card.jobTitle}` : "",
      isSet(card.phone) ? `TEL;TYPE=CELL:${card.phone}` : "",
      isSet(card.email) ? `EMAIL:${card.email}` : "",
      isSet(card.website) ? `URL:${card.website}` : "",
      isSet(card.address || card.location) ? `ADR;TYPE=WORK:;;${card.address || card.location};;;;` : "",
      "END:VCARD",
    ]
      .filter(Boolean)
      .join("\n");
    const blob = new Blob([lines], { type: "text/vcard" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${card.personName.replace(/\s+/g, "-") || "contact"}.vcf`;
    a.click();
    URL.revokeObjectURL(url);
    setSaved(true);
  };

  const share = async () => {
    const url = typeof window !== "undefined" ? window.location.href : "";
    try {
      if (navigator.share) {
        await navigator.share({ title: card.personName, text: card.companyName, url });
        return;
      }
    } catch {
      /* fall through */
    }
    try {
      await navigator.clipboard.writeText(url);
    } catch {
      /* ignore */
    }
  };

  const waHref = actions?.whatsappHref;
  const webLabel = actions?.webSurveyLabel || "Contact us";
  const mapsQuery = isSet(card.address) ? card.address : card.location;
  const addressLine = isSet(card.address) ? card.address : isSet(card.location) ? card.location : "";

  return (
    <main className={`smartcard-root ${bgClass} relative min-h-dvh w-full overflow-hidden`}>
      <SmartCardThemeArt themeId={id} />
      <div className="relative mx-auto flex min-h-dvh w-full max-w-sm flex-col px-3.5 pb-4 pt-4">
        <section
          className="relative overflow-hidden px-3.5 pb-3.5 pt-3.5"
          style={{
            borderRadius: Math.min(radius, 18),
            background: `linear-gradient(160deg, ${surface}, ${alpha(accent, 0.04)})`,
            border: `1px solid ${border}`,
            boxShadow: `0 16px 40px -28px ${alpha(accent, 0.55)}`,
          }}
        >
          <div className="flex items-center gap-2">
            {isSet(card.companyLogo) ? (
              <CompanyLogoBadge src={card.companyLogo} companyName={card.companyName} />
            ) : (
              <div
                className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-[10px] font-bold"
                style={{ background: `linear-gradient(135deg, ${accent}, ${accent2})`, color: onAccent }}
              >
                ✦
              </div>
            )}
            <span className="min-w-0 truncate text-[12px] font-semibold tracking-wide" style={{ color: ink }}>
              {card.companyName}
            </span>
          </div>

          <div className="mt-3 flex items-center gap-3">
            <div
              className="flex h-14 w-14 shrink-0 items-center justify-center overflow-hidden rounded-full text-[18px] font-semibold"
              style={{
                background: `linear-gradient(140deg, ${alpha(accent, 0.35)}, ${alpha(accent2, 0.35)})`,
                border: `1.5px solid ${alpha(accent, 0.45)}`,
                color: ink,
              }}
            >
              {isSet(card.personPhoto) ? (
                <img
                  src={card.personPhoto}
                  alt={card.personName}
                  width={56}
                  height={56}
                  decoding="async"
                  fetchPriority="high"
                  className="h-full w-full object-cover"
                />
              ) : (
                initials(card.personName)
              )}
            </div>
            <div className="min-w-0">
              <h1 className="truncate text-[18px] font-semibold leading-tight" style={{ color: ink }}>
                {card.personName}
              </h1>
              {isSet(card.jobTitle) ? (
                <p className="mt-0.5 text-[11.5px] font-medium tracking-wide" style={{ color: accent }}>
                  {card.jobTitle}
                </p>
              ) : null}
              {isSet(card.tagline) ? (
                <p className="mt-1 line-clamp-2 text-[11px] leading-snug" style={{ color: sub }}>
                  {card.tagline}
                </p>
              ) : null}
              {isSet(addressLine) ? (
                <p className="mt-1 line-clamp-2 text-[11px] leading-snug" style={{ color: sub }}>
                  {addressLine}
                </p>
              ) : null}
            </div>
          </div>

          {actions?.previewBanner}

          <div className="mt-3 grid grid-cols-4 gap-1 border-t pt-3" style={{ borderColor: border }}>
            <IconLink href={isSet(card.phone) ? `tel:${card.phone}` : "#"} label="Call" glow={alpha(accent, 0.12)}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                <path d="M6.5 3h3l1.5 4-2 1.5a12 12 0 006.5 6.5l1.5-2 4 1.5v3a2 2 0 01-2.2 2A17 17 0 014.5 5.2 2 2 0 016.5 3z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
              </svg>
            </IconLink>
            <IconLink href={isSet(card.email) ? `mailto:${card.email}` : "#"} label="Email" glow={alpha(accent2, 0.12)}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                <rect x="3" y="5" width="18" height="14" rx="2.5" stroke="currentColor" strokeWidth="1.6" />
                <path d="M4 7l8 6 8-6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
              </svg>
            </IconLink>
            <IconLink href={isSet(card.website) ? card.website : "#"} label="Website" glow={alpha(accent3, 0.12)}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.6" />
                <path d="M3 12h18M12 3a15 15 0 010 18M12 3a15 15 0 000 18" stroke="currentColor" strokeWidth="1.4" />
              </svg>
            </IconLink>
            <IconLink
              href={isSet(mapsQuery) ? `https://maps.google.com/?q=${encodeURIComponent(mapsQuery)}` : "#"}
              label="Location"
              glow={alpha(accent3, 0.14)}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                <path d="M12 21s7-5.5 7-11a7 7 0 10-14 0c0 5.5 7 11 7 11z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
                <circle cx="12" cy="10" r="2.4" stroke="currentColor" strokeWidth="1.6" />
              </svg>
            </IconLink>
          </div>
        </section>

        <div className="mt-3 grid grid-cols-2 gap-2">
          <button
            type="button"
            onClick={saveContact}
            className="px-3 py-2.5 text-[13px] font-semibold active:scale-[0.98]"
            style={{
              borderRadius: "14px",
              background: `linear-gradient(135deg, ${accent}, ${accent2})`,
              color: onAccent,
            }}
          >
            {saved ? "Saved ✓" : "Save contact"}
          </button>
          <button
            type="button"
            onClick={() => void share()}
            className="px-3 py-2.5 text-[13px] font-semibold active:scale-[0.98]"
            style={{ borderRadius: "14px", background: surface, border: `1px solid ${border}`, color: ink }}
          >
            Share card
          </button>
        </div>

        {!actions?.hideFeedback ? (
          <div className="mt-3">
            <p className="mb-2 text-center text-[10px] font-semibold uppercase tracking-[0.16em]" style={{ color: sub }}>
              Contact us · post your request
            </p>
            <div className="grid grid-cols-2 gap-2">
              {waHref || actions?.onWhatsApp ? (
                waHref && !actions?.onWhatsApp ? (
                  <a
                    href={waHref}
                    target="_blank"
                    rel="noreferrer"
                    className="flex flex-col items-center justify-center gap-1 rounded-2xl px-3 py-3.5 text-center active:scale-[0.98]"
                    style={{
                      background: "linear-gradient(150deg, rgba(37,211,102,0.2), rgba(255,255,255,0.03))",
                      border: "1px solid rgba(37,211,102,0.35)",
                      color: ink,
                    }}
                  >
                    {WaIcon}
                    <span className="text-[13px] font-semibold">Contact us</span>
                    <span className="text-[10.5px]" style={{ color: sub }}>
                      via WhatsApp
                    </span>
                  </a>
                ) : (
                  <button
                    type="button"
                    onClick={actions?.onWhatsApp}
                    className="flex flex-col items-center justify-center gap-1 rounded-2xl px-3 py-3.5 text-center active:scale-[0.98]"
                    style={{
                      background: "linear-gradient(150deg, rgba(37,211,102,0.2), rgba(255,255,255,0.03))",
                      border: "1px solid rgba(37,211,102,0.35)",
                      color: ink,
                    }}
                  >
                    {WaIcon}
                    <span className="text-[13px] font-semibold">Contact us</span>
                    <span className="text-[10.5px]" style={{ color: sub }}>
                      via WhatsApp
                    </span>
                  </button>
                )
              ) : null}
              {actions?.onWebSurvey ? (
                <button
                  type="button"
                  onClick={actions.onWebSurvey}
                  className="flex flex-col items-center justify-center gap-1 rounded-2xl px-3 py-3.5 text-center active:scale-[0.98]"
                  style={{
                    background: `linear-gradient(150deg, ${alpha(accent, 0.2)}, ${alpha(accent2, 0.04)})`,
                    border: `1px solid ${alpha(accent, 0.35)}`,
                    color: ink,
                  }}
                >
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden>
                    <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.6" />
                    <path d="M3 12h18M12 3a15 15 0 010 18M12 3a15 15 0 000 18" stroke="currentColor" strokeWidth="1.4" />
                  </svg>
                  <span className="text-[13px] font-semibold">{webLabel}</span>
                  <span className="text-[10.5px]" style={{ color: sub }}>
                    via web · post your request
                  </span>
                </button>
              ) : null}
            </div>
          </div>
        ) : null}

        {socials.length ? (
          <div className="mt-3 flex items-center justify-center gap-2">
            {socials.map((s) => (
              <a
                key={s.label}
                href={s.href}
                target="_blank"
                rel="noreferrer"
                aria-label={s.label}
                className="flex h-8 w-8 items-center justify-center rounded-full active:scale-95"
                style={{ background: surface, border: `1px solid ${border}`, color: ink }}
              >
                {socialIcons[s.label]}
              </a>
            ))}
          </div>
        ) : null}

        <footer className="mt-auto pt-3 text-center text-[10px]" style={{ color: sub }}>
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
