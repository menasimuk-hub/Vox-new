import * as React from "react";
import { FileText, PhoneCall, X } from "lucide-react";

import { InterviewRecordingPlayer } from "@/components/interview-recording-player";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { useAiFollowUpCallDetail } from "@/lib/queries";
import { cn } from "@/lib/utils";

export type AiFollowUpReport = {
  id?: string;
  status?: string | null;
  scheduled_at?: string | null;
  call_id?: string | null;
  call_reason?: string | null;
  transcript_preview?: string | null;
  has_recording?: boolean;
  recording_play_url?: string | null;
  duration_label?: string | null;
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

function AiFollowUpTranscriptDialog({
  open,
  onOpenChange,
  jobId,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  jobId: string | null;
}) {
  const detailQ = useAiFollowUpCallDetail(jobId, open);
  const lines = (detailQ.data?.transcript_lines || []) as Array<{ speaker: string; text: string }>;
  const transcript = String(detailQ.data?.transcript || "");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] max-w-2xl overflow-hidden p-0">
        <DialogHeader className="border-b border-border bg-[#0f172a] px-5 py-4 text-left">
          <div className="flex items-start justify-between gap-3">
            <div>
              <DialogTitle className="flex items-center gap-2 text-base text-white">
                <FileText className="size-4 text-sky-400" />
                AI follow-up transcript
              </DialogTitle>
              <p className="mt-1 text-xs text-slate-400">What the customer said on the recovery call</p>
            </div>
            <Button
              size="icon"
              variant="ghost"
              className="text-slate-300 hover:bg-white/10 hover:text-white"
              onClick={() => onOpenChange(false)}
            >
              <X className="size-4" />
            </Button>
          </div>
        </DialogHeader>
        <div className="max-h-[60vh] overflow-y-auto bg-[#111827] px-5 py-4">
          {detailQ.isLoading ? (
            <div className="space-y-3">
              <Skeleton className="h-12 w-full bg-slate-800" />
              <Skeleton className="h-12 w-5/6 bg-slate-800" />
              <Skeleton className="h-12 w-4/6 bg-slate-800" />
            </div>
          ) : lines.length > 0 ? (
            <div className="space-y-3">
              {lines.map((line, i) => {
                const isAgent = ["agent", "assistant"].includes(String(line.speaker || "").toLowerCase());
                return (
                  <div
                    key={`${line.speaker}-${i}`}
                    className={`rounded-lg border px-3 py-2 text-sm leading-relaxed ${
                      isAgent
                        ? "border-sky-500/20 bg-sky-500/10 text-sky-50"
                        : "border-emerald-500/20 bg-emerald-500/10 text-emerald-50"
                    }`}
                  >
                    <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider opacity-70">{line.speaker}</p>
                    <p>{line.text}</p>
                  </div>
                );
              })}
            </div>
          ) : (
            <pre className="whitespace-pre-wrap text-sm leading-relaxed text-slate-200">
              {transcript || "Transcript not available yet."}
            </pre>
          )}
        </div>
        <div className="border-t border-border bg-muted/40 px-5 py-3 text-[11px] text-muted-foreground">
          Transcript and recording sync after the AI follow-up call completes.
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function AiFollowUpAssistancePanel({ report }: { report?: AiFollowUpReport | null }) {
  const [transcriptOpen, setTranscriptOpen] = React.useState(false);
  if (!report?.status) return null;

  const jobId = String(report.id || "").trim() || null;
  const terminal = ["completed", "opted_out", "voicemail", "busy", "no_answer", "failed"].includes(
    String(report.status || "").toLowerCase(),
  );
  const detailQ = useAiFollowUpCallDetail(jobId, Boolean(jobId && terminal));

  const callReason =
    (typeof detailQ.data?.call_reason === "string" && detailQ.data.call_reason.trim()) ||
    (typeof report.call_reason === "string" && report.call_reason.trim()) ||
    null;
  const recordingPath =
    (typeof detailQ.data?.recording_play_url === "string" && detailQ.data.recording_play_url) ||
    (typeof report.recording_play_url === "string" && report.recording_play_url) ||
    null;
  const durationLabel =
    (typeof detailQ.data?.duration_label === "string" && detailQ.data.duration_label) ||
    (typeof report.duration_label === "string" && report.duration_label) ||
    null;
  const hangup =
    typeof detailQ.data?.hangup_cause === "string"
      ? detailQ.data.hangup_cause
      : typeof report.outcome?.hangup_cause === "string"
        ? report.outcome.hangup_cause
        : null;
  const promoEmail = report.promo_email;

  return (
    <>
      <Card className="border-primary/30 bg-primary/5">
        <CardContent className="space-y-4 p-4">
          <div className="flex items-center justify-between gap-2">
            <p className="flex items-center gap-2 font-medium">
              <PhoneCall className="size-4 text-primary" />
              AI call assistance
            </p>
            <Badge variant={aiFollowUpStatusTone(report.status)}>{aiFollowUpStatusLabel(report.status)}</Badge>
          </div>

          <div className="space-y-2">
            <p className="text-xs font-medium text-foreground">Problem reported on call</p>
            {detailQ.isLoading && !callReason ? (
              <Skeleton className="h-14 w-full" />
            ) : (
              <blockquote className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 px-3 py-3 text-sm leading-relaxed text-foreground">
                {callReason || "Loading what the customer said on the AI call…"}
              </blockquote>
            )}
          </div>

          <div className="space-y-2">
            <p className="text-xs font-medium text-foreground">Recording</p>
            <InterviewRecordingPlayer
              playPath={recordingPath}
              durationLabel={durationLabel ? `${durationLabel} · AI follow-up` : "AI follow-up recording"}
            />
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="w-full"
              disabled={!jobId}
              onClick={() => setTranscriptOpen(true)}
            >
              <FileText className="mr-2 size-4" />
              Open transcript
            </Button>
          </div>

          <div className="space-y-1 text-xs text-muted-foreground">
            {report.scheduled_at ? (
              <p>
                Called:{" "}
                {new Date(report.scheduled_at).toLocaleString("en-GB", { dateStyle: "short", timeStyle: "short" })}
              </p>
            ) : null}
            {durationLabel ? <p>Duration: {durationLabel}</p> : null}
            {hangup ? <p>Hangup: {String(hangup).replace(/_/g, " ")}</p> : null}
          </div>

          {report.promo_enabled ? (
            <div className="space-y-1 text-xs text-muted-foreground">
              <p className="font-medium text-foreground">Promo code</p>
              <p>Code: {report.promo_code || "—"}</p>
              {promoEmail?.ok ? (
                <p>Emailed to {promoEmail.to || "customer"}</p>
              ) : promoEmail?.reason ? (
                <p>Email not sent: {String(promoEmail.reason).replace(/_/g, " ")}</p>
              ) : report.status === "completed" ? (
                <p>Email pending — configure survey.codes@voxbulk.com in Admin</p>
              ) : null}
            </div>
          ) : null}
        </CardContent>
      </Card>

      <AiFollowUpTranscriptDialog open={transcriptOpen} onOpenChange={setTranscriptOpen} jobId={jobId} />
    </>
  );
}
