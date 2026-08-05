import { cn } from "@/lib/utils";

export type LeadScoreLabel = "Hot" | "Warm" | "Cold";

/** SoT score badge tones (vox-connect-suite). */
export function scoreTone(score?: string | null) {
  const s = String(score || "").toLowerCase();
  if (s === "hot") {
    return "bg-rose-500/15 text-rose-600 dark:text-rose-400 border-rose-500/30";
  }
  if (s === "warm") {
    return "bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-500/30";
  }
  if (s === "cold") {
    return "bg-sky-500/15 text-sky-600 dark:text-sky-400 border-sky-500/30";
  }
  return "bg-muted text-muted-foreground border-border";
}

export function titleScore(score?: string | null): LeadScoreLabel | "Unscored" {
  const s = String(score || "").toLowerCase();
  if (s === "hot") return "Hot";
  if (s === "warm") return "Warm";
  if (s === "cold") return "Cold";
  return "Unscored";
}

export function scoreBadgeClass(score?: string | null) {
  return cn("gap-1 text-[10px]", scoreTone(score));
}
