import DOMPurify from "dompurify";

/** Strip scripts/handlers from CMS HTML before dangerouslySetInnerHTML. */
export function sanitizeCmsHtml(html: string): string {
  const raw = String(html || "");
  if (!raw) return "";
  try {
    return DOMPurify.sanitize(raw, { USE_PROFILES: { html: true } });
  } catch {
    return raw.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, "");
  }
}
