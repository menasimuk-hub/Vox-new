import * as React from "react";
import { FileText, X } from "lucide-react";

import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useInterviewRecipientDetail } from "@/lib/queries";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  orderId: string | null;
  recipientId: string | null;
  candidateName?: string;
};

export function InterviewTranscriptDialog({ open, onOpenChange, orderId, recipientId, candidateName }: Props) {
  const detailQ = useInterviewRecipientDetail(orderId, recipientId, open);
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
                Call transcript
              </DialogTitle>
              <p className="mt-1 text-xs text-slate-400">
                {candidateName || "Candidate"} · Telnyx voice · AI screening
              </p>
            </div>
            <Button size="icon" variant="ghost" className="text-slate-300 hover:bg-white/10 hover:text-white" onClick={() => onOpenChange(false)}>
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
                const isAgent = line.speaker.toLowerCase() === "agent" || line.speaker.toLowerCase() === "assistant";
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
            <pre className="whitespace-pre-wrap text-sm leading-relaxed text-slate-200">{transcript || "Transcript not available yet."}</pre>
          )}
        </div>
        <div className="border-t border-border bg-muted/40 px-5 py-3 text-[11px] text-muted-foreground">
          Transcript synced from Telnyx after the call completes. Recording playback uses the same call session.
        </div>
      </DialogContent>
    </Dialog>
  );
}
