import { Link } from "@tanstack/react-router";
import { useCallback, useEffect, useMemo, useState, type CSSProperties } from "react";
import { apiFetch } from "@/lib/api";
import { getThemePack, resolveThemeId } from "@/components/feedback-survey/theme-registry";
import type { Theme } from "@/components/feedback-survey/types";
import "@/components/feedback-survey/survey-themes.css";

type ExpoPublicPayload = {
  ok?: boolean;
  token?: string;
  wa_url?: string;
  whatsapp_url?: string;
  web_url?: string;
  theme_id?: string;
  company_name?: string;
  questions?: Array<{ key: string; prompt: string; label?: string }>;
  booth?: {
    name?: string;
    company_display_name?: string;
    exhibition_name?: string;
    is_expired?: boolean;
    closed_message?: string | null;
    question_count?: number;
  };
};

type Phase = "loading" | "error" | "choose" | "web" | "thanks" | "closed";

function themeStyleVars(theme: Theme): CSSProperties {
  return {
    "--survey-ink": theme.ink,
    "--survey-sub": theme.sub,
    "--survey-card": theme.card,
    "--survey-border": theme.border,
    "--survey-accent": theme.accent,
    "--survey-accent2": theme.accent2,
    color: theme.ink,
  } as CSSProperties;
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
    <svg
      viewBox="0 0 24 24"
      className={`h-5 w-5 shrink-0 transition-transform group-hover:translate-x-0.5 ${className}`}
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M5 12h14M13 5l7 7-7 7" />
    </svg>
  );
}

export type PublicExpoLandingProps = {
  token: string;
  /** Wizard / dashboard preview — skip API fetch */
  preview?: boolean;
  previewCompanyName?: string;
  previewEventName?: string;
  previewWaUrl?: string;
};

export function PublicExpoLanding({
  token,
  preview = false,
  previewCompanyName,
  previewEventName,
  previewWaUrl,
}: PublicExpoLandingProps) {
  const [phase, setPhase] = useState<Phase>(preview ? "choose" : "loading");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [payload, setPayload] = useState<ExpoPublicPayload | null>(
    preview
      ? {
          ok: true,
          theme_id: "survey-temp",
          company_name: previewCompanyName || "Your stand",
          wa_url: previewWaUrl || "#",
          booth: {
            company_display_name: previewCompanyName || "Your stand",
            exhibition_name: previewEventName || "Exhibition",
            is_expired: false,
          },
          questions: [],
        }
      : null,
  );
  const [sessionId, setSessionId] = useState("");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [contact, setContact] = useState({ name: "", company: "", mobile: "", email: "" });
  const [started, setStarted] = useState(false);

  const themeId = resolveThemeId(payload?.theme_id || "survey-temp");
  const company =
    payload?.booth?.company_display_name ||
    payload?.company_name ||
    previewCompanyName ||
    "Exhibitor";
  const pack = useMemo(() => getThemePack(themeId, company), [themeId, company]);
  const theme = pack.theme;
  const Art = pack.Art;
  const eventName = payload?.booth?.exhibition_name || previewEventName || "";
  const waUrl = payload?.wa_url || payload?.whatsapp_url || previewWaUrl || "";

  useEffect(() => {
    if (preview) return;
    let cancelled = false;
    (async () => {
      try {
        const data = await apiFetch<ExpoPublicPayload>(`/public/expo/${encodeURIComponent(token)}`);
        if (cancelled) return;
        setPayload(data);
        if (data?.booth?.is_expired) {
          setPhase("closed");
        } else {
          setPhase("choose");
        }
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : "Booth not found");
        setPhase("error");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token, preview]);

  const startWeb = useCallback(async () => {
    if (preview) {
      setPhase("web");
      setQuestion("What's your full name?");
      return;
    }
    setBusy(true);
    setError("");
    try {
      setPhase("web");
    } finally {
      setBusy(false);
    }
  }, [preview]);

  const submitStart = useCallback(async () => {
    if (preview) {
      setStarted(true);
      setQuestion("What is the main thing you're looking for or interested in right now?");
      return;
    }
    const mobile = contact.mobile.trim();
    const email = contact.email.trim();
    if (!mobile || !email) {
      setError("Mobile and email are required for the web path.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const res = await apiFetch<{
        ok?: boolean;
        session_id?: string;
        done?: boolean;
        question?: string;
      }>(`/public/expo/${encodeURIComponent(token)}/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          mobile,
          email,
          name: contact.name.trim() || undefined,
          company: contact.company.trim() || undefined,
        }),
      });
      if (res.done) {
        setPhase("thanks");
        return;
      }
      setSessionId(String(res.session_id || ""));
      setStarted(true);
      setQuestion(String(res.question || "Thanks — next question coming up."));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start");
    } finally {
      setBusy(false);
    }
  }, [contact, preview, token]);

  const submitAnswer = useCallback(async () => {
    const text = answer.trim();
    if (!text) return;
    if (preview) {
      setPhase("thanks");
      return;
    }
    if (!sessionId) return;
    setBusy(true);
    setError("");
    try {
      const res = await apiFetch<{
        ok?: boolean;
        done?: boolean;
        question?: string;
      }>(`/public/expo/${encodeURIComponent(token)}/answer`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, answer: text }),
      });
      setAnswer("");
      if (res.done) {
        setPhase("thanks");
        return;
      }
      setQuestion(String(res.question || ""));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save answer");
    } finally {
      setBusy(false);
    }
  }, [answer, preview, sessionId, token]);

  if (phase === "loading") {
    return (
      <main className={`grid h-[100svh] place-items-center ${theme.bgClass}`} style={themeStyleVars(theme)}>
        <p className="text-sm" style={{ color: theme.sub }}>
          Loading…
        </p>
      </main>
    );
  }

  if (phase === "error") {
    return (
      <main className={`grid h-[100svh] place-items-center px-6 ${theme.bgClass}`} style={themeStyleVars(theme)}>
        <div className="max-w-sm text-center">
          <h1 className="font-display text-2xl">Booth unavailable</h1>
          <p className="mt-2 text-sm" style={{ color: theme.sub }}>
            {error || "This Expo QR is not available."}
          </p>
          <Link to="/" className="mt-6 inline-block text-sm underline">
            Back to VoxBulk
          </Link>
        </div>
      </main>
    );
  }

  if (phase === "closed") {
    return (
      <main className={`grid h-[100svh] place-items-center px-6 ${theme.bgClass}`} style={themeStyleVars(theme)}>
        <div className="max-w-sm text-center">
          <h1 className="font-display text-2xl">Stand closed</h1>
          <p className="mt-2 text-sm" style={{ color: theme.sub }}>
            {payload?.booth?.closed_message || "This Expo stand has closed for this exhibition."}
          </p>
        </div>
      </main>
    );
  }

  if (phase === "thanks") {
    return (
      <main className={`relative grid h-[100svh] place-items-center overflow-hidden px-6 ${theme.bgClass}`} style={themeStyleVars(theme)}>
        <Art />
        <div className="relative max-w-sm text-center">
          <div
            className="mx-auto grid h-20 w-20 place-items-center rounded-full text-white shadow-lift"
            style={{ background: theme.gradientButton }}
          >
            <svg viewBox="0 0 24 24" className="h-9 w-9" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
              <path d="M5 12l5 5L20 7" />
            </svg>
          </div>
          <h1 className="mt-6 font-display text-4xl" style={{ color: theme.ink }}>
            Thanks
            <span style={{ color: theme.accent }}>.</span>
          </h1>
          <p className="mt-3 text-[15px] leading-relaxed" style={{ color: theme.sub }}>
            We&apos;ve got your details — enjoy the show.
          </p>
        </div>
      </main>
    );
  }

  if (phase === "web") {
    return (
      <main className={`relative min-h-[100svh] overflow-hidden ${theme.bgClass}`} style={themeStyleVars(theme)}>
        <Art />
        <div className="relative mx-auto flex min-h-[100svh] w-full max-w-md flex-col px-5 pb-8 pt-6">
          <header className="text-center">
            <span className="font-display text-[15px] tracking-tight">{company}</span>
            {eventName ? (
              <p className="mt-1 text-[12px]" style={{ color: theme.sub }}>
                {eventName}
              </p>
            ) : null}
          </header>
          {!started ? (
            <div className="mt-8 space-y-3">
              <h1 className="font-display text-3xl leading-tight">
                Quick intro
                <span style={{ color: theme.accent }}>.</span>
              </h1>
              <p className="text-[13px]" style={{ color: theme.sub }}>
                Web path is in English. Prefer another language? Use WhatsApp.
              </p>
              {(
                [
                  ["name", "Name"],
                  ["company", "Company"],
                  ["mobile", "Mobile *"],
                  ["email", "Email *"],
                ] as const
              ).map(([key, label]) => (
                <label key={key} className="block text-[12px] font-medium" style={{ color: theme.sub }}>
                  {label}
                  <input
                    className="mt-1 w-full rounded-xl border px-3 py-2.5 text-[15px]"
                    style={{ background: theme.card, borderColor: theme.border, color: theme.ink }}
                    value={contact[key]}
                    onChange={(e) => setContact((c) => ({ ...c, [key]: e.target.value }))}
                    autoComplete={key === "email" ? "email" : key === "mobile" ? "tel" : "off"}
                  />
                </label>
              ))}
              {error ? <p className="text-[13px] text-red-600">{error}</p> : null}
              <button
                type="button"
                disabled={busy}
                onClick={() => void submitStart()}
                className="mt-2 w-full rounded-2xl py-3.5 text-[15px] font-semibold text-white shadow-lift disabled:opacity-60"
                style={{ background: theme.gradientButton }}
              >
                Continue
              </button>
              <button
                type="button"
                className="w-full text-center text-[12px] underline"
                style={{ color: theme.sub }}
                onClick={() => setPhase("choose")}
              >
                Back to options
              </button>
            </div>
          ) : (
            <div className="mt-8 space-y-4">
              <p className="text-[11px] font-medium uppercase tracking-[0.2em]" style={{ color: theme.sub }}>
                Question
              </p>
              <h1 className="font-display text-[26px] leading-tight">{question}</h1>
              <textarea
                className="min-h-[120px] w-full rounded-2xl border px-3 py-3 text-[15px]"
                style={{ background: theme.card, borderColor: theme.border, color: theme.ink }}
                value={answer}
                onChange={(e) => setAnswer(e.target.value)}
                placeholder="Type your answer…"
              />
              {error ? <p className="text-[13px] text-red-600">{error}</p> : null}
              <button
                type="button"
                disabled={busy || !answer.trim()}
                onClick={() => void submitAnswer()}
                className="w-full rounded-2xl py-3.5 text-[15px] font-semibold text-white shadow-lift disabled:opacity-60"
                style={{ background: theme.gradientButton }}
              >
                Send answer
              </button>
            </div>
          )}
        </div>
      </main>
    );
  }

  // choose — same pattern as Customer Feedback WelcomeChoose
  const bgClass = theme.bgClass || "bg-warm-gradient";
  return (
    <main className={`relative h-[100svh] overflow-hidden ${bgClass}`} style={themeStyleVars(theme)}>
      <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="animate-float-blob absolute -left-24 top-10 h-72 w-72 rounded-full blur-3xl" style={{ background: `${theme.accent}26` }} />
        <div className="animate-float-blob-2 absolute -right-20 bottom-10 h-80 w-80 rounded-full blur-3xl" style={{ background: `${theme.accent2}4d` }} />
      </div>

      <div className="relative mx-auto flex h-[100svh] w-full max-w-md flex-col px-5 pb-5 pt-4 sm:max-w-lg sm:px-6 sm:pt-6">
        <header className="animate-rise flex flex-col items-center gap-2 text-center" style={{ animationDelay: "60ms" }}>
          <span className="font-display text-[15px] tracking-tight" style={{ color: theme.ink }}>
            {company}
          </span>
          {eventName ? (
            <p className="text-[12px]" style={{ color: theme.sub }}>
              {eventName}
            </p>
          ) : null}
        </header>

        <div className="mt-5 sm:mt-8">
          <h1
            className="animate-rise mt-2 font-display text-[34px] leading-[1.05] sm:text-5xl"
            style={{ animationDelay: "300ms", color: theme.ink }}
          >
            Nice to meet
            <br />
            <span className="italic" style={{ color: theme.ink, opacity: 0.9 }}>
              you
            </span>
            <span style={{ color: theme.accent }}>.</span>
          </h1>
          <p
            className="animate-rise mt-3 max-w-sm text-[13.5px] leading-relaxed"
            style={{ animationDelay: "400ms", color: theme.sub }}
          >
            Under a minute — choose WhatsApp (any language) or complete here in English.
          </p>
        </div>

        <div className="animate-rise mt-4" style={{ animationDelay: "480ms" }}>
          <div
            className="inline-flex items-start gap-2 rounded-full border px-3 py-1.5 text-[11.5px] leading-snug shadow-soft backdrop-blur"
            style={{ background: `${theme.card}b3`, borderColor: theme.border, color: theme.sub }}
          >
            <span aria-hidden>🌍</span>
            <span>WhatsApp = all languages · Web = English</span>
          </div>
        </div>

        <div className="mt-5 grid gap-3">
          {waUrl ? (
            <a
              href={preview ? undefined : waUrl}
              target={preview ? undefined : "_blank"}
              rel={preview ? undefined : "noopener noreferrer"}
              onClick={preview ? (e) => e.preventDefault() : undefined}
              className="animate-rise group relative overflow-hidden rounded-2xl p-4 text-left shadow-lift transition-transform active:scale-[0.98] hover:-translate-y-0.5"
              style={{ animationDelay: "560ms", background: "#25D366", color: "#fff" }}
            >
              <div className="flex items-center gap-3.5">
                <span className="animate-float-icon shrink-0">
                  <WhatsAppGlyph />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="text-[15.5px] font-semibold tracking-tight">Continue on WhatsApp</div>
                  <div className="mt-0.5 text-[11.5px] opacity-85">💬 Reply in your own language · voice OK</div>
                </div>
                <ArrowGlyph />
              </div>
            </a>
          ) : null}

          <button
            type="button"
            disabled={busy}
            onClick={() => void startWeb()}
            className="animate-rise group relative overflow-hidden rounded-2xl border p-4 text-left shadow-soft transition-transform active:scale-[0.98] hover:-translate-y-0.5 disabled:opacity-60"
            style={{ animationDelay: "640ms", background: theme.card, borderColor: theme.border, color: theme.ink }}
          >
            <div className="flex items-center gap-3.5">
              <span className="animate-float-icon shrink-0" style={{ color: theme.ink }}>
                <SparkGlyph />
              </span>
              <div className="min-w-0 flex-1">
                <div className="text-[15.5px] font-semibold tracking-tight">Complete here</div>
                <div className="mt-0.5 text-[11.5px]" style={{ color: theme.sub }}>
                  Quick on-page form · English
                </div>
              </div>
              <ArrowGlyph className="opacity-60" />
            </div>
          </button>
        </div>

        {error ? <p className="mt-3 text-center text-[13px] text-red-600">{error}</p> : null}

        <footer className="animate-rise mt-auto pt-4 text-center text-[10.5px]" style={{ animationDelay: "780ms", color: theme.sub, opacity: 0.8 }}>
          Your reply is private and only shared with {company}.
        </footer>
      </div>
    </main>
  );
}
