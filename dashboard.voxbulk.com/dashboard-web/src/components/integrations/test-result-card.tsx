import * as React from "react";
import { AlertTriangle, CheckCircle2, Loader2, XCircle } from "lucide-react";

import { cn } from "@/lib/utils";

export type CheckEntry = {
  name: string;
  status: "ok" | "fail";
  message: string;
};

export type TestResult = {
  ok: boolean;
  checked_at?: string;
  latency_ms?: number;
  summary?: string;
  checks?: CheckEntry[];
};

type Props = {
  loading: boolean;
  result: TestResult | null;
  className?: string;
};

const CHECK_LABEL: Record<string, string> = {
  token: "Access token",
  scopes: "Required scopes",
  auth_mode: "Auth mode",
  connection: "Connection",
  event_type: "Selected event type",
  event_types: "Event types",
  selected_event_type: "Selected event type",
  calendars: "Calendar access",
  meeting_links: "Meeting links",
  selected_meeting_link: "Selected meeting link",
  schedule_url: "Booking page URL",
  contacts_probe: "Sample contact fetch",
  hubspot_crm: "HubSpot CRM connection",
};

function formatLabel(name: string): string {
  return CHECK_LABEL[name] || name.replace(/_/g, " ");
}

export function TestResultCard({ loading, result, className }: Props) {
  if (loading) {
    return (
      <div className={cn("flex items-center gap-2 rounded-md border bg-muted/30 p-3 text-sm text-muted-foreground", className)}>
        <Loader2 className="size-4 animate-spin" />
        Running deep health check…
      </div>
    );
  }
  if (!result) return null;

  const headerIcon = result.ok ? (
    <CheckCircle2 className="size-4 text-success" />
  ) : (
    <AlertTriangle className="size-4 text-destructive" />
  );

  return (
    <div
      className={cn(
        "rounded-md border p-3 text-sm",
        result.ok ? "border-success/30 bg-success/5" : "border-destructive/30 bg-destructive/5",
        className,
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          {headerIcon}
          <span className="font-medium">{result.ok ? "Connection healthy" : "Connection issue"}</span>
        </div>
        {typeof result.latency_ms === "number" ? (
          <span className="text-xs text-muted-foreground">{result.latency_ms} ms</span>
        ) : null}
      </div>
      {result.summary ? (
        <p className="mt-1 text-xs text-muted-foreground">{result.summary}</p>
      ) : null}
      {Array.isArray(result.checks) && result.checks.length > 0 ? (
        <ul className="mt-2 space-y-1.5">
          {result.checks.map((c, i) => (
            <li key={`${c.name}-${i}`} className="flex items-start gap-2 text-xs">
              {c.status === "ok" ? (
                <CheckCircle2 className="mt-0.5 size-3.5 shrink-0 text-success" />
              ) : (
                <XCircle className="mt-0.5 size-3.5 shrink-0 text-destructive" />
              )}
              <div className="min-w-0">
                <div className="font-medium leading-tight">{formatLabel(c.name)}</div>
                <div className="text-muted-foreground">{c.message}</div>
              </div>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
