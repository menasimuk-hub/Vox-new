import { Loader2 } from "lucide-react";

export function AtsScore({
  score,
  status,
  label,
}: {
  score: number | null | undefined;
  status?: string | null;
  label?: string | null;
}) {
  const st = String(status || "").toLowerCase();
  if (st === "pending" || st === "analyzing") {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
        <Loader2 className="size-3 animate-spin" />
        Analyzing…
      </span>
    );
  }
  if (st === "failed") {
    return <span className="text-xs text-destructive">Failed</span>;
  }
  if (score == null) {
    return <span className="text-xs text-muted-foreground">{label && label !== "—" ? label : "—"}</span>;
  }
  const tone =
    score >= 75
      ? "bg-success/15 text-success border-success/30"
      : score >= 50
        ? "bg-warning/15 text-warning border-warning/30"
        : "bg-destructive/15 text-destructive border-destructive/30";
  return (
    <div className={`inline-flex h-6 min-w-[44px] items-center justify-center rounded-md border px-1.5 text-xs font-semibold tabular-nums ${tone}`}>
      {score}%
    </div>
  );
}
