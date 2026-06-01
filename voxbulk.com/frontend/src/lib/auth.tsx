import * as React from "react";
import { apiFetch, clearSession, getAccessToken, oauthStartUrl, setSession, needsOnboardingFor } from "@/lib/api";
import { consumeLogoutQueryParam } from "@/lib/session-storage";

export type AuthUser = {
  user_id: string;
  org_id: string;
  email: string;
  onboarding_complete: boolean;
  dashboard_setup_complete: boolean;
  onboarding_state?: string;
  admin_access?: boolean;
  is_superuser?: boolean;
};

type AuthCtx = {
  user: AuthUser | null;
  loading: boolean;
  refresh: () => Promise<AuthUser | null>;
  login: (email: string, password: string) => Promise<AuthUser>;
  register: (email: string, password: string, organisationName: string) => Promise<AuthUser>;
  logout: () => void;
  startOAuth: (provider: string) => void;
  consumeOAuthHash: () => boolean;
  needsOnboarding: (user?: AuthUser | null) => boolean;
};

const Ctx = React.createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = React.useState<AuthUser | null>(null);
  const [loading, setLoading] = React.useState(true);

  const refresh = React.useCallback(async (): Promise<AuthUser | null> => {
    const token = getAccessToken();
    if (!token) {
      setUser(null);
      setLoading(false);
      return null;
    }
    try {
      const me = await apiFetch<AuthUser>("/auth/me");
      setUser(me);
      return me;
    } catch {
      clearSession();
      setUser(null);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    if (consumeLogoutQueryParam()) {
      clearSession();
      setUser(null);
      setLoading(false);
      return;
    }
    void refresh();
  }, [refresh]);

  const login = React.useCallback(async (email: string, password: string): Promise<AuthUser> => {
    const { getApiBaseUrl } = await import("@/lib/api");
    const body = new URLSearchParams({ username: email.trim(), password });
    const tokenRes = await fetch(`${getApiBaseUrl()}/auth/token`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });
    const data = (await tokenRes.json().catch(() => ({}))) as { access_token?: string; org_id?: string; user_id?: string; detail?: string };
    if (!tokenRes.ok) throw new Error(String(data?.detail || "Sign in failed"));
    setSession(String(data.access_token), String(data.org_id), String(data.user_id));
    const me = await refresh();
    if (!me) throw new Error("Sign in failed");
    return me;
  }, [refresh]);

  const register = React.useCallback(async (email: string, password: string, organisationName: string): Promise<AuthUser> => {
    const data = await apiFetch<{ access_token: string; org_id: string; user_id: string }>("/auth/register", {
      method: "POST",
      body: JSON.stringify({
        email: email.trim(),
        password,
        organisation_name: organisationName.trim() || "My organisation",
      }),
    });
    setSession(data.access_token, data.org_id, data.user_id);
    const me = await refresh();
    if (!me) throw new Error("Registration failed");
    return me;
  }, [refresh]);

  const logout = React.useCallback(() => {
    clearSession();
    setUser(null);
  }, []);

  const startOAuth = React.useCallback((provider: string) => {
    window.location.href = oauthStartUrl(provider);
  }, []);

  const consumeOAuthHash = React.useCallback(() => {
    const hash = window.location.hash.replace(/^#/, "");
    if (!hash) return false;
    const params = new URLSearchParams(hash);
    const token = params.get("access_token");
    if (!token) return false;
    setSession(token, params.get("org_id") || undefined, params.get("user_id") || undefined);
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
    void refresh();
    return true;
  }, [refresh]);

  const needsOnboarding = React.useCallback((subject?: AuthUser | null) => {
    return needsOnboardingFor(subject ?? user);
  }, [user]);

  const value: AuthCtx = React.useMemo(
    () => ({
      user,
      loading,
      refresh,
      login,
      register,
      logout,
      startOAuth,
      consumeOAuthHash,
      needsOnboarding,
    }),
    [user, loading, refresh, login, register, logout, startOAuth, consumeOAuthHash, needsOnboarding],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const ctx = React.useContext(Ctx);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
