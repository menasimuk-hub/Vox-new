import * as React from "react";

import { cn } from "@/lib/utils";

type Props = {
  usedDisplay: string;
  includedDisplay: string;
  remainingDisplay?: string;
  percent?: number;
  className?: string;
};

export function PackageValuePoolBar({
  usedDisplay,
  includedDisplay,
  remainingDisplay,
  percent = 0,
  className,
}: Props) {
  const pct = Math.min(100, Math.max(0, Math.round(percent)));
  return (
    <div className={cn("space-y-2 rounded-xl border border-border/80 bg-background/60 p-3", className)}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">Package value pool</p>
        {remainingDisplay ? (
          <p className="text-xs tabular-nums text-muted-foreground">{remainingDisplay} remaining</p>
        ) : null}
      </div>
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 text-sm">
        <span className="font-semibold tabular-nums text-primary">{usedDisplay}</span>
        <span className="text-muted-foreground">used of</span>
        <span className="font-semibold tabular-nums">{includedDisplay}</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-primary/15">
        <div className="h-full rounded-full bg-primary/80 transition-all" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
