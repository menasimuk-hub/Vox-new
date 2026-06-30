import { Phone, MessageCircle, FileText, QrCode, Globe } from "lucide-react";
import * as React from "react";
import { cn } from "@/lib/utils";
import type { AllowanceRow } from "@/lib/billing/allowances";
import { formatRemaining } from "@/lib/billing/allowances";

const KEY_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  calls: Phone,
  whatsapp: MessageCircle,
  cv_scans: FileText,
  feedback_wa: QrCode,
  feedback_web: Globe,
};

type Props = {
  row: AllowanceRow;
  compact?: boolean;
  className?: string;
};

export function AnimatedAllowanceKpi({ row, compact, className }: Props) {
  const Icon = KEY_ICONS[row.key] || Phone;
  const pct =
    row.included > 0 && !row.unlimited
      ? Math.min(100, Math.round(row.pct_used ?? (row.used / row.included) * 100))
      : 0;
  const lowRemaining =
    !row.unlimited && row.included > 0 && (row.remaining ?? 0) / row.included < 0.2;
  const remainingLabel = formatRemaining(row);

  return (
    <div
      className={cn(
        "flex min-w-0 items-start gap-2 rounded-xl border border-border bg-background/50 p-3",
        compact ? "p-2.5" : "p-3",
        className,
      )}
    >
      <span className="relative grid size-9 shrink-0 place-items-center rounded-lg bg-muted">
        <Icon className="size-4 text-muted-foreground" />
        <span className="absolute -right-0.5 -top-0.5 flex size-2">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-500 opacity-75" />
          <span className="relative inline-flex size-2 rounded-full bg-emerald-500" />
        </span>
      </span>
      <div className="min-w-0 flex-1 space-y-1.5">
        <p className="truncate text-[10px] font-medium uppercase tracking-wider text-muted-foreground">{row.label}</p>
        <div className={cn("flex flex-wrap items-baseline gap-x-3 gap-y-0.5", compact ? "text-sm" : "text-base")}>
          <span className="tabular-nums">
            <span className="font-semibold text-blue-600 dark:text-blue-400">{row.used.toLocaleString()}</span>
            <span className="ml-1 text-xs text-muted-foreground">used</span>
          </span>
          <span className="tabular-nums">
            <span
              className={cn(
                "font-semibold text-emerald-600 dark:text-emerald-400",
                lowRemaining && "motion-safe:animate-pulse",
              )}
            >
              {remainingLabel}
            </span>
            <span className="ml-1 text-xs text-muted-foreground">
              {row.unlimited ? "" : row.included > 0 ? "left" : ""}
            </span>
          </span>
        </div>
        {row.included > 0 && !row.unlimited ? (
          <div className="space-y-1">
            <div className="h-2 overflow-hidden rounded-full bg-emerald-500/20">
              <div
                className="h-full rounded-full bg-blue-500/90 transition-all"
                style={{ width: `${pct}%` }}
              />
            </div>
            <p className="text-[10px] tabular-nums text-muted-foreground">
              {row.used.toLocaleString()} / {row.included.toLocaleString()} {row.unit}
            </p>
          </div>
        ) : (
          <p className="text-[10px] text-muted-foreground">{row.included <= 0 ? "Pay per use · wallet" : "Unlimited"}</p>
        )}
      </div>
    </div>
  );
}
