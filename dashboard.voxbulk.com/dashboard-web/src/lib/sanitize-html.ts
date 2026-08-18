import DOMPurify from "dompurify";

export function sanitizeCmsHtml(html: string): string {
  const raw = String(html || "");
  if (!raw) return "";
  return DOMPurify.sanitize(raw, { USE_PROFILES: { html: true } });
}
