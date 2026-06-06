import { ApiError } from "@/lib/api";

/** Parse WA survey generate API failures into user-visible lines (all validation errors when present). */
export function parseWaSurveyGenerateErrors(e: unknown): string[] {
  if (e instanceof ApiError) {
    const root = e.data && typeof e.data === "object" ? (e.data as Record<string, unknown>) : null;
    const detail = root?.detail;
    if (detail && typeof detail === "object" && detail !== null) {
      const errors = (detail as { errors?: unknown }).errors;
      if (Array.isArray(errors) && errors.length) {
        return errors.map((line) => String(line)).filter(Boolean);
      }
      const message = (detail as { message?: unknown }).message;
      if (message) return [String(message)];
    }
    if (typeof detail === "string" && detail.trim()) return [detail];
    if (detail && typeof detail === "object" && detail !== null) {
      const nested = (detail as { detail?: unknown }).detail;
      if (typeof nested === "string" && nested.trim()) return [nested];
    }
    if (e.message && !/^\d{3}\s/.test(e.message)) return [e.message];
  }
  if (e instanceof Error && e.message) return [e.message];
  return ["Could not generate survey. Check your template selections and try again."];
}

export function formatWaSurveyGenerateError(e: unknown): string {
  return parseWaSurveyGenerateErrors(e)[0] || "Could not generate survey";
}
