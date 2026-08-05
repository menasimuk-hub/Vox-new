import { createFileRoute, Link } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowDownRight,
  ArrowUpRight,
  Building2,
  Flame,
  Mail,
  Minus,
  Phone,
  QrCode,
  Thermometer,
  User,
  Users,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { apiFetch, buildAuthHeaders, getApiBaseUrl } from "@/lib/api";
import { cn } from "@/lib/utils";

type LeadAnswer = {
  question_key?: string;
  question_label?: string;
  question_prompt?: string;
  answer_text?: string | null;
  original_text?: string | null;
  answer_text_en?: string | null;
  answer_source?: string | null;
  audio_url?: string | null;
};

type Lead = {
  id: string;
  name?: string | null;
  company?: string | null;
  representative_id?: string | null;
  representative_name?: string | null;
  visitor_phone?: string | null;
  visitor_email?: string | null;
  lead_score?: string | null;
  interest?: string | null;
  buying_timeline?: string | null;
  ai_summary?: string | null;
  suggested_follow_up?: string | null;
  follow_up_status?: string;
  channel?: string | null;
  business_card_url?: string | null;
  created_at?: string | null;
  answers?: LeadAnswer[];
};

type Summary = {
  scans: number;
  scans_today?: number;
  leads: number;
  leads_today?: number;
  hot: number;
  warm: number;
  cold: number;
  need_follow_up?: number;
  leads_this_week?: number;
  leads_this_month?: number;
  daily?: Array<{ day: string; scans: number; leads: number; hot: number }>;
  by_representative?: Array<{ id: string; name: string; scan_count: number; lead_count: number }>;
  active_reps?: number;
  seat_quantity?: number;
};

type RepRow = {
  id: string;
  name: string;
  scan_count?: number;
  status?: string;
  email?: string | null;
};

const TRANSLATION_UNAVAILABLE = "[Translation unavailable]";

function displayAnswer(en?: string | null, original?: string | null, fallback?: string | null): string {
  const english = String(en || fallback || "").trim();
  const orig = String(original || fallback || "").trim();
  if (!english || english === TRANSLATION_UNAVAILABLE) return orig || "—";
  return english;
}

function formatTs(value?: string | null): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" });
}

function ScoreBadge({ score }: { score?: string | null }) {
  const s = String(score || "").toLowerCase();
  if (s === "hot") return <Badge className="bg-orange-500/15 text-orange-700 hover:bg-orange-500/15">Hot</Badge>;
  if (s === "warm") return <Badge className="bg-amber-500/15 text-amber-800 hover:bg-amber-500/15">Warm</Badge>;
  if (s === "cold") return <Badge className="bg-sky-500/15 text-sky-700 hover:bg-sky-500/15">Cold</Badge>;
  return <Badge variant="secondary">Unscored</Badge>;
}

function DetailRow({
  icon,
  label,
  value,
}: {
  icon?: React.ReactNode;
  label: string;
  value?: string | null;
}) {
  if (!value) return null;
  return (
    <div className="flex items-start gap-3">
      {icon ? <span className="mt-0.5 text-muted-foreground">{icon}</span> : null}
      <div className="min-w-0">
        <p className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</p>
        <p className="truncate text-sm font-medium">{value}</p>
      </div>
    </div>
  );
}

function useAuthenticatedMediaUrl(path?: string | null) {
  const [src, setSrc] = React.useState<string | null>(null);
  React.useEffect(() => {
    let revoked: string | null = null;
    let cancelled = false;
    setSrc(null);
    if (!path) return;
    (async () => {
      try {
        const base = getApiBaseUrl().replace(/\/+$/, "");
        const res = await fetch(`${base}${path}`, { headers: buildAuthHeaders() });
        if (!res.ok) return;
        const blob = await res.blob();
        if (cancelled) return;
        const url = URL.createObjectURL(blob);
        revoked = url;
        setSrc(url);
      } catch {
        /* ignore */
      }
    })();
    return () => {
      cancelled = true;
      if (revoked) URL.revokeObjectURL(revoked);
    };
  }, [path]);
  return src;
}

function VoiceAnswerAudio({ audioUrl }: { audioUrl: string }) {
  const src = useAuthenticatedMediaUrl(audioUrl);
  if (!src) {
    return <p className="mt-3 text-xs text-muted-foreground">Loading recording…</p>;
  }
  return (
    <audio controls preload="none" className="mt-3 w-full" src={src}>
      Your browser does not support audio playback.
    </audio>
  );
}

export const Route = createFileRoute("/_app/smart-card/leads")({
  head: () => ({ meta: [{ title: "Lead results — Smart Card QR" }] }),
  validateSearch: (search: Record<string, unknown>) => ({
    representative_id: typeof search.representative_id === "string" ? search.representative_id : undefined,
  }),
  component: SmartCardLeadsPage,
});

function SmartCardLeadsPage() {
  const qc = useQueryClient();
  const { representative_id: initialRepId } = Route.useSearch();
  const [repId, setRepId] = React.useState(initialRepId || "all");
  const [score, setScore] = React.useState("all");
  const [selected, setSelected] = React.useState<Lead | null>(null);

  React.useEffect(() => {
    if (initialRepId) setRepId(initialRepId);
  }, [initialRepId]);

  const qs = new URLSearchParams(
    repId !== "all" ? { representative_id: repId } : undefined,
  ).toString();

  const summaryQ = useQuery({
    queryKey: ["smart-card", "summary", repId],
    queryFn: () =>
      apiFetch<{ ok: boolean } & Summary>(`/smart-card/results/summary${qs ? `?${qs}` : ""}`),
  });

  const repsQ = useQuery({
    queryKey: ["smart-card", "reps", "leads-page"],
    queryFn: () => apiFetch<{ ok: boolean; items: RepRow[] }>("/smart-card/representatives"),
  });

  const leadsQ = useQuery({
    queryKey: ["smart-card", "leads", repId],
    queryFn: () =>
      apiFetch<{ ok: boolean; items: Lead[] }>(`/smart-card/results/leads${qs ? `?${qs}` : ""}`),
  });

  const detailQ = useQuery({
    queryKey: ["smart-card", "lead", selected?.id],
    enabled: Boolean(selected?.id),
    queryFn: () => apiFetch<{ ok: boolean; item: Lead }>(`/smart-card/results/leads/${selected!.id}`),
  });

  const detail = detailQ.data?.item || selected;
  const cardSrc = useAuthenticatedMediaUrl(detail?.business_card_url);

  const markMut = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      apiFetch(`/smart-card/results/leads/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ follow_up_status: status }),
      }),
    onSuccess: async () => {
      toast.success("Follow-up updated");
      await qc.invalidateQueries({ queryKey: ["smart-card", "leads"] });
      await qc.invalidateQueries({ queryKey: ["smart-card", "summary"] });
      await qc.invalidateQueries({ queryKey: ["smart-card", "lead"] });
    },
    onError: (e: Error) => toast.error(e.message || "Update failed"),
  });

  const summary = summaryQ.data;
  const daily = summary?.daily || [];
  const allLeads = leadsQ.data?.items || [];
  const leads =
    score === "all" ? allLeads : allLeads.filter((l) => String(l.lead_score || "").toLowerCase() === score);
  const byRep =
    summary?.by_representative ||
    (repsQ.data?.items || [])
      .filter((r) => r.status !== "archived")
      .map((r) => ({
        id: r.id,
        name: r.name,
        scan_count: r.scan_count || 0,
        lead_count: 0,
      }));

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Smart Card QR"
        title="Lead results"
        description="Owner/manager see all cards; linked members see only their own. Open a lead for answers, voice playback, and translations."
        actions={
          <Button asChild variant="outline" size="sm" className="gap-1.5">
            <Link to="/smart-card">
              <QrCode className="size-4" /> Saved cards
            </Link>
          </Button>
        }
      />

      <div className="flex flex-wrap gap-3">
        <select
          className="h-9 rounded-lg border bg-background px-3 text-sm shadow-sm"
          value={repId}
          onChange={(e) => setRepId(e.target.value)}
        >
          <option value="all">All cards</option>
          {(repsQ.data?.items || [])
            .filter((r) => r.status !== "archived")
            .map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
        </select>
        <select
          className="h-9 rounded-lg border bg-background px-3 text-sm shadow-sm"
          value={score}
          onChange={(e) => setScore(e.target.value)}
        >
          <option value="all">All scores</option>
          <option value="hot">Hot</option>
          <option value="warm">Warm</option>
          <option value="cold">Cold</option>
        </select>
      </div>

      {summaryQ.isLoading ? (
        <Skeleton className="h-32 rounded-2xl" />
      ) : summary ? (
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <RichKpi
              label="Scans total"
              value={summary.scans}
              sub={`${summary.active_reps ?? 0} representatives`}
              trend={(summary.scans_today || 0) > 0 ? "up" : "flat"}
              labelDelta={`${summary.scans_today || 0} today`}
              todayLabel={`${summary.scans_today || 0} today`}
              icon={<QrCode className="size-4" />}
              spark={daily.map((d) => d.scans)}
              accent="sky"
            />
            <RichKpi
              label="Leads total"
              value={summary.leads}
              sub={`${summary.leads_this_week || 0} this week`}
              trend={(summary.leads_today || 0) > 0 ? "up" : "flat"}
              labelDelta={`${summary.leads_today || 0} today`}
              todayLabel={`${summary.leads_today || 0} today`}
              icon={<User className="size-4" />}
              spark={daily.map((d) => d.leads)}
              accent="emerald"
            />
            <RichKpi
              label="Hot leads"
              value={summary.hot}
              sub={`${summary.warm} warm · ${summary.cold} cold`}
              trend="up"
              labelDelta={`${summary.need_follow_up || 0} need follow-up`}
              todayLabel="Priority follow-up"
              icon={<Flame className="size-4" />}
              spark={daily.map((d) => d.hot)}
              accent="orange"
            />
            <RichKpi
              label="This month"
              value={summary.leads_this_month || 0}
              sub="Completed leads"
              trend="flat"
              labelDelta="Calendar month"
              todayLabel={`${summary.leads_this_week || 0} this week`}
              icon={<Thermometer className="size-4" />}
              spark={daily.map((d) => d.leads)}
              accent="violet"
            />
          </div>

          <div className="grid gap-4 lg:grid-cols-[1.6fr_1fr]">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Last 7 days</CardTitle>
                <p className="text-xs text-muted-foreground">Scans and leads (UK calendar days)</p>
              </CardHeader>
              <CardContent className="h-[220px]">
                {daily.length === 0 ? (
                  <p className="grid h-full place-items-center text-sm text-muted-foreground">No activity yet</p>
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={daily} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
                      <defs>
                        <linearGradient id="scScans" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="#0ea5e9" stopOpacity={0.35} />
                          <stop offset="100%" stopColor="#0ea5e9" stopOpacity={0} />
                        </linearGradient>
                        <linearGradient id="scLeads" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="#10b981" stopOpacity={0.3} />
                          <stop offset="100%" stopColor="#10b981" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                      <XAxis dataKey="day" tick={{ fontSize: 11 }} />
                      <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                      <Tooltip
                        contentStyle={{
                          background: "hsl(var(--card))",
                          border: "1px solid hsl(var(--border))",
                          borderRadius: 8,
                          fontSize: 12,
                        }}
                      />
                      <Area
                        type="monotone"
                        dataKey="scans"
                        name="Scans"
                        stroke="#0ea5e9"
                        fill="url(#scScans)"
                        strokeWidth={2}
                      />
                      <Area
                        type="monotone"
                        dataKey="leads"
                        name="Leads"
                        stroke="#10b981"
                        fill="url(#scLeads)"
                        strokeWidth={2}
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-base">
                  <Users className="size-4" /> By card
                </CardTitle>
                <p className="text-xs text-muted-foreground">Click a row to filter</p>
              </CardHeader>
              <CardContent className="max-h-[220px] overflow-auto p-0">
                {byRep.length === 0 ? (
                  <p className="grid h-[180px] place-items-center text-sm text-muted-foreground">No representatives</p>
                ) : (
                  <table className="w-full text-left text-sm">
                    <thead className="sticky top-0 border-b bg-muted/40 text-xs text-muted-foreground">
                      <tr>
                        <th className="px-4 py-2 font-medium">Name</th>
                        <th className="px-3 py-2 font-medium tabular-nums">Scans</th>
                        <th className="px-4 py-2 font-medium tabular-nums">Leads</th>
                      </tr>
                    </thead>
                    <tbody>
                      {byRep.map((r) => (
                        <tr
                          key={r.id}
                          className={cn(
                            "cursor-pointer border-b last:border-0 hover:bg-muted/40",
                            repId === r.id && "bg-muted/50",
                          )}
                          onClick={() => setRepId(r.id)}
                        >
                          <td className="truncate px-4 py-2 font-medium">{r.name}</td>
                          <td className="px-3 py-2 tabular-nums">{r.scan_count}</td>
                          <td className="px-4 py-2 tabular-nums">{r.lead_count}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      ) : null}

      <div className="space-y-3">
        <h2 className="text-sm font-semibold tracking-tight">Recent leads</h2>
        {leadsQ.isLoading ? <Skeleton className="h-24 rounded-xl" /> : null}
        {leads.map((lead) => (
          <Card
            key={lead.id}
            className="cursor-pointer transition hover:border-foreground/20 hover:shadow-sm"
            onClick={() => setSelected(lead)}
          >
            <CardContent className="space-y-2 p-4">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <p className="font-medium">
                    {lead.name || "Unknown"} · {lead.company || "—"}
                  </p>
                  <p className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                    <ScoreBadge score={lead.lead_score} />
                    <span>
                      {lead.representative_name} · {lead.follow_up_status || "open"} · {formatTs(lead.created_at)}
                    </span>
                  </p>
                </div>
                {lead.follow_up_status === "open" ? (
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={(e) => {
                      e.stopPropagation();
                      markMut.mutate({ id: lead.id, status: "done" });
                    }}
                  >
                    Mark done
                  </Button>
                ) : null}
              </div>
              {lead.ai_summary ? <p className="text-sm text-muted-foreground">{lead.ai_summary}</p> : null}
            </CardContent>
          </Card>
        ))}
        {!leadsQ.isLoading && leads.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No leads yet
            {repId !== "all" ? " for this card" : ""}. Preview scans are hidden from results.
          </p>
        ) : null}
      </div>

      <Sheet open={selected != null} onOpenChange={(open) => !open && setSelected(null)}>
        <SheetContent side="right" className="flex w-full flex-col gap-0 overflow-hidden p-0 sm:max-w-lg">
          {detail ? (
            <>
              <div className="border-b bg-muted/30 px-6 py-5">
                <SheetHeader className="space-y-3 text-left">
                  <div>
                    <p className="text-[11px] font-medium uppercase tracking-[0.16em] text-muted-foreground">
                      Lead detail
                    </p>
                    <SheetTitle className="mt-1 truncate text-xl font-semibold tracking-tight">
                      {detail.name || "Unnamed lead"}
                    </SheetTitle>
                    <SheetDescription className="mt-2 flex flex-wrap items-center gap-2">
                      <ScoreBadge score={detail.lead_score} />
                      <span className="text-sm text-muted-foreground">
                        {detail.representative_name || "Card"}
                      </span>
                      <span className="text-sm text-muted-foreground">· {formatTs(detail.created_at)}</span>
                    </SheetDescription>
                  </div>
                  {detail.follow_up_status === "open" ? (
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() => markMut.mutate({ id: detail.id, status: "done" })}
                    >
                      Mark follow-up done
                    </Button>
                  ) : null}
                </SheetHeader>
              </div>

              <div className="flex-1 space-y-6 overflow-y-auto px-6 py-5">
                {cardSrc ? (
                  <section>
                    <p className="text-[11px] font-medium uppercase tracking-[0.16em] text-muted-foreground">
                      Business card
                    </p>
                    <img
                      src={cardSrc}
                      alt="Business card"
                      className="mt-2 w-full rounded-xl border bg-background object-contain shadow-sm"
                    />
                  </section>
                ) : null}

                <section className="rounded-xl border bg-card p-4 shadow-sm">
                  <p className="text-[11px] font-medium uppercase tracking-[0.16em] text-muted-foreground">
                    Contact
                  </p>
                  <div className="mt-3 grid gap-3">
                    <DetailRow icon={<User className="size-4" />} label="Name" value={detail.name} />
                    <DetailRow icon={<Building2 className="size-4" />} label="Company" value={detail.company} />
                    <DetailRow icon={<Phone className="size-4" />} label="Phone" value={detail.visitor_phone} />
                    <DetailRow icon={<Mail className="size-4" />} label="Email" value={detail.visitor_email} />
                    <DetailRow label="Channel" value={detail.channel} />
                    <DetailRow label="Follow-up" value={detail.follow_up_status || "open"} />
                  </div>
                </section>

                <section className="rounded-xl border bg-card p-4 shadow-sm">
                  <p className="text-[11px] font-medium uppercase tracking-[0.16em] text-muted-foreground">
                    Qualification
                  </p>
                  <div className="mt-3 grid gap-3">
                    <DetailRow label="Interest" value={detail.interest} />
                    <DetailRow label="Timeline" value={detail.buying_timeline} />
                  </div>
                  {detail.ai_summary ? (
                    <p className="mt-3 text-sm text-muted-foreground">{detail.ai_summary}</p>
                  ) : null}
                  {detail.suggested_follow_up ? (
                    <p className="mt-2 rounded-md border bg-muted/40 p-2 text-sm">{detail.suggested_follow_up}</p>
                  ) : null}
                </section>

                {(detail.answers || []).length > 0 ? (
                  <section className="space-y-3">
                    <p className="text-[11px] font-medium uppercase tracking-[0.16em] text-muted-foreground">
                      Questions &amp; answers
                    </p>
                    {(detail.answers || []).map((a, i) => {
                      const original = (a.original_text || a.answer_text || "").trim();
                      const englishRaw = (a.answer_text_en || a.answer_text || "").trim();
                      const english =
                        !englishRaw || englishRaw === TRANSLATION_UNAVAILABLE ? "" : englishRaw;
                      const showBoth =
                        original && english && original.toLowerCase() !== english.toLowerCase();
                      return (
                        <div
                          key={`${a.question_key}-${i}`}
                          className="rounded-xl border bg-card p-4 text-sm shadow-sm"
                        >
                          <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
                            {a.question_label || a.question_key || "Question"}
                            {a.answer_source === "voice" ? " · Voice" : null}
                          </p>
                          {a.question_prompt ? (
                            <p className="mt-1.5 text-[13px] font-medium text-foreground">{a.question_prompt}</p>
                          ) : null}
                          {a.answer_source === "voice" && a.audio_url ? (
                            <VoiceAnswerAudio audioUrl={a.audio_url} />
                          ) : null}
                          {showBoth ? (
                            <div className="mt-3 space-y-3">
                              <div>
                                <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
                                  Original
                                </p>
                                <p className="mt-0.5 whitespace-pre-wrap leading-relaxed">{original}</p>
                              </div>
                              <Separator />
                              <div>
                                <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
                                  English
                                </p>
                                <p className="mt-0.5 whitespace-pre-wrap leading-relaxed">{english}</p>
                              </div>
                            </div>
                          ) : (
                            <p className="mt-2 whitespace-pre-wrap leading-relaxed">
                              {displayAnswer(englishRaw, original, a.answer_text)}
                            </p>
                          )}
                        </div>
                      );
                    })}
                  </section>
                ) : detailQ.isLoading ? (
                  <Skeleton className="h-24 w-full rounded-xl" />
                ) : (
                  <p className="text-sm text-muted-foreground">No question answers stored for this lead.</p>
                )}
              </div>
            </>
          ) : null}
        </SheetContent>
      </Sheet>
    </div>
  );
}

function RichKpi({
  label,
  value,
  sub,
  todayLabel,
  trend,
  labelDelta,
  icon,
  spark,
  accent,
}: {
  label: string;
  value: number;
  sub?: string;
  todayLabel: string;
  trend: "up" | "down" | "flat";
  labelDelta?: string;
  icon: React.ReactNode;
  spark: number[];
  accent: "sky" | "emerald" | "orange" | "violet";
}) {
  const meta =
    trend === "up"
      ? { Arrow: ArrowUpRight, cls: "text-emerald-700 bg-emerald-500/10 border-emerald-500/20", stroke: "#10b981" }
      : trend === "down"
        ? { Arrow: ArrowDownRight, cls: "text-rose-700 bg-rose-500/10 border-rose-500/20", stroke: "#f43f5e" }
        : { Arrow: Minus, cls: "text-muted-foreground bg-muted border-border", stroke: "#94a3b8" };
  const { Arrow } = meta;
  const iconBg =
    accent === "sky"
      ? "bg-sky-500/10 text-sky-700"
      : accent === "emerald"
        ? "bg-emerald-500/10 text-emerald-700"
        : accent === "orange"
          ? "bg-orange-500/10 text-orange-700"
          : "bg-violet-500/10 text-violet-700";
  const deltaText = labelDelta || todayLabel;

  return (
    <Card className="overflow-hidden transition hover:-translate-y-0.5 hover:shadow-md">
      <CardContent className="flex flex-col gap-3 p-3">
        <div className="flex items-start justify-between gap-2">
          <span className={cn("grid size-7 place-items-center rounded-lg", iconBg)}>{icon}</span>
          <span
            className={cn(
              "inline-flex items-center gap-1 rounded-full border px-1.5 py-0.5 text-[10px] font-medium tabular-nums",
              meta.cls,
            )}
          >
            <Arrow className="size-3" /> {deltaText}
          </span>
        </div>
        <div>
          <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">{label}</p>
          <p className="mt-0.5 text-lg font-semibold tracking-tight tabular-nums">{value.toLocaleString()}</p>
          {sub ? <p className="mt-0.5 text-[11px] text-muted-foreground">{sub}</p> : null}
          <p className="mt-1 text-xs font-medium text-foreground/80">{todayLabel}</p>
        </div>
        <div className="-mx-1 -mb-1 h-8">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart
              data={(spark.length ? spark : [0, 0, 0]).map((v, i) => ({ i, v }))}
              margin={{ top: 4, right: 0, left: 0, bottom: 0 }}
            >
              <Area
                type="monotone"
                dataKey="v"
                stroke={meta.stroke}
                strokeWidth={1.75}
                fill={meta.stroke}
                fillOpacity={0.12}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}
