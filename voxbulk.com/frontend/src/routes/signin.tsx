import { createFileRoute, useNavigate, Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { z } from "zod";
import { SiteHeader, SiteFooter } from "@/components/SiteShell";
import { toast } from "sonner";
import { Mail, Lock, ArrowRight, Loader2 } from "lucide-react";
import { BrandLogo } from "@/components/BrandLogo";
import { SocialAuthButtons } from "@/components/SocialAuthButtons";
import { useAuth } from "@/lib/auth";
import { resolvePostLoginDestination } from "@/lib/api";
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

function SignInPage() {
  const navigate = useNavigate();
  const auth = useAuth();
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [orgName, setOrgName] = useState("");
  const [loading, setLoading] = useState(false);
  const [oauthLoading, setOauthLoading] = useState<string | null>(null);

  useEffect(() => {
    if (auth.consumeOAuthHash()) return;
    const params = new URLSearchParams(window.location.search);
    const oauthError = params.get("oauth_error");
    if (oauthError) toast.error(oauthError);
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
    <div className="bg-background text-body antialiased min-h-screen flex flex-col">
      <SiteHeader />
      <main className="flex-1 pt-[110px] md:pt-[130px] pb-24">
        <div className="max-w-[460px] mx-auto px-5 md:px-10">
          <div className="text-center">
            <BrandLogo surface="light" className="h-13 mx-auto w-auto" />
            <h1 className="mt-5 text-[30px] md:text-[36px] font-bold tracking-[-0.03em] text-heading leading-[1.1]">
              {mode === "signin" ? "Welcome back" : "Create your account"}
            </h1>
            <p className="mt-2 text-body text-[15px]">
              {mode === "signin" ? "Sign in to access your dashboard." : "Get started with VOXBULK in 30 seconds."}
            </p>
          </div>

          <div className="mt-8 bg-white border border-border rounded-2xl p-7 shadow-elegant">
            <SocialAuthButtons onOAuth={oauth} oauthLoading={oauthLoading} />

            <div className="my-6 flex items-center gap-3">
              <div className="flex-1 h-px bg-border" />
              <span className="text-[12px] uppercase tracking-wider text-muted-text">or</span>
              <div className="flex-1 h-px bg-border" />
            </div>

            <form onSubmit={handleEmail} className="space-y-3">
              {mode === "signup" ? (
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
                    type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@company.com"
                    className="w-full pl-10 pr-3 py-3 rounded-xl border border-border bg-secondary/30 text-[15px] focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
                  />
                </div>
              </label>
              <label className="block">
                <span className="text-[12.5px] font-semibold uppercase tracking-wider text-muted-text">Password</span>
                <div className="mt-1.5 relative">
                  <Lock size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-text" />
                  <input
                    type="password" required value={password} onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••" minLength={6}
                    className="w-full pl-10 pr-3 py-3 rounded-xl border border-border bg-secondary/30 text-[15px] focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
                  />
                </div>
              </label>
              <button type="submit" disabled={loading} className="btn-primary w-full !py-3 mt-2">
                {loading ? <Loader2 size={16} className="animate-spin" /> : <>{mode === "signin" ? "Sign in" : "Create account"} <ArrowRight size={15} /></>}
              </button>
            </form>

            <p className="mt-5 text-center text-[13.5px] text-muted-text">
              {mode === "signin" ? "Don't have an account?" : "Already have an account?"}{" "}
              <button onClick={() => setMode(mode === "signin" ? "signup" : "signin")} className="text-primary font-semibold hover:underline">
                {mode === "signin" ? "Sign up" : "Sign in"}
              </button>
            </p>
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
