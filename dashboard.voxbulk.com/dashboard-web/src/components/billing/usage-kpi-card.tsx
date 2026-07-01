import { Clock, MessageCircle, Phone, Wallet, type LucideIcon } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

export type UsageKpiAccent = "primary" | "success" | "warning" | "violet";

const ACCENT_STYLES: Record<UsageKpiAccent, string> = {
  primary: "border-primary/30 bg-primary/5 ring-1 ring-primary/15",
  success: "border-success/30 bg-success/5 ring-1 ring-success/15",
  warning: "border-amber-500/30 bg-amber-500/5 ring-1 ring-amber-500/15",
  violet: "border-violet-500/30 bg-violet-500/5 ring-1 ring-violet-500/15",
};

const ACCENT_ICON: Record<UsageKpiAccent, LucideIcon> = {
  primary: Phone,
  success: MessageCircle,
  warning: Clock,
  violet: Wallet,
};

const ACCENT_ICON_COLOR: Record<UsageKpiAccent, string> = {
  primary: "text-primary",
  success: "text-success",
  warning: "text-amber-600 dark:text-amber-400",
  violet: "text-violet-600 dark:text-violet-400",
};

type Props = {
  label: string;
  value: string;
  sub?: string;
  accent: UsageKpiAccent;
  className?: string;
};

export function UsageKpiCard({ label, value, sub, accent, className }: Props) {
  const Icon = ACCENT_ICON[accent];
  return (
    <div
      className={cn(
        "flex min-w-0 flex-col gap-2 rounded-xl border p-4",
        ACCENT_STYLES[accent],
        className,
      )}
    >
      <div className="flex items-center gap-2">
        <span className={cn("grid size-8 shrink-0 place-items-center rounded-lg bg-background/80", ACCENT_ICON_COLOR[accent])}>
          <Icon className="size-4" aria-hidden />
        </span>
        <p className="truncate text-xs font-medium text-muted-foreground">{label}</p>
      </div>
      <p className="text-xl font-semibold tabular-nums">{value}</p>
      {sub ? <p className="text-[11px] leading-snug text-muted-foreground">{sub}</p> : null}
    </div>
  );
}

export function UsageKpiCardSkeleton() {
  return <div className="h-[7.5rem] animate-pulse rounded-xl border border-border bg-muted/40" />;
}
