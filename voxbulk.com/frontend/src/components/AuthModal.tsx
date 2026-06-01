import { useEffect, useState, createContext, useContext, useCallback } from "react";
import { useNavigate } from "@tanstack/react-router";
import { z } from "zod";
import { toast } from "sonner";
import { Mail, Lock, ArrowRight, Loader2, X } from "lucide-react";
import { BrandLogo } from "@/components/BrandLogo";
import { SocialAuthButtons } from "@/components/SocialAuthButtons";
import { useAuth } from "@/lib/auth";
import { resolvePostLoginDestination } from "@/lib/api";
import type { AuthUser } from "@/lib/auth";

type AuthModalCtx = { open: () => void; close: () => void; isOpen: boolean };
const Ctx = createContext<AuthModalCtx>({ open: () => {}, close: () => {}, isOpen: false });

export const useAuthModal = () => useContext(Ctx);

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
      {isOpen && <AuthModal onClose={close} />}
    </Ctx.Provider>
  );
}

const credSchema = z.object({
  email: z.string().trim().email("Enter a valid email").max(255),
  password: z.string().min(6, "Password must be at least 6 characters").max(128),
});

function AuthModal({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate();
  const auth = useAuth();
  const [mode, setMode] = useState<"signin" | "signup" | "forgot">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [orgName, setOrgName] = useState("");
  const [loading, setLoading] = useState(false);
  const [oauthLoading, setOauthLoading] = useState<string | null>(null);

  const routeAfterAuth = (user: AuthUser) => {
    onClose();
    const destination = resolvePostLoginDestination(user);
    if (!destination) return;
    if (destination.kind === "onboarding") navigate({ to: "/onboarding" });
    else window.location.href = destination.url;
  };

  const handleEmail = async (e: React.FormEvent) => {
    e.preventDefault();
    if (mode === "forgot") {
      const emailSchema = z.string().trim().email("Enter a valid email").max(255);
      const parsed = emailSchema.safeParse(email);
      if (!parsed.success) { toast.error(parsed.error.message); return; }
      setLoading(true);
      try {
        const res = await fetch(`${import.meta.env.VITE_API_BASE_URL}/auth/forgot-password`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email }),
        });
        if (!res.ok) throw new Error("Failed to send reset email");
        toast.success("Check your email for a password reset link!");
        setMode("signin");
        setEmail("");
      } catch (e: unknown) {
        toast.error(e instanceof Error ? e.message : "Something went wrong");
      } finally {
        setLoading(false);
      }
      return;
    }
    const parsed = credSchema.safeParse({ email, password });
    if (!parsed.success) { toast.error(parsed.error.issues[0].message); return; }
    if (mode === "signup" && !orgName.trim()) {
      toast.error("Company name is required");
      return;
    }
    setLoading(true);
    try {
      const user =
        mode === "signup"
          ? await auth.register(email, password, orgName.trim())
          : await auth.login(email, password);
      toast.success(mode === "signup" ? "Account created!" : "Welcome back!");
      routeAfterAuth(user);
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  };

  const oauth = (provider: string) => {
    setOauthLoading(provider);
    auth.startOAuth(provider);
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 animate-fade-in">
      <div className="absolute inset-0 bg-heading/40 backdrop-blur-md" onClick={onClose} />
      <div className="relative w-full max-w-[460px] bg-white rounded-3xl shadow-elevated border border-border overflow-hidden animate-scale-in">
        <button
          onClick={onClose}
          aria-label="Close"
          className="absolute top-4 right-4 z-10 w-9 h-9 rounded-full hover:bg-secondary text-muted-text hover:text-heading flex items-center justify-center transition-colors"
        >
          <X size={18} />
        </button>

        {/* Decorative top */}
        <div className="relative h-24 bg-gradient-to-br from-primary/10 via-primary/5 to-accent/10 border-b border-border overflow-hidden">
          <div className="absolute inset-0 bg-grid opacity-50" />
          <div className="absolute inset-0 flex items-center justify-center">
            <BrandLogo surface="light" className="h-7 w-auto object-contain" />
          </div>
        </div>

        <div className="p-7">
          <h2 className="text-[24px] font-bold tracking-[-0.02em] text-heading text-center">
            {mode === "signin" ? "Welcome back" : mode === "signup" ? "Create your account" : "Reset password"}
          </h2>
          <p className="mt-1 text-[13.5px] text-body text-center">
            {mode === "signin" ? "Sign in to access your dashboard." : mode === "signup" ? "Get started in 30 seconds." : "Enter your email to receive a password reset link."}
          </p>

          {mode !== "forgot" && (
            <div className="mt-6">
              <SocialAuthButtons onOAuth={oauth} oauthLoading={oauthLoading} compact />
            </div>
          )}

          {mode !== "forgot" && (
            <div className="my-5 flex items-center gap-3">
              <div className="flex-1 h-px bg-border" />
              <span className="text-[11px] uppercase tracking-wider text-muted-text">or with email</span>
              <div className="flex-1 h-px bg-border" />
            </div>
          )}

          <form onSubmit={handleEmail} className={mode === "forgot" ? "space-y-3 mt-6" : "space-y-3"}>
            {mode === "signup" ? (
              <div className="relative">
                <label htmlFor="auth-org" className="sr-only">Company name</label>
                <input
                  id="auth-org"
                  type="text"
                  required
                  value={orgName}
                  onChange={(e) => setOrgName(e.target.value)}
                  placeholder="Company name"
                  className="w-full px-3 py-3 rounded-xl border border-border bg-secondary/40 text-[14.5px] focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
                />
              </div>
            ) : null}
            <div className="relative">
              <label htmlFor="auth-email" className="sr-only">Email address</label>
              <Mail size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-text" />
              <input
                id="auth-email"
                type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
                placeholder="you@company.com"

                className="w-full pl-10 pr-3 py-3 rounded-xl border border-border bg-secondary/40 text-[14.5px] focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
              />
            </div>
            {mode !== "forgot" && (
              <div className="relative">
                <label htmlFor="auth-password" className="sr-only">Password</label>
                <Lock size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-text" />
                <input
                  id="auth-password"
                  type="password" required value={password} onChange={(e) => setPassword(e.target.value)}
                  placeholder="Password" minLength={6}
                  className="w-full pl-10 pr-3 py-3 rounded-xl border border-border bg-secondary/40 text-[14.5px] focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
                />
              </div>
            )}
            <button type="submit" disabled={loading} className="btn-primary w-full !py-3">
              {loading ? <Loader2 size={16} className="animate-spin" /> : <>{mode === "signin" ? "Sign in" : mode === "signup" ? "Create account" : "Send reset link"} <ArrowRight size={15} /></>}
            </button>
          </form>

          <p className="mt-4 text-center text-[13px] text-muted-text">
            {mode === "forgot" ? (
              <>
                Remember your password?{" "}
                <button onClick={() => { setMode("signin"); setEmail(""); }} className="text-primary font-semibold hover:underline">
                  Sign in
                </button>
              </>
            ) : mode === "signin" ? (
              <>
                New here?{" "}
                <button onClick={() => setMode("signup")} className="text-primary font-semibold hover:underline">
                  Create an account
                </button>
              </>
            ) : (
              <>
                Already have an account?{" "}
                <button onClick={() => setMode("signin")} className="text-primary font-semibold hover:underline">
                  Sign in
                </button>
              </>
            )}
          </p>

          {mode === "signin" && (
            <div className="mt-2 text-center">
              <button onClick={() => setMode("forgot")} className="text-[12px] text-primary hover:underline font-medium">
                Forgot password?
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
