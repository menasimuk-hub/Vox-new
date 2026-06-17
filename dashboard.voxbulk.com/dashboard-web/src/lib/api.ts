import {
  clearAllSessionStorage,
  LOGOUT_QUERY,
  readAccessTokenFromStorage,
  readOrgIdFromStorage,
} from "@/lib/session-storage";

function productionApiOrigin() {
  if (typeof window === "undefined") return "";
  if (window.location.hostname === "dashboard.voxbulk.com") return "https://api.voxbulk.com";
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
  if (/^192\.168\.\d{1,3}\.\d{1,3}$/.test(h)) return true;
  if (/^10\.\d{1,3}\.\d{1,3}\.\d{1,3}$/.test(h)) return true;
  if (/^172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3}$/.test(h)) return true;
  return false;
}

function forceCrossOriginApi() {
  return ["true", "1"].includes(String(import.meta.env.VITE_FORCE_CROSS_ORIGIN_API ?? "").toLowerCase());
}

export function getApiBaseUrl() {
  const raw = (import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_RETOVER_API_BASE_URL || "")
    .trim()
    .replace(/\/+$/, "");

  // Local Vite dev: same-origin paths → proxy to FastAPI (:5175 → :8000).
  // Ignore baked production API URLs (common when .env copied from VPS).
  if (
    isViteDevelopment() &&
    isLocalDevHost() &&
    !forceCrossOriginApi() &&
    (!raw || LOCAL_LOOPBACK_FASTAPI_ORIGINS.has(raw) || raw.includes("api.voxbulk.com"))
  ) {
    return "";
  }

  if (raw) {
    try {
      const configured = new URL(raw.includes("://") ? raw : `https://${raw}`);
      if (typeof window !== "undefined" && configured.hostname === window.location.hostname) {
        const fallback = productionApiOrigin();
        if (fallback) return fallback;
      }
      return configured.origin;
    } catch {
      /* use defaults below */
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

function syncOrgIdFromToken(token: string) {
  const payload = decodeJwtPayload(token);
  if (!payload?.org_id) return;
  const orgId = String(payload.org_id);
  if (readOrgIdFromStorage() !== orgId) {
    localStorage.setItem("voxbulk_org_id", orgId);
    localStorage.removeItem("retover_org_id");
  }
}

export function getAccessToken() {
  const candidates = [readAccessTokenFromStorage()].filter(Boolean);

  const storedOrgId = readOrgIdFromStorage();
  const usable = candidates
    .filter(isTokenUsable)
    .map((token) => ({ token, payload: decodeJwtPayload(token) }));

  const withMatchingOrg = usable.find(
    ({ payload }) => payload?.org_id && String(payload.org_id) === String(storedOrgId),
  );
  const picked = withMatchingOrg || usable.find(({ payload }) => payload?.org_id) || usable[0];
  if (!picked?.token) return "";

  syncOrgIdFromToken(picked.token);
  return picked.token;
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

async function requestFetch(url: string, options: RequestInit = {}) {
  try {
    return await fetch(url, options);
  } catch (cause) {
    const message = cause instanceof Error ? cause.message : "Failed to fetch";
    throw new ApiError(message, { isNetworkError: true });
  }
}

export function getPublicSignInUrl() {
  const raw = String(import.meta.env.VITE_PUBLIC_SIGNIN_URL || "")
    .trim()
    .replace(/\/+$/, "");
  if (raw) return raw;
  if (typeof window !== "undefined") {
    const h = window.location.hostname;
    if (h === "localhost" || h === "127.0.0.1" || h === "::1") return "/login";
    if (h === "dashboard.voxbulk.com") return "/login";
  }
  return "/login";
}

const DEV_PUBLIC_MARKETING = "http://localhost:5173";
const DEV_NON_MARKETING_PORTS = new Set(["5174", "5175"]);

function marketingOriginAfterLogout() {
  const productionDefault =
    typeof window !== "undefined" && window.location.hostname === "dashboard.voxbulk.com"
      ? "https://voxbulk.com"
      : DEV_PUBLIC_MARKETING;
  const raw = String(import.meta.env.VITE_PUBLIC_APP_URL || productionDefault)
    .trim()
    .replace(/\/+$/, "");
  try {
    const u = new URL(raw.includes("://") ? raw : `http://${raw}`);
    const port = String(u.port || (u.protocol === "https:" ? "443" : "80"));
    const loop = u.hostname === "localhost" || u.hostname === "127.0.0.1" || u.hostname === "::1";
    if (loop && DEV_NON_MARKETING_PORTS.has(port)) return DEV_PUBLIC_MARKETING;
    if (typeof window !== "undefined" && u.host === window.location.host) return DEV_PUBLIC_MARKETING;
    return u.origin;
  } catch {
    return DEV_PUBLIC_MARKETING;
  }
}

function getPublicLogoutLandingUrl() {
  const u = new URL(`${marketingOriginAfterLogout().replace(/\/+$/, "")}/`);
  u.searchParams.set(LOGOUT_QUERY, "1");
  return u.toString();
}

export function logoutDashboard() {
  if (typeof window === "undefined") return;
  try {
    clearAllSessionStorage();
  } catch {
    /* ignore */
  }
  window.location.replace("/login?logout=1");
}

export function redirectToSignIn() {
  window.location.replace(getPublicSignInUrl());
}

export function handleUnauthorizedApiError(err: ApiError, { redirect = true } = {}) {
  if (err.status !== 401 && !/invalid authentication credentials/i.test(String(err.message || ""))) {
    return false;
  }
  if (redirect) setTimeout(() => redirectToSignIn(), 800);
  return true;
}

/** Unauthenticated API calls (public booking pages, etc.). */
export async function publicApiFetch<T = unknown>(path: string, options: RequestInit = {}) {
  const baseUrl = getApiBaseUrl();
  const url = baseUrl ? `${baseUrl}${path}` : path;
  const headers = new Headers(options.headers || {});
  headers.set("Accept", "application/json");
  if (options.body != null && typeof options.body === "string" && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const res = await requestFetch(url, { ...options, headers });
  const text = await res.text();
  const data = text ? safeJson(text) : null;
  if (!res.ok) {
    const detail =
      (data && typeof data === "object" && "detail" in data && String((data as { detail: unknown }).detail)) ||
      text ||
      res.statusText;
    throw new ApiError(String(detail || "Request failed"), { status: res.status, data });
  }
  return data as T;
}

function apiErrorMessage(data: unknown, fallback: string): string {
  const detail =
    data && typeof data === "object" && "detail" in data ? (data as { detail?: string | unknown }).detail : null;
  if (typeof detail === "string" && detail.trim()) {
    return detail.trim();
  }
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object" && "msg" in item) return String((item as { msg?: string }).msg || "");
        return "";
      })
      .filter(Boolean);
    if (parts.length) return parts.join("; ");
  }
  if (data && typeof data === "object" && "message" in data) {
    const msg = String((data as { message?: string }).message || "").trim();
    if (msg) return msg;
  }
  return fallback;
}

export async function apiFetch<T = unknown>(path: string, options: RequestInit & { redirectOn401?: boolean } = {}) {
  const baseUrl = getApiBaseUrl();
  const url = baseUrl ? `${baseUrl}${path}` : path;

  const headers = buildAuthHeaders(options.headers);
  headers.set("Accept", "application/json");
  if (options.body != null && typeof options.body === "string" && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const res = await requestFetch(url, { ...options, headers });
  const text = await res.text();
  const data = text ? safeJson(text) : null;

  if (!res.ok) {
    const message = apiErrorMessage(data, `${res.status} ${res.statusText}`.trim());
    const err = new ApiError(message, { status: res.status, data });
    if (res.status === 401 && options.redirectOn401 !== false) handleUnauthorizedApiError(err);
    throw err;
  }
  return data as T;
}

export async function apiUploadFiles(
  path: string,
  files: File[],
  fieldName = "files",
  extraFields: Record<string, string | number | boolean | null | undefined> = {},
) {
  const baseUrl = getApiBaseUrl();
  const url = baseUrl ? `${baseUrl}${path}` : path;
  const fd = new FormData();
  files.forEach((file) => {
    if (file) fd.append(fieldName, file);
  });
  Object.entries(extraFields).forEach(([key, value]) => {
    if (value != null) fd.append(key, String(value));
  });
  const headers = buildAuthHeaders();
  const res = await requestFetch(url, { method: "POST", headers, body: fd });
  const text = await res.text();
  const data = text ? safeJson(text) : null;
  if (!res.ok) {
    const err = new ApiError(apiErrorMessage(data, `${res.status} ${res.statusText}`.trim()), {
      status: res.status,
      data,
    });
    if (res.status === 401) handleUnauthorizedApiError(err);
    throw err;
  }
  return data;
}

function filenameFromContentDisposition(header: string | null): string | null {
  if (!header) return null;
  const utf8 = /filename\*=UTF-8''([^;]+)/i.exec(header);
  if (utf8?.[1]) {
    try {
      return decodeURIComponent(utf8[1]);
    } catch {
      /* ignore */
    }
  }
  const quoted = /filename="([^"]+)"/i.exec(header);
  if (quoted?.[1]) return quoted[1].trim();
  const plain = /filename=([^;]+)/i.exec(header);
  return plain?.[1]?.trim().replace(/^["']|["']$/g, "") || null;
}

export async function downloadAuthenticatedFile(path: string, filename = "download") {
  const baseUrl = getApiBaseUrl();
  const url = baseUrl ? `${baseUrl}${path}` : path;
  const headers = buildAuthHeaders();
  const res = await requestFetch(url, { headers });
  if (!res.ok) {
    const text = await res.text();
    let message = `${res.status} ${res.statusText}`.trim();
    try {
      const data = JSON.parse(text);
      if (typeof data?.detail === "string") message = data.detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(message, { status: res.status });
  }
  const blob = await res.blob();
  const resolvedName =
    filenameFromContentDisposition(res.headers.get("content-disposition")) || filename;
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = resolvedName;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(objectUrl);
}

export async function openAuthenticatedHtmlInTab(path: string) {
  const baseUrl = getApiBaseUrl();
  const url = baseUrl ? `${baseUrl}${path}` : path;
  const headers = buildAuthHeaders();
  const res = await requestFetch(url, { headers });
  if (!res.ok) {
    const text = await res.text();
    let message = `${res.status} ${res.statusText}`.trim();
    try {
      const data = JSON.parse(text);
      if (typeof data?.detail === "string") message = data.detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(message, { status: res.status });
  }
  const html = await res.text();
  const blob = new Blob([html], { type: "text/html;charset=utf-8" });
  const objectUrl = URL.createObjectURL(blob);
  const tab = window.open(objectUrl, "_blank", "noopener,noreferrer");
  if (!tab) {
    URL.revokeObjectURL(objectUrl);
    throw new ApiError("Pop-up blocked — allow pop-ups to view the report.");
  }
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 120_000);
}

export async function fetchAuthenticatedBlob(path: string) {
  const baseUrl = getApiBaseUrl();
  const url = baseUrl ? `${baseUrl}${path}` : path;
  const headers = buildAuthHeaders();
  const res = await requestFetch(url, { headers });
  if (!res.ok) {
    const text = await res.text();
    let message = `${res.status} ${res.statusText}`.trim();
    try {
      const data = JSON.parse(text);
      if (typeof data?.detail === "string") message = data.detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(message, { status: res.status });
  }
  return res.blob();
}
