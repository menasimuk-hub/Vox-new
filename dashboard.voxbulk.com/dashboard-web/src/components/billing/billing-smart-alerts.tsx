import { Link } from "@tanstack/react-router";
import { AlertTriangle } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import type { AllowanceAlert } from "@/lib/billing/allowances";
import { cn } from "@/lib/utils";

export type BillingAlertItem = {
  id: string;
  tone: "warning" | "destructive" | "info";
  title: string;
  detail?: string;
  actionLabel?: string;
  onAction?: () => void;
  href?: string;
  hrefSearch?: Record<string, string>;
};

type Props = {
  alerts: BillingAlertItem[];
  className?: string;
};

export function BillingSmartAlerts({ alerts, className }: Props) {
  if (alerts.length === 0) return null;

  const toneCls = (tone: BillingAlertItem["tone"]) => {
    if (tone === "destructive") return "border-destructive/40 bg-destructive/10 text-destructive";
    if (tone === "info") return "border-blue-500/40 bg-blue-500/10 text-blue-600 dark:text-blue-400";
    return "border-amber-500/40 bg-amber-500/10 text-amber-600 dark:text-amber-400";
  };

  return (
    <div className={cn("space-y-2", className)}>
      {alerts.map((a) => (
        <div
          key={a.id}
          className={cn("flex flex-wrap items-start justify-between gap-3 rounded-lg border px-4 py-3 text-sm", toneCls(a.tone))}
        >
          <div className="flex items-start gap-2">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" />
            <div>
              <p className="font-medium text-foreground">{a.title}</p>
              {a.detail ? <p className="text-muted-foreground">{a.detail}</p> : null}
            </div>
          </div>
          {a.actionLabel && a.onAction ? (
            <Button size="sm" variant="outline" onClick={a.onAction}>
              {a.actionLabel}
            </Button>
          ) : null}
          {a.actionLabel && a.href ? (
            <Button asChild size="sm" variant="outline">
              <Link to={a.href} search={a.hrefSearch}>
                {a.actionLabel}
              </Link>
            </Button>
          ) : null}
        </div>
      ))}
    </div>
  );
}

export function allowanceAlertsToItems(
  alerts: AllowanceAlert[],
  opts?: { onViewUsage?: () => void },
): BillingAlertItem[] {
  return alerts.map((a, i) => ({
    id: `allowance-${a.key || i}`,
    tone: a.level === "critical" ? "destructive" : "warning",
    title: a.message,
    detail: "Check your allowance before launching more campaigns.",
    actionLabel: "View usage",
    href: opts?.onViewUsage ? undefined : "/account/usage",
    onAction: opts?.onViewUsage,
  }));
}
