export const STORAGE_KEYS = {
  accessToken: "voxbulk_access_token",
  orgId: "voxbulk_org_id",
  userId: "voxbulk_user_id",
  adminAccessToken: "voxbulk_admin_access_token",
  adminSelectedOrgId: "voxbulk_admin_selected_org_id",
  signupOrgId: "voxbulk_signup_org_id",
  userEmail: "voxbulk_user_email",
} as const;

const LEGACY_KEYS = {
  accessToken: "retover_access_token",
  orgId: "retover_org_id",
  userId: "retover_user_id",
  adminAccessToken: "retover_admin_access_token",
  adminSelectedOrgId: "retover_admin_selected_org_id",
  signupOrgId: "retover_signup_org_id",
  userEmail: "retover_user_email",
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
}

export function readAccessTokenFromStorage() {
  const candidates = [
    readKey(STORAGE_KEYS.accessToken, LEGACY_KEYS.accessToken),
    localStorage.getItem("access_token") || "",
  ].filter(Boolean);
  return candidates[0] || "";
}

export function readOrgIdFromStorage() {
  return readKey(STORAGE_KEYS.orgId, LEGACY_KEYS.orgId);
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

export function clearAllSessionStorage() {
  for (const key of Object.values(STORAGE_KEYS)) {
    removeKey(key, LEGACY_KEYS[key as keyof typeof LEGACY_KEYS]);
  }
  localStorage.removeItem("access_token");
}
