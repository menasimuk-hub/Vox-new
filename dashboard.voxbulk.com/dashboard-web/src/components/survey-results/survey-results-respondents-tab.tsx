import * as React from "react";
import { TriangleAlert as AlertTriangle, Search, X } from "lucide-react";

import { SurveyResultsRespondentRow, type SurveyResultRespondent } from "@/components/survey-results/survey-results-respondent-row";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

type FilterKey = "all" | "flagged" | "unhappy" | "neutral" | "happy";

const FILTERS: Array<{ key: FilterKey; label: string }> = [
  { key: "all", label: "All" },
  { key: "flagged", label: "Flagged" },
  { key: "unhappy", label: "Unhappy" },
  { key: "neutral", label: "Neutral" },
  { key: "happy", label: "Happy" },
];

function matchesFilter(row: SurveyResultRespondent, filter: FilterKey) {
  const sentiment = String(row.sentiment_label || "").toLowerCase();
  if (filter === "flagged") return Boolean(row.needs_follow_up || row.is_unhappy);
  if (filter === "unhappy") return Boolean(row.is_unhappy) || sentiment.includes("negative") || sentiment.includes("unhappy");
  if (filter === "happy") return sentiment.includes("positive") || sentiment.includes("happy") || sentiment.includes("excellent");
  if (filter === "neutral") return !row.is_unhappy && (sentiment.includes("neutral") || sentiment.includes("mixed") || !sentiment);
  return true;
}

export function SurveyResultsRespondentsTab({
  respondents,
  unhappyCount,
  onOpenRespondent,
}: {
  respondents: SurveyResultRespondent[];
  unhappyCount: number;
  onOpenRespondent: (row: SurveyResultRespondent) => void;
}) {
  const [search, setSearch] = React.useState("");
  const [filter, setFilter] = React.useState<FilterKey>("all");
  const [bannerDismissed, setBannerDismissed] = React.useState(false);

  const completed = React.useMemo(
    () =>
      respondents.filter(
        (r) => String(r.status_label || "").toLowerCase() === "completed" || Boolean(r.completed_at),
      ),
    [respondents],
  );

  const filtered = React.useMemo(() => {
    const q = search.trim().toLowerCase();
    return completed.filter((row) => {
      if (!matchesFilter(row, filter)) return false;
      if (!q) return true;
      const name = String(row.name || "").toLowerCase();
      const phone = String(row.phone || "").toLowerCase();
      return name.includes(q) || phone.includes(q);
    });
  }, [completed, filter, search]);

  return (
    <div className="space-y-4">
      {unhappyCount > 0 && !bannerDismissed ? (
        <Card className="border-destructive/40 bg-destructive/5">
          <CardContent className="flex flex-wrap items-center justify-between gap-3 p-4">
            <div className="flex items-start gap-2 text-sm">
              <AlertTriangle className="mt-0.5 size-4 shrink-0 text-destructive" />
              <p>
                <strong>{unhappyCount}</strong> customer{unhappyCount === 1 ? "" : "s"} flagged as unhappy and may need a follow-up call.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Button size="sm" variant="destructive" onClick={() => setFilter("unhappy")}>
                View {unhappyCount}
              </Button>
              <Button size="icon" variant="ghost" className="size-8" onClick={() => setBannerDismissed(true)} aria-label="Dismiss">
                <X className="size-4" />
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold">All respondents</h3>
          <p className="text-sm text-muted-foreground">{filtered.length} of {completed.length} completed</p>
        </div>
        <div className="relative w-full max-w-xs">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            className="pl-8"
            placeholder="Search name or phone"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        {FILTERS.map((item) => (
          <Button
            key={item.key}
            size="sm"
            variant={filter === item.key ? "default" : "outline"}
            className={cn("rounded-full")}
            onClick={() => setFilter(item.key)}
          >
            {item.label}
          </Button>
        ))}
      </div>

      <Card>
        <CardContent className="p-0">
          {filtered.length === 0 ? (
            <p className="p-6 text-sm text-muted-foreground">No respondents match this filter.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px] text-sm">
                <thead>
                  <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-muted-foreground">
                    <th className="px-4 py-3">Customer</th>
                    <th className="px-4 py-3">Mobile</th>
                    <th className="px-4 py-3">Sentiment</th>
                    <th className="px-4 py-3">Quick view</th>
                    <th className="px-4 py-3 text-right">Details</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((row) => (
                    <SurveyResultsRespondentRow
                      key={row.id || `${row.phone}-${row.name}`}
                      respondent={row}
                      onOpen={() => onOpenRespondent(row)}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
