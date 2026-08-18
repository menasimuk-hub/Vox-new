import { STORAGE_KEYS, writeSessionToStorage } from "@/lib/session-storage";

function parseAuthHandoffFromHash(): { accessToken: string; orgId?: string; userId?: string } | null {
  if (typeof window === "undefined") return null;
  const raw = window.location.hash;
  if (!raw || raw.length <= 1) return null;
  try {
    const params = new URLSearchParams(raw.startsWith("#") ? raw.slice(1) : raw);
    const accessToken = params.get("access_token");
    if (!accessToken) return null;
    return {
      accessToken,
      orgId: params.get("org_id") || undefined,
      userId: params.get("user_id") || undefined,
    };
  } catch {
    return null;
  }
}

export function hasAuthHandoffInHash(): boolean {
  return parseAuthHandoffFromHash() != null;
}

/** Store a legacy hash JWT (in-flight OAuth links). New OAuth uses an HttpOnly cookie instead. */
export function storeAuthHandoffFromHash(): string | null {
  const parsed = parseAuthHandoffFromHash();
  if (!parsed) return null;
  localStorage.setItem(STORAGE_KEYS.accessToken, parsed.accessToken);
  localStorage.setItem("access_token", parsed.accessToken);
  writeSessionToStorage(parsed.accessToken, parsed.orgId, parsed.userId);
  // writeSessionToStorage clears JWTs; restore the one-time hash token for Bearer fallback.
  localStorage.setItem(STORAGE_KEYS.accessToken, parsed.accessToken);
  localStorage.setItem("access_token", parsed.accessToken);
  return parsed.accessToken;
}

export function stripAuthHashFromUrl(): void {
  if (typeof window === "undefined") return;
  if (!window.location.hash) return;
  const target = `${window.location.pathname}${window.location.search}` || "/";
  window.history.replaceState(window.history.state, "", target);
}

/** Public app (:5173) and dashboard (:5175) do not share localStorage — consume one-time hash tokens. */
export function consumeAuthHandoffFromHash(): boolean {
  const accessToken = storeAuthHandoffFromHash();
  if (!accessToken) return false;
  stripAuthHashFromUrl();
  return true;
}

/** @deprecated Use consumeAuthHandoffFromHash */
export const consumeRetoverAuthHandoffFromHash = consumeAuthHandoffFromHash;
