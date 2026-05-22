import { lazy, Suspense, useEffect, useState, createContext, useContext, useCallback } from "react";

type AuthModalCtx = { open: () => void; close: () => void; isOpen: boolean };
const Ctx = createContext<AuthModalCtx>({ open: () => {}, close: () => {}, isOpen: false });

export const useAuthModal = () => useContext(Ctx);

const AuthModalPanel = lazy(() => import("./AuthModalPanel"));

export function AuthModalProvider({ children }: { children: React.ReactNode }) {
  const [isOpen, setIsOpen] = useState(false);
  const open = useCallback(() => setIsOpen(true), []);
  const close = useCallback(() => setIsOpen(false), []);

  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = "";
      window.removeEventListener("keydown", onKey);
    };
  }, [isOpen, close]);

  return (
    <Ctx.Provider value={{ open, close, isOpen }}>
      {children}
      {isOpen ? (
        <Suspense fallback={null}>
          <AuthModalPanel onClose={close} />
        </Suspense>
      ) : null}
    </Ctx.Provider>
  );
}
