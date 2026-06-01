import { writeSessionToStorage } from "@/lib/session-storage";

/** Public app (:5173) and dashboard (:5175) do not share localStorage — consume one-time hash tokens. */
export function consumeAuthHandoffFromHash() {
  if (typeof window === "undefined") return;
  const raw = window.location.hash;
  if (!raw || raw.length <= 1) return;
  try {
    const params = new URLSearchParams(raw.startsWith("#") ? raw.slice(1) : raw);
    const accessToken = params.get("access_token");
    if (!accessToken) return;
    writeSessionToStorage(
      accessToken,
      params.get("org_id") || undefined,
      params.get("user_id") || undefined,
    );
    const { pathname, search } = window.location;
    window.history.replaceState(null, "", pathname + search);
  } catch {
    /* ignore */
  }
}

/** @deprecated Use consumeAuthHandoffFromHash */
export const consumeRetoverAuthHandoffFromHash = consumeAuthHandoffFromHash;
