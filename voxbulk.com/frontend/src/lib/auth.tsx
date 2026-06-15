import * as React from "react";
import { apiFetch, clearSession, getAccessToken, oauthStartUrl, setSession, needsOnboardingFor, type InvitePreview, type OrgLoginOption } from "@/lib/api";
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

export type LoginResult =
  | { kind: "authenticated"; user: AuthUser }
  | { kind: "org_selection"; organisations: OrgLoginOption[] };

type AuthCtx = {
  user: AuthUser | null;
  loading: boolean;
  refresh: () => Promise<AuthUser | null>;
  login: (email: string, password: string, orgId?: string) => Promise<LoginResult>;
  register: (email: string, password: string, organisationName: string) => Promise<AuthUser>;
  acceptInvite: (token: string, password: string) => Promise<AuthUser>;
  previewInvite: (token: string) => Promise<InvitePreview>;
  logout: () => void;
  startOAuth: (provider: string, inviteToken?: string) => void;
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

  const login = React.useCallback(async (email: string, password: string, orgId?: string): Promise<LoginResult> => {
    const { getApiBaseUrl } = await import("@/lib/api");
    const body = new URLSearchParams({ username: email.trim(), password });
    if (orgId) body.set("org_id", orgId);
    const base = getApiBaseUrl().replace(/\/+$/, "");
    const tokenUrl = import.meta.env.DEV ? "/auth/token" : base ? `${base}/auth/token` : "/auth/token";
    const tokenRes = await fetch(tokenUrl, {
      method: "POST",
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
      return { kind: "org_selection", organisations: data.organisations };
    }
    setSession(String(data.access_token), String(data.org_id), String(data.user_id));
    const me = await refresh();
    if (!me) throw new Error("Sign in failed");
    return { kind: "authenticated", user: me };
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

  const previewInvite = React.useCallback(async (token: string): Promise<InvitePreview> => {
    return apiFetch<InvitePreview>(`/auth/invite-preview?token=${encodeURIComponent(token)}`);
  }, []);

  const acceptInvite = React.useCallback(async (token: string, password: string): Promise<AuthUser> => {
    const data = await apiFetch<{ access_token: string; org_id: string; user_id: string }>("/auth/accept-invite", {
      method: "POST",
      body: JSON.stringify({ token, password }),
    });
    setSession(data.access_token, data.org_id, data.user_id);
    const me = await refresh();
    if (!me) throw new Error("Could not complete invitation");
    return me;
  }, [refresh]);

  const logout = React.useCallback(() => {
    clearSession();
    setUser(null);
  }, []);

  const startOAuth = React.useCallback((provider: string, inviteToken?: string) => {
    window.location.href = oauthStartUrl(provider, { inviteToken });
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
      acceptInvite,
      previewInvite,
      logout,
      startOAuth,
      consumeOAuthHash,
      needsOnboarding,
    }),
    [user, loading, refresh, login, register, acceptInvite, previewInvite, logout, startOAuth, consumeOAuthHash, needsOnboarding],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const ctx = React.useContext(Ctx);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
