import * as React from "react";

import { SmartCardTemplate, type SmartCardData } from "@/components/smart-card/SmartCardTemplate";
import {
  getSmartCardThemeTokens,
  normalizeSmartCardThemeId,
  SmartCardThemeArt,
  type SmartCardThemeId,
} from "@/components/smart-card/smart-card-themes";
import type { DeliveredAsset } from "@/components/smart-card/SmartCardWebSession";

const SmartCardWebSession = React.lazy(() =>
  import("@/components/smart-card/SmartCardWebSession").then((m) => ({ default: m.SmartCardWebSession })),
);

const API = (import.meta as any).env?.VITE_API_URL || "https://api.voxbulk.com";

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
  theme_id?: string | null;
  representative?: {
    name?: string;
    email?: string;
    website?: string;
    mobile?: string;
    landline?: string;
    job_title?: string | null;
    location?: string | null;
    address?: string | null;
    social_links?: SocialLinks | null;
    photo_url?: string | null;
  };
  company?: {
    name?: string;
    website?: string;
    description?: string;
    tagline?: string | null;
    location?: string | null;
    location_label?: string | null;
    address?: string | null;
    logo_url?: string | null;
    logo_tone?: string | null;
  };
};

type Phase = "card" | "web" | "done" | "blocked";

function mediaUrl(path?: string | null): string | null {
  if (!path) return null;
  if (/^https?:\/\//i.test(path)) return path;
  return `${API}${path}`;
}

function ensureHttp(url: string) {
  const u = url.trim();
  if (!u) return u;
  if (/^https?:\/\//i.test(u) || u.startsWith("mailto:") || u.startsWith("tel:")) return u;
  return `https://${u}`;
}

export function PublicSmartCardLanding({
  token,
  themeOverride,
  themePreviewLabel,
}: {
  token: string;
  themeOverride?: SmartCardThemeId | string;
  /** When set (theme picker scan), show banner and use override theme with live card data */
  themePreviewLabel?: string;
}) {
  const [meta, setMeta] = React.useState<CardMeta | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [phase, setPhase] = React.useState<Phase>("card");
  const [doneMsg, setDoneMsg] = React.useState("Thank you");
  const [doneAssets, setDoneAssets] = React.useState<DeliveredAsset[]>([]);
  const [blockMessage, setBlockMessage] = React.useState<string | undefined>();
  const [webRunId, setWebRunId] = React.useState(0);

  React.useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const shellRes = await fetch(`${API}/public/smart-card/${encodeURIComponent(token)}`);
        const shell = await shellRes.json();
        if (!shellRes.ok) {
          throw new Error(typeof shell?.detail === "string" ? shell.detail : "Not found");
        }
        if (cancelled) return;
        setMeta(shell);
        if (shell.status === "expired" || shell.status === "preview_exhausted") {
          setPhase("blocked");
          return;
        }
        const revealRes = await fetch(`${API}/public/smart-card/${encodeURIComponent(token)}/reveal`, {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: "{}",
        });
        const full = await revealRes.json().catch(() => ({}));
        if (cancelled) return;
        if (!revealRes.ok) {
          // Keep shell (names/photos) visible; contact fields stay empty until retry.
          setError(typeof full?.detail === "string" ? full.detail : "Could not load contact details");
          return;
        }
        setMeta(full);
        setError(null);
      } catch (e: any) {
        if (!cancelled) setError(e?.message || "Failed to load");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  const themeId = normalizeSmartCardThemeId(themeOverride || meta?.theme_id);
  const tokens = getSmartCardThemeTokens(themeId);

  const rep = meta?.representative;
  const company = meta?.company;
  const personName = rep?.name || "Representative";
  const companyName = company?.name || "Company";
  const jobTitle = (rep?.job_title || "").trim();
  const tagline = (company?.tagline || company?.description || "").trim();
  const location = (company?.address || company?.location || rep?.address || rep?.location || "").trim();
  const address = (company?.address || rep?.address || location).trim();
  const phone = (rep?.mobile || rep?.landline || "").trim();
  const email = (rep?.email || "").trim();
  const website = (rep?.website || company?.website || "").trim();
  const socials = rep?.social_links || {};
  const photoSrc = mediaUrl(rep?.photo_url) || "";
  const logoSrc = mediaUrl(company?.logo_url) || "";
  const waHref =
    meta?.feedback_whatsapp_url ||
    meta?.whatsapp_url ||
    (phone
      ? `https://wa.me/${phone.replace(/\D/g, "")}?text=${encodeURIComponent("Hi! I'd like to get in touch.")}`
      : null);

  const card: SmartCardData = {
    companyName,
    companyLogo: logoSrc,
    companyLogoTone: company?.logo_tone || null,
    personName,
    personPhoto: photoSrc,
    jobTitle,
    tagline,
    phone,
    email,
    website: website ? ensureHttp(website) : "",
    location,
    address,
    instagram: socials.instagram ? ensureHttp(socials.instagram) : "",
    linkedin: socials.linkedin ? ensureHttp(socials.linkedin) : "",
    facebook: socials.facebook ? ensureHttp(socials.facebook) : "",
    x: socials.x ? ensureHttp(socials.x) : "",
    tiktok: socials.tiktok ? ensureHttp(socials.tiktok) : "",
  };

  const startWeb = () => {
    setError(null);
    setWebRunId((n) => n + 1);
    setPhase("web");
  };

  if (error && !meta) {
    return (
      <main className={`${tokens.bgClass} relative flex min-h-dvh items-center justify-center p-6`}>
        <p className="text-rose-300">{error}</p>
      </main>
    );
  }

  if (!meta) {
    return (
      <main className={`${tokens.bgClass} relative flex min-h-dvh items-center justify-center p-6`}>
        <p style={{ color: tokens.sub }}>Loading…</p>
      </main>
    );
  }

  if (phase === "blocked") {
    return (
      <main className={`${tokens.bgClass} relative min-h-dvh overflow-hidden`}>
        <SmartCardThemeArt themeId={themeId} />
        <div className="relative mx-auto flex min-h-dvh max-w-md flex-col justify-center px-5 py-10 text-center">
          <h1 className="font-display text-[22px] font-semibold" style={{ color: tokens.ink }}>
            {companyName}
          </h1>
          <p className="mt-3 text-[14px] leading-relaxed" style={{ color: tokens.sub }}>
            {blockMessage || meta.message || "This Smart Card QR is unavailable."}
          </p>
          {meta.renew_url ? (
            <a
              href={meta.renew_url}
              target="_blank"
              rel="noreferrer"
              className="mt-6 inline-flex items-center justify-center rounded-2xl px-4 py-3 text-[14px] font-semibold"
              style={{
                background: `linear-gradient(135deg,${tokens.accent},${tokens.accent2})`,
                color: tokens.onAccent,
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
      <main className={`${tokens.bgClass} relative min-h-dvh overflow-hidden`}>
        <SmartCardThemeArt themeId={themeId} />
        <div className="relative mx-auto flex min-h-dvh max-w-md flex-col items-center justify-center px-5 text-center">
          <div
            className="flex h-16 w-16 items-center justify-center rounded-2xl text-2xl"
            style={{
              background: `linear-gradient(135deg,${tokens.accent},${tokens.accent2})`,
              color: tokens.onAccent,
            }}
          >
            ✓
          </div>
          <h1 className="font-display mt-5 text-[24px] font-semibold" style={{ color: tokens.ink }}>
            Thank you
          </h1>
          <p className="mt-2 text-[14px] leading-relaxed" style={{ color: tokens.sub }}>
            {doneMsg}
          </p>
          {doneAssets.length ? (
            <div className="mt-6 w-full max-w-sm">
              <p className="text-[11px] font-medium uppercase tracking-[0.2em]" style={{ color: tokens.sub }}>
                Your documents
              </p>
              <div className="mt-3 grid gap-2.5">
                {doneAssets.map((asset) => (
                  <a
                    key={asset.id}
                    href={asset.url}
                    target="_blank"
                    rel="noreferrer"
                    download={asset.filename}
                    className="flex items-center gap-3 rounded-2xl px-4 py-3 text-left text-[14px] font-medium"
                    style={{
                      background: tokens.surface,
                      border: `1px solid ${tokens.border}`,
                      color: tokens.ink,
                    }}
                  >
                    <span aria-hidden>📄</span>
                    {asset.title || "Download"}
                  </a>
                ))}
              </div>
              <p className="mt-3 text-[12px]" style={{ color: tokens.sub }}>
                We have emailed these to you as attachments too.
              </p>
            </div>
          ) : null}
          <button
            type="button"
            onClick={() => setPhase("card")}
            className="mt-8 rounded-2xl px-4 py-2.5 text-[13px] font-medium"
            style={{ background: tokens.surface, border: `1px solid ${tokens.border}`, color: tokens.ink }}
          >
            Back to card
          </button>
        </div>
      </main>
    );
  }

  if (phase === "web") {
    return (
      <React.Suspense
        fallback={
          <main className={`${tokens.bgClass} relative flex min-h-dvh items-center justify-center`}>
            <p className="text-sm" style={{ color: tokens.sub }}>
              Loading…
            </p>
          </main>
        }
      >
        <SmartCardWebSession
          key={webRunId}
          token={token}
          companyName={companyName}
          themeId={themeId}
          onDone={(msg, assets) => {
            setDoneMsg(msg);
            setDoneAssets(assets || []);
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
      </React.Suspense>
    );
  }

  return (
    <SmartCardTemplate
      card={card}
      tokens={tokens}
      actions={{
        whatsappHref: waHref,
        onWebSurvey: startWeb,
        trackEvent: (eventType) => {
          const url = `${API}/public/smart-card/${encodeURIComponent(token)}/events`;
          const body = JSON.stringify({ event_type: eventType });
          try {
            if (typeof navigator !== "undefined" && typeof navigator.sendBeacon === "function") {
              const blob = new Blob([body], { type: "application/json" });
              if (navigator.sendBeacon(url, blob)) return;
            }
          } catch {
            /* fall through */
          }
          void fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body,
            keepalive: true,
          }).catch(() => undefined);
        },
        previewBanner: themePreviewLabel ? (
          <p
            className="mt-4 rounded-full px-3 py-1 text-center text-[11px] font-medium"
            style={{
              background: "rgba(251,191,36,0.15)",
              color: "#fbbf24",
              border: "1px solid rgba(251,191,36,0.35)",
            }}
          >
            Theme preview — {themePreviewLabel}
          </p>
        ) : meta.status === "preview" && typeof meta.preview_tests_remaining === "number" ? (
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
        ) : null,
      }}
    />
  );
}
