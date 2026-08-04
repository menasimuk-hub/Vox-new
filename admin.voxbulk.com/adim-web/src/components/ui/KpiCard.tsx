import * as React from "react";
import { ArrowUpRight, TrendingUp, type LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";
import { Sparkline } from "@/components/ui/Sparkline";

export const KPI_TONES: Record<string, string> = {
  primary: "bg-primary/10 text-primary",
  info: "bg-info-soft text-info",
  success: "bg-success-soft text-success",
  warning: "bg-warning-soft text-warning",
  danger: "bg-destructive/10 text-destructive",
};

export function useCountUp(target: number | string | null | undefined, duration = 900) {
  const [value, setValue] = React.useState(0);
  React.useEffect(() => {
    const to = Number(target) || 0;
    let raf = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const p = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - p, 3);
      setValue(Math.round(to * eased));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, duration]);
  return value;
}

export type KpiValueTone = "default" | "ok" | "warn" | "bad";

export interface KpiCardProps {
  icon?: LucideIcon;
  label: React.ReactNode;
  value: number | string | null | undefined;
  hint?: React.ReactNode;
  sub?: React.ReactNode;
  tone?: keyof typeof KPI_TONES;
  valueTone?: KpiValueTone;
  trend?: React.ReactNode;
  spark?: number[];
  index?: number;
  className?: string;
  /** Compact dashboard tile (reference /dashboard KPI button). */
  variant?: "default" | "dashboard";
  onClick?: () => void;
}

/**
 * KpiCard — compact stat card. Use `variant="dashboard"` for the Phase-1
 * Home Dashboard 8-col KPI grid (matches telynx-settings-hub AdminDashboard).
 */
export function KpiCard({
  icon: Icon,
  label,
  value,
  hint,
  sub,
  tone = "primary",
  valueTone = "default",
  trend,
  spark,
  index = 0,
  className,
  variant = "default",
  onClick,
}: KpiCardProps) {
  const numeric =
    value !== null && value !== undefined && value !== "—" && Number.isFinite(Number(value));
  const counted = useCountUp(numeric ? Number(value) : 0);
  const display = numeric ? counted.toLocaleString() : value ?? "—";
  const caption = sub ?? hint;

  if (variant === "dashboard") {
    const Comp: "button" | "div" = onClick ? "button" : "div";
    return (
      <Comp
        type={onClick ? "button" : undefined}
        onClick={onClick}
        style={{ animationDelay: `${index * 40}ms` }}
        className={cn(
          "group animate-in fade-in-50 slide-in-from-bottom-2 rounded-xl border border-border bg-card p-2.5 text-left shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-ring/40 hover:shadow-md",
          onClick && "cursor-pointer",
          className,
        )}
      >
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
            {Icon ? <Icon className="h-3.5 w-3.5" /> : null}
            <span className="truncate">{label}</span>
          </span>
          {onClick ? (
            <ArrowUpRight className="h-3 w-3 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
          ) : null}
        </div>
        <div className="mt-1 flex items-end justify-between gap-1">
          <span
            className={cn(
              "text-xl font-semibold leading-none tabular-nums",
              valueTone === "ok" && "text-success",
              valueTone === "warn" && "text-warning",
              valueTone === "bad" && "text-destructive",
            )}
          >
            {display}
          </span>
          {trend ? (
            <span className="flex items-center gap-0.5 text-[10px] text-muted-foreground">
              <TrendingUp className="h-3 w-3" />
              {trend}
            </span>
          ) : null}
        </div>
        {caption ? (
          <p className="mt-0.5 truncate text-[10px] text-muted-foreground">{caption}</p>
        ) : null}
        {spark?.length ? (
          <div
            className={cn(
              "mt-1 text-primary",
              valueTone === "ok" && "text-success",
              valueTone === "warn" && "text-warning",
            )}
          >
            <Sparkline data={spark} />
          </div>
        ) : null}
      </Comp>
    );
  }

  return (
    <div
      className={cn(
        "ds-scope animate-in fade-in slide-in-from-bottom-2 rounded-lg border border-border bg-card p-3.5 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md",
        className,
      )}
      style={{ animationDuration: "500ms", animationDelay: `${index * 60}ms`, animationFillMode: "both" }}
    >
      {Icon ? (
        <span className={cn("flex size-8 items-center justify-center rounded-md", KPI_TONES[tone])}>
          <Icon size={16} />
        </span>
      ) : null}
      <div className="mt-2.5 text-[22px] font-semibold leading-none tabular-nums">{display}</div>
      <div className="mt-1 text-[11px] text-muted-foreground">{label}</div>
      {caption ? <div className="mt-0.5 text-[10.5px] text-muted-foreground/80">{caption}</div> : null}
    </div>
  );
}

export default KpiCard;
