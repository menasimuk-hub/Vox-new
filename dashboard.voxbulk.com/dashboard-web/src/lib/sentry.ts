import * as Sentry from "@sentry/react";

const SENSITIVE = /authorization|cookie|access_token|refresh_token|jwt|phone|secret|token/i;

function scrub(value: unknown): unknown {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    const out: Record<string, unknown> = {};
    for (const [key, nested] of Object.entries(value as Record<string, unknown>)) {
      out[key] = SENSITIVE.test(key) ? "[Filtered]" : scrub(nested);
    }
    return out;
  }
  return value;
}

function sentryDsn(): string {
  return String(import.meta.env.VITE_SENTRY_DSN || "").trim();
}

export function initDashboardSentry(): void {
  const dsn = sentryDsn();
  if (!dsn || typeof window === "undefined") {
    return;
  }
  Sentry.init({
    dsn,
    sendDefaultPii: false,
    tracesSampleRate: 0.05,
    beforeSend(event) {
      if (event.request?.headers) {
        event.request.headers = scrub(event.request.headers) as typeof event.request.headers;
      }
      if (event.extra) {
        event.extra = scrub(event.extra) as typeof event.extra;
      }
      return event;
    },
  });
}

export function captureDashboardException(error: unknown): void {
  if (!sentryDsn()) {
    return;
  }
  Sentry.captureException(error);
}
