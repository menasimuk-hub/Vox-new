import { Link } from "@tanstack/react-router";
import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { apiFetch, apiUpload, getApiBaseUrl } from "@/lib/api";
import { buildCopy, getThemePack, resolveThemeId } from "@/components/feedback-survey/theme-registry";
import type { Theme } from "@/components/feedback-survey/types";
import { VoiceDetail, type VoiceDetailHandle } from "@/components/feedback-survey/VoiceDetail";
import "@/components/feedback-survey/survey-themes.css";

const EXPO_THEME_ID = "expo";
const EXPO_SERVICE_LABEL = "Expo & Professional Services";

type ExpoOption = { value: string; label: string };
type ExpoQuestion = {
  key: string;
  prompt: string;
  label?: string;
  input?: string;
  options?: ExpoOption[];
  allow_voice?: boolean;
};

type ExpoPublicPayload = {
  ok?: boolean;
  token?: string;
  wa_url?: string;
  whatsapp_url?: string;
  web_url?: string;
  theme_id?: string;
  company_name?: string;
  logo_url?: string | null;
  contact_capture?: string;
  questions?: ExpoQuestion[];
  assets?: ExpoAsset[];
  step_total?: number;
  booth?: {
    name?: string;
    company_display_name?: string;
    exhibition_name?: string;
    is_expired?: boolean;
    closed_message?: string | null;
    contact_capture?: string;
    question_count?: number;
  };
};

type ExpoAsset = {
  id?: string;
  title?: string;
  short_description?: string;
  kind?: string;
  purpose?: string;
  url?: string;
};

type ExpoSummary = {
  name?: string | null;
  company?: string | null;
  email?: string | null;
  mobile?: string | null;
  interest?: string | null;
  timeline?: string | null;
  answers?: Array<{ key?: string; answer?: string }>;
};

type AdvanceResult = {
  ok?: boolean;
  session_id?: string;
  done?: boolean;
  question?: string;
  question_key?: string;
  contact_substep?: string;
  input?: string;
  options?: ExpoOption[];
  allow_voice?: boolean;
  awaiting_pick?: boolean;
  candidates?: Array<{ id?: string; title?: string; short_description?: string }>;
  assets?: ExpoAsset[] | unknown;
  asset_options?: ExpoAsset[] | unknown;
  card_fields?: Record<string, string | null>;
  error?: string;
  summary?: ExpoSummary;
  company_card?: string | null;
  representatives?: Array<{
    name?: string;
    company_name?: string;
    email?: string;
    mobile?: string;
    telephone?: string;
    website?: string;
  }> | null;
  company_website?: string | null;
  company_logo_url?: string | null;
  vcard_url?: string | null;
  at_start?: boolean;
  step_index?: number;
  step_total?: number;
};

type Phase = "loading" | "error" | "choose" | "web" | "thanks" | "closed";
type WebStep = "contact" | "confirm" | "question" | "pick";

type LiveQuestion = {
  key: string;
  prompt: string;
  input: string;
  options: ExpoOption[];
  allow_voice: boolean;
};

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

function logoSrc(logoUrl?: string | null) {
  if (!logoUrl) return "";
  return `${getApiBaseUrl().replace(/\/+$/, "")}${logoUrl}`;
}

function WhatsAppGlyph() {
  return (
    <svg viewBox="0 0 32 32" className="h-9 w-9" fill="currentColor" aria-hidden>
      <path d="M16 3C8.82 3 3 8.82 3 16c0 2.29.6 4.43 1.66 6.29L3 29l6.9-1.62A12.94 12.94 0 0 0 16 29c7.18 0 13-5.82 13-13S23.18 3 16 3Zm7.4 18.46c-.31.87-1.82 1.66-2.5 1.71-.66.05-1.31.27-4.4-.93-3.71-1.45-6.07-5.27-6.25-5.52-.18-.25-1.5-1.99-1.5-3.8 0-1.81.95-2.69 1.28-3.07.34-.37.74-.46.99-.46.25 0 .49 0 .71.01.23.01.53-.09.83.64.31.74 1.05 2.55 1.14 2.73.09.18.15.4.03.65-.12.25-.18.4-.37.61-.18.21-.39.47-.55.63-.18.18-.37.39-.16.74.21.34.94 1.55 2.02 2.5 1.39 1.23 2.56 1.6 2.9 1.78.34.18.55.15.74-.09.21-.25.86-1 1.09-1.34.22-.34.46-.28.77-.17.31.12 1.97.93 2.31 1.1.34.17.56.25.65.39.09.13.09.74-.22 1.61Z" />
    </svg>
  );
}

/** High-contrast download control for the dark Expo theme (avoids blue-on-blue). */
function DownloadGlyph({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" aria-hidden>
      <path
        d="M12 3v12m0 0l-4-4m4 4l4-4M4 19h16"
        stroke="currentColor"
        strokeWidth="2.25"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

const DOWNLOAD_BTN_STYLE = {
  background: "#ffffff",
  color: "#0f172a",
  border: "1px solid rgba(255,255,255,0.95)",
  boxShadow: "0 10px 28px -12px rgba(15,23,42,0.55)",
} as const;

function storageKey(token: string) {
  return `expo:web:${token}`;
}

type StoredWebSession = {
  sessionId: string;
  webStep?: WebStep;
  progressIndex?: number;
  progressTotal?: number;
  contact?: { name: string; company: string; mobile: string; email: string };
  downloadAssets?: ExpoAsset[];
  updatedAt?: number;
};

function readStoredSession(token: string): StoredWebSession | null {
  try {
    const raw = localStorage.getItem(storageKey(token));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as StoredWebSession;
    if (!parsed?.sessionId) return null;
    return parsed;
  } catch {
    return null;
  }
}

function writeStoredSession(token: string, data: StoredWebSession) {
  try {
    localStorage.setItem(storageKey(token), JSON.stringify({ ...data, updatedAt: Date.now() }));
  } catch {
    /* ignore quota */
  }
}

function clearStoredSession(token: string) {
  try {
    localStorage.removeItem(storageKey(token));
  } catch {
    /* ignore */
  }
}

function purposeBadge(purpose?: string) {
  const p = String(purpose || "").toLowerCase();
  if (p === "catalogue") return "Catalogue";
  if (p === "price_list") return "Price list";
  if (p === "product") return "Product";
  return "File";
}

async function downloadSameTab(url: string, filename: string, onBusy?: (v: boolean) => void) {
  if (!url || url === "#") return;
  onBusy?.(true);
  try {
    const res = await fetch(url, { credentials: "omit" });
    if (!res.ok) throw new Error(`download_failed_${res.status}`);
    const blob = await res.blob();
    const objectUrl = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = objectUrl;
    a.download = filename || "download.pdf";
    a.rel = "noopener";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(objectUrl);
  } catch {
    // Fallback: navigate same tab (still no target=_blank)
    window.location.assign(url);
  } finally {
    onBusy?.(false);
  }
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
          theme_id: EXPO_THEME_ID,
          company_name: previewCompanyName || "Your stand",
          wa_url: previewWaUrl || "#",
          contact_capture: "offer_both",
          booth: {
            company_display_name: previewCompanyName || "Your stand",
            exhibition_name: previewEventName || "Exhibition",
            is_expired: false,
            contact_capture: "offer_both",
          },
          questions: [
            {
              key: "contact",
              prompt: "Upload a business card or enter your details",
              input: "contact",
              options: [],
            },
            {
              key: "interest",
              prompt: "What are you looking for today at our stand?",
              input: "text",
              allow_voice: true,
              options: [],
            },
            {
              key: "role",
              prompt: "Which best describes your role?",
              input: "choice",
              options: [
                { value: "Buyer", label: "Buyer / purchasing" },
                { value: "Specifier", label: "Specifier / technical" },
                { value: "Influencer", label: "Influencer / recommender" },
              ],
            },
            {
              key: "timeline",
              prompt: "When are you planning to decide or take the next step?",
              input: "choice",
              options: [
                { value: "This week", label: "This week" },
                { value: "This month", label: "This month" },
                { value: "Later", label: "Later" },
              ],
            },
          ],
        }
      : null,
  );

  const [sessionId, setSessionId] = useState("");
  const [webStep, setWebStep] = useState<WebStep>("contact");
  const [liveQ, setLiveQ] = useState<LiveQuestion | null>(null);
  const [selectedValue, setSelectedValue] = useState("");
  const [textAnswer, setTextAnswer] = useState("");
  const [contact, setContact] = useState({ name: "", company: "", mobile: "", email: "" });
  const [cardPreview, setCardPreview] = useState<string | null>(null);
  const [cardFile, setCardFile] = useState<File | null>(null);
  const [candidates, setCandidates] = useState<Array<{ id?: string; title?: string; short_description?: string }>>([]);
  const [progressIndex, setProgressIndex] = useState(1);
  const [progressTotal, setProgressTotal] = useState(6);
  const [selectedValues, setSelectedValues] = useState<string[]>([]);
  const [downloadAssets, setDownloadAssets] = useState<ExpoAsset[]>([]);
  const [summary, setSummary] = useState<ExpoSummary | null>(null);
  const [companyCard, setCompanyCard] = useState<string | null>(null);
  const [representatives, setRepresentatives] = useState<
    Array<{
      name?: string;
      company_name?: string;
      email?: string;
      mobile?: string;
      telephone?: string;
      website?: string;
    }>
  >([]);
  const [companyWebsite, setCompanyWebsite] = useState<string | null>(null);
  const [companyLogoUrl, setCompanyLogoUrl] = useState<string | null>(null);
  const [vcardUrl, setVcardUrl] = useState<string | null>(null);
  const cardInputRef = useRef<HTMLInputElement>(null);
  const voiceRef = useRef<VoiceDetailHandle>(null);
  const sessionIdRef = useRef("");
  const isDownloadingRef = useRef(false);
  const suppressStopRef = useRef(false);
  sessionIdRef.current = sessionId;

  const questions = useMemo(
    () => (payload?.questions || []).filter((q) => q.key !== "contact"),
    [payload?.questions],
  );
  const contactCapture =
    payload?.contact_capture || payload?.booth?.contact_capture || "offer_both";

  const themeId = resolveThemeId(payload?.theme_id || EXPO_THEME_ID);
  const company =
    payload?.booth?.company_display_name ||
    payload?.company_name ||
    previewCompanyName ||
    "Exhibitor";
  const pack = useMemo(() => getThemePack(themeId, company), [themeId, company]);
  const theme = pack.theme;
  const Art = pack.Art;
  const copy = useMemo(
    () => buildCopy(pack, company, EXPO_SERVICE_LABEL),
    [pack, company],
  );
  const eventName = payload?.booth?.exhibition_name || previewEventName || "";
  const waUrl = payload?.wa_url || payload?.whatsapp_url || previewWaUrl || "";
  const logo = logoSrc(payload?.logo_url);

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
          clearStoredSession(token);
          return;
        }
        const stored = readStoredSession(token);
        if (stored?.sessionId) {
          try {
            const resumed = await apiFetch<AdvanceResult>(
              `/public/expo/${encodeURIComponent(token)}/sessions/${encodeURIComponent(stored.sessionId)}`,
            );
            if (cancelled) return;
            if (resumed?.done) {
              clearStoredSession(token);
              setPhase("choose");
              return;
            }
            setPhase("web");
            if (stored.contact) setContact(stored.contact);
            if (stored.downloadAssets?.length) setDownloadAssets(stored.downloadAssets);
            if (stored.progressIndex) setProgressIndex(stored.progressIndex);
            if (stored.progressTotal) setProgressTotal(stored.progressTotal);
            applyAdvance(resumed);
            return;
          } catch {
            clearStoredSession(token);
          }
        }
        setPhase("choose");
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : "Booth not found");
        setPhase("error");
      }
    })();
    return () => {
      cancelled = true;
    };
    // applyAdvance is stable enough; omit to avoid remount loops
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, preview]);

  const mergeDownloadAssets = useCallback((incoming: ExpoAsset[]) => {
    if (!incoming.length) return;
    setDownloadAssets((prev) => {
      const seen = new Set(prev.map((p) => p.id || p.url));
      const merged = [...prev];
      for (const a of incoming) {
        const k = a.id || a.url;
        if (k && !seen.has(k)) {
          seen.add(k);
          merged.push(a);
        }
      }
      return merged;
    });
  }, []);

  const applyAdvance = useCallback((res: AdvanceResult) => {
    if (res.session_id) setSessionId(String(res.session_id));
    if (res.error) setError(String(res.error));
    else setError("");
    if (typeof res.step_index === "number" && res.step_index > 0) setProgressIndex(res.step_index);
    if (typeof res.step_total === "number" && res.step_total > 0) setProgressTotal(res.step_total);
    if (res.summary) setSummary(res.summary);
    if (res.company_card) setCompanyCard(String(res.company_card));
    if (Array.isArray(res.representatives)) setRepresentatives(res.representatives);
    if (res.company_website) setCompanyWebsite(String(res.company_website));
    if (res.company_logo_url) {
      const raw = String(res.company_logo_url);
      setCompanyLogoUrl(raw.startsWith("http") ? raw : logoSrc(raw));
    }
    if (res.vcard_url) {
      const raw = String(res.vcard_url);
      if (raw.startsWith("http")) setVcardUrl(raw);
      else setVcardUrl(`${getApiBaseUrl().replace(/\/$/, "")}${raw.startsWith("/") ? raw : `/${raw}`}`);
    } else if (token) {
      setVcardUrl(`${getApiBaseUrl().replace(/\/$/, "")}/public/expo/${encodeURIComponent(token)}/vcard`);
    }
    const fromAssets = Array.isArray(res.assets)
      ? (res.assets as ExpoAsset[]).filter((a) => a && (a.url || a.id))
      : [];
    const fromOptions = Array.isArray(res.asset_options)
      ? (res.asset_options as ExpoAsset[]).filter((a) => a && (a.url || a.id))
      : [];
    mergeDownloadAssets(fromAssets.length ? fromAssets : fromOptions);
    if (res.done) {
      clearStoredSession(token);
      setPhase("thanks");
      return;
    }
    if (res.awaiting_pick && res.candidates?.length) {
      setCandidates(res.candidates);
      setWebStep("pick");
      setLiveQ({
        key: "product_pick",
        prompt: String(res.question || "Which would you like?"),
        input: "pick",
        options: [],
        allow_voice: false,
      });
      setSelectedValue("");
      setSelectedValues([]);
      return;
    }

    const key = String(res.question_key || "").trim();
    const sub = String(res.contact_substep || "").trim().toLowerCase();
    const input = String(res.input || "").trim();
    const prompt = String(res.question || "").trim();
    const options = Array.isArray(res.options) ? res.options : [];

    if (key === "contact" || input === "contact" || input === "contact_confirm" || sub) {
      if (input === "contact_confirm" || sub === "confirm") {
        setWebStep("confirm");
        if (res.card_fields) {
          setContact({
            name: String(res.card_fields.name || "").trim(),
            company: String(res.card_fields.company || "").trim(),
            mobile: String(res.card_fields.phone || "").trim(),
            email: String(res.card_fields.email || "").trim(),
          });
        }
      } else {
        setWebStep("contact");
        if (sub === "awaiting" || sub === "card_retry" || !res.card_fields) {
          setCardFile(null);
        }
        if (prompt && /couldn'?t read|enter your|please try/i.test(prompt)) {
          setError(prompt);
        }
      }
      setLiveQ(null);
      setSelectedValue("");
      setSelectedValues([]);
      setTextAnswer("");
      setCandidates([]);
      return;
    }

    setWebStep("question");
    setLiveQ({
      key: key || "question",
      prompt: prompt || "Your answer",
      input: input || (options.length ? "choice" : "text"),
      options,
      allow_voice: Boolean(res.allow_voice),
    });
    setSelectedValue("");
    setSelectedValues([]);
    setTextAnswer("");
    setCandidates([]);
  }, [mergeDownloadAssets, token]);

  // Persist progress for refresh / PDF download return
  useEffect(() => {
    if (preview || phase !== "web" || !sessionId) return;
    writeStoredSession(token, {
      sessionId,
      webStep,
      progressIndex,
      progressTotal,
      contact,
      downloadAssets,
    });
  }, [phase, preview, token, sessionId, webStep, progressIndex, progressTotal, contact, downloadAssets]);

  const startWeb = useCallback(async () => {
    clearStoredSession(token);
    setError("");
    setPhase("web");
    setWebStep("contact");
    setLiveQ(null);
    setSessionId("");
    setSelectedValue("");
    setSelectedValues([]);
    setTextAnswer("");
    setCardFile(null);
    setCardPreview(null);
    setProgressIndex(1);
    setProgressTotal(
      Math.max(2, payload?.step_total || payload?.booth?.question_count || questions.length + 1),
    );
    setDownloadAssets([]);
    setSummary(null);
    setContact({ name: "", company: "", mobile: "", email: "" });
  }, [payload?.booth?.question_count, payload?.step_total, questions.length, token]);

  const stopAndFinish = useCallback(async () => {
    const sid = sessionIdRef.current;
    if (!sid || preview) {
      setPhase("thanks");
      return;
    }
    setBusy(true);
    try {
      const res = await apiFetch<AdvanceResult>(
        `/public/expo/${encodeURIComponent(token)}/sessions/${encodeURIComponent(sid)}/stop`,
        { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" },
      );
      applyAdvance(res);
    } catch {
      setPhase("thanks");
    } finally {
      setBusy(false);
    }
  }, [applyAdvance, preview, token]);

  const handleBack = useCallback(async () => {
    if (busy) return;
    if (webStep === "contact") {
      if (sessionId) await stopAndFinish();
      else setPhase("choose");
      return;
    }
    if (preview) {
      if (webStep === "confirm") setWebStep("contact");
      else if (webStep === "pick") setWebStep("question");
      else setWebStep("contact");
      setProgressIndex((n) => Math.max(1, n - 1));
      return;
    }
    if (!sessionId) {
      setPhase("choose");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const res = await apiFetch<AdvanceResult>(
        `/public/expo/${encodeURIComponent(token)}/sessions/${encodeURIComponent(sessionId)}/back`,
        { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" },
      );
      applyAdvance(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not go back");
    } finally {
      setBusy(false);
    }
  }, [applyAdvance, busy, preview, sessionId, stopAndFinish, token, webStep]);

  useEffect(() => {
    if (preview || phase !== "web") return;
    const onLeave = () => {
      if (isDownloadingRef.current || suppressStopRef.current) return;
      const sid = sessionIdRef.current;
      if (!sid) return;
      try {
        const url = `${getApiBaseUrl().replace(/\/+$/, "")}/public/expo/${encodeURIComponent(token)}/sessions/${encodeURIComponent(sid)}/stop`;
        if (navigator.sendBeacon) {
          navigator.sendBeacon(url, new Blob(["{}"], { type: "application/json" }));
        }
      } catch {
        /* ignore */
      }
    };
    window.addEventListener("pagehide", onLeave);
    return () => window.removeEventListener("pagehide", onLeave);
  }, [phase, preview, token]);

  const handleAssetDownload = useCallback(
    async (a: ExpoAsset) => {
      const url = String(a.url || "").trim();
      if (!url) return;
      const name = `${a.title || a.id || "download"}.pdf`.replace(/[^\w.\- ]+/g, "_");
      isDownloadingRef.current = true;
      suppressStopRef.current = true;
      try {
        if (a.id && !selectedValues.includes(String(a.id))) {
          setSelectedValues((prev) => {
            const withoutNo = prev.filter((v) => !/no thanks|^no$/i.test(v));
            return [...withoutNo, String(a.id)];
          });
        }
        await downloadSameTab(url, name);
      } finally {
        window.setTimeout(() => {
          isDownloadingRef.current = false;
          suppressStopRef.current = false;
        }, 2000);
      }
    },
    [selectedValues],
  );

  const submitCardOrContact = useCallback(async () => {
    if (preview) {
      setWebStep("question");
      setLiveQ({
        key: questions[0]?.key || "interest",
        prompt: questions[0]?.prompt || "What are you looking for today?",
        input: questions[0]?.input || "text",
        options: questions[0]?.options || [],
        allow_voice: Boolean(questions[0]?.allow_voice),
      });
      return;
    }
    setBusy(true);
    setError("");
    try {
      if (cardFile) {
        const start = await apiFetch<AdvanceResult>(`/public/expo/${encodeURIComponent(token)}/start`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ card_first: true, defer_contact: true }),
        });
        const sid = String(start.session_id || "");
        if (!sid) throw new Error("Could not start session");
        setSessionId(sid);
        const form = new FormData();
        form.append("file", cardFile, cardFile.name || "card.jpg");
        const res = await apiUpload<AdvanceResult>(
          `/public/expo/${encodeURIComponent(token)}/sessions/${encodeURIComponent(sid)}/card`,
          form,
        );
        applyAdvance(res);
        return;
      }

      if (contactCapture === "card_only") {
        setError("Please take or upload a photo of your business card.");
        return;
      }
      const mobile = contact.mobile.trim();
      const email = contact.email.trim();
      const name = contact.name.trim();
      const companyVal = contact.company.trim();
      if (!mobile || !email) {
        setError("Mobile and email are required.");
        return;
      }
      if (!name || !companyVal) {
        setError("Name and company are required (or upload a business card).");
        return;
      }
      const res = await apiFetch<AdvanceResult>(`/public/expo/${encodeURIComponent(token)}/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          mobile,
          email,
          name,
          company: companyVal,
        }),
      });
      applyAdvance(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not continue");
    } finally {
      setBusy(false);
    }
  }, [applyAdvance, cardFile, contact, contactCapture, preview, questions, token]);

  const submitConfirmContact = useCallback(async () => {
    if (preview) {
      setWebStep("question");
      setLiveQ({
        key: "interest",
        prompt: "What are you looking for today at our stand?",
        input: "text",
        options: [],
        allow_voice: true,
      });
      return;
    }
    if (!sessionId) {
      setError("Session missing — go back and start again.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const res = await apiFetch<AdvanceResult>(
        `/public/expo/${encodeURIComponent(token)}/sessions/${encodeURIComponent(sessionId)}/contact`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: contact.name.trim(),
            company: contact.company.trim(),
            mobile: contact.mobile.trim(),
            email: contact.email.trim(),
          }),
        },
      );
      applyAdvance(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save contact details");
    } finally {
      setBusy(false);
    }
  }, [applyAdvance, contact, preview, sessionId, token]);

  const submitAnswer = useCallback(
    async (rawAnswer?: string) => {
      const answer = String(
        rawAnswer !== undefined && rawAnswer !== null ? rawAnswer : selectedValue || textAnswer,
      ).trim();
      if (preview) {
        const idx = questions.findIndex((q) => q.key === liveQ?.key);
        const next = questions[idx + 1];
        if (!next) setPhase("thanks");
        else {
          setLiveQ({
            key: next.key,
            prompt: next.prompt,
            input: next.input || "text",
            options: next.options || [],
            allow_voice: Boolean(next.allow_voice),
          });
          setSelectedValue("");
          setTextAnswer("");
        }
        return;
      }
      if (!sessionId) {
        setError("Session missing — go back and start again.");
        return;
      }
      if (!answer) {
        setError("Please choose or type an answer.");
        return;
      }
      setBusy(true);
      setError("");
      try {
        const res = await apiFetch<AdvanceResult>(`/public/expo/${encodeURIComponent(token)}/answer`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: sessionId, answer }),
        });
        applyAdvance(res);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Could not save answer");
      } finally {
        setBusy(false);
      }
    },
    [applyAdvance, liveQ?.key, preview, questions, selectedValue, sessionId, textAnswer, token],
  );

  const submitVoice = useCallback(async () => {
    if (preview) {
      await submitAnswer(textAnswer || "Voice note");
      return;
    }
    const blob = voiceRef.current?.getBlob() || null;
    const typed = (voiceRef.current?.getText() || textAnswer).trim();
    if (!blob && typed) {
      await submitAnswer(typed);
      return;
    }
    if (!blob) {
      setError("Record a voice note or type your answer.");
      return;
    }
    if (!sessionId) {
      setError("Session missing — go back and start again.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const form = new FormData();
      form.append("file", blob, "voice.webm");
      const res = await apiUpload<AdvanceResult>(
        `/public/expo/${encodeURIComponent(token)}/sessions/${encodeURIComponent(sessionId)}/voice`,
        form,
      );
      applyAdvance(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not process voice note");
    } finally {
      setBusy(false);
    }
  }, [applyAdvance, preview, sessionId, submitAnswer, textAnswer, token]);

  const onCardPicked = (file: File | null) => {
    if (cardPreview) URL.revokeObjectURL(cardPreview);
    setCardFile(file);
    setCardPreview(file ? URL.createObjectURL(file) : null);
  };

  if (phase === "loading") {
    return (
      <div className="feedback-survey-root">
        <main className={`grid h-[100svh] place-items-center ${theme.bgClass}`} style={themeStyleVars(theme)}>
          <p className="text-sm" style={{ color: theme.sub }}>
            Loading…
          </p>
        </main>
      </div>
    );
  }

  if (phase === "error") {
    return (
      <div className="feedback-survey-root">
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
      </div>
    );
  }

  if (phase === "closed") {
    return (
      <div className="feedback-survey-root">
        <main className={`grid h-[100svh] place-items-center px-6 ${theme.bgClass}`} style={themeStyleVars(theme)}>
          <div className="max-w-sm text-center">
            <h1 className="font-display text-2xl">Stand closed</h1>
            <p className="mt-2 text-sm" style={{ color: theme.sub }}>
              {payload?.booth?.closed_message || "This Expo stand has closed for this exhibition."}
            </p>
          </div>
        </main>
      </div>
    );
  }

  if (phase === "thanks") {
    const brandName =
      payload?.company_name ||
      payload?.booth?.company_display_name ||
      payload?.booth?.name ||
      company ||
      "";
    const rows = [
      summary?.name ? ["Name", summary.name] : null,
      summary?.company ? ["Company", summary.company] : null,
      summary?.mobile && !String(summary.mobile).startsWith("web-pending") ? ["Mobile", summary.mobile] : null,
      summary?.email && summary.email !== "pending@expo.local" ? ["Email", summary.email] : null,
      summary?.interest ? ["Interest", summary.interest] : null,
      summary?.timeline ? ["Timeline", summary.timeline] : null,
    ].filter(Boolean) as Array<[string, string]>;
    return (
      <div className="feedback-survey-root">
        <main
          className={`relative grid min-h-[100svh] place-items-center overflow-y-auto px-6 py-10 ${theme.bgClass}`}
          style={themeStyleVars(theme)}
        >
          <Art />
          <div className="relative w-full max-w-sm text-center">
            {logo || brandName ? (
              <div className="animate-confetti-rise mb-5 flex flex-col items-center gap-2">
                {logo ? (
                  <img
                    src={logo}
                    alt={brandName || "Exhibitor"}
                    className="h-14 w-auto max-w-[200px] object-contain"
                  />
                ) : null}
                {brandName ? (
                  <p className="font-display text-xl font-semibold" style={{ color: theme.ink }}>
                    {brandName}
                  </p>
                ) : null}
              </div>
            ) : null}
            <div
              className="animate-tick-pop mx-auto grid h-20 w-20 place-items-center rounded-full text-white shadow-lift"
              style={{ background: theme.gradientButton }}
            >
              <svg
                viewBox="0 0 24 24"
                className="h-9 w-9"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden
              >
                <path d="M5 12l5 5L20 7" />
              </svg>
            </div>
            <h1
              className="animate-confetti-rise mt-6 font-display text-4xl"
              style={{ animationDelay: "120ms", color: theme.ink }}
            >
              {copy.thankYouTitle}
              <span style={{ color: theme.accent }}>.</span>
            </h1>
            <p
              className="animate-confetti-rise mt-3 text-[15px] leading-relaxed"
              style={{ animationDelay: "240ms", color: theme.sub }}
            >
              {downloadAssets.length
                ? "Thanks — your downloads are ready below."
                : copy.thankYouSubtitle}
            </p>
            {rows.length ? (
              <div
                className="animate-confetti-rise mt-5 rounded-2xl border p-4 text-left shadow-soft"
                style={{
                  animationDelay: "300ms",
                  background: theme.card,
                  borderColor: theme.border,
                }}
              >
                <p className="text-[11px] font-medium uppercase tracking-[0.18em]" style={{ color: theme.sub }}>
                  We saved
                </p>
                <ul className="mt-2 space-y-1.5">
                  {rows.map(([label, value]) => (
                    <li key={label} className="text-[13px]">
                      <span style={{ color: theme.sub }}>{label}: </span>
                      <span style={{ color: theme.ink }}>{value}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
            {(companyCard || representatives.length > 0 || companyLogoUrl || logo || vcardUrl) ? (
              <div
                className="animate-confetti-rise mt-4 overflow-hidden rounded-2xl border text-left shadow-soft"
                style={{
                  animationDelay: "330ms",
                  background: theme.card,
                  borderColor: theme.border,
                }}
              >
                {(companyLogoUrl || logo) ? (
                  <div
                    className="flex items-center justify-center border-b px-4 py-5"
                    style={{ borderColor: theme.border, background: "rgba(255,255,255,0.04)" }}
                  >
                    <img
                      src={companyLogoUrl || logo}
                      alt={company}
                      className="max-h-16 w-auto max-w-[200px] object-contain"
                    />
                  </div>
                ) : null}
                <div className="p-4">
                  <p className="text-[11px] font-medium uppercase tracking-[0.18em]" style={{ color: theme.sub }}>
                    Stay in touch
                  </p>
                  <p className="mt-2 text-base font-semibold" style={{ color: theme.ink }}>
                    {company}
                  </p>
                  {companyWebsite ? (
                    <a
                      href={companyWebsite.startsWith("http") ? companyWebsite : `https://${companyWebsite}`}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-1 block text-[13px] underline-offset-2 hover:underline"
                      style={{ color: theme.sub }}
                    >
                      {companyWebsite.replace(/^https?:\/\//, "")}
                    </a>
                  ) : null}
                  {representatives.length > 0 ? (
                    <ul className="mt-3 space-y-2.5">
                      {representatives.map((rep, idx) => (
                        <li key={`${rep.email || rep.name || idx}`} className="text-[13px]" style={{ color: theme.ink }}>
                          <div className="font-medium">{rep.name || "Contact"}</div>
                          {rep.company_name && rep.company_name !== company ? (
                            <div style={{ color: theme.sub }}>{rep.company_name}</div>
                          ) : null}
                          {rep.email ? <div style={{ color: theme.sub }}>{rep.email}</div> : null}
                          {rep.mobile ? <div style={{ color: theme.sub }}>{rep.mobile}</div> : null}
                          {rep.telephone ? <div style={{ color: theme.sub }}>{rep.telephone}</div> : null}
                        </li>
                      ))}
                    </ul>
                  ) : companyCard ? (
                    <p className="mt-2 whitespace-pre-line text-[13px] leading-relaxed" style={{ color: theme.ink }}>
                      {companyCard
                        .replace(/🖼️ Logo:.*$/gm, "")
                        .replace(/📇 Tap the contact card.*$/gm, "")
                        .trim()}
                    </p>
                  ) : null}
                  {vcardUrl ? (
                    <a
                      href={vcardUrl}
                      download
                      className="mt-3 inline-flex w-full items-center justify-center gap-2 rounded-2xl px-4 py-3 text-sm font-semibold"
                      style={DOWNLOAD_BTN_STYLE}
                    >
                      Save contacts to phone
                    </a>
                  ) : null}
                </div>
              </div>
            ) : null}
            {downloadAssets.length ? (
              <div className="animate-confetti-rise mt-4 grid gap-2" style={{ animationDelay: "360ms" }}>
                <p
                  className="text-left text-[11px] font-medium uppercase tracking-[0.18em]"
                  style={{ color: theme.sub }}
                >
                  Your downloads
                </p>
                {downloadAssets.map((a) => (
                  <button
                    key={a.id || a.url}
                    type="button"
                    onClick={() => void handleAssetDownload(a)}
                    className="inline-flex items-center justify-center gap-2 rounded-2xl px-4 py-3.5 text-sm font-semibold"
                    style={DOWNLOAD_BTN_STYLE}
                  >
                    <DownloadGlyph className="h-4 w-4 shrink-0" />
                    <span>Download {a.title || "file"}</span>
                  </button>
                ))}
              </div>
            ) : null}
          </div>
        </main>
      </div>
    );
  }

  if (phase === "web") {
    const progressPct = Math.round((progressIndex / Math.max(1, progressTotal)) * 100);
    const displayPrompt =
      webStep === "contact"
        ? contactCapture === "card_only"
          ? "Please upload a photo of your business card to continue."
          : "Upload a business card, or enter your details."
        : webStep === "confirm"
          ? "Check your details, then continue"
          : webStep === "pick"
            ? liveQ?.prompt || "Which would you like?"
            : liveQ?.prompt || "";
    const isMulti = liveQ?.input === "multi_choice";

    return (
      <div className="feedback-survey-root">
        <main
          className={`relative flex h-[100svh] flex-col overflow-hidden ${theme.bgClass}`}
          style={themeStyleVars(theme)}
        >
          <Art />
          <div className="relative mx-auto flex h-[100svh] w-full max-w-md flex-col px-5 pb-5 pt-4 sm:max-w-lg sm:pt-6">
            <div className="flex items-center justify-between">
              <div className="inline-flex items-center gap-2">
                {logo ? (
                  <img
                    src={logo}
                    alt=""
                    className="h-7 w-7 rounded-md object-contain p-0.5 shadow-soft"
                    style={{ background: theme.card }}
                  />
                ) : (
                  <span
                    className="grid h-7 w-7 place-items-center rounded-md text-[11px] font-bold shadow-soft"
                    style={{ background: theme.gradientButton, color: "#fff" }}
                  >
                    {(company || "E").slice(0, 1).toUpperCase()}
                  </span>
                )}
                <div className="flex flex-col leading-tight">
                  <span className="font-display text-sm tracking-tight">{company}</span>
                  <span
                    className="text-[10px] font-medium uppercase tracking-[0.18em]"
                    style={{ color: theme.sub }}
                  >
                    {eventName || copy.serviceLabel}
                  </span>
                </div>
              </div>
              <span className="text-[11px] font-medium" style={{ color: theme.sub }}>
                {progressIndex} / {progressTotal}
              </span>
            </div>

            <div className="mt-3 h-1 w-full overflow-hidden rounded-full" style={{ background: theme.border }}>
              <div
                className="h-full rounded-full transition-all duration-500 ease-out"
                style={{ width: `${progressPct}%`, background: theme.gradientProgress }}
              />
            </div>

            <div className="flex flex-1 flex-col justify-center overflow-y-auto py-4">
              <div className="animate-rise space-y-4">
                {webStep === "contact" ? (
                  <>
                    <p className="text-[11px] font-medium uppercase tracking-[0.2em]" style={{ color: theme.sub }}>
                      Contact
                    </p>
                    <h1 className="font-display text-[28px] leading-[1.15] sm:text-[32px]" style={{ color: theme.ink }}>
                      {displayPrompt}
                    </h1>
                    <input
                      ref={cardInputRef}
                      type="file"
                      accept="image/*"
                      capture="environment"
                      className="hidden"
                      onChange={(e) => onCardPicked(e.target.files?.[0] || null)}
                    />
                    {contactCapture !== "manual_only" ? (
                      <button
                        type="button"
                        onClick={() => cardInputRef.current?.click()}
                        className="flex w-full flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed px-4 py-6 text-[15px] font-semibold shadow-lift transition-transform active:scale-[0.98]"
                        style={{
                          background: theme.gradientButton,
                          borderColor: "transparent",
                          color: "#fff",
                          boxShadow: theme.selectedShadow,
                        }}
                      >
                        <span className="text-2xl" aria-hidden>
                          📷
                        </span>
                        <span>
                          {cardPreview ? "Retake / change business card" : "Take photo of business card"}
                        </span>
                        <span className="text-[12px] font-medium opacity-90">
                          Camera or upload — we read the details for you
                        </span>
                      </button>
                    ) : null}
                    {cardPreview ? (
                      <img
                        src={cardPreview}
                        alt="Business card preview"
                        className="h-36 w-full rounded-xl object-cover shadow-soft"
                      />
                    ) : null}

                    {contactCapture !== "card_only" && !cardFile ? (
                      <div className="grid gap-2.5">
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
                              className="mt-1 w-full rounded-2xl border px-4 py-3 text-[15px] shadow-soft outline-none"
                              style={{ background: theme.card, borderColor: theme.border, color: theme.ink }}
                              value={contact[key]}
                              onChange={(e) => setContact((c) => ({ ...c, [key]: e.target.value }))}
                              autoComplete={key === "email" ? "email" : key === "mobile" ? "tel" : "off"}
                            />
                          </label>
                        ))}
                      </div>
                    ) : null}
                  </>
                ) : null}

                {webStep === "confirm" ? (
                  <>
                    <p className="text-[11px] font-medium uppercase tracking-[0.2em]" style={{ color: theme.sub }}>
                      Confirm details
                    </p>
                    <h1 className="font-display text-[28px] leading-[1.15] sm:text-[32px]" style={{ color: theme.ink }}>
                      {displayPrompt}
                    </h1>
                    <div className="grid gap-2.5">
                      {(
                        [
                          ["name", "Name *"],
                          ["company", "Company"],
                          ["mobile", "Mobile *"],
                          ["email", "Email *"],
                        ] as const
                      ).map(([key, label]) => (
                        <label key={key} className="block text-[12px] font-medium" style={{ color: theme.sub }}>
                          {label}
                          <input
                            className="mt-1 w-full rounded-2xl border px-4 py-3 text-[15px] shadow-soft outline-none"
                            style={{ background: theme.card, borderColor: theme.border, color: theme.ink }}
                            value={contact[key]}
                            onChange={(e) => setContact((c) => ({ ...c, [key]: e.target.value }))}
                            autoComplete={key === "email" ? "email" : key === "mobile" ? "tel" : "off"}
                          />
                        </label>
                      ))}
                    </div>
                  </>
                ) : null}

                {webStep === "question" && liveQ ? (
                  liveQ.input === "choice" || liveQ.input === "multi_choice" ? (
                    liveQ.options.length > 0 ? (
                    <>
                      <p className="text-[11px] font-medium uppercase tracking-[0.2em]" style={{ color: theme.sub }}>
                        Question
                      </p>
                      <h1 className="font-display text-[28px] leading-[1.15] sm:text-[32px]" style={{ color: theme.ink }}>
                        {liveQ.prompt}
                      </h1>
                      {isMulti ? (
                        <p className="text-[12.5px]" style={{ color: theme.sub }}>
                          Select all that apply
                        </p>
                      ) : null}
                      <div className="mt-2 grid gap-2.5">
                        {liveQ.options.map((opt) => {
                          const selected = isMulti
                            ? selectedValues.includes(opt.value)
                            : selectedValue === opt.value;
                          return (
                            <button
                              key={opt.value}
                              type="button"
                              disabled={busy}
                              onClick={() => {
                                if (!isMulti) {
                                  setSelectedValue(opt.value);
                                  return;
                                }
                                const isNo = /no thanks|^no$/i.test(opt.value);
                                setSelectedValues((prev) => {
                                  if (isNo) return selected ? [] : [opt.value];
                                  const withoutNo = prev.filter((v) => !/no thanks|^no$/i.test(v));
                                  if (selected) return withoutNo.filter((v) => v !== opt.value);
                                  return [...withoutNo, opt.value];
                                });
                              }}
                              className="group flex items-center justify-between rounded-2xl border px-4 py-3.5 text-left text-[15px] font-medium transition-all active:scale-[0.98] disabled:opacity-50"
                              style={
                                selected
                                  ? {
                                      background: theme.gradientButton,
                                      color: "#fff",
                                      borderColor: "transparent",
                                      boxShadow: theme.selectedShadow,
                                    }
                                  : { background: theme.card, borderColor: theme.border, color: theme.ink }
                              }
                            >
                              <span>{opt.label}</span>
                              <span
                                className="grid h-5 w-5 place-items-center rounded-full"
                                style={
                                  selected
                                    ? { background: "#fff", color: theme.accent }
                                    : { border: `1px solid ${theme.border}` }
                                }
                              >
                                {selected ? (
                                  <svg
                                    viewBox="0 0 24 24"
                                    className="h-3 w-3"
                                    fill="none"
                                    stroke="currentColor"
                                    strokeWidth="3.5"
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    aria-hidden
                                  >
                                    <path d="M5 12l5 5L20 7" />
                                  </svg>
                                ) : null}
                              </span>
                            </button>
                          );
                        })}
                      </div>
                      {downloadAssets.length && liveQ.key === "consent_info" ? (
                        <div className="mt-3 grid gap-2">
                          <p className="text-[12px]" style={{ color: theme.sub }}>
                            Download any file below — the questionnaire stays open.
                          </p>
                          {downloadAssets.map((a) => (
                            <div
                              key={a.id || a.url}
                              className="rounded-xl px-3.5 py-3 text-left"
                              style={DOWNLOAD_BTN_STYLE}
                            >
                              <div className="flex items-start gap-2.5">
                                <span
                                  className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-lg"
                                  style={{ background: "#e2e8f0", color: "#0f172a" }}
                                >
                                  <DownloadGlyph className="h-4 w-4" />
                                </span>
                                <div className="min-w-0 flex-1">
                                  <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                                    {purposeBadge(a.purpose)}
                                  </p>
                                  <p className="text-[13px] font-semibold text-slate-900">
                                    {a.title || "Download"}
                                  </p>
                                  {a.short_description ? (
                                    <p className="mt-0.5 text-[12px] leading-snug text-slate-600">
                                      {a.short_description}
                                    </p>
                                  ) : null}
                                  <button
                                    type="button"
                                    className="mt-2 text-[12px] font-semibold underline underline-offset-2"
                                    style={{ color: "#0f172a" }}
                                    onClick={() => void handleAssetDownload(a)}
                                  >
                                    Download file
                                  </button>
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      ) : null}
                    </>
                    ) : (
                      <VoiceDetail
                        ref={voiceRef}
                        theme={theme}
                        eyebrow="Question"
                        title={liveQ.prompt}
                        hint={
                          liveQ.allow_voice
                            ? "Type in English, or record a voice note in any language — we translate to English."
                            : "Type your answer."
                        }
                        text={textAnswer}
                        onTextChange={setTextAnswer}
                        allowVoice={Boolean(liveQ.allow_voice)}
                        disabled={busy}
                        placeholder="Your answer…"
                      />
                    )
                  ) : (
                    <VoiceDetail
                      ref={voiceRef}
                      theme={theme}
                      eyebrow="Question"
                      title={liveQ.prompt}
                      hint={
                        liveQ.allow_voice
                          ? "Type in English, or record a voice note in any language — we translate to English."
                          : "Type your answer."
                      }
                      text={textAnswer}
                      onTextChange={setTextAnswer}
                      allowVoice={Boolean(liveQ.allow_voice)}
                      disabled={busy}
                      placeholder="Your answer…"
                    />
                  )
                ) : null}

                {webStep === "pick" ? (
                  <>
                    <p className="text-[11px] font-medium uppercase tracking-[0.2em]" style={{ color: theme.sub }}>
                      Choose a pack
                    </p>
                    <h1 className="font-display text-[26px] leading-[1.15] sm:text-[30px]" style={{ color: theme.ink }}>
                      {displayPrompt}
                    </h1>
                    <div className="grid gap-2.5">
                      {candidates.map((c, i) => {
                        const value = String(i + 1);
                        const selected = selectedValue === value || selectedValue === c.id;
                        return (
                          <button
                            key={c.id || value}
                            type="button"
                            disabled={busy}
                            onClick={() => setSelectedValue(value)}
                            className="rounded-2xl border px-4 py-3.5 text-left transition-all active:scale-[0.98]"
                            style={
                              selected
                                ? {
                                    background: theme.gradientButton,
                                    color: "#fff",
                                    borderColor: "transparent",
                                    boxShadow: theme.selectedShadow,
                                  }
                                : { background: theme.card, borderColor: theme.border, color: theme.ink }
                            }
                          >
                            <div className="text-[15px] font-semibold">
                              {i + 1}. {c.title || "Product"}
                            </div>
                            {c.short_description ? (
                              <div className="mt-0.5 text-[12px]" style={{ opacity: selected ? 0.9 : 0.65 }}>
                                {c.short_description}
                              </div>
                            ) : null}
                          </button>
                        );
                      })}
                    </div>
                  </>
                ) : null}

                {error ? <p className="text-[13px]" style={{ color: "#f87171" }}>{error}</p> : null}
              </div>
            </div>

            <div className="flex items-center gap-3">
              <button
                type="button"
                disabled={busy}
                onClick={() => void handleBack()}
                className="inline-flex h-12 items-center gap-1.5 rounded-full border px-4 text-sm font-medium shadow-soft transition-all active:scale-[0.97] disabled:opacity-40"
                style={{ background: theme.card, borderColor: theme.border, color: theme.ink }}
              >
                <svg
                  viewBox="0 0 24 24"
                  className="h-4 w-4"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden
                >
                  <path d="M15 18l-6-6 6-6" />
                </svg>
                Back
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => {
                  if (webStep === "contact") void submitCardOrContact();
                  else if (webStep === "confirm") void submitConfirmContact();
                  else if (webStep === "pick") void submitAnswer(selectedValue);
                  else if (liveQ?.input === "multi_choice") void submitAnswer(selectedValues.join(", "));
                  else if (liveQ?.input === "choice") void submitAnswer(selectedValue);
                  else if (liveQ?.allow_voice) void submitVoice();
                  else void submitAnswer(textAnswer);
                }}
                className="inline-flex h-12 flex-1 items-center justify-center gap-2 rounded-full px-6 text-sm font-semibold text-white shadow-lift transition-all active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-40"
                style={{ background: theme.gradientButton }}
              >
                {busy ? "Please wait…" : webStep === "confirm" ? "Confirm & continue" : "Continue"}
                <svg
                  viewBox="0 0 24 24"
                  className="h-4 w-4"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden
                >
                  <path d="M5 12h14M13 5l7 7-7 7" />
                </svg>
              </button>
            </div>
          </div>
        </main>
      </div>
    );
  }

  // choose — SurveyTemplate welcome energy on expo Art backdrop
  return (
    <div className="feedback-survey-root">
      <main className={`relative h-[100svh] overflow-hidden ${theme.bgClass}`} style={themeStyleVars(theme)}>
        <Art />

        <div className="relative mx-auto flex h-[100svh] w-full max-w-md flex-col px-5 pb-5 pt-4 sm:max-w-lg sm:px-6 sm:pt-6">
          <header className="animate-rise flex flex-col items-center gap-2 text-center" style={{ animationDelay: "60ms" }}>
            {logo ? (
              <img
                src={logo}
                alt=""
                className="h-10 w-10 rounded-xl object-contain p-1 shadow-lift ring-1"
                style={{ background: theme.card, borderColor: theme.border }}
              />
            ) : (
              <span
                className="grid h-10 w-10 place-items-center rounded-xl text-sm font-bold shadow-lift"
                style={{ background: theme.gradientButton, color: "#fff" }}
              >
                {(company || "E").slice(0, 1).toUpperCase()}
              </span>
            )}
            <span className="font-display text-[15px] tracking-tight" style={{ color: theme.ink }}>
              {company}
            </span>
            {eventName ? (
              <p className="text-[12px]" style={{ color: theme.sub }}>
                {eventName}
              </p>
            ) : (
              <p
                className="text-[10px] font-medium uppercase tracking-[0.18em]"
                style={{ color: theme.sub }}
              >
                {copy.serviceLabel}
              </p>
            )}
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
              style={{ background: theme.card, borderColor: theme.border, color: theme.sub }}
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
              style={{
                animationDelay: "640ms",
                background: theme.gradientButton,
                borderColor: "transparent",
                color: "#fff",
                boxShadow: theme.selectedShadow,
              }}
            >
              <div className="flex items-center gap-3.5">
                <span className="animate-float-icon shrink-0">
                  <SparkGlyph />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="text-[15.5px] font-semibold tracking-tight">Complete here</div>
                  <div className="mt-0.5 text-[11.5px] opacity-85">Buttons · card photo · voice · English</div>
                </div>
                <ArrowGlyph />
              </div>
            </button>
          </div>

          {error ? <p className="mt-3 text-center text-[13px]" style={{ color: "#f87171" }}>{error}</p> : null}

          <footer
            className="animate-rise mt-auto pt-4 text-center text-[10.5px]"
            style={{ animationDelay: "780ms", color: theme.sub, opacity: 0.8 }}
          >
            Your reply is private and only shared with {company}.
          </footer>
        </div>
      </main>
    </div>
  );
}
