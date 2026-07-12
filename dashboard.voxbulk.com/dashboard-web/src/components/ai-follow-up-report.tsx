import { PhoneCall } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export type AiFollowUpReport = {
  id?: string;
  status?: string | null;
  scheduled_at?: string | null;
  call_id?: string | null;
  poor_topics?: string[];
  positive_topics?: string[];
  outcome?: Record<string, unknown> | null;
  updated_at?: string | null;
};

export function aiFollowUpStatusLabel(status?: string | null): string {
  const raw = String(status || "").trim().toLowerCase();
  if (!raw) return "";
  return raw.replace(/_/g, " ");
}

export function aiFollowUpStatusTone(status?: string | null): "default" | "secondary" | "destructive" | "outline" {
  const raw = String(status || "").trim().toLowerCase();
  if (raw === "completed") return "default";
  if (raw === "scheduled" || raw === "dispatched") return "secondary";
  if (["failed", "opted_out", "blocked_low_balance", "cancelled"].includes(raw)) return "destructive";
  return "outline";
}

export function AiFollowUpStatusIcon({
  status,
  className,
}: {
  status?: string | null;
  className?: string;
}) {
  if (!status) return null;
  const tone = aiFollowUpStatusTone(status);
  return (
    <span
      className={cn(
        "inline-flex size-7 items-center justify-center rounded-full border",
        tone === "default" && "border-primary/30 bg-primary/10 text-primary",
        tone === "secondary" && "border-border bg-muted text-muted-foreground",
        tone === "destructive" && "border-destructive/30 bg-destructive/10 text-destructive",
        tone === "outline" && "border-border bg-background text-muted-foreground",
        className,
      )}
      title={`AI follow-up: ${aiFollowUpStatusLabel(status)}`}
      aria-label={`AI follow-up ${aiFollowUpStatusLabel(status)}`}
    >
      <PhoneCall className="size-3.5" />
    </span>
  );
}

export function AiFollowUpAssistancePanel({ report }: { report?: AiFollowUpReport | null }) {
  if (!report?.status) return null;
  const poor = report.poor_topics || [];
  const outcome = report.outcome || {};
  const skip = typeof outcome.skip_reason === "string" ? outcome.skip_reason : null;
  const defer = typeof outcome.defer_reason === "string" ? outcome.defer_reason : null;
  const excerpt =
    (typeof outcome.transcript_excerpt === "string" && outcome.transcript_excerpt) ||
    (typeof outcome.opt_out_text === "string" && outcome.opt_out_text) ||
    null;
  const hangup = typeof outcome.hangup_cause === "string" ? outcome.hangup_cause : null;

  return (
    <Card className="border-primary/30 bg-primary/5">
      <CardContent className="space-y-2 p-4">
        <div className="flex items-center justify-between gap-2">
          <p className="flex items-center gap-2 font-medium">
            <PhoneCall className="size-4 text-primary" />
            AI call assistance
          </p>
          <Badge variant={aiFollowUpStatusTone(report.status)}>{aiFollowUpStatusLabel(report.status)}</Badge>
        </div>
        {poor.length > 0 ? (
          <p className="text-xs text-muted-foreground">
            Focus topics: {poor.slice(0, 4).join(", ")}
          </p>
        ) : (
          <p className="text-xs text-muted-foreground">
            Scheduled after a low rating with no written reason.
          </p>
        )}
        {report.scheduled_at ? (
          <p className="text-xs text-muted-foreground">
            Scheduled:{" "}
            {new Date(report.scheduled_at).toLocaleString("en-GB", { dateStyle: "short", timeStyle: "short" })}
          </p>
        ) : null}
        {skip ? <p className="text-xs text-muted-foreground">Skipped: {skip}</p> : null}
        {defer ? <p className="text-xs text-muted-foreground">Deferred: {defer}</p> : null}
        {hangup ? <p className="text-xs text-muted-foreground">Hangup: {hangup}</p> : null}
        {excerpt ? (
          <blockquote className="rounded-lg border border-border bg-background/70 px-3 py-2 text-xs text-muted-foreground">
            {excerpt}
          </blockquote>
        ) : null}
      </CardContent>
    </Card>
  );
}
