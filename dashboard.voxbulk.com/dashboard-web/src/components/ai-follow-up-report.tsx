import { PhoneCall } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export type AiFollowUpPoorAnswer = {
  question?: string;
  answer?: string;
};

export type AiFollowUpReport = {
  id?: string;
  status?: string | null;
  scheduled_at?: string | null;
  call_id?: string | null;
  poor_topics?: string[];
  poor_answers?: AiFollowUpPoorAnswer[];
  why_unhappy?: string | null;
  positive_topics?: string[];
  promo_enabled?: boolean;
  promo_code?: string | null;
  promo_email?: { ok?: boolean; reason?: string; to?: string } | null;
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

function formatDuration(seconds: unknown): string | null {
  const n = typeof seconds === "number" ? seconds : Number(seconds);
  if (!Number.isFinite(n) || n < 0) return null;
  if (n < 60) return `${Math.round(n)}s`;
  const m = Math.floor(n / 60);
  const s = Math.round(n % 60);
  return `${m}m ${s}s`;
}

export function AiFollowUpAssistancePanel({ report }: { report?: AiFollowUpReport | null }) {
  if (!report?.status) return null;
  const poor = report.poor_topics || [];
  const poorAnswers = (report.poor_answers || []).filter((a) => a?.question || a?.answer);
  const outcome = report.outcome || {};
  const skip = typeof outcome.skip_reason === "string" ? outcome.skip_reason : null;
  const defer = typeof outcome.defer_reason === "string" ? outcome.defer_reason : null;
  const excerpt =
    (typeof outcome.transcript_excerpt === "string" && outcome.transcript_excerpt) ||
    (typeof outcome.opt_out_text === "string" && outcome.opt_out_text) ||
    null;
  const hangup = typeof outcome.hangup_cause === "string" ? outcome.hangup_cause : null;
  const duration = formatDuration(outcome.duration_seconds);
  const why =
    (typeof report.why_unhappy === "string" && report.why_unhappy.trim()) ||
    (typeof outcome.why_unhappy === "string" && outcome.why_unhappy.trim()) ||
    null;
  const promoEmail = report.promo_email || (typeof outcome.promo_email === "object" && outcome.promo_email ? (outcome.promo_email as AiFollowUpReport["promo_email"]) : null);

  return (
    <Card className="border-primary/30 bg-primary/5">
      <CardContent className="space-y-3 p-4">
        <div className="flex items-center justify-between gap-2">
          <p className="flex items-center gap-2 font-medium">
            <PhoneCall className="size-4 text-primary" />
            AI call assistance
          </p>
          <Badge variant={aiFollowUpStatusTone(report.status)}>{aiFollowUpStatusLabel(report.status)}</Badge>
        </div>

        <div className="space-y-1.5">
          <p className="text-xs font-medium text-foreground">Why the customer was unhappy</p>
          {poorAnswers.length > 0 ? (
            <ul className="space-y-1 text-xs text-muted-foreground">
              {poorAnswers.slice(0, 6).map((row, idx) => (
                <li key={`${row.question}-${idx}`}>
                  <span className="text-foreground/80">{row.question || "Topic"}:</span>{" "}
                  {row.answer || "—"}
                </li>
              ))}
            </ul>
          ) : why ? (
            <p className="text-xs text-muted-foreground">{why}</p>
          ) : poor.length > 0 ? (
            <p className="text-xs text-muted-foreground">Low scores on: {poor.slice(0, 4).join(", ")}</p>
          ) : (
            <p className="text-xs text-muted-foreground">
              Scheduled after a low rating with no written reason in the survey.
            </p>
          )}
        </div>

        <div className="space-y-1 text-xs text-muted-foreground">
          <p className="font-medium text-foreground">Call report</p>
          {report.scheduled_at ? (
            <p>
              Scheduled:{" "}
              {new Date(report.scheduled_at).toLocaleString("en-GB", { dateStyle: "short", timeStyle: "short" })}
            </p>
          ) : null}
          {duration ? <p>Duration: {duration}</p> : null}
          {hangup ? <p>Hangup: {hangup.replace(/_/g, " ")}</p> : null}
          {skip ? <p>Skipped: {skip}</p> : null}
          {defer ? <p>Deferred: {defer}</p> : null}
          {report.call_id ? <p className="break-all">Call ID: {report.call_id}</p> : null}
        </div>

        {excerpt ? (
          <div className="space-y-1">
            <p className="text-xs font-medium text-foreground">Call notes / transcript</p>
            <blockquote className="rounded-lg border border-border bg-background/70 px-3 py-2 text-xs text-muted-foreground whitespace-pre-wrap">
              {excerpt}
            </blockquote>
          </div>
        ) : null}

        {report.promo_enabled ? (
          <div className="space-y-1 text-xs text-muted-foreground">
            <p className="font-medium text-foreground">Promo code</p>
            <p>Code: {report.promo_code || "—"}</p>
            {promoEmail?.ok ? (
              <p>Emailed to {promoEmail.to || "customer"}</p>
            ) : promoEmail?.reason ? (
              <p>Email not sent: {String(promoEmail.reason).replace(/_/g, " ")}</p>
            ) : report.status === "completed" ? (
              <p>Email pending or not configured</p>
            ) : (
              <p>Sent by email after a completed call (when mailbox is enabled)</p>
            )}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
