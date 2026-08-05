import { createFileRoute, Link } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Building2,
  CheckCheck,
  CheckCircle2,
  ChevronRight,
  CreditCard,
  Download,
  Flame,
  Globe,
  Mail,
  MessageCircle,
  MousePointerClick,
  Phone,
  QrCode,
  ScanLine,
  Search,
  User,
  Users,
  XCircle,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { apiFetch, buildAuthHeaders, getApiBaseUrl } from "@/lib/api";
import { scoreBadgeClass, titleScore } from "@/lib/lead-score";
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
  catalogue_requested?: boolean;
  business_card_url?: string | null;
  created_at?: string | null;
  is_preview?: boolean;
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
  const label = titleScore(score);
  return (
    <Badge variant="outline" className={scoreBadgeClass(score)}>
      {label}
    </Badge>
  );
}

function CardCell({ on, onView }: { on: boolean; onView?: () => void }) {
  if (!on) {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
        <XCircle className="size-3.5" /> None
      </span>
    );
  }
  return (
    <button
      type="button"
      className="inline-flex items-center gap-1 rounded-md border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-xs text-emerald-700 transition hover:bg-emerald-500/20 dark:text-emerald-400"
      onClick={(e) => {
        e.stopPropagation();
        onView?.();
      }}
    >
      <ScanLine className="size-3.5" /> View card
    </button>
  );
}

function CatalogueCell({ requested }: { requested: boolean }) {
  return requested ? (
    <span className="inline-flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400">
      <Download className="size-3.5" /> Requested
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
      <XCircle className="size-3.5" /> Not requested
    </span>
  );
}

function FollowUpCell({ status }: { status?: string | null }) {
  const s = String(status || "open").toLowerCase();
  if (s === "done" || s === "closed") {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400" title="Follow-up done">
        <CheckCircle2 className="size-3.5" />
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 text-xs text-amber-600 dark:text-amber-400" title="Needs follow-up">
      <Flame className="size-3.5" />
    </span>
  );
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
  const [q, setQ] = React.useState("");
  const [selected, setSelected] = React.useState<Lead | null>(null);

  const repsQ = useQuery({
    queryKey: ["smart-card", "reps", "leads-page"],
    queryFn: () => apiFetch<{ ok: boolean; items: RepRow[] }>("/smart-card/representatives"),
  });

  const activeReps = React.useMemo(
    () => (repsQ.data?.items || []).filter((r) => r.status !== "archived"),
    [repsQ.data],
  );

  const [selectedRepIds, setSelectedRepIds] = React.useState<string[]>([]);

  React.useEffect(() => {
    if (!activeReps.length) return;
    if (initialRepId) {
      setSelectedRepIds([initialRepId]);
      return;
    }
    setSelectedRepIds((prev) => (prev.length ? prev : activeReps.map((r) => r.id)));
  }, [activeReps, initialRepId]);

  const summaryQ = useQuery({
    queryKey: ["smart-card", "summary"],
    queryFn: () => apiFetch<{ ok: boolean } & Summary>("/smart-card/results/summary"),
  });

  const leadsQ = useQuery({
    queryKey: ["smart-card", "leads"],
    queryFn: () => apiFetch<{ ok: boolean; items: Lead[] }>("/smart-card/results/leads"),
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

  const toggleRep = (id: string) =>
    setSelectedRepIds((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  const allSelected = activeReps.length > 0 && selectedRepIds.length === activeReps.length;

  const scoped = (leadsQ.data?.items || []).filter((l) =>
    selectedRepIds.includes(String(l.representative_id || "")),
  );
  const rows = scoped.filter(
    (l) =>
      q === "" ||
      `${l.name} ${l.company} ${l.interest} ${l.representative_name} ${l.id}`
        .toLowerCase()
        .includes(q.toLowerCase()),
  );

  const hotCount = scoped.filter((l) => String(l.lead_score || "").toLowerCase() === "hot").length;

  const perRep = activeReps
    .filter((r) => selectedRepIds.includes(r.id))
    .map((r) => {
      const leadsFor = scoped.filter((l) => l.representative_id === r.id);
      return {
        name: (r.name || "").split(" ")[0] || r.name,
        leads: leadsFor.length,
        hot: leadsFor.filter((l) => String(l.lead_score || "").toLowerCase() === "hot").length,
      };
    });

  const summary = summaryQ.data;

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="Smart Card QR"
        title="Leads by card"
        description="Pick one card, a few, or all of them — every scan is attributed to the rep who owns the card."
        actions={
          <div className="flex flex-wrap gap-2">
            <Button asChild variant="outline" size="sm" className="gap-1.5">
              <Link to="/smart-card">
                <QrCode className="size-4" /> Saved cards
              </Link>
            </Button>
          </div>
        }
      />

      <Card>
        <CardHeader className="gap-2 pb-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <CardTitle className="flex items-center gap-2 text-base">
              <CreditCard className="size-4 text-primary" /> Select cards
            </CardTitle>
            <CardDescription>
              {selectedRepIds.length} of {activeReps.length} cards included in the results below
            </CardDescription>
          </div>
          <Button
            size="sm"
            variant="outline"
            className="gap-1.5 text-xs"
            onClick={() => setSelectedRepIds(allSelected ? [] : activeReps.map((r) => r.id))}
          >
            <CheckCheck className="size-3.5" /> {allSelected ? "Clear all" : "Select all"}
          </Button>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          {repsQ.isLoading ? <Skeleton className="h-12 w-40" /> : null}
          {activeReps.map((r) => {
            const on = selectedRepIds.includes(r.id);
            const leadCount = (leadsQ.data?.items || []).filter((l) => l.representative_id === r.id).length;
            const hot = (leadsQ.data?.items || []).filter(
              (l) => l.representative_id === r.id && String(l.lead_score || "").toLowerCase() === "hot",
            ).length;
            return (
              <button
                key={r.id}
                type="button"
                onClick={() => toggleRep(r.id)}
                className={cn(
                  "flex items-center gap-2 rounded-xl border px-3 py-2 text-left transition",
                  on ? "border-primary bg-primary/10" : "border-border hover:border-primary/40",
                )}
              >
                <span
                  className={cn(
                    "grid size-7 place-items-center rounded-lg text-[11px] font-semibold",
                    on ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground",
                  )}
                >
                  {(r.name || "?")
                    .split(" ")
                    .map((n) => n[0])
                    .join("")
                    .slice(0, 2)}
                </span>
                <span>
                  <span className="block text-xs font-medium">{r.name}</span>
                  <span className="block text-[10px] text-muted-foreground">
                    {leadCount} leads · {hot} hot
                  </span>
                </span>
              </button>
            );
          })}
        </CardContent>
      </Card>

      <div className="grid gap-3 sm:grid-cols-4">
        <Kpi icon={Users} label="Leads shown" value={String(scoped.length)} tone="text-primary" />
        <Kpi icon={Flame} label="Hot leads" value={String(hotCount)} tone="text-rose-500" />
        <Kpi
          icon={CreditCard}
          label="Cards selected"
          value={`${selectedRepIds.length}/${activeReps.length || 0}`}
          tone="text-violet-500"
        />
        <Kpi
          icon={Download}
          label="Scans (all)"
          value={String(summary?.scans ?? "—")}
          tone="text-emerald-500"
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Leads per selected card</CardTitle>
          <CardDescription>Total vs hot</CardDescription>
        </CardHeader>
        <CardContent className="h-[240px]">
          {perRep.length === 0 ? (
            <p className="grid h-full place-items-center text-sm text-muted-foreground">Select a card</p>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={perRep}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} className="stroke-border" />
                <XAxis dataKey="name" tickLine={false} axisLine={false} className="text-xs" />
                <YAxis tickLine={false} axisLine={false} className="text-xs" allowDecimals={false} />
                <Tooltip />
                <Bar dataKey="leads" radius={[6, 6, 0, 0]} fill="#8b5cf6" />
                <Bar dataKey="hot" radius={[6, 6, 0, 0]} fill="#f43f5e" />
              </BarChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <CardTitle className="text-base">Recent leads</CardTitle>
            <CardDescription className="flex items-center gap-1.5">
              {rows.length} captured
              <span className="inline-flex items-center gap-1 text-primary">
                <MousePointerClick className="size-3" /> click a row to open the card scan and answers
              </span>
            </CardDescription>
          </div>
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search leads, rep, company…"
              className="h-8 w-56 pl-8 text-xs"
            />
          </div>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          {leadsQ.isLoading ? <Skeleton className="h-24 w-full" /> : null}
          <table className="w-full min-w-[1040px] text-sm">
            <thead>
              <tr className="border-b border-border text-left text-[11px] uppercase tracking-wider text-muted-foreground">
                <th className="py-2 pr-3">Lead</th>
                <th className="py-2 pr-3">Company</th>
                <th className="py-2 pr-3">Rep</th>
                <th className="py-2 pr-3">Channel</th>
                <th className="py-2 pr-3">Card</th>
                <th className="py-2 pr-3">Catalogue</th>
                <th className="py-2 pr-3">Follow-up</th>
                <th className="py-2 pr-3">Score</th>
                <th className="py-2 pr-3">Captured</th>
                <th className="py-2" />
              </tr>
            </thead>
            <tbody>
              {rows.map((l) => (
                <tr
                  key={l.id}
                  onClick={() => setSelected(l)}
                  className="group cursor-pointer border-b border-border/60 transition hover:bg-muted/50 last:border-0"
                >
                  <td className="py-2.5 pr-3">
                    <p className="font-medium">{l.name || "Unknown"}</p>
                    <p className="text-[11px] text-muted-foreground">{l.interest || "—"}</p>
                    {l.is_preview ? (
                      <Badge variant="outline" className="mt-1 border-amber-500/40 text-[10px] text-amber-700 dark:text-amber-400">
                        Preview test
                      </Badge>
                    ) : null}
                  </td>
                  <td className="py-2.5 pr-3 text-muted-foreground">{l.company || "—"}</td>
                  <td className="py-2.5 pr-3 text-muted-foreground">{l.representative_name || "—"}</td>
                  <td className="py-2.5 pr-3">
                    <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                      {String(l.channel || "").toLowerCase().includes("whatsapp") ? (
                        <MessageCircle className="size-3.5 text-emerald-500" />
                      ) : (
                        <Globe className="size-3.5 text-primary" />
                      )}
                      {l.channel || "Web"}
                    </span>
                  </td>
                  <td className="py-2.5 pr-3">
                    <CardCell on={Boolean(l.business_card_url)} onView={() => setSelected(l)} />
                  </td>
                  <td className="py-2.5 pr-3">
                    <CatalogueCell requested={Boolean(l.catalogue_requested)} />
                  </td>
                  <td className="py-2.5 pr-3">
                    <FollowUpCell status={l.follow_up_status} />
                  </td>
                  <td className="py-2.5 pr-3">
                    <ScoreBadge score={l.lead_score} />
                  </td>
                  <td className="py-2.5 pr-3 text-xs text-muted-foreground">{formatTs(l.created_at)}</td>
                  <td className="py-2.5 text-right">
                    <ChevronRight className="ml-auto size-4 text-muted-foreground transition group-hover:translate-x-0.5 group-hover:text-primary" />
                  </td>
                </tr>
              ))}
              {!leadsQ.isLoading && rows.length === 0 ? (
                <tr>
                  <td colSpan={10} className="py-8 text-center text-xs text-muted-foreground">
                    No leads for the selected cards yet — complete a WhatsApp or web questionnaire after scanning.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </CardContent>
      </Card>

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
                      {detail.is_preview ? (
                        <Badge variant="outline" className="border-amber-500/40 text-[10px] text-amber-700 dark:text-amber-400">
                          Preview test
                        </Badge>
                      ) : null}
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

                <div className="flex flex-wrap gap-2">
                  <Badge variant="outline" className="gap-1 text-[10px]">
                    {detail.catalogue_requested ? (
                      <>
                        <Download className="size-3 text-emerald-500" /> Catalogue requested
                      </>
                    ) : (
                      <>
                        <XCircle className="size-3 text-muted-foreground" /> Catalogue not requested
                      </>
                    )}
                  </Badge>
                </div>

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
                    <DetailRow label="Catalogue" value={detail.catalogue_requested ? "Requested" : "Not requested"} />
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
                      const differs =
                        Boolean(original) &&
                        Boolean(english) &&
                        original.toLowerCase() !== english.toLowerCase();
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
                          <div className="mt-3 space-y-3">
                            <div>
                              <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
                                Original{differs ? "" : " · English"}
                              </p>
                              <p className="mt-0.5 whitespace-pre-wrap leading-relaxed" dir="auto">
                                {original || displayAnswer(englishRaw, original, a.answer_text)}
                              </p>
                            </div>
                            {differs ? (
                              <>
                                <Separator />
                                <div>
                                  <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
                                    English
                                  </p>
                                  <p className="mt-0.5 whitespace-pre-wrap leading-relaxed">{english}</p>
                                </div>
                              </>
                            ) : null}
                          </div>
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

function Kpi({
  icon: Icon,
  label,
  value,
  tone,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
  tone: string;
}) {
  return (
    <Card>
      <CardContent className="flex items-center gap-3 p-4">
        <div
          className={cn(
            "grid size-10 place-items-center rounded-xl bg-background shadow-sm ring-1 ring-border",
            tone,
          )}
        >
          <Icon className="size-5" />
        </div>
        <div>
          <p className="text-[11px] uppercase tracking-wider text-muted-foreground">{label}</p>
          <p className={cn("text-xl font-semibold tabular-nums", tone)}>{value}</p>
        </div>
      </CardContent>
    </Card>
  );
}
