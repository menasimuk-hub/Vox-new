import { createFileRoute, useNavigate, Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { z } from "zod";
import { SiteHeader, SiteFooter } from "@/components/SiteShell";
import { toast } from "sonner";
import { Mail, Lock, ArrowRight, Loader2, Building2 } from "lucide-react";
import { BrandLogo } from "@/components/BrandLogo";
import { SocialAuthButtons } from "@/components/SocialAuthButtons";
import { useAuth } from "@/lib/auth";
import { apiFetch, resolvePostLoginDestination, type InvitePreview, type OrgLoginOption } from "@/lib/api";
import type { AuthUser } from "@/lib/auth";

export const Route = createFileRoute("/signin")({
  head: () => ({
    meta: [
      { title: "Sign in — VOXBULK" },
      { name: "description", content: "Sign in to your VoxBulk account to manage AI voice and messaging campaigns, workflows and results dashboards." },
      { property: "og:title", content: "Sign in — VoxBulk" },
      { property: "og:description", content: "Access your VoxBulk dashboard." },
      { property: "og:url", content: "https://voxbulk.com/signin" },
    ],
    links: [{ rel: "canonical", href: "https://voxbulk.com/signin" }],
  }),
  component: SignInPage,
});

const credSchema = z.object({
  email: z.string().trim().email("Enter a valid email").max(255),
  password: z.string().min(6, "Password must be at least 6 characters").max(128),
});

type PromoPreview = {
  code: string;
  name: string;
  offer_type: string;
  wallet_credit_pence?: number;
  wallet_credit_gbp?: string;
  signup_url?: string;
};

function SignInPage() {
  const navigate = useNavigate();
  const auth = useAuth();
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [orgName, setOrgName] = useState("");
  const [loading, setLoading] = useState(false);
  const [oauthLoading, setOauthLoading] = useState<string | null>(null);
  const [inviteToken, setInviteToken] = useState<string | null>(null);
  const [invitePreview, setInvitePreview] = useState<InvitePreview | null>(null);
  const [inviteLoading, setInviteLoading] = useState(false);
  const [orgChoices, setOrgChoices] = useState<OrgLoginOption[] | null>(null);
  const [oauthSelectToken, setOauthSelectToken] = useState<string | null>(null);
  const [promoCode, setPromoCode] = useState<string | null>(null);
  const [promoPreview, setPromoPreview] = useState<PromoPreview | null>(null);
  const [promoLoading, setPromoLoading] = useState(false);

  useEffect(() => {
    const oauthResult = auth.consumeOAuthHash();
    if (oauthResult.kind === "org_selection") {
      setOauthSelectToken(oauthResult.selectionToken);
      void auth.fetchOAuthOrgSelection(oauthResult.selectionToken).then(setOrgChoices).catch((e: unknown) => {
        toast.error(e instanceof Error ? e.message : "Could not load companies");
      });
      return;
    }
    if (oauthResult.kind === "authenticated") return;
    const params = new URLSearchParams(window.location.search);
    const oauthError = params.get("oauth_error");
    if (oauthError) toast.error(oauthError);
    const tok = params.get("invite_token");
    if (tok) {
      setInviteToken(tok);
      setInviteLoading(true);
      void auth
        .previewInvite(tok)
        .then((preview) => {
          setInvitePreview(preview);
          setEmail(preview.email);
          setMode("signin");
        })
        .catch((e: unknown) => {
          toast.error(e instanceof Error ? e.message : "Invite link is invalid or expired");
          setInviteToken(null);
        })
        .finally(() => setInviteLoading(false));
    }
    const promo = params.get("promo")?.trim().toUpperCase();
    if (promo) {
      setPromoCode(promo);
      setMode("signup");
      setPromoLoading(true);
      void apiFetch<{ ok?: boolean; promo: PromoPreview }>(`/promo/${encodeURIComponent(promo)}`)
        .then((res) => setPromoPreview(res.promo))
        .catch((e: unknown) => {
          toast.error(e instanceof Error ? e.message : "Promo code is invalid or expired");
          setPromoCode(null);
          setPromoPreview(null);
        })
        .finally(() => setPromoLoading(false));
    }
  }, [auth]);

  const routeAfterAuth = (user: AuthUser) => {
    const destination = resolvePostLoginDestination(user);
    if (!destination) return;
    if (destination.kind === "onboarding") navigate({ to: "/onboarding" });
    else window.location.href = destination.url;
  };

  useEffect(() => {
    if (auth.loading) return;
    if (!auth.user) return;
    routeAfterAuth(auth.user);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [auth.loading, auth.user?.user_id, auth.user?.admin_access, auth.user?.is_superuser]);

  const handleEmail = async (e: React.FormEvent) => {
    e.preventDefault();
    const parsed = credSchema.safeParse({ email, password });
    if (!parsed.success) { toast.error(parsed.error.issues[0].message); return; }
    if (!inviteToken && mode === "signup" && !orgName.trim()) {
      toast.error("Company name is required");
      return;
    }
    setLoading(true);
    try {
      if (inviteToken) {
        const user = await auth.acceptInvite(inviteToken, password);
        toast.success(`Joined ${invitePreview?.organisation_name || "organisation"}!`);
        routeAfterAuth(user);
        return;
      }
      if (mode === "signup") {
        const user = await auth.register(email, password, orgName.trim(), promoCode || undefined);
        toast.success(promoCode ? "Account created — welcome credit applied!" : "Account created!");
        routeAfterAuth(user);
        return;
      }
      const result = await auth.login(email, password);
      if (result.kind === "org_selection") {
        setOrgChoices(result.organisations);
        toast.message("Choose which company to open");
        return;
      }
      toast.success("Welcome back!");
      routeAfterAuth(result.user);
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  };

  const pickOrganisation = async (orgId: string) => {
    setLoading(true);
    try {
      if (oauthSelectToken) {
        const user = await auth.completeOAuthOrgSelection(oauthSelectToken, orgId);
        toast.success("Welcome back!");
        routeAfterAuth(user);
        return;
      }
      const result = await auth.login(email, password, orgId);
      if (result.kind !== "authenticated") return;
      toast.success("Welcome back!");
      routeAfterAuth(result.user);
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Could not sign in");
    } finally {
      setLoading(false);
    }
  };

  const oauth = (provider: string) => {
    setOauthLoading(provider);
    auth.startOAuth(provider, inviteToken || undefined, promoCode || undefined);
  };

  const inviteActive = Boolean(inviteToken && invitePreview);

  return (
    <div className="bg-background text-body antialiased min-h-screen flex flex-col">
      <SiteHeader />
      <main className="flex-1 pt-[110px] md:pt-[130px] pb-24">
        <div className="max-w-[460px] mx-auto px-5 md:px-10">
          <div className="text-center">
            <BrandLogo surface="light" className="h-13 mx-auto w-auto" />
            <h1 className="mt-5 text-[30px] md:text-[36px] font-bold tracking-[-0.03em] text-heading leading-[1.1]">
              {inviteActive ? "Accept invitation" : mode === "signin" ? "Welcome back" : "Create your account"}
            </h1>
            <p className="mt-2 text-body text-[15px]">
              {inviteActive
                ? `Join ${invitePreview?.organisation_name || "an organisation"} as ${invitePreview?.role || "team member"}.`
                : mode === "signin"
                  ? "Sign in to access your dashboard."
                  : "Get started with VOXBULK in 30 seconds."}
            </p>
          </div>

          <div className="mt-8 bg-white border border-border rounded-2xl p-7 shadow-elegant">
            {promoPreview && !inviteActive ? (
              <div className="mb-5 rounded-xl border border-primary/25 bg-primary/5 px-4 py-3 text-sm text-heading">
                <p className="font-semibold text-primary">Offer applied: {promoPreview.name}</p>
                {promoPreview.wallet_credit_pence ? (
                  <p className="mt-1 text-muted-text">
                    Includes {promoPreview.wallet_credit_gbp || `£${(promoPreview.wallet_credit_pence / 100).toFixed(2)}`} welcome wallet credit after signup.
                  </p>
                ) : null}
              </div>
            ) : null}
            {inviteLoading || promoLoading ? (
              <div className="flex justify-center py-8"><Loader2 className="animate-spin text-primary" /></div>
            ) : orgChoices && orgChoices.length > 0 ? (
              <div className="space-y-3">
                <p className="text-sm text-muted-text">You belong to more than one company. Which one should we open?</p>
                {orgChoices.map((org) => (
                  <button
                    key={org.org_id}
                    type="button"
                    disabled={loading}
                    onClick={() => void pickOrganisation(org.org_id)}
                    className="w-full flex items-center gap-3 rounded-xl border border-border px-4 py-3 text-left hover:border-primary/40 hover:bg-secondary/30 transition-colors"
                  >
                    <Building2 className="size-5 text-primary shrink-0" />
                    <div className="min-w-0">
                      <div className="font-semibold text-heading truncate">{org.name}</div>
                      <div className="text-xs text-muted-text capitalize">{org.role}</div>
                    </div>
                  </button>
                ))}
                <button type="button" className="text-sm text-muted-text hover:text-heading" onClick={() => { setOrgChoices(null); setOauthSelectToken(null); }}>
                  Back
                </button>
              </div>
            ) : (
              <>
                <SocialAuthButtons onOAuth={oauth} oauthLoading={oauthLoading} />

                <div className="my-6 flex items-center gap-3">
                  <div className="flex-1 h-px bg-border" />
                  <span className="text-[12px] uppercase tracking-wider text-muted-text">or</span>
                  <div className="flex-1 h-px bg-border" />
                </div>

                <form onSubmit={handleEmail} className="space-y-3">
                  {!inviteActive && mode === "signup" ? (
                    <label className="block">
                      <span className="text-[12.5px] font-semibold uppercase tracking-wider text-muted-text">Company</span>
                      <input
                        type="text"
                        required
                        value={orgName}
                        onChange={(e) => setOrgName(e.target.value)}
                        placeholder="Acme Ltd"
                        className="mt-1.5 w-full px-3 py-3 rounded-xl border border-border bg-secondary/30 text-[15px] focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
                      />
                    </label>
                  ) : null}
                  <label className="block">
                    <span className="text-[12.5px] font-semibold uppercase tracking-wider text-muted-text">Email</span>
                    <div className="mt-1.5 relative">
                      <Mail size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-text" />
                      <input
                        type="email"
                        required
                        value={email}
                        readOnly={inviteActive}
                        onChange={(e) => setEmail(e.target.value)}
                        placeholder="you@company.com"
                        className="w-full pl-10 pr-3 py-3 rounded-xl border border-border bg-secondary/30 text-[15px] focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary read-only:opacity-80"
                      />
                    </div>
                  </label>
                  <label className="block">
                    <span className="text-[12.5px] font-semibold uppercase tracking-wider text-muted-text">
                      {inviteActive ? "Create password" : "Password"}
                    </span>
                    <div className="mt-1.5 relative">
                      <Lock size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-text" />
                      <input
                        type="password"
                        required
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        placeholder="••••••••"
                        minLength={6}
                        className="w-full pl-10 pr-3 py-3 rounded-xl border border-border bg-secondary/30 text-[15px] focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
                      />
                    </div>
                  </label>
                  <button type="submit" disabled={loading} className="btn-primary w-full !py-3 mt-2">
                    {loading ? (
                      <Loader2 size={16} className="animate-spin" />
                    ) : (
                      <>
                        {inviteActive ? "Join organisation" : mode === "signin" ? "Sign in" : "Create account"}{" "}
                        <ArrowRight size={15} />
                      </>
                    )}
                  </button>
                </form>

                {!inviteActive ? (
                  <p className="mt-5 text-center text-[13.5px] text-muted-text">
                    {mode === "signin" ? "Don't have an account?" : "Already have an account?"}{" "}
                    <button onClick={() => setMode(mode === "signin" ? "signup" : "signin")} className="text-primary font-semibold hover:underline">
                      {mode === "signin" ? "Sign up" : "Sign in"}
                    </button>
                  </p>
                ) : (
                  <p className="mt-5 text-center text-[13px] text-muted-text">
                    Already have a password? Enter it above and click Join — we will add you to this company.
                  </p>
                )}
              </>
            )}
          </div>

          <p className="mt-5 text-center text-[12px] text-muted-text">
            By continuing, you agree to our <Link to="/terms" className="underline hover:text-heading">Terms</Link> and <Link to="/privacy" className="underline hover:text-heading">Privacy Policy</Link>.
          </p>
        </div>
      </main>
      <SiteFooter />
    </div>
  );
}
