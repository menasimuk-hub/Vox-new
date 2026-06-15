import {
  clearSessionStorage,
  normalizeHandoffBaseUrl,
  readAccessTokenFromStorage,
  readOrgIdFromStorage,
  readUserIdFromStorage,
  writeSessionToStorage,
} from "@/lib/session-storage";

function productionApiOrigin() {
  if (typeof window === "undefined") return "";
  const h = window.location.hostname;
  if (h === "voxbulk.com" || h === "www.voxbulk.com") return "https://api.voxbulk.com";
  return "";
}

const LOCAL_LOOPBACK_FASTAPI_ORIGINS = new Set(["http://127.0.0.1:8000", "http://localhost:8000"]);

function isViteDevelopment() {
  return import.meta.env.DEV === true || import.meta.env.MODE === "development";
}

function isLocalDevHost() {
  if (typeof window === "undefined") return false;
  const h = window.location.hostname.toLowerCase();
  if (h === "localhost" || h === "127.0.0.1" || h === "::1") return true;
  // Vite "Network" URLs (e.g. http://192.168.0.21:5173) must use the dev proxy too.
  if (/^192\.168\.\d{1,3}\.\d{1,3}$/.test(h)) return true;
  if (/^10\.\d{1,3}\.\d{1,3}\.\d{1,3}$/.test(h)) return true;
  if (/^172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3}$/.test(h)) return true;
  return false;
}

export function getApiBaseUrl() {
  const raw = (import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_RETOVER_API_BASE_URL || "")
    .trim()
    .replace(/\/+$/, "");

  // Local Vite dev: same-origin /auth → proxy → FastAPI (:5173 → :8000).
  if (isViteDevelopment() && isLocalDevHost() && (!raw || LOCAL_LOOPBACK_FASTAPI_ORIGINS.has(raw) || raw.includes("api.voxbulk.com"))) {
    return "";
  }

  if (raw) {
    try {
      const configured = new URL(raw.includes("://") ? raw : `https://${raw}`);
      if (typeof window !== "undefined" && configured.hostname === window.location.hostname) {
        const fallback = productionApiOrigin();
        if (fallback) return fallback;
      }
      if (configured.hostname === "voxbulk.com" || configured.hostname === "www.voxbulk.com") {
        return "https://api.voxbulk.com";
      }
      return configured.origin;
    } catch {
      /* fall through */
    }
  }

  if (typeof window !== "undefined") {
    const h = window.location.hostname;
    if (h === "localhost" || h === "127.0.0.1" || h === "::1") return "";
    const prod = productionApiOrigin();
    if (prod) return prod;
  }
  return "";
}

/** Marketing site (voxbulk.com): same-origin `/frontpage` → Vite preview proxy → FastAPI on :8000. */
export function getFrontpageApiBaseUrl() {
  if (typeof window !== "undefined") {
    const h = window.location.hostname.toLowerCase();
    if (h === "voxbulk.com" || h === "www.voxbulk.com") return "";
  }
  if (isViteDevelopment() && isLocalDevHost()) return "";
  return getApiBaseUrl();
}

function frontpageApiUrl(path: string) {
  const base = getFrontpageApiBaseUrl().replace(/\/+$/, "");
  const p = path.startsWith("/") ? path : `/${path}`;
  return `${base}${p}`;
}

export async function frontpageApiFetch<T = unknown>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = buildAuthHeaders(options.headers);
  if (options.body && !headers.has("Content-Type") && typeof options.body === "string") {
    headers.set("Content-Type", "application/json");
  }
  const res = await requestFetch(frontpageApiUrl(path), { ...options, headers });
  const text = await res.text();
  const data = text ? safeJson(text) : null;
  if (!res.ok) {
    const detail =
      (data && typeof data === "object" && "detail" in data && String((data as { detail: unknown }).detail)) ||
      (typeof data === "string" ? data : "") ||
      res.statusText ||
      "Request failed";
    throw new ApiError(detail, { status: res.status, data });
  }
  return (data ?? {}) as T;
}

function decodeJwtPayload(token: string) {
  try {
    const part = String(token || "").split(".")[1];
    if (!part) return null;
    const normalized = part.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=");
    return JSON.parse(atob(padded)) as { sub?: string; org_id?: string; exp?: number };
  } catch {
    return null;
  }
}

function isTokenUsable(token: string) {
  const payload = decodeJwtPayload(token);
  if (!payload?.sub) return false;
  if (payload.exp && payload.exp * 1000 <= Date.now()) return false;
  return true;
}

export function getAccessToken() {
  const token = readAccessTokenFromStorage();
  return isTokenUsable(token) ? token : "";
}

export function setSession(token: string, orgId?: string, userId?: string) {
  writeSessionToStorage(token, orgId, userId);
}

export function clearSession() {
  clearSessionStorage();
}

export function buildAuthHeaders(extraHeaders?: HeadersInit) {
  const headers = new Headers(extraHeaders || {});
  const token = getAccessToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const orgId = readOrgIdFromStorage();
  if (orgId && !headers.has("X-Voxbulk-Org-Id")) headers.set("X-Voxbulk-Org-Id", orgId);
  return headers;
}

export class ApiError extends Error {
  status?: number;
  data?: unknown;
  isNetworkError?: boolean;

  constructor(message: string, opts?: { status?: number; data?: unknown; isNetworkError?: boolean }) {
    super(message);
    this.name = "ApiError";
    this.status = opts?.status;
    this.data = opts?.data;
    this.isNetworkError = opts?.isNetworkError;
  }
}

function safeJson(text: string) {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

function apiUrl(path: string) {
  const base = getApiBaseUrl().replace(/\/+$/, "");
  const p = path.startsWith("/") ? path : `/${path}`;
  return `${base}${p}`;
}

async function requestFetch(url: string, options: RequestInit = {}) {
  try {
    return await fetch(url, options);
  } catch (cause) {
    const message = cause instanceof Error ? cause.message : "Failed to fetch";
    throw new ApiError(message, { isNetworkError: true });
  }
}

export async function apiFetch<T = unknown>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = buildAuthHeaders(options.headers);
  if (options.body && !headers.has("Content-Type") && typeof options.body === "string") {
    headers.set("Content-Type", "application/json");
  }
  const res = await requestFetch(apiUrl(path), { ...options, headers });
  const text = await res.text();
  const data = text ? safeJson(text) : null;
  if (!res.ok) {
    const detail =
      (data && typeof data === "object" && "detail" in data && String((data as { detail: unknown }).detail)) ||
      (typeof data === "string" ? data : "") ||
      res.statusText ||
      "Request failed";
    throw new ApiError(detail, { status: res.status, data });
  }
  return (data ?? {}) as T;
}

export async function apiUpload<T = unknown>(path: string, form: FormData, method = "POST"): Promise<T> {
  const headers = buildAuthHeaders();
  const res = await requestFetch(apiUrl(path), { method, body: form, headers });
  const text = await res.text();
  const data = text ? safeJson(text) : null;
  if (!res.ok) {
    const detail =
      (data && typeof data === "object" && "detail" in data && String((data as { detail: unknown }).detail)) ||
      res.statusText ||
      "Upload failed";
    throw new ApiError(detail, { status: res.status, data });
  }
  return (data ?? {}) as T;
}

export function oauthStartUrl(provider: string) {
  return apiUrl(`/auth/oauth/${encodeURIComponent(provider)}/start`);
}

export function getDashboardUrl() {
  const raw = String(import.meta.env.VITE_POST_LOGIN_DASHBOARD_URL || "").trim().replace(/\/+$/, "");
  return normalizeHandoffBaseUrl(raw, "https://dashboard.voxbulk.com");
}

export function getAdminUrl() {
  const raw = String(import.meta.env.VITE_POST_LOGIN_ADMIN_URL || "").trim().replace(/\/+$/, "");
  return normalizeHandoffBaseUrl(raw, "https://admin.voxbulk.com");
}

function buildAuthHandoffUrl(base: string) {
  if (typeof window === "undefined") return base;
  const token = getAccessToken();
  if (!token) return base;
  const params = new URLSearchParams();
  params.set("access_token", token);
  const orgId = readOrgIdFromStorage();
  const userId = readUserIdFromStorage();
  if (orgId) params.set("org_id", orgId);
  if (userId) params.set("user_id", userId);
  return `${base}#${params.toString()}`;
}

/** Pass JWT to dashboard on another origin (5173 → 5175) via URL hash. */
export function getDashboardHandoffUrl() {
  return buildAuthHandoffUrl(getDashboardUrl());
}

/** Pass JWT to admin console on another origin (5173 → 5174) via URL hash. */
export function getAdminHandoffUrl() {
  return buildAuthHandoffUrl(getAdminUrl());
}

export type PostLoginUser = {
  admin_access?: boolean;
  is_superuser?: boolean;
  onboarding_complete?: boolean;
  dashboard_setup_complete?: boolean;
};

export function hasPlatformAdminAccess(user: PostLoginUser | null | undefined) {
  return Boolean(user?.admin_access || user?.is_superuser);
}

export function needsOnboardingFor(user: PostLoginUser | null | undefined) {
  if (!user) return false;
  if (hasPlatformAdminAccess(user)) return false;
  return !user.onboarding_complete && !user.dashboard_setup_complete;
}

/** Route platform admins to admin; everyone else to the customer dashboard. */
export function getPostLoginHandoffUrl(user: PostLoginUser | null | undefined) {
  if (hasPlatformAdminAccess(user)) return getAdminHandoffUrl();
  return getDashboardHandoffUrl();
}

export function resolvePostLoginDestination(user: PostLoginUser | null | undefined) {
  if (!user) return null;
  if (needsOnboardingFor(user)) return { kind: "onboarding" as const };
  return { kind: "handoff" as const, url: getPostLoginHandoffUrl(user) };
}
