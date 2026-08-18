import { createFileRoute, useNavigate } from "@tanstack/react-router";
import * as React from "react";
import { Loader2, Lock, Mail } from "lucide-react";
import { toast } from "sonner";

import { SocialAuthButtons } from "@/components/SocialAuthButtons";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { brandAssets } from "@/lib/brand";
import { apiFetch, getAccessToken, getApiBaseUrl, oauthStartUrl } from "@/lib/api";
import { clearAllSessionStorage, writeSessionToStorage } from "@/lib/session-storage";

export const Route = createFileRoute("/login")({
  component: DashboardLoginPage,
});

type OrgLoginOption = {
  org_id: string;
  name?: string | null;
  org_name?: string | null;
  role?: string | null;
  is_main?: boolean;
};

function DashboardLoginPage() {
  const navigate = useNavigate();
  const [mode, setMode] = React.useState<"signin" | "forgot">("signin");
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [loading, setLoading] = React.useState(false);
  const [oauthLoading, setOauthLoading] = React.useState<string | null>(null);
  const [orgChoices, setOrgChoices] = React.useState<OrgLoginOption[] | null>(null);
  const [selectedOrgId, setSelectedOrgId] = React.useState("");
  const loggedOut = typeof window !== "undefined" && new URLSearchParams(window.location.search).get("logout") === "1";

  React.useEffect(() => {
    if (loggedOut) {
      try {
        clearAllSessionStorage();
      } catch {
        /* ignore */
      }
      return;
    }
    const hash = window.location.hash.replace(/^#/, "");
    const hp = new URLSearchParams(hash);
    if (hp.get("oauth") === "1" && !hp.get("oauth_org_select")) {
      window.history.replaceState(window.history.state, "", "/login");
      window.location.replace("/");
      return;
    }
    void apiFetch("/auth/me", { redirectOn401: false })
      .then(() => navigate({ to: "/" }))
      .catch(() => {
        if (getAccessToken()) void navigate({ to: "/" });
      });
  }, [navigate, loggedOut]);

  React.useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const oauthError = params.get("oauth_error");
    if (oauthError) {
      toast.error(oauthError);
      params.delete("oauth_error");
      params.delete("provider");
      const qs = params.toString();
      window.history.replaceState(window.history.state, "", qs ? `/login?${qs}` : "/login");
    }
  }, []);

  const completeLogin = async (body: URLSearchParams) => {
    const base = getApiBaseUrl().replace(/\/+$/, "");
    const tokenRes = await fetch(`${base}/auth/token`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });
    const data = (await tokenRes.json().catch(() => ({}))) as {
      access_token?: string;
      org_id?: string;
      user_id?: string;
      detail?: string;
      org_selection_required?: boolean;
      organisations?: OrgLoginOption[];
    };
    if (!tokenRes.ok) throw new Error(String(data?.detail || "Sign in failed"));
    if (data.org_selection_required && Array.isArray(data.organisations)) {
      setOrgChoices(data.organisations);
      const main = data.organisations.find((o) => o.is_main);
      setSelectedOrgId(String(main?.org_id || data.organisations[0]?.org_id || ""));
      return;
    }
    if (!data.org_id && !data.access_token) throw new Error("Sign in failed");
    writeSessionToStorage(String(data.access_token || ""), data.org_id, data.user_id);
    window.location.replace("/");
  };

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      if (mode === "forgot") {
        await apiFetch("/auth/forgot-password", {
          method: "POST",
          body: JSON.stringify({ email: email.trim() }),
        });
        toast.success("Check your email for a password reset link!");
        setMode("signin");
        return;
      }
      const body = new URLSearchParams({ username: email.trim(), password });
      if (selectedOrgId) body.set("org_id", selectedOrgId);
      await completeLogin(body);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Sign in failed");
    } finally {
      setLoading(false);
    }
  };

  const onOAuth = (provider: string) => {
    setOauthLoading(provider);
    window.location.href = oauthStartUrl(provider, { returnTo: "dashboard" });
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm space-y-6">
        <div className="text-center">
          <img src={brandAssets.iconBlack} alt="VoxBulk" className="mx-auto size-14" />
          <h1 className="mt-4 text-xl font-semibold tracking-tight">
            {mode === "forgot" ? "Reset password" : "Sign in to VoxBulk"}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {mode === "forgot" ? "We will email you a reset link." : "Customer dashboard"}
          </p>
          {loggedOut && mode === "signin" ? (
            <p className="mt-2 text-sm text-muted-foreground">You have been signed out.</p>
          ) : null}
        </div>

        {mode === "signin" ? <SocialAuthButtons onOAuth={onOAuth} oauthLoading={oauthLoading} compact /> : null}

        {mode === "signin" ? (
          <div className="relative">
            <div className="absolute inset-0 flex items-center">
              <span className="w-full border-t border-border" />
            </div>
            <div className="relative flex justify-center text-xs uppercase">
              <span className="bg-background px-2 text-muted-foreground">or continue with email</span>
            </div>
          </div>
        ) : null}

        <form onSubmit={(e) => void onSubmit(e)} className="space-y-4 rounded-xl border border-border bg-card p-5 shadow-sm">
          <div className="space-y-1.5">
            <Label htmlFor="login-email">Email</Label>
            <div className="relative">
              <Mail className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                id="login-email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="pl-9"
                placeholder="you@company.com"
              />
            </div>
          </div>
          {mode === "signin" ? (
            <div className="space-y-1.5">
              <div className="flex items-center justify-between gap-2">
                <Label htmlFor="login-password">Password</Label>
                <button
                  type="button"
                  className="text-xs text-primary underline-offset-2 hover:underline"
                  onClick={() => setMode("forgot")}
                >
                  Forgot password?
                </button>
              </div>
              <div className="relative">
                <Lock className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  id="login-password"
                  type="password"
                  autoComplete="current-password"
                  required
                  minLength={8}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="pl-9"
                />
              </div>
            </div>
          ) : null}

          {mode === "signin" && orgChoices && orgChoices.length > 1 ? (
            <div className="space-y-1.5">
              <Label htmlFor="login-org">Organisation</Label>
              <select
                id="login-org"
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
                value={selectedOrgId}
                onChange={(e) => setSelectedOrgId(e.target.value)}
              >
                {orgChoices.map((o) => (
                  <option key={o.org_id} value={o.org_id}>
                    {(o.name || o.org_name || o.org_id) + (o.is_main ? " (Main)" : "")}
                  </option>
                ))}
              </select>
            </div>
          ) : null}

          <Button type="submit" className="w-full" disabled={loading}>
            {loading ? <Loader2 className="size-4 animate-spin" /> : mode === "forgot" ? "Send reset link" : "Sign in"}
          </Button>
        </form>

        <p className="text-center text-xs text-muted-foreground">
          {mode === "forgot" ? (
            <>
              Remember your password?{" "}
              <button type="button" className="text-primary underline-offset-2 hover:underline" onClick={() => setMode("signin")}>
                Sign in
              </button>
            </>
          ) : (
            <>
              Need an account?{" "}
              <a href="https://voxbulk.com/signin" className="text-primary underline-offset-2 hover:underline">
                Register on voxbulk.com
              </a>
            </>
          )}
        </p>
      </div>
    </div>
  );
}
