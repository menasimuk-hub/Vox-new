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

export function usePwaInstall() {
  const [canInstall, setCanInstall] = React.useState(false);
  const [installed, setInstalled] = React.useState(isStandaloneDisplay);
  const deferredRef = React.useRef<BeforeInstallPromptEvent | null>(null);

  React.useEffect(() => {
    if (isStandaloneDisplay()) {
      setInstalled(true);
      setCanInstall(false);
      return;
    }

    const onBeforeInstall = (e: Event) => {
      e.preventDefault();
      deferredRef.current = e as BeforeInstallPromptEvent;
      setCanInstall(true);
    };
    const onInstalled = () => {
      deferredRef.current = null;
      setCanInstall(false);
      setInstalled(true);
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
    if (!evt) return false;
    await evt.prompt();
    const choice = await evt.userChoice;
    if (choice.outcome === "accepted") {
      deferredRef.current = null;
      setCanInstall(false);
      setInstalled(true);
      return true;
    }
    return false;
  }, []);

  return { canInstall: canInstall && !installed, installed, install };
}
