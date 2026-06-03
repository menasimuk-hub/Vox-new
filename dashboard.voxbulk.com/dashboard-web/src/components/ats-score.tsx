import { Loader2 } from "lucide-react";
import { ATS_ANALYZING_LABEL, isAtsAnalyzingStatus } from "@/lib/interview-campaign";

export function AtsScore({
  score,
  status,
  label,
  minThreshold,
  excluded,
}: {
  score: number | null | undefined;
  status?: string | null;
  label?: string | null;
  minThreshold?: number;
  excluded?: boolean;
}) {
  const st = String(status || "").toLowerCase();
  if (isAtsAnalyzingStatus(st)) {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
        <Loader2 className="size-3 animate-spin" />
        {ATS_ANALYZING_LABEL}
      </span>
    );
  }
  if (st === "failed") {
    return <span className="text-xs text-destructive">Failed</span>;
  }
  if (score == null) {
    return <span className="text-xs text-muted-foreground">{label && label !== "—" ? label : "—"}</span>;
  }

  const belowCutoff =
    minThreshold != null && !Number.isNaN(minThreshold) && score != null
      ? score < minThreshold
      : Boolean(excluded);

  const tone = belowCutoff
    ? "bg-destructive/15 text-destructive border-destructive ring-1 ring-destructive/40"
    : score >= 75
      ? "bg-success/15 text-success border-success/30"
      : score >= 50
        ? "bg-warning/15 text-warning border-warning/30"
        : "bg-destructive/15 text-destructive border-destructive/30";

  return (
    <div className="space-y-0.5">
      <div
        className={`inline-flex h-6 min-w-[44px] items-center justify-center rounded-md border px-1.5 text-xs font-semibold tabular-nums ${tone}`}
        title={belowCutoff && minThreshold != null ? `Below ${minThreshold}% cutoff` : undefined}
      >
        {score}%
      </div>
      {belowCutoff ? (
        <p className="text-[10px] font-medium text-destructive">Below cutoff</p>
      ) : null}
    </div>
  );
}
