/** Convert a datetime-local input value to UTC ISO string for the API. */
export function toIsoFromLocal(value?: string | null): string | null {
  const text = String(value || "").trim();
  if (!text) return null;
  try {
    return new Date(text).toISOString();
  } catch {
    return null;
  }
}
