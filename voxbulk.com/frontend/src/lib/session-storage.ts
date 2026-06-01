export const STORAGE_KEYS = {
  accessToken: "voxbulk_access_token",
  orgId: "voxbulk_org_id",
  userId: "voxbulk_user_id",
} as const;

const LEGACY_KEYS = {
  accessToken: "retover_access_token",
  orgId: "retover_org_id",
  userId: "retover_user_id",
} as const;

export const LOGOUT_QUERY = "voxbulk_logout";
export const LEGACY_LOGOUT_QUERY = "retover_logout";

function readKey(key: string, legacyKey: string) {
  if (typeof window === "undefined") return "";
  const current = localStorage.getItem(key);
  if (current) return current;
  const legacy = localStorage.getItem(legacyKey);
  if (!legacy) return "";
  localStorage.setItem(key, legacy);
  localStorage.removeItem(legacyKey);
  return legacy;
}

function removeKey(key: string, legacyKey: string) {
  localStorage.removeItem(key);
  localStorage.removeItem(legacyKey);
  localStorage.removeItem("access_token");
}

export function readAccessTokenFromStorage() {
  return readKey(STORAGE_KEYS.accessToken, LEGACY_KEYS.accessToken);
}

export function readOrgIdFromStorage() {
  return readKey(STORAGE_KEYS.orgId, LEGACY_KEYS.orgId);
}

export function readUserIdFromStorage() {
  return readKey(STORAGE_KEYS.userId, LEGACY_KEYS.userId);
}

export function writeSessionToStorage(token: string, orgId?: string, userId?: string) {
  localStorage.setItem(STORAGE_KEYS.accessToken, token);
  localStorage.removeItem(LEGACY_KEYS.accessToken);
  localStorage.setItem("access_token", token);
  if (orgId) {
    localStorage.setItem(STORAGE_KEYS.orgId, orgId);
    localStorage.removeItem(LEGACY_KEYS.orgId);
  }
  if (userId) {
    localStorage.setItem(STORAGE_KEYS.userId, userId);
    localStorage.removeItem(LEGACY_KEYS.userId);
  }
}

export function clearSessionStorage() {
  removeKey(STORAGE_KEYS.accessToken, LEGACY_KEYS.accessToken);
  removeKey(STORAGE_KEYS.orgId, LEGACY_KEYS.orgId);
  removeKey(STORAGE_KEYS.userId, LEGACY_KEYS.userId);
}

/** Clear session when admin/dashboard redirect here after logout (`?voxbulk_logout=1`). */
export function consumeLogoutQueryParam() {
  if (typeof window === "undefined") return false;
  const params = new URLSearchParams(window.location.search);
  const flag = params.get(LOGOUT_QUERY) || params.get(LEGACY_LOGOUT_QUERY);
  if (!flag) return false;
  clearSessionStorage();
  params.delete(LOGOUT_QUERY);
  params.delete(LEGACY_LOGOUT_QUERY);
  const q = params.toString();
  const clean = `${window.location.pathname}${q ? `?${q}` : ""}`;
  window.history.replaceState(window.history.state, "", clean);
  return true;
}

export function normalizeHandoffBaseUrl(raw: string, fallback: string) {
  const base = String(raw || "").trim() || fallback;
  try {
    const u = new URL(base.includes("://") ? base : `http://${base}`);
    const loopback = u.hostname === "localhost" || u.hostname === "127.0.0.1" || u.hostname === "::1";
    if (loopback && u.protocol === "https:") u.protocol = "http:";
    return u.origin;
  } catch {
    return fallback;
  }
}
