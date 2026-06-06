import { cn } from "@/lib/utils";

export function Summary({
  label,
  value,
  className,
  valueClassName,
}: {
  label: string;
  value: string;
  className?: string;
  valueClassName?: string;
}) {
  return (
    <div className={cn("rounded-xl border border-border bg-muted/30 p-3", className)}>
      <p className="text-[11px] uppercase tracking-wider text-muted-foreground">{label}</p>
      <p className={cn("text-sm font-semibold", valueClassName)}>{value}</p>
    </div>
  );
}
