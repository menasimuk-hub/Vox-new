import { createFileRoute, useNavigate, Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { z } from "zod";
import { SiteHeader, SiteFooter } from "@/components/SiteShell";
import { toast } from "sonner";
import { Mail, Lock, ArrowRight, Loader2 } from "lucide-react";
import logo from "@/assets/logo-rekovo.svg";
import {
  acceptInvite,
  adminUrlWithAuthHandoff,
  clinicDashboardUrlWithAuthHandoff,
  clearClinicAuthSession,
  clearAllRetoverSiteLocalKeys,
  fetchInvitePreview,
  fetchSocialLoginProviders,
  forgotPasswordRequest,
  getApiBaseUrl,
  getPostLoginTargets,
  loginWithPassword,
  registerUser,
  retoverFetch,
  setMembershipRole,
  setUserAuthSession,
  submitSelfServeRequest,
  fetchPromoPreview,
  fetchPublicPlans,
} from "@/lib/retoverApi";

type SocialProviderRow = {
  provider: "google" | "facebook" | "linkedin";
  enabled: boolean;
  configured: boolean;
  missing_fields: string[];
  login_supported: boolean;
  reason: string;
};

const PROVIDER_ORDER = ["google", "facebook", "linkedin"] as const;

function mergeSocialProviderRows(apiRows: unknown): SocialProviderRow[] {
  const rows = Array.isArray(apiRows) ? apiRows : [];
  const map = new Map<string, Partial<SocialProviderRow>>();
  for (const raw of rows) {
    const r = raw as Partial<SocialProviderRow>;
    const p = r?.provider;
    if (p === "google" || p === "facebook" || p === "linkedin") map.set(p, r);
  }
  return PROVIDER_ORDER.map((p) => {
    const fromApi = map.get(p);
    const reason =
      typeof fromApi?.reason === "string" && fromApi.reason.trim() ? fromApi.reason.trim() : "";
    return {
      provider: p,
      enabled: Boolean(fromApi?.enabled),
      configured: Boolean(fromApi?.configured),
      missing_fields: Array.isArray(fromApi?.missing_fields)
        ? fromApi!.missing_fields!.map(String)
        : [],
      login_supported: Boolean(fromApi?.login_supported),
      reason:
        reason ||
        (!fromApi
          ? "OAuth status unavailable — check API connectivity or server configuration."
          : "This provider is not configured for sign-in yet."),
    };
  });
}

const errorMessage = (error: unknown, fallback: string) =>
  error instanceof Error ? error.message : fallback;

const CLINIC_ROLES = [
  { value: "dental", label: "Dental" },
  { value: "receptionist", label: "Receptionist" },
  { value: "owner", label: "Owner" },
  { value: "manager", label: "Manager" },
] as const;

export const Route = createFileRoute("/signin")({
  head: () => ({
    meta: [
      { title: "Sign in — VOXBULK.COM" },
      { name: "description", content: "Sign in to your VOXBULK.COM account." },
    ],
  }),
  component: SignInPage,
});

const credSchema = z.object({
  email: z.string().trim().email("Enter a valid email").max(255),
  password: z.string().min(6, "Password must be at least 6 characters").max(128),
});

function SignInPage() {
  const navigate = useNavigate();
  const orgIdFromUrl =
    typeof window !== "undefined"
      ? new URLSearchParams(window.location.search).get("org_id")
      : null;
  const inviteTokenFromUrl =
    typeof window !== "undefined"
      ? new URLSearchParams(window.location.search).get("invite_token")
      : null;
  const promoFromUrl =
    typeof window !== "undefined" ? new URLSearchParams(window.location.search).get("promo") : null;
  const planFromUrl =
    typeof window !== "undefined" ? new URLSearchParams(window.location.search).get("plan") : null;
  const modeFromUrl =
    typeof window !== "undefined" ? new URLSearchParams(window.location.search).get("mode") : null;
  const orgId =
    orgIdFromUrl ||
    (typeof window !== "undefined" ? localStorage.getItem("retover_signup_org_id") : null);
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [phase, setPhase] = useState<"credentials" | "role">("credentials");
  const [selectedRole, setSelectedRole] = useState<string>("dental");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [orgName, setOrgName] = useState("");
  const [planCode, setPlanCode] = useState("starter");
  const [promoCode, setPromoCode] = useState<string | null>(promoFromUrl);
  const [promoPreview, setPromoPreview] = useState<{ name?: string; trial_days?: number; plan_code?: string } | null>(null);
  const [signupPlans, setSignupPlans] = useState<Array<{ code: string; name: string; price_gbp_pence?: number }>>([]);
  const [loading, setLoading] = useState(false);
  const [oauthLoading, setOauthLoading] = useState<string | null>(null);
  const [socialProviders, setSocialProviders] = useState<SocialProviderRow[]>(() =>
    mergeSocialProviderRows([]),
  );
  const [socialProvidersLoading, setSocialProvidersLoading] = useState(true);
  const [pending, setPending] = useState(false);
  const [inviteOrgName, setInviteOrgName] = useState<string | null>(null);
  const [credentialView, setCredentialView] = useState<"login" | "forgot">("login");
  const [forgotMessage, setForgotMessage] = useState("");
  const [forgotSending, setForgotSending] = useState(false);

  const showForgot = mode === "signin" && credentialView === "forgot";

  useEffect(() => {
    if (mode !== "signin") setCredentialView("login");
  }, [mode]);

  useEffect(() => {
    if (modeFromUrl === "signup") setMode("signup");
  }, [modeFromUrl]);

  useEffect(() => {
    if (!planFromUrl) return;
    setMode("signup");
    setPlanCode(planFromUrl.trim().toLowerCase());
  }, [planFromUrl]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const rows = (await fetchPublicPlans()) as Array<{ code: string; name: string; price_gbp_pence?: number }>;
        if (cancelled) return;
        setSignupPlans(Array.isArray(rows) ? rows : []);
      } catch {
        if (!cancelled) setSignupPlans([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!promoFromUrl) return;
    setMode("signup");
    setPromoCode(promoFromUrl.toUpperCase());
    let cancelled = false;
    (async () => {
      try {
        const data = (await fetchPromoPreview(promoFromUrl)) as { promo?: { name?: string; trial_days?: number; plan_code?: string } };
        if (cancelled) return;
        const promo = data?.promo;
        setPromoPreview(promo || null);
        if (promo?.plan_code) setPlanCode(promo.plan_code);
      } catch {
        if (!cancelled) toast.error("This offer link is invalid or expired.");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [promoFromUrl]);

  useEffect(() => {
    let cancelled = false;
    setSocialProvidersLoading(true);
    (async () => {
      try {
        const rows = await fetchSocialLoginProviders();
        if (cancelled) return;
        setSocialProviders(mergeSocialProviderRows(rows));
      } catch {
        if (cancelled) return;
        setSocialProviders(mergeSocialProviderRows([]));
      } finally {
        if (!cancelled) setSocialProvidersLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // OAuth callback handoff: backend redirects to /signin#access_token=...&org_id=...&user_id=...
  useEffect(() => {
    if (typeof window === "undefined") return;
    const hash = window.location.hash || "";
    if (!hash.startsWith("#")) return;
    const params = new URLSearchParams(hash.slice(1));
    const access_token = params.get("access_token");
    const org_id = params.get("org_id");
    const user_id = params.get("user_id");
    const oauth = params.get("oauth");
    if (!oauth || !access_token || !org_id || !user_id) return;

    try {
      setUserAuthSession({ access_token, org_id, user_id });
      localStorage.setItem("retover_user_email", email || "");
      // Clear fragment so refresh doesn't repeat.
      window.history.replaceState(
        {},
        document.title,
        window.location.pathname + window.location.search,
      );
      toast.success("Signed in.");
      proceedAfterCredentialAuth().catch(() => routeAfterAuthToRightApp());
    } catch (e: unknown) {
      toast.error(errorMessage(e, "Could not complete sign-in"));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // OAuth error returned via query string from backend callback
  useEffect(() => {
    if (typeof window === "undefined") return;
    const q = new URLSearchParams(window.location.search);
    const err = q.get("oauth_error");
    if (!err) return;
    toast.error(err);
    q.delete("oauth_error");
    q.delete("provider");
    const next = q.toString();
    window.history.replaceState(
      {},
      document.title,
      window.location.pathname + (next ? `?${next}` : ""),
    );
  }, []);

  useEffect(() => {
    if (!inviteTokenFromUrl) return;
    let cancelled = false;
    setMode("signup");
    (async () => {
      try {
        const p = await fetchInvitePreview(inviteTokenFromUrl);
        if (cancelled) return;
        setEmail(String(p.email || ""));
        setInviteOrgName(p.organisation_name ? String(p.organisation_name) : null);
        if (p.role) setSelectedRole(String(p.role));
      } catch (e: unknown) {
        toast.error(errorMessage(e, "Invalid or expired invitation"));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [inviteTokenFromUrl]);

  // If already signed in: superusers go to marketing home; clinic users without role stay to pick role
  useEffect(() => {
    const token = localStorage.getItem("retover_access_token");
    if (!token) return;
    let cancelled = false;
    (async () => {
      try {
        const me = await retoverFetch("/auth/me");
        if (cancelled) return;
        if (me?.is_superuser || me?.admin_access) {
          navigate({ to: "/" });
          return;
        }
        if (!me?.role) {
          setPhase("role");
          return;
        }
        navigate({ to: "/" });
      } catch (e: unknown) {
        if (cancelled) return;
        const st = typeof e === "object" && e && "status" in e ? e.status : undefined;
        if (st === 401 || st === 403) clearClinicAuthSession();
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [navigate]);

  useEffect(() => {
    if (orgIdFromUrl) localStorage.setItem("retover_signup_org_id", orgIdFromUrl);
  }, [orgIdFromUrl]);

  const shouldOpenAdminApp = (me) => Boolean(me?.is_superuser || me?.admin_access)

  const routeAfterAuthToRightApp = async () => {
    const { adminUrl, dashboardUrl } = getPostLoginTargets();
    const me = await retoverFetch("/auth/me");
    if (shouldOpenAdminApp(me)) {
      // Hand-off to admin app
      localStorage.setItem(
        "retover_admin_access_token",
        localStorage.getItem("retover_access_token") || "",
      );
      window.location.assign(adminUrlWithAuthHandoff(adminUrl));
      return;
    }
    window.location.assign(clinicDashboardUrlWithAuthHandoff(dashboardUrl));
  };

  /** After token exists: platform admin → admin; clinic without role → stay on role step; else → dashboard */
  const proceedAfterCredentialAuth = async () => {
    const me = await retoverFetch("/auth/me");
    if (shouldOpenAdminApp(me)) {
      await routeAfterAuthToRightApp();
      return;
    }
    if (!me?.role) {
      setPhase("role");
      return;
    }
    await routeAfterAuthToRightApp();
  };

  const handleSaveRole = async () => {
    setLoading(true);
    try {
      await setMembershipRole(selectedRole);
      toast.success("Role saved.");
      await routeAfterAuthToRightApp();
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
        if (inviteTokenFromUrl) {
          const data = await acceptInvite({ token: inviteTokenFromUrl, password });
          setUserAuthSession(data);
          localStorage.setItem("retover_user_email", email);
          toast.success("Invitation accepted.");
          await proceedAfterCredentialAuth();
          return;
        }
        if (orgId) {
          const derived = (email.split("@")[1] || "New organisation").replace(/\..*$/, "");
          const data = await registerUser({
            email,
            password,
            organisation_name: derived || "New organisation",
            org_id: orgId || undefined,
          });
          setUserAuthSession(data);
          localStorage.setItem("retover_user_email", email);
          toast.success("Account created.");
          setPhase("role");
        } else {
          const name = (orgName || "").trim();
          if (!name) throw new Error("Organisation / clinic name is required");
          const result = await submitSelfServeRequest({
            email,
            password,
            organisation_name: name,
            plan_code: planCode,
            promo_code: promoCode || undefined,
          });
          if (result?.status === "approved" && result?.access_token) {
            setUserAuthSession(result);
            localStorage.setItem("retover_user_email", email);
            toast.success("Account created — you're ready to go.");
            await proceedAfterCredentialAuth();
          } else {
            setPending(true);
            toast.success("Request submitted. Await admin approval.");
          }
        }
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

  const providerState = (p: "google" | "facebook" | "linkedin") => {
    return socialProviders.find((x) => x.provider === p) || null;
  };

  const handleForgotSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const em = email.trim();
    const parsed = z.string().trim().email("Enter a valid email").max(255).safeParse(em);
    if (!parsed.success) {
      toast.error(parsed.error.issues[0]?.message || "Invalid email");
      return;
    }
    setForgotSending(true);
    setForgotMessage("");
    try {
      const res = await forgotPasswordRequest(em);
      setForgotMessage(String(res?.message || ""));
      toast.success("Request received.");
    } catch (err: unknown) {
      toast.error(errorMessage(err, "Could not submit request. Try again later."));
    } finally {
      setForgotSending(false);
    }
  };

  const oauth = async (provider: "google" | "facebook" | "linkedin") => {
    const s = providerState(provider);
    if (!s) return;
    if (!s.enabled || !s.configured || !s.login_supported) {
      toast.error(s.reason || "Provider unavailable");
      return;
    }
    setOauthLoading(provider);
    try {
      const base = getApiBaseUrl();
      const u = new URL(`${base}/auth/oauth/${provider}/start`);
      if (inviteTokenFromUrl) u.searchParams.set("invite_token", inviteTokenFromUrl);
      if (orgIdFromUrl) u.searchParams.set("org_id", orgIdFromUrl);
      window.location.assign(u.toString());
    } finally {
      setOauthLoading(null);
    }
  };

  return (
    <div className="bg-background text-body antialiased min-h-screen flex flex-col">
      <SiteHeader />
      <main className="flex-1 pt-[110px] md:pt-[130px] pb-24">
        <div className="max-w-[480px] mx-auto px-5 md:px-10">
          <div className="text-center">
            <img src={logo} alt="VOXBULK.COM" className="h-10 mx-auto" />
            <h1 className="mt-5 text-[30px] md:text-[36px] font-bold tracking-[-0.03em] text-heading leading-[1.1]">
              {showForgot
                ? "Forgot password"
                : mode === "signin"
                  ? "Welcome back"
                  : "Create your account"}
            </h1>
            <p className="mt-2 text-body text-[15px]">
              {showForgot
                ? "Enter your email. If it matches an account, you will receive reset instructions shortly."
                : mode === "signin"
                  ? "Sign in to access your dashboard."
                  : "Create your account, then continue through the onboarding flow."}
            </p>
            {inviteTokenFromUrl && (
              <div className="mt-3 inline-flex items-center gap-2 rounded-full border border-border bg-secondary/50 px-3 py-1.5 text-[12.5px] text-muted-text">
                <strong className="text-heading font-semibold">Admin invitation</strong>
                <span>
                  — Join{" "}
                  {inviteOrgName ? (
                    <strong className="text-heading">{inviteOrgName}</strong>
                  ) : (
                    "your clinic"
                  )}{" "}
                  and set your password below.
                </span>
              </div>
            )}
            {orgId && !inviteTokenFromUrl && (
              <div className="mt-3 inline-flex items-center gap-2 rounded-full border border-border bg-secondary/50 px-3 py-1.5 text-[12.5px] text-muted-text">
                <strong className="text-heading font-semibold">Clinic invite</strong>
                <span>— You are signing up for this organisation.</span>
              </div>
            )}
            {!orgId && !inviteTokenFromUrl && mode === "signup" && promoPreview && (
              <div className="mt-3 rounded-xl border border-primary/30 bg-primary/5 px-4 py-3 text-[13px] text-heading">
                <strong>Special offer applied</strong>
                <div className="mt-1 text-muted-text">
                  {promoPreview.name || "Dental package"}
                  {promoPreview.trial_days ? ` · ${promoPreview.trial_days}-day trial` : ""}
                  {promoCode ? ` · Code ${promoCode}` : ""}
                </div>
              </div>
            )}
            {!orgId && !inviteTokenFromUrl && mode === "signup" && (
              <div className="mt-3 text-[12.5px] text-muted-text">
                Self-serve signup: create your clinic, choose a package, then wait for admin
                approval.
              </div>
            )}
          </div>

          <div className="mt-8 bg-white border border-border rounded-2xl p-6 md:p-7 shadow-elegant">
            {phase === "role" ? (
              <div className="space-y-4">
                <h2 className="text-lg font-semibold text-heading text-center">Choose your role</h2>
                <p className="text-[13.5px] text-muted-text text-center">
                  We use this to tailor your dashboard. You can change it later if needed.
                </p>
                <div className="grid grid-cols-2 gap-2">
                  {CLINIC_ROLES.map((r) => (
                    <button
                      key={r.value}
                      type="button"
                      onClick={() => setSelectedRole(r.value)}
                      className={`rounded-xl border px-3 py-3 text-[14px] font-medium transition-colors ${
                        selectedRole === r.value
                          ? "border-primary bg-primary/10 text-heading"
                          : "border-border bg-secondary/30 text-body hover:bg-secondary/50"
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
                  className="btn-primary w-full !py-3"
                >
                  {loading ? (
                    <Loader2 size={16} className="animate-spin" />
                  ) : (
                    <>
                      Continue <ArrowRight size={15} />
                    </>
                  )}
                </button>
              </div>
            ) : (
              <>
                <div className="grid gap-6">
                  {/* Social */}
                  {!showForgot && (
                    <div className="grid gap-3">
                      <div className="text-center">
                        <h2 className="text-[13px] font-semibold uppercase tracking-wider text-muted-text">
                          Continue with
                        </h2>
                        {socialProvidersLoading ? (
                          <p className="mt-1 text-[12px] text-muted-text">
                            Checking social sign-in…
                          </p>
                        ) : null}
                      </div>
                      <div className="grid gap-2.5">
                        {(["google", "facebook", "linkedin"] as const).map((p) => {
                          const s = providerState(p);
                          if (!s) return null;
                          const disabled =
                            !s.enabled ||
                            !s.configured ||
                            !s.login_supported ||
                            oauthLoading != null;
                          const reason = !s.enabled
                            ? s.reason
                            : !s.configured
                              ? `${s.reason}${s.missing_fields?.length ? ` (${s.missing_fields.join(", ")})` : ""}`
                              : !s.login_supported
                                ? s.reason
                                : "";
                          const icon =
                            p === "google" ? (
                              <GoogleIcon />
                            ) : p === "facebook" ? (
                              <FacebookIcon />
                            ) : (
                              <LinkedInIcon />
                            );
                          const label =
                            p === "google"
                              ? "Continue with Google"
                              : p === "facebook"
                                ? "Continue with Facebook"
                                : "Continue with LinkedIn";
                          return (
                            <div key={p} className="grid gap-1.5">
                              <SocialBtn
                                onClick={() => oauth(p)}
                                loading={oauthLoading === p}
                                label={label}
                                icon={icon}
                                disabled={disabled}
                              />
                              {disabled && reason ? (
                                <div className="text-[12px] leading-snug text-muted-text text-center px-2">
                                  {reason}
                                </div>
                              ) : null}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {!showForgot && (
                    <div className="flex items-center gap-3">
                      <div className="flex-1 h-px bg-border" />
                      <span className="text-[12px] font-semibold uppercase tracking-wider text-muted-text">
                        Or continue with email
                      </span>
                      <div className="flex-1 h-px bg-border" />
                    </div>
                  )}

                  {showForgot ? (
                    <form onSubmit={handleForgotSubmit} className="space-y-3">
                      <label className="block">
                        <span className="text-[12.5px] font-semibold uppercase tracking-wider text-muted-text">
                          Email
                        </span>
                        <div className="mt-1.5 relative">
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
                            className="w-full pl-10 pr-3 py-3 rounded-xl border border-border bg-secondary/30 text-[15px] focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
                          />
                        </div>
                      </label>
                      {forgotMessage ? (
                        <div className="rounded-xl border border-border bg-secondary/40 p-3 text-[13.5px] text-body">
                          {forgotMessage}
                        </div>
                      ) : null}
                      <button
                        type="submit"
                        disabled={forgotSending}
                        className="btn-primary w-full !py-3"
                      >
                        {forgotSending ? (
                          <Loader2 size={16} className="animate-spin" />
                        ) : (
                          "Send reset link"
                        )}
                      </button>
                      <p className="text-center text-[13px] text-muted-text">
                        <button
                          type="button"
                          onClick={() => {
                            setCredentialView("login");
                            setForgotMessage("");
                          }}
                          className="text-primary font-semibold hover:underline"
                        >
                          Back to sign in
                        </button>
                      </p>
                    </form>
                  ) : (
                    <>
                      <form onSubmit={handleEmail} className="space-y-3">
                        {pending && (
                          <div className="rounded-xl border border-border bg-secondary/50 p-3 text-[13.5px] text-body">
                            <strong className="text-heading">Pending approval.</strong> An admin
                            must approve your request before you can log in.
                          </div>
                        )}
                        <label className="block">
                          <span className="text-[12.5px] font-semibold uppercase tracking-wider text-muted-text">
                            Email
                          </span>
                          <div className="mt-1.5 relative">
                            <Mail
                              size={16}
                              className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-text"
                            />
                            <input
                              type="email"
                              required
                              readOnly={Boolean(inviteTokenFromUrl)}
                              value={email}
                              onChange={(e) => setEmail(e.target.value)}
                              placeholder="you@clinic.co.uk"
                              className="w-full pl-10 pr-3 py-3 rounded-xl border border-border bg-secondary/30 text-[15px] focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
                            />
                          </div>
                        </label>
                        <label className="block">
                          <span className="text-[12.5px] font-semibold uppercase tracking-wider text-muted-text">
                            Password
                          </span>
                          <div className="mt-1.5 relative">
                            <Lock
                              size={16}
                              className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-text"
                            />
                            <input
                              type="password"
                              required
                              value={password}
                              onChange={(e) => setPassword(e.target.value)}
                              placeholder="••••••••"
                              minLength={6}
                              autoComplete={mode === "signin" ? "current-password" : "new-password"}
                              className="w-full pl-10 pr-3 py-3 rounded-xl border border-border bg-secondary/30 text-[15px] focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
                            />
                          </div>
                        </label>
                        {mode === "signup" && !orgId && !inviteTokenFromUrl && (
                          <>
                            <label className="block">
                              <span className="text-[12.5px] font-semibold uppercase tracking-wider text-muted-text">
                                Organisation / clinic
                              </span>
                              <div className="mt-1.5">
                                <input
                                  type="text"
                                  required
                                  value={orgName}
                                  onChange={(e) => setOrgName(e.target.value)}
                                  placeholder="e.g. Northgate Dental"
                                  className="w-full px-3 py-3 rounded-xl border border-border bg-secondary/30 text-[15px] focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
                                />
                              </div>
                            </label>
                            <label className="block">
                              <span className="text-[12.5px] font-semibold uppercase tracking-wider text-muted-text">
                                Package
                              </span>
                              <div className="mt-1.5">
                                {promoPreview?.plan_code ? (
                                  <input
                                    type="text"
                                    readOnly
                                    value={promoPreview.plan_code}
                                    className="w-full px-3 py-3 rounded-xl border border-border bg-secondary/50 text-[15px] text-muted-text"
                                  />
                                ) : (
                                  <select
                                    value={planCode}
                                    onChange={(e) => setPlanCode(e.target.value)}
                                    className="w-full px-3 py-3 rounded-xl border border-border bg-secondary/30 text-[15px] focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
                                  >
                                    {signupPlans.length ? (
                                      signupPlans.map((p) => (
                                        <option key={p.code} value={p.code}>
                                          {p.name}
                                          {p.price_gbp_pence != null
                                            ? ` (£${(Number(p.price_gbp_pence) / 100).toFixed(0)}/mo)`
                                            : ""}
                                        </option>
                                      ))
                                    ) : (
                                      <>
                                        <option value="starter">Starter</option>
                                        <option value="practice">Practice</option>
                                        <option value="group">Group</option>
                                        <option value="dental_1">Dental P1 (£199)</option>
                                        <option value="dental_2">Dental P2 (£299)</option>
                                      </>
                                    )}
                                  </select>
                                )}
                              </div>
                              <p className="mt-1 text-[12.5px] text-muted-text">
                                Payment method: bank transfer (for now).
                              </p>
                            </label>
                          </>
                        )}
                        <button
                          type="submit"
                          disabled={loading}
                          className="btn-primary w-full !py-3 mt-2"
                        >
                          {loading ? (
                            <Loader2 size={16} className="animate-spin" />
                          ) : (
                            <>
                              {mode === "signin" ? "Sign in" : "Create account"}{" "}
                              <ArrowRight size={15} />
                            </>
                          )}
                        </button>
                        {mode === "signin" && !inviteTokenFromUrl ? (
                          <p className="text-center text-[13px] text-muted-text">
                            <button
                              type="button"
                              className="text-primary font-semibold hover:underline"
                              onClick={() => {
                                setCredentialView("forgot");
                                setForgotMessage("");
                              }}
                            >
                              Forgot password?
                            </button>
                          </p>
                        ) : null}
                      </form>
                    </>
                  )}

                  {!showForgot && (
                    <p className="mt-5 text-center text-[13.5px] text-muted-text">
                      {mode === "signin" ? "Don't have an account?" : "Already have an account?"}{" "}
                      <button
                        type="button"
                        onClick={() => setMode(mode === "signin" ? "signup" : "signin")}
                        className="text-primary font-semibold hover:underline"
                      >
                        {mode === "signin" ? "Sign up" : "Sign in"}
                      </button>
                    </p>
                  )}
                </div>
              </>
            )}
          </div>

          <p className="mt-5 text-center text-[12px] text-muted-text">
            By continuing, you agree to our{" "}
            <Link to="/legal-policies" search={{ tab: "terms" }} className="underline hover:text-heading">
              Terms
            </Link>{" "}
            and{" "}
            <Link to="/legal-policies" search={{ tab: "privacy" }} className="underline hover:text-heading">
              Privacy Policy
            </Link>
            .
          </p>
        </div>
      </main>
      <SiteFooter />
    </div>
  );
}

function SocialBtn({
  onClick,
  label,
  icon,
  loading,
  disabled,
}: {
  onClick: () => void;
  label: string;
  icon: React.ReactNode;
  loading?: boolean;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={Boolean(disabled) || Boolean(loading)}
      className="w-full flex items-center justify-center gap-3 h-12 rounded-xl border border-border bg-white hover:bg-secondary/60 text-[14.5px] font-medium text-heading transition-colors disabled:opacity-60 disabled:hover:bg-white"
    >
      {loading ? <Loader2 size={16} className="animate-spin" /> : icon}
      {label}
    </button>
  );
}

function GoogleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 48 48">
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
    <svg width="18" height="18" viewBox="0 0 24 24" fill="#1877F2">
      <path d="M24 12a12 12 0 1 0-13.875 11.853V15.47H7.078V12h3.047V9.356c0-3.007 1.792-4.668 4.533-4.668 1.312 0 2.686.234 2.686.234v2.953H15.83c-1.49 0-1.955.925-1.955 1.874V12h3.328l-.532 3.469h-2.796v8.385A12.003 12.003 0 0 0 24 12z" />
    </svg>
  );
}

function LinkedInIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="#0A66C2">
      <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.065 2.065 0 1 1 0-4.13 2.065 2.065 0 0 1 0 4.13zM6.813 20.452H3.861V9h2.952v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.727v20.545C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.273V1.727C24 .774 23.2 0 22.222 0z" />
    </svg>
  );
}
