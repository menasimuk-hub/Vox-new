import { useEffect, useMemo, useState } from "react";

type FeedbackData = {
  locations?: Array<{ id: string; name: string; trend?: string; latest_score?: number }>;
  months?: string[];
  scores_by_location?: Record<string, number[]>;
  sample_responses?: Array<{ id: string; location: string; score: number; category: string; comment: string }>;
  story_lines?: string[];
};

type LiveRow = {
  score?: number | null;
  comment?: string;
  name?: string;
  location?: string;
  at?: string;
};

export function FeedbackDemoPanel({
  data,
  highlightTarget,
  filterLocation,
  liveRows,
}: {
  data: FeedbackData | null;
  highlightTarget?: string | null;
  filterLocation?: string | null;
  liveRows: LiveRow[];
}) {
  const months = data?.months || ["Mar", "Apr", "May", "Jun", "Jul", "Aug"];
  const locations = data?.locations || [];
  const scores = data?.scores_by_location || {};
  const [visibleLocs, setVisibleLocs] = useState<string[]>([]);

  useEffect(() => {
    setVisibleLocs(locations.map((l) => l.id));
  }, [locations]);

  const responses = useMemo(() => {
    const base = data?.sample_responses || [];
    const loc = (filterLocation || "").toLowerCase();
    const filtered = loc ? base.filter((r) => r.location === loc) : base;
    return [
      ...liveRows.map((r, i) => ({
        id: `live-${i}`,
        location: (r.location || "leeds").toLowerCase(),
        score: Number(r.score || 5),
        category: "live",
        comment: r.comment || "Live demo response",
        live: true as const,
        name: r.name,
      })),
      ...filtered.map((r) => ({ ...r, live: false as const, name: undefined as string | undefined })),
    ];
  }, [data, filterLocation, liveRows]);

  const pulse = (id: string) =>
    highlightTarget === id ? "ring-2 ring-primary ring-offset-2 animate-pulse" : "";

  return (
    <div className="space-y-4" data-demo-section="feedback">
      <div className={`rounded-2xl border border-border bg-white p-4 ${pulse("locations-overview")}`} data-demo-target="locations-overview">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-text mb-3">Locations</div>
        <div className="grid grid-cols-3 gap-2">
          {locations.map((loc) => (
            <div
              key={loc.id}
              data-demo-target={`${loc.id}-card`}
              className={`rounded-xl border border-border p-3 ${pulse(`${loc.id}-card`)} ${
                filterLocation === loc.id ? "border-primary bg-primary/5" : ""
              }`}
            >
              <div className="font-semibold text-heading text-[14px]">{loc.name}</div>
              <div className="text-[20px] font-bold text-heading mt-1">{loc.latest_score?.toFixed(1)}</div>
              <div className="text-[11px] text-muted-text capitalize">{loc.trend}</div>
            </div>
          ))}
        </div>
      </div>

      <div className={`rounded-2xl border border-border bg-white p-4 ${pulse("score-chart")}`} data-demo-target="score-chart">
        <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-text">Score over 6 months</div>
          <div className="flex flex-wrap gap-2">
            {locations.map((loc) => {
              const on = visibleLocs.includes(loc.id);
              return (
                <button
                  key={loc.id}
                  type="button"
                  className={`text-[11px] px-2 py-1 rounded-full border ${on ? "border-primary text-heading" : "border-border text-muted-text"}`}
                  onClick={() =>
                    setVisibleLocs((prev) => (prev.includes(loc.id) ? prev.filter((x) => x !== loc.id) : [...prev, loc.id]))
                  }
                >
                  {loc.name}
                </button>
              );
            })}
          </div>
        </div>
        <div className="space-y-3">
          {locations
            .filter((l) => visibleLocs.includes(l.id))
            .map((loc) => {
              const series = scores[loc.id] || [];
              const max = 5;
              const min = 3.5;
              return (
                <div
                  key={loc.id}
                  data-demo-target={`${loc.id}-chart`}
                  className={`rounded-xl border border-border/60 p-3 ${pulse(`${loc.id}-chart`)}`}
                >
                  <div className="text-[12px] font-semibold text-heading mb-2">{loc.name}</div>
                  <div className="flex items-end gap-1 h-16">
                    {series.map((v, i) => {
                      const h = Math.max(8, ((v - min) / (max - min)) * 100);
                      return (
                        <div key={months[i] || i} className="flex-1 flex flex-col items-center gap-1">
                          <div className="w-full rounded-t bg-primary/80" style={{ height: `${h}%` }} title={String(v)} />
                          <span className="text-[9px] text-muted-text">{months[i]}</span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
        </div>
      </div>

      <div className={`rounded-2xl border border-border bg-white p-4 ${pulse("responses-list")}`} data-demo-target="responses-list">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-text mb-3">Recent responses</div>
        <ul className="space-y-2 max-h-48 overflow-auto">
          {responses.slice(0, 12).map((r) => (
            <li
              key={r.id}
              className={`rounded-xl border px-3 py-2 text-[13px] ${
                r.live ? "border-emerald-400 bg-emerald-50" : "border-border"
              }`}
            >
              <div className="flex justify-between gap-2">
                <span className="font-semibold text-heading capitalize">
                  {r.live ? r.name || "You" : r.location} · {r.score}/5
                </span>
                {r.live && <span className="text-[10px] font-bold uppercase text-emerald-700">Live</span>}
              </div>
              <p className="text-body mt-0.5">{r.comment}</p>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
