import { cn } from "@/lib/utils";

export type BadgeTone =
  | "live"
  | "scheduled"
  | "finished"
  | "archived"
  | "quoted"
  | "awaiting-payment"
  | "payment-failed"
  | "calling"
  | "rebooked"
  | "no-answer"
  | "completed"
  | "paused"
  | "approved-script"
  | "draft-script"
  | "wa-sent";

const map: Record<BadgeTone, { cls: string; label: string; dot?: "pulse" | "static" }> = {
  live: { cls: "bg-success text-success-foreground", label: "Live", dot: "pulse" },
  scheduled: { cls: "bg-info text-info-foreground", label: "Scheduled" },
  finished: { cls: "bg-muted text-muted-foreground border border-border", label: "Finished" },
  archived: { cls: "bg-secondary text-secondary-foreground", label: "Archived" },
  quoted: { cls: "bg-accent text-accent-foreground", label: "Quoted" },
  "awaiting-payment": { cls: "bg-warning text-warning-foreground", label: "Awaiting payment" },
  "payment-failed": { cls: "bg-destructive text-destructive-foreground", label: "Payment failed" },
  calling: { cls: "bg-primary text-primary-foreground", label: "Calling", dot: "pulse" },
  rebooked: { cls: "bg-success text-success-foreground", label: "Rebooked" },
  "no-answer": { cls: "bg-muted text-muted-foreground border border-border", label: "No answer" },
  completed: { cls: "bg-success/15 text-success border border-success/30", label: "Completed" },
  paused: { cls: "bg-warning/20 text-warning-foreground border border-warning/40", label: "Paused" },
  "approved-script": { cls: "bg-success/15 text-success border border-success/30", label: "Approved script" },
  "draft-script": { cls: "bg-muted text-muted-foreground border border-border", label: "Draft script" },
  "wa-sent": { cls: "bg-info/15 text-info border border-info/30", label: "WhatsApp sent" },
};

export function StatusBadge({ tone, className, label }: { tone: BadgeTone | string; className?: string; label?: string }) {
  const cfg = map[tone as BadgeTone] ?? map.finished;
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11px] font-medium whitespace-nowrap", cfg.cls, className)}>
      {cfg.dot === "pulse" && <span className="size-1.5 rounded-full bg-current opacity-90 animate-pulse" />}
      {label ?? cfg.label}
    </span>
  );
}
