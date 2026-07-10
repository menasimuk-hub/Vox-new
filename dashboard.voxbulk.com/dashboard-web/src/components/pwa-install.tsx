import * as React from "react";
import { MonitorDown, X } from "lucide-react";
import { Button } from "@/components/ui/button";

type BeforeInstallPromptEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
};

const DISMISS_KEY = "voxbulk_pwa_install_dismissed_v1";

type PwaInstallContextValue = {
  canInstall: boolean;
  hasNativePrompt: boolean;
  installed: boolean;
  isIos: boolean;
  isAndroid: boolean;
  isSafari: boolean;
  showHelp: boolean;
  setShowHelp: (open: boolean) => void;
  showBanner: boolean;
  dismissBanner: () => void;
  install: () => Promise<boolean>;
};

const PwaInstallContext = React.createContext<PwaInstallContextValue | null>(null);

function isStandaloneDisplay() {
  if (typeof window === "undefined") return false;
  return (
    window.matchMedia("(display-mode: standalone)").matches ||
    (window.navigator as Navigator & { standalone?: boolean }).standalone === true
  );
}

function isIosDevice() {
  if (typeof window === "undefined") return false;
  const ua = window.navigator.userAgent || "";
  const iOS = /iPad|iPhone|iPod/.test(ua);
  const iPadOs = window.navigator.platform === "MacIntel" && window.navigator.maxTouchPoints > 1;
  return iOS || iPadOs;
}

function isAndroidDevice() {
  if (typeof window === "undefined") return false;
  return /Android/i.test(window.navigator.userAgent || "");
}

function isSafariBrowser() {
  if (typeof window === "undefined") return false;
  const ua = window.navigator.userAgent || "";
  return /Safari/.test(ua) && !/CriOS|FxiOS|EdgiOS|OPiOS|Chrome|Android/.test(ua);
}

function isMobileBrowser() {
  if (typeof window === "undefined") return false;
  return isIosDevice() || isAndroidDevice() || window.matchMedia("(max-width: 768px)").matches;
}

export function PwaInstallProvider({ children }: { children: React.ReactNode }) {
  const [nativePromptReady, setNativePromptReady] = React.useState(false);
  const [installed, setInstalled] = React.useState(false);
  const [isIos, setIsIos] = React.useState(false);
  const [isAndroid, setIsAndroid] = React.useState(false);
  const [isMobile, setIsMobile] = React.useState(false);
  const [isSafari, setIsSafari] = React.useState(false);
  const [showHelp, setShowHelp] = React.useState(false);
  const [bannerDismissed, setBannerDismissed] = React.useState(true);
  const deferredRef = React.useRef<BeforeInstallPromptEvent | null>(null);

  React.useEffect(() => {
    setInstalled(isStandaloneDisplay());
    setIsIos(isIosDevice());
    setIsAndroid(isAndroidDevice());
    setIsMobile(isMobileBrowser());
    setIsSafari(isSafariBrowser());
    try {
      setBannerDismissed(window.localStorage.getItem(DISMISS_KEY) === "1");
    } catch {
      setBannerDismissed(false);
    }

    if (isStandaloneDisplay()) {
      setNativePromptReady(false);
      return;
    }

    const onBeforeInstall = (e: Event) => {
      e.preventDefault();
      deferredRef.current = e as BeforeInstallPromptEvent;
      setNativePromptReady(true);
    };
    const onInstalled = () => {
      deferredRef.current = null;
      setNativePromptReady(false);
      setInstalled(true);
      setShowHelp(false);
    };

    window.addEventListener("beforeinstallprompt", onBeforeInstall);
    window.addEventListener("appinstalled", onInstalled);
    return () => {
      window.removeEventListener("beforeinstallprompt", onBeforeInstall);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, []);

  const canOfferInstall = !installed && (isIos || isAndroid || isMobile || nativePromptReady);

  const install = React.useCallback(async () => {
    const evt = deferredRef.current;
    if (evt) {
      await evt.prompt();
      const choice = await evt.userChoice;
      if (choice.outcome === "accepted") {
        deferredRef.current = null;
        setNativePromptReady(false);
        setInstalled(true);
        return true;
      }
      return false;
    }
    setShowHelp(true);
    return false;
  }, []);

  const dismissBanner = React.useCallback(() => {
    setBannerDismissed(true);
    try {
      window.localStorage.setItem(DISMISS_KEY, "1");
    } catch {
      /* ignore */
    }
  }, []);

  const value: PwaInstallContextValue = {
    canInstall: canOfferInstall,
    hasNativePrompt: nativePromptReady,
    installed,
    isIos,
    isAndroid,
    isSafari,
    showHelp,
    setShowHelp,
    showBanner: canOfferInstall && !bannerDismissed && isMobile,
    dismissBanner,
    install,
  };

  return <PwaInstallContext.Provider value={value}>{children}</PwaInstallContext.Provider>;
}

export function usePwaInstall() {
  const ctx = React.useContext(PwaInstallContext);
  if (!ctx) {
    throw new Error("usePwaInstall must be used within PwaInstallProvider");
  }
  return ctx;
}

export function PwaInstallHelpDialog() {
  const { showHelp, setShowHelp, isIos, isAndroid, isSafari, hasNativePrompt, install } = usePwaInstall();
  if (!showHelp) return null;

  return (
    <div className="fixed inset-0 z-[80] flex items-end justify-center bg-black/50 p-4 sm:items-center">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="pwa-install-title"
        className="w-full max-w-sm rounded-2xl border border-border bg-background p-5 shadow-xl"
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 id="pwa-install-title" className="text-base font-semibold">
              {isIos ? "Install on iPhone / iPad" : "Install on Android"}
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {isIos
                ? isSafari
                  ? "Add VoxBulk to your Home Screen for a full-screen app."
                  : "Open this page in Safari first, then add it to your Home Screen."
                : "Add VoxBulk to your Home Screen from Chrome."}
            </p>
          </div>
          <Button type="button" size="icon" variant="ghost" className="size-8 shrink-0" onClick={() => setShowHelp(false)}>
            <X className="size-4" />
          </Button>
        </div>

        {isIos ? (
          <ol className="mt-4 list-decimal space-y-2 ps-5 text-sm text-foreground">
            <li>
              Tap the <span className="font-medium">Share</span> button in Safari
            </li>
            <li>
              Choose <span className="font-medium">Add to Home Screen</span>
            </li>
            <li>
              Tap <span className="font-medium">Add</span>
            </li>
          </ol>
        ) : (
          <ol className="mt-4 list-decimal space-y-2 ps-5 text-sm text-foreground">
            <li>
              Tap the <span className="font-medium">⋮</span> menu (top-right in Chrome)
            </li>
            <li>
              Tap <span className="font-medium">Install app</span> or <span className="font-medium">Add to Home screen</span>
            </li>
            <li>
              Tap <span className="font-medium">Install</span> / <span className="font-medium">Add</span>
            </li>
          </ol>
        )}

        <div className="mt-5 flex flex-col gap-2">
          {hasNativePrompt && !isIos ? (
            <Button
              type="button"
              className="w-full"
              onClick={() => {
                void install().then((ok) => {
                  if (ok) setShowHelp(false);
                });
              }}
            >
              Install now
            </Button>
          ) : null}
          <Button
            type="button"
            variant={hasNativePrompt && !isIos ? "outline" : "default"}
            className="w-full"
            onClick={() => setShowHelp(false)}
          >
            Got it
          </Button>
        </div>
        {isAndroid ? (
          <p className="mt-3 text-[11px] text-muted-foreground">
            If you already added the old icon, remove it first, then install again for the dark splash.
          </p>
        ) : null}
      </div>
    </div>
  );
}

export function PwaInstallBanner() {
  const { showBanner, dismissBanner, install, isIos } = usePwaInstall();
  if (!showBanner) return null;

  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-0 z-[70] p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] md:hidden">
      <div className="pointer-events-auto mx-auto flex max-w-lg items-center gap-3 rounded-2xl border border-border bg-background/95 p-3 shadow-xl backdrop-blur">
        <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-[#0f1b3d]">
          <img src="/pwa/icon-192.png?v=black6" alt="" className="size-8 rounded-lg" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold leading-tight">Install VoxBulk</p>
          <p className="text-[11px] text-muted-foreground">
            {isIos ? "Add to Home Screen for full-screen access" : "Add to your phone home screen"}
          </p>
        </div>
        <Button type="button" size="sm" className="shrink-0" onClick={() => void install()}>
          Install
        </Button>
        <Button type="button" size="icon" variant="ghost" className="size-8 shrink-0" onClick={dismissBanner} aria-label="Dismiss">
          <X className="size-4" />
        </Button>
      </div>
    </div>
  );
}

export function PwaInstallButton() {
  const { canInstall, install, isIos } = usePwaInstall();
  if (!canInstall) return null;
  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      className="inline-flex h-8 gap-1.5 px-2 sm:h-9 sm:px-3"
      onClick={() => void install()}
      aria-label="Install VoxBulk app"
      title={isIos ? "Add to Home Screen" : "Install app"}
    >
      <MonitorDown className="size-4" />
      <span className="text-xs font-medium">{isIos ? "Add to Home" : "Install"}</span>
    </Button>
  );
}
