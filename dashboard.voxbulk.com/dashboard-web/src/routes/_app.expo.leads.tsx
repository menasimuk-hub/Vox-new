import { createFileRoute, Link } from "@tanstack/react-router";
import {
  FileSpreadsheet,
  Flame,
  Mail,
  Phone,
  QrCode,
  Snowflake,
  Thermometer,
  Trash2,
  Building2,
  User,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { apiFetch, buildAuthHeaders, downloadAuthenticatedFile, getApiBaseUrl } from "@/lib/api";
import { cn } from "@/lib/utils";

type LeadAnswer = {
  question_key?: string;
  question_label?: string;
  question_prompt?: string;
  answer_text?: string | null;
  original_text?: string | null;
  answer_text_en?: string | null;
  answer_source?: string | null;
  step_order?: number;
};

const TRANSLATION_UNAVAILABLE = "[Translation unavailable]";

function displayPhone(phone?: string | null): string | null {
  const p = String(phone || "").trim();
  if (!p || p.startsWith("web-pending-") || p.startsWith("web-card-")) return null;
  return p;
}

function displayEmail(email?: string | null): string | null {
  const e = String(email || "").trim().toLowerCase();
  if (!e || e.endsWith("@expo.local")) return null;
  return String(email || "").trim() || null;
}

function displayInterest(interest?: string | null): string {
  const t = String(interest || "").trim();
  if (!t || t === TRANSLATION_UNAVAILABLE) return "—";
  return t;
}

function displayAnswer(en?: string | null, original?: string | null, fallback?: string | null): string {
  const english = String(en || fallback || "").trim();
  const orig = String(original || fallback || "").trim();
  if (!english || english === TRANSLATION_UNAVAILABLE) return orig || "—";
  return english;
}

type LeadRow = {
  id: string;
  created_at?: string | null;
  detected_language?: string | null;
  country_hint?: string | null;
  visitor_phone?: string | null;
  visitor_email?: string | null;
  name?: string | null;
  company?: string | null;
  interest?: string | null;
  buying_timeline?: string | null;
  lead_score?: string | null;
  booth_name?: string | null;
  booth_code?: string | null;
  offer_sent_at?: string | null;
  follow_up_status?: string | null;
  assets_sent?: string[];
  consent_acknowledged?: boolean;
  business_card_url?: string | null;
  answers?: LeadAnswer[];
};

export const Route = createFileRoute("/_app/expo/leads")({
  head: () => ({ meta: [{ title: "Expo leads — VoxBulk" }] }),
  validateSearch: (search: Record<string, unknown>) => ({
    booth_id: typeof search.booth_id === "string" ? search.booth_id : undefined,
  }),
  component: ExpoLeads,
});

function ExpoLeads() {
  const queryClient = useQueryClient();
  const { booth_id: initialBoothId } = Route.useSearch();
  const [boothId, setBoothId] = React.useState(initialBoothId || "all");
  const [score, setScore] = React.useState("all");
  const [selected, setSelected] = React.useState<LeadRow | null>(null);
  const [deleteTarget, setDeleteTarget] = React.useState<LeadRow | null>(null);
  const [deleting, setDeleting] = React.useState(false);

  React.useEffect(() => {
    if (initialBoothId) setBoothId(initialBoothId);
  }, [initialBoothId]);

  const boothsQ = useQuery({
    queryKey: ["expo", "booths"],
    queryFn: () => apiFetch<{ items: { id: string; name: string }[] }>("/expo/booths"),
  });

  const filters = {
    ...(boothId !== "all" ? { booth_id: boothId } : {}),
    ...(score !== "all" ? { score } : {}),
  };
  const qs = new URLSearchParams(filters).toString();

  const summaryQ = useQuery({
    queryKey: ["expo", "summary", boothId],
    queryFn: () =>
      apiFetch<{
        scans: number;
        scans_today?: number;
        sessions_started: number;
        completed_leads: number;
        leads_today?: number;
        hot: number;
        warm: number;
        cold: number;
        offers_sent: number;
        daily?: Array<{ day: string; scans: number; leads: number; hot: number }>;
      }>(`/expo/results/summary${boothId !== "all" ? `?booth_id=${boothId}` : ""}`),
  });

  const leadsQ = useQuery({
    queryKey: ["expo", "leads", boothId, score],
    queryFn: () => apiFetch<{ items: LeadRow[] }>(`/expo/results/leads${qs ? `?${qs}` : ""}`),
  });

  const detailQ = useQuery({
    queryKey: ["expo", "lead", selected?.id],
    enabled: Boolean(selected?.id),
    queryFn: () => apiFetch<{ item: LeadRow }>(`/expo/results/leads/${selected!.id}`),
  });

  const detail = detailQ.data?.item || selected;
  const [cardSrc, setCardSrc] = React.useState<string | null>(null);

  React.useEffect(() => {
    let revoked: string | null = null;
    let cancelled = false;
    setCardSrc(null);
    const path = detail?.business_card_url;
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
        setCardSrc(url);
      } catch {
        /* ignore */
      }
    })();
    return () => {
      cancelled = true;
      if (revoked) URL.revokeObjectURL(revoked);
    };
  }, [detail?.business_card_url, detail?.id]);

  const summary = summaryQ.data;
  const leads = leadsQ.data?.items || [];

  async function handleExport(scope: "all" | "lead" = "all") {
    try {
      const params = new URLSearchParams();
      params.set("format", "xlsx");
      if (boothId !== "all") params.set("booth_id", boothId);
      // Path without .xlsx extension — more reliable behind nginx
      await downloadAuthenticatedFile(`/expo/results/export?${params.toString()}`, "expo-leads.xlsx");
      toast.success(scope === "lead" ? "Excel downloaded" : "Excel export ready");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Export failed");
    }
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await apiFetch(`/expo/results/leads/${deleteTarget.id}`, { method: "DELETE" });
      toast.success("Lead deleted");
      if (selected?.id === deleteTarget.id) setSelected(null);
      setDeleteTarget(null);
      await queryClient.invalidateQueries({ queryKey: ["expo"] });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not delete lead");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="VoxBulk Expo"
        title="Lead results"
        description="Exhibition leads from WhatsApp and web — filter, open a lead, export, or delete."
        actions={
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" className="gap-1.5" onClick={() => void handleExport("all")}>
              <FileSpreadsheet className="size-4" /> Export Excel
            </Button>
            <Button asChild variant="outline" size="sm" className="gap-1.5">
              <Link to="/expo">
                <QrCode className="size-4" /> Saved booths
              </Link>
            </Button>
          </div>
        }
      />

      <div className="flex flex-wrap gap-3">
        <select
          className="h-9 rounded-lg border bg-background px-3 text-sm shadow-sm"
          value={boothId}
          onChange={(e) => setBoothId(e.target.value)}
        >
          <option value="all">All booths</option>
          {(boothsQ.data?.items || []).map((b) => (
            <option key={b.id} value={b.id}>
              {b.name}
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
        <Skeleton className="h-28 rounded-2xl" />
      ) : summary ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Kpi
            title="Scans total"
            value={summary.scans}
            hint={`${summary.scans_today ?? 0} today`}
            accent="from-sky-500/15 to-sky-500/5"
            icon={<QrCode className="size-4 text-sky-600" />}
          />
          <Kpi
            title="Completed leads"
            value={summary.completed_leads}
            hint={`${summary.leads_today ?? 0} today`}
            accent="from-emerald-500/15 to-emerald-500/5"
            icon={<User className="size-4 text-emerald-600" />}
          />
          <Kpi
            title="Hot / Warm / Cold"
            value={`${summary.hot} / ${summary.warm} / ${summary.cold}`}
            accent="from-amber-500/15 to-orange-500/5"
            icon={<Flame className="size-4 text-orange-600" />}
          />
          <Kpi
            title="Offers sent"
            value={summary.offers_sent}
            accent="from-violet-500/15 to-violet-500/5"
            icon={<Mail className="size-4 text-violet-600" />}
          />
        </div>
      ) : null}

      {leadsQ.isLoading ? (
        <Skeleton className="h-96 rounded-2xl" />
      ) : leadsQ.isError ? (
        <Card>
          <CardContent className="py-10 text-center text-sm text-destructive">
            {leadsQ.error instanceof Error ? leadsQ.error.message : "Unable to load leads."}
          </CardContent>
        </Card>
      ) : (
        <div className="overflow-hidden rounded-2xl border bg-card shadow-sm">
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead>
                <tr className="border-b bg-muted/40 text-[11px] uppercase tracking-wider text-muted-foreground">
                  <th className="px-4 py-3 font-medium">Lead</th>
                  <th className="px-4 py-3 font-medium">Interest</th>
                  <th className="px-4 py-3 font-medium">Score</th>
                  <th className="px-4 py-3 font-medium">Booth</th>
                  <th className="px-4 py-3 font-medium">When</th>
                  <th className="px-4 py-3 font-medium text-right"> </th>
                </tr>
              </thead>
              <tbody>
                {leads.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-4 py-12 text-center text-muted-foreground">
                      No leads yet — share your Expo QR at the stand.
                    </td>
                  </tr>
                ) : (
                  leads.map((lead) => (
                    <tr
                      key={lead.id}
                      className="cursor-pointer border-t transition hover:bg-muted/30"
                      onClick={() => setSelected(lead)}
                    >
                      <td className="px-4 py-3">
                        <p className="font-medium text-foreground">{lead.name || "Unknown"}</p>
                        <p className="text-xs text-muted-foreground">
                          {[lead.company, displayPhone(lead.visitor_phone)].filter(Boolean).join(" · ") || "—"}
                        </p>
                      </td>
                      <td className="max-w-[220px] truncate px-4 py-3 text-muted-foreground" title={displayInterest(lead.interest)}>
                        {displayInterest(lead.interest)}
                      </td>
                      <td className="px-4 py-3">
                        <ScoreBadge score={lead.lead_score} />
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">{lead.booth_code || lead.booth_name || "—"}</td>
                      <td className="whitespace-nowrap px-4 py-3 text-muted-foreground">{formatTs(lead.created_at)}</td>
                      <td className="px-4 py-3 text-right" onClick={(e) => e.stopPropagation()}>
                        <Button
                          size="icon"
                          variant="ghost"
                          className="size-8 text-muted-foreground hover:text-destructive"
                          onClick={() => setDeleteTarget(lead)}
                          aria-label="Delete lead"
                        >
                          <Trash2 className="size-4" />
                        </Button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <Sheet open={selected != null} onOpenChange={(open) => !open && setSelected(null)}>
        <SheetContent side="right" className="flex w-full flex-col gap-0 overflow-hidden p-0 sm:max-w-lg">
          {detail ? (
            <>
              <div className="border-b bg-muted/30 px-6 py-5">
                <SheetHeader className="space-y-3 text-left">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <p className="text-[11px] font-medium uppercase tracking-[0.16em] text-muted-foreground">
                        Lead detail
                      </p>
                      <SheetTitle className="mt-1 truncate text-xl font-semibold tracking-tight">
                        {detail.name || "Unnamed lead"}
                      </SheetTitle>
                      <SheetDescription className="mt-2 flex flex-wrap items-center gap-2">
                        <ScoreBadge score={detail.lead_score} />
                        <span className="text-sm text-muted-foreground">
                          {detail.booth_name || detail.booth_code || "Booth"}
                        </span>
                        <span className="text-sm text-muted-foreground">· {formatTs(detail.created_at)}</span>
                      </SheetDescription>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2 pt-1">
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      className="gap-1.5"
                      onClick={() => void handleExport("lead")}
                    >
                      <FileSpreadsheet className="size-3.5" /> Export Excel
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      className="gap-1.5 text-destructive hover:text-destructive"
                      onClick={() => setDeleteTarget(detail)}
                    >
                      <Trash2 className="size-3.5" /> Delete
                    </Button>
                  </div>
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
                ) : detail.business_card_url && detailQ.isLoading ? (
                  <Skeleton className="h-44 w-full rounded-xl" />
                ) : null}

                <section className="rounded-xl border bg-card p-4 shadow-sm">
                  <p className="text-[11px] font-medium uppercase tracking-[0.16em] text-muted-foreground">
                    Contact
                  </p>
                  <div className="mt-3 grid gap-3">
                    <DetailRow icon={<User className="size-4" />} label="Name" value={detail.name} />
                    <DetailRow icon={<Building2 className="size-4" />} label="Company" value={detail.company} />
                    <DetailRow
                      icon={<Phone className="size-4" />}
                      label="Phone"
                      value={displayPhone(detail.visitor_phone)}
                    />
                    <DetailRow
                      icon={<Mail className="size-4" />}
                      label="Email"
                      value={displayEmail(detail.visitor_email)}
                    />
                  </div>
                </section>

                <section className="rounded-xl border bg-card p-4 shadow-sm">
                  <p className="text-[11px] font-medium uppercase tracking-[0.16em] text-muted-foreground">
                    Qualification
                  </p>
                  <div className="mt-3 grid gap-3">
                    <DetailRow
                      label="Interest"
                      value={displayInterest(detail.interest) === "—" ? null : displayInterest(detail.interest)}
                    />
                    <DetailRow label="Timeline" value={detail.buying_timeline} />
                    <DetailRow label="Language" value={detail.detected_language || detail.country_hint} />
                    <DetailRow label="Offer sent" value={detail.offer_sent_at ? formatTs(detail.offer_sent_at) : "No"} />
                    <DetailRow label="Follow-up" value={detail.follow_up_status || "none"} />
                  </div>
                </section>

                {detail.assets_sent && detail.assets_sent.length > 0 ? (
                  <section>
                    <p className="text-[11px] font-medium uppercase tracking-[0.16em] text-muted-foreground">
                      Assets sent
                    </p>
                    <ul className="mt-2 space-y-1.5 text-sm">
                      {detail.assets_sent.map((a) => (
                        <li key={a} className="rounded-lg border bg-muted/40 px-3 py-2">
                          {a}
                        </li>
                      ))}
                    </ul>
                  </section>
                ) : null}

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
                        <div key={`${a.question_key}-${i}`} className="rounded-xl border bg-card p-4 text-sm shadow-sm">
                          <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
                            {a.question_label || a.question_key || "Question"}
                            {a.answer_source === "voice" ? " · Voice" : null}
                          </p>
                          {a.question_prompt ? (
                            <p className="mt-1.5 text-[13px] font-medium text-foreground">{a.question_prompt}</p>
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
                ) : null}
              </div>
            </>
          ) : null}
        </SheetContent>
      </Sheet>

      <AlertDialog open={deleteTarget != null} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this lead?</AlertDialogTitle>
            <AlertDialogDescription>
              Removes {deleteTarget?.name || "this lead"} and their Expo session answers. This cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleting}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              disabled={deleting}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={(e) => {
                e.preventDefault();
                void confirmDelete();
              }}
            >
              {deleting ? "Deleting…" : "Delete"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function Kpi({
  title,
  value,
  hint,
  accent,
  icon,
}: {
  title: string;
  value: number | string;
  hint?: string;
  accent: string;
  icon: React.ReactNode;
}) {
  return (
    <Card className={cn("overflow-hidden border-0 shadow-sm ring-1 ring-border/60")}>
      <CardContent className={cn("bg-gradient-to-br p-4", accent)}>
        <div className="flex items-center justify-between">
          <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">{title}</p>
          <div className="grid size-8 place-items-center rounded-lg bg-background/80 shadow-sm">{icon}</div>
        </div>
        <p className="mt-2 text-2xl font-semibold tracking-tight tabular-nums">
          {typeof value === "number" ? value.toLocaleString() : value}
        </p>
        {hint ? <p className="mt-1 text-xs font-medium text-foreground/70">{hint}</p> : null}
      </CardContent>
    </Card>
  );
}

function DetailRow({
  label,
  value,
  icon,
}: {
  label: string;
  value?: string | null;
  icon?: React.ReactNode;
}) {
  return (
    <div className="flex gap-3">
      {icon ? <div className="mt-0.5 text-muted-foreground">{icon}</div> : null}
      <div className="min-w-0 flex-1">
        <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">{label}</p>
        <p className="mt-0.5 text-sm text-foreground">{value || "—"}</p>
      </div>
    </div>
  );
}

function ScoreBadge({ score }: { score?: string | null }) {
  const s = String(score || "").toLowerCase();
  if (!s) return <span className="text-muted-foreground">—</span>;
  if (s === "hot") {
    return (
      <Badge className="gap-1 bg-orange-600 hover:bg-orange-600">
        <Flame className="size-3" /> HOT
      </Badge>
    );
  }
  if (s === "warm") {
    return (
      <Badge variant="secondary" className="gap-1 text-amber-800">
        <Thermometer className="size-3" /> WARM
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className="gap-1">
      <Snowflake className="size-3" /> COLD
    </Badge>
  );
}

function formatTs(value?: string | null) {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString("en-GB", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return value;
  }
}
