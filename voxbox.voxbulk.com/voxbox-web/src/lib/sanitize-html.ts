import DOMPurify from "dompurify";

/** Strip scripts/handlers from inbound HTML mail before dangerouslySetInnerHTML. */
export function sanitizeMailHtml(html: string): string {
  const raw = String(html || "");
  if (!raw) return "";
  try {
    return DOMPurify.sanitize(raw, { USE_PROFILES: { html: true } });
  } catch {
    return "";
  }
}
