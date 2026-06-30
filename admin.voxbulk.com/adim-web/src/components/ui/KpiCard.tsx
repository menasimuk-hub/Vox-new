import * as React from "react";
import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

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

export interface KpiCardProps {
  icon?: LucideIcon;
  label: React.ReactNode;
  value: number | string | null | undefined;
  hint?: React.ReactNode;
  tone?: keyof typeof KPI_TONES;
  index?: number;
  className?: string;
}

/**
 * KpiCard — compact, colored stat card with a count-up + staggered fade/slide-in
 * entrance. Shared across the admin dashboards.
 */
export function KpiCard({ icon: Icon, label, value, hint, tone = "primary", index = 0, className }: KpiCardProps) {
  const numeric =
    value !== null && value !== undefined && value !== "—" && Number.isFinite(Number(value));
  const counted = useCountUp(numeric ? Number(value) : 0);
  const display = numeric ? counted.toLocaleString() : value ?? "—";
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
      {hint ? <div className="mt-0.5 text-[10.5px] text-muted-foreground/80">{hint}</div> : null}
    </div>
  );
}

export default KpiCard;
