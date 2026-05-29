/** Public app (:5173) and dashboard (:5175) do not share localStorage — consume one-time hash tokens. */
export function consumeRetoverAuthHandoffFromHash() {
  if (typeof window === "undefined") return;
  const raw = window.location.hash;
  if (!raw || raw.length <= 1) return;
  try {
    const params = new URLSearchParams(raw.startsWith("#") ? raw.slice(1) : raw);
    const accessToken = params.get("access_token");
    if (!accessToken) return;
    localStorage.setItem("retover_access_token", accessToken);
    localStorage.setItem("access_token", accessToken);
    const orgId = params.get("org_id");
    const userId = params.get("user_id");
    if (orgId) localStorage.setItem("retover_org_id", orgId);
    if (userId) localStorage.setItem("retover_user_id", userId);
    const { pathname, search } = window.location;
    window.history.replaceState(null, "", pathname + search);
  } catch {
    /* ignore */
  }
}
