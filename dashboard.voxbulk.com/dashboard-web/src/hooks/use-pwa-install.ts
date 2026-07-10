import * as React from "react";

type BeforeInstallPromptEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
};

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

function isSafariBrowser() {
  if (typeof window === "undefined") return false;
  const ua = window.navigator.userAgent || "";
  // Chrome/Firefox/Edge on iOS include CriOS/FxiOS/EdgiOS — native Share→Add Home works best in Safari.
  return /Safari/.test(ua) && !/CriOS|FxiOS|EdgiOS|OPiOS|Chrome|Android/.test(ua);
}

export function usePwaInstall() {
  const [canInstall, setCanInstall] = React.useState(false);
  const [installed, setInstalled] = React.useState(isStandaloneDisplay);
  const [iosInstallAvailable, setIosInstallAvailable] = React.useState(false);
  const [showIosHelp, setShowIosHelp] = React.useState(false);
  const deferredRef = React.useRef<BeforeInstallPromptEvent | null>(null);

  React.useEffect(() => {
    if (isStandaloneDisplay()) {
      setInstalled(true);
      setCanInstall(false);
      setIosInstallAvailable(false);
      return;
    }

    if (isIosDevice()) {
      setIosInstallAvailable(true);
    }

    const onBeforeInstall = (e: Event) => {
      e.preventDefault();
      deferredRef.current = e as BeforeInstallPromptEvent;
      setCanInstall(true);
    };
    const onInstalled = () => {
      deferredRef.current = null;
      setCanInstall(false);
      setIosInstallAvailable(false);
      setInstalled(true);
      setShowIosHelp(false);
    };

    window.addEventListener("beforeinstallprompt", onBeforeInstall);
    window.addEventListener("appinstalled", onInstalled);
    return () => {
      window.removeEventListener("beforeinstallprompt", onBeforeInstall);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, []);

  const install = React.useCallback(async () => {
    const evt = deferredRef.current;
    if (evt) {
      await evt.prompt();
      const choice = await evt.userChoice;
      if (choice.outcome === "accepted") {
        deferredRef.current = null;
        setCanInstall(false);
        setInstalled(true);
        return true;
      }
      return false;
    }
    if (isIosDevice()) {
      setShowIosHelp(true);
      return false;
    }
    return false;
  }, []);

  return {
    canInstall: (canInstall || iosInstallAvailable) && !installed,
    installed,
    isIos: iosInstallAvailable,
    isSafari: isSafariBrowser(),
    showIosHelp,
    setShowIosHelp,
    install,
  };
}
