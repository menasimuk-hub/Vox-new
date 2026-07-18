import { useEffect, useState } from "react";
import { Link } from "@tanstack/react-router";

const STORAGE_KEY = "vox_cookie_consent";
const OPEN_EVENT = "vox:open-cookie-consent";

export type CookieConsentValue = "all" | "essential";

export function openCookiePreferences() {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new Event(OPEN_EVENT));
}

function readConsent(): CookieConsentValue | null {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    return v === "all" || v === "essential" ? v : null;
  } catch {
    return null;
  }
}

function writeConsent(value: CookieConsentValue) {
  try {
    localStorage.setItem(STORAGE_KEY, value);
  } catch {
    /* ignore quota / private mode */
  }
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent("vox:cookie-consent", { detail: value }));
  }
}

/** Lightweight first-visit privacy/cookie bar — no third-party scripts. */
export function CookieConsentBanner() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (!readConsent()) setVisible(true);
    const onOpen = () => setVisible(true);
    window.addEventListener(OPEN_EVENT, onOpen);
    return () => window.removeEventListener(OPEN_EVENT, onOpen);
  }, []);

  if (!visible) return null;

  const choose = (value: CookieConsentValue) => {
    writeConsent(value);
    setVisible(false);
  };

  return (
    <div
      role="dialog"
      aria-label="Cookie and privacy preferences"
      className="fixed inset-x-0 bottom-0 z-[80] p-3 md:p-4 pointer-events-none"
    >
      <div className="pointer-events-auto mx-auto max-w-[720px] rounded-2xl border border-border bg-white shadow-elevated px-4 py-4 md:px-5 md:py-4">
        <p className="text-[13.5px] md:text-[14px] text-body leading-[1.55]">
          We use necessary cookies to run the site. Optional analytics cookies help us improve VoxBulk — only with your consent.{" "}
          <Link to="/cookies" className="text-primary font-semibold underline-offset-2 hover:underline">
            Cookie Policy
          </Link>
          {" · "}
          <Link to="/privacy" className="text-primary font-semibold underline-offset-2 hover:underline">
            Privacy
          </Link>
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => choose("essential")}
            className="inline-flex items-center justify-center h-9 px-3.5 rounded-xl border border-border text-[13px] font-semibold text-heading hover:bg-beige transition-colors"
          >
            Essential only
          </button>
          <button
            type="button"
            onClick={() => choose("all")}
            className="inline-flex items-center justify-center h-9 px-3.5 rounded-xl bg-navy text-white text-[13px] font-semibold hover:bg-navy/90 transition-colors"
          >
            Accept all
          </button>
        </div>
      </div>
    </div>
  );
}
