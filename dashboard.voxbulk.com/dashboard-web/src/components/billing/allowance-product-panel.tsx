import { Link } from "@tanstack/react-router";
import * as React from "react";

import { AnimatedAllowanceKpi } from "@/components/billing/animated-allowance-kpi";
import type { AllowanceRow, ProductPanelMeta } from "@/lib/billing/allowances";
import { formatAllowancePeriod } from "@/lib/billing/allowances";
import { cn } from "@/lib/utils";

type Props = {
  meta: ProductPanelMeta;
  rows: AllowanceRow[];
  periodLabel?: string;
  sharedPool?: boolean;
  compact?: boolean;
  hideFooter?: boolean;
  className?: string;
  /** Core billing card: show used count + bar only (no left / fraction line). */
  usedOnlyKpis?: boolean;
};

export function AllowanceProductPanel({
  meta,
  rows,
  periodLabel,
  sharedPool,
  compact,
  hideFooter,
  className,
  usedOnlyKpis,
}: Props) {
  const period =
    periodLabel ||
    formatAllowancePeriod(rows[0]?.period_start, rows[0]?.period_end) ||
    "";

  if (rows.length === 0) return null;

  return (
    <div className={cn("space-y-3", className)}>
      {sharedPool ? (
        <p className="text-xs text-muted-foreground">Shared allowance pool — AI minutes and WA surveys draw from one plan balance.</p>
      ) : null}
      <div className={cn("grid gap-2", compact ? "grid-cols-1 sm:grid-cols-2" : "sm:grid-cols-2")}>
        {rows.map((row) => (
          <AnimatedAllowanceKpi key={row.key} row={row} compact={compact} usedOnly={usedOnlyKpis} />
        ))}
      </div>
      {!hideFooter && period ? (
        <p className="text-xs text-muted-foreground">
          Period: {period}
          {" · "}
          <Link to={meta.usageLink} className="text-primary underline-offset-4 hover:underline">
            View campaign usage →
          </Link>
        </p>
      ) : null}
    </div>
  );
}
