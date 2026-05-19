import { useEffect, useState, createContext, useContext, useCallback } from "react";
import { z } from "zod";
import { toast } from "sonner";
import { Mail, Lock, ArrowRight, Loader2, X } from "lucide-react";
import logo from "@/assets/logo-rekovo.svg";
import {
  adminUrlWithAuthHandoff,
  clinicDashboardUrlWithAuthHandoff,
  fetchSocialLoginProviders,
  getApiBaseUrl,
  getPostLoginTargets,
  loginWithPassword,
  registerUser,
  retoverFetch,
  setMembershipRole,
  setUserAuthSession,
} from "@/lib/retoverApi";

const CLINIC_ROLES = [
  { value: "dental", label: "Dental" },
  { value: "receptionist", label: "Receptionist" },
  { value: "owner", label: "Owner" },
  { value: "manager", label: "Manager" },
] as const;

const SOCIAL_PROVIDER_ORDER = ["google", "facebook", "linkedin"] as const;

type SocialProvider = {
  provider: (typeof SOCIAL_PROVIDER_ORDER)[number];
  enabled: boolean;
  configured: boolean;
  missing_fields: string[];
  login_supported: boolean;
  reason: string;
};

type AuthModalCtx = { open: () => void; close: () => void; isOpen: boolean };
const Ctx = createContext<AuthModalCtx>({ open: () => {}, close: () => {}, isOpen: false });

export const useAuthModal = () => useContext(Ctx);

const errorMessage = (error: unknown, fallback: string) =>
  error instanceof Error ? error.message : fallback;

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
  const orgIdFromUrl =
    typeof window !== "undefined"
      ? new URLSearchParams(window.location.search).get("org_id")
      : null;
  const inviteTokenFromUrl =
    typeof window !== "undefined"
      ? new URLSearchParams(window.location.search).get("invite_token")
      : null;
  const inviteOrgId =
    orgIdFromUrl ||
    (typeof window !== "undefined" ? window.localStorage.getItem("retover_signup_org_id") : null);
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [phase, setPhase] = useState<"credentials" | "role">("credentials");
  const [selectedRole, setSelectedRole] = useState<string>("dental");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [oauthLoading, setOauthLoading] = useState<string | null>(null);
  const [socialProviders, setSocialProviders] = useState<SocialProvider[]>([]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const rows = await fetchSocialLoginProviders();
        if (cancelled) return;
        if (Array.isArray(rows)) setSocialProviders(rows as SocialProvider[]);
      } catch {
        if (!cancelled) setSocialProviders([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (orgIdFromUrl) window.localStorage.setItem("retover_signup_org_id", orgIdFromUrl);
  }, [orgIdFromUrl]);

  const providerState = (p: SocialProvider["provider"]) =>
    socialProviders.find((x) => x.provider === p) || null;

  const shouldOpenAdminApp = (me: { is_superuser?: boolean; admin_access?: boolean } | null) =>
    Boolean(me?.is_superuser || me?.admin_access)

  const redirectToTargetApp = async () => {
    onClose();
    const { adminUrl, dashboardUrl } = getPostLoginTargets();
    const me = await retoverFetch("/auth/me");
    if (shouldOpenAdminApp(me)) {
      localStorage.setItem(
        "retover_admin_access_token",
        localStorage.getItem("retover_access_token") || "",
      );
      window.location.assign(adminUrlWithAuthHandoff(adminUrl));
      return;
    }
    window.location.assign(clinicDashboardUrlWithAuthHandoff(dashboardUrl));
  };

  const proceedAfterCredentialAuth = async () => {
    const me = await retoverFetch("/auth/me");
    if (shouldOpenAdminApp(me)) {
      await redirectToTargetApp();
      return;
    }
    if (!me?.role) {
      setPhase("role");
      return;
    }
    await redirectToTargetApp();
  };

  const handleSaveRole = async () => {
    setLoading(true);
    try {
      await setMembershipRole(selectedRole);
      toast.success("Role saved.");
      await redirectToTargetApp();
    } catch (e: unknown) {
      toast.error(errorMessage(e, "Could not save role"));
    } finally {
      setLoading(false);
    }
  };

  const handleEmail = async (e: React.FormEvent) => {
    e.preventDefault();
    const parsed = credSchema.safeParse({ email, password });
    if (!parsed.success) {
      toast.error(parsed.error.issues[0].message);
      return;
    }
    setLoading(true);
    try {
      if (mode === "signup") {
        const orgName = (email.split("@")[1] || "New organisation").replace(/\..*$/, "");
        const data = await registerUser({
          email,
          password,
          organisation_name: orgName || "New organisation",
          org_id: inviteOrgId || undefined,
        });
        setUserAuthSession(data);
        localStorage.setItem("retover_user_email", email);
        toast.success("Account created.");
        setPhase("role");
      } else {
        const data = await loginWithPassword({
          email: parsed.data.email,
          password: parsed.data.password,
        });
        setUserAuthSession(data);
        localStorage.setItem("retover_user_email", parsed.data.email);
        toast.success("Welcome back!");
        await proceedAfterCredentialAuth();
      }
    } catch (e: unknown) {
      toast.error(errorMessage(e, "Something went wrong"));
    } finally {
      setLoading(false);
    }
  };

  const providerLabel = (provider: SocialProvider["provider"]) =>
    provider === "google" ? "Google" : provider === "facebook" ? "Facebook" : "LinkedIn";

  const providerIcon = (provider: SocialProvider["provider"]) =>
    provider === "google" ? (
      <GoogleIcon />
    ) : provider === "facebook" ? (
      <FacebookIcon />
    ) : (
      <LinkedInIcon />
    );

  const providerUnavailableReason = (provider: SocialProvider["provider"]) => {
    const s = providerState(provider);
    if (!s) return "Provider status unavailable.";
    if (!s.enabled) return s.reason || `${providerLabel(provider)} is disabled.`;
    if (!s.configured) {
      const missing = s.missing_fields?.length ? ` (${s.missing_fields.join(", ")})` : "";
      return `${s.reason || `${providerLabel(provider)} is not configured.`}${missing}`;
    }
    if (!s.login_supported) return s.reason || `${providerLabel(provider)} login is unavailable.`;
    return "";
  };

  const oauth = async (provider: SocialProvider["provider"]) => {
    const s = providerState(provider);
    if (!s || !s.enabled || !s.configured || !s.login_supported) {
      toast.error(providerUnavailableReason(provider));
      return;
    }
    setOauthLoading(provider);
    try {
      const base = getApiBaseUrl();
      const u = new URL(`${base}/auth/oauth/${provider}/start`);
      if (inviteTokenFromUrl) u.searchParams.set("invite_token", inviteTokenFromUrl);
      if (orgIdFromUrl) u.searchParams.set("org_id", orgIdFromUrl);
      window.location.assign(u.toString());
    } catch (e: unknown) {
      toast.error(errorMessage(e, "Sign-in failed"));
      setOauthLoading(null);
    }
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
            <img src={logo} alt="VOXBULK.COM" className="h-9 w-auto" />
          </div>
        </div>

        <div className="p-7">
          {phase === "role" ? (
            <>
              <h2 className="text-[24px] font-bold tracking-[-0.02em] text-heading text-center">
                Choose your role
              </h2>
              <p className="mt-1 text-[13.5px] text-body text-center">
                Tailors your clinic dashboard.
              </p>
              <div className="mt-5 grid grid-cols-2 gap-2">
                {CLINIC_ROLES.map((r) => (
                  <button
                    key={r.value}
                    type="button"
                    onClick={() => setSelectedRole(r.value)}
                    className={`rounded-xl border px-3 py-3 text-[13.5px] font-medium transition-colors ${
                      selectedRole === r.value
                        ? "border-primary bg-primary/10 text-heading"
                        : "border-border bg-secondary/40 text-body hover:bg-secondary/60"
                    }`}
                  >
                    {r.label}
                  </button>
                ))}
              </div>
              <button
                type="button"
                disabled={loading}
                onClick={handleSaveRole}
                className="btn-primary w-full !py-3 mt-5"
              >
                {loading ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : (
                  <>
                    Continue <ArrowRight size={15} />
                  </>
                )}
              </button>
            </>
          ) : (
            <>
              <h2 className="text-[24px] font-bold tracking-[-0.02em] text-heading text-center">
                {mode === "signin" ? "Welcome back" : "Create your account"}
              </h2>
              <p className="mt-1 text-[13.5px] text-body text-center">
                {mode === "signin"
                  ? "Sign in to access your dashboard."
                  : "Get started in 30 seconds."}
              </p>

              <div className="mt-6 grid gap-2">
                {SOCIAL_PROVIDER_ORDER.map((provider) => {
                  const disabled =
                    !providerState(provider) ||
                    !providerState(provider)?.enabled ||
                    !providerState(provider)?.configured ||
                    !providerState(provider)?.login_supported ||
                    oauthLoading != null;
                  const reason = disabled ? providerUnavailableReason(provider) : "";
                  return (
                    <div className="grid gap-1" key={provider}>
                      <SocialBtn
                        onClick={() => oauth(provider)}
                        loading={oauthLoading === provider}
                        label={`Continue with ${providerLabel(provider)}`}
                        icon={providerIcon(provider)}
                        disabled={disabled}
                      />
                      {disabled && reason ? (
                        <div className="text-[11px] leading-snug text-muted-text text-center px-1">
                          {reason}
                        </div>
                      ) : null}
                    </div>
                  );
                })}
              </div>

              <div className="my-5 flex items-center gap-3">
                <div className="flex-1 h-px bg-border" />
                <span className="text-[11px] uppercase tracking-wider text-muted-text">
                  or with email
                </span>
                <div className="flex-1 h-px bg-border" />
              </div>

              <form onSubmit={handleEmail} className="space-y-3">
                <div className="relative">
                  <Mail
                    size={16}
                    className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-text"
                  />
                  <input
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@clinic.co.uk"
                    className="w-full pl-10 pr-3 py-3 rounded-xl border border-border bg-secondary/40 text-[14.5px] focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
                  />
                </div>
                <div className="relative">
                  <Lock
                    size={16}
                    className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-text"
                  />
                  <input
                    type="password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Password"
                    minLength={6}
                    className="w-full pl-10 pr-3 py-3 rounded-xl border border-border bg-secondary/40 text-[14.5px] focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
                  />
                </div>
                <button type="submit" disabled={loading} className="btn-primary w-full !py-3">
                  {loading ? (
                    <Loader2 size={16} className="animate-spin" />
                  ) : (
                    <>
                      {mode === "signin" ? "Sign in" : "Create account"} <ArrowRight size={15} />
                    </>
                  )}
                </button>
              </form>

              <p className="mt-4 text-center text-[13px] text-muted-text">
                {mode === "signin" ? "New here?" : "Already have an account?"}{" "}
                <button
                  type="button"
                  onClick={() => setMode(mode === "signin" ? "signup" : "signin")}
                  className="text-primary font-semibold hover:underline"
                >
                  {mode === "signin" ? "Create an account" : "Sign in"}
                </button>
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function SocialBtn({
  onClick,
  label,
  icon,
  loading,
  compact,
  disabled,
}: {
  onClick: () => void;
  label: string;
  icon: React.ReactNode;
  loading?: boolean;
  compact?: boolean;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={Boolean(disabled) || Boolean(loading)}
      className={`flex items-center justify-center gap-2.5 ${compact ? "h-11" : "h-11"} rounded-xl border border-border bg-white hover:bg-secondary/60 text-[13.5px] font-medium text-heading transition-colors disabled:opacity-60`}
    >
      {loading ? <Loader2 size={15} className="animate-spin" /> : icon}
      {label}
    </button>
  );
}

function GoogleIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 48 48">
      <path
        fill="#FFC107"
        d="M43.6 20.5H42V20H24v8h11.3C33.7 32.4 29.2 35.5 24 35.5c-6.4 0-11.5-5.1-11.5-11.5S17.6 12.5 24 12.5c2.9 0 5.6 1.1 7.6 2.9l5.7-5.7C33.6 6.5 29 4.5 24 4.5 13.2 4.5 4.5 13.2 4.5 24S13.2 43.5 24 43.5 43.5 34.8 43.5 24c0-1.2-.1-2.4-.4-3.5z"
      />
      <path
        fill="#FF3D00"
        d="m6.3 14.7 6.6 4.8C14.7 16 19 12.5 24 12.5c2.9 0 5.6 1.1 7.6 2.9l5.7-5.7C33.6 6.5 29 4.5 24 4.5 16.3 4.5 9.7 8.6 6.3 14.7z"
      />
      <path
        fill="#4CAF50"
        d="M24 43.5c5 0 9.5-1.9 12.9-5l-6-4.9c-1.9 1.4-4.3 2.4-6.9 2.4-5.2 0-9.6-3.4-11.2-8L6.4 33C9.7 39.2 16.3 43.5 24 43.5z"
      />
      <path
        fill="#1976D2"
        d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4-4 5.3l6 4.9c-.4.4 6.7-4.9 6.7-14.2 0-1.2-.1-2.4-.4-3.5z"
      />
    </svg>
  );
}
function FacebookIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="#1877F2">
      <path d="M24 12a12 12 0 1 0-13.875 11.853V15.47H7.078V12h3.047V9.356c0-3.007 1.792-4.668 4.533-4.668 1.312 0 2.686.234 2.686.234v2.953H15.83c-1.49 0-1.955.925-1.955 1.874V12h3.328l-.532 3.469h-2.796v8.385A12.003 12.003 0 0 0 24 12z" />
    </svg>
  );
}
function LinkedInIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="#0A66C2">
      <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.065 2.065 0 1 1 0-4.13 2.065 2.065 0 0 1 0 4.13zM6.813 20.452H3.861V9h2.952v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.727v20.545C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.273V1.727C24 .774 23.2 0 22.222 0z" />
    </svg>
  );
}
