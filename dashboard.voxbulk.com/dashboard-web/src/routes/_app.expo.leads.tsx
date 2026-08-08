import { createFileRoute, Link } from "@tanstack/react-router";
import {
  CheckCircle2,
  ChevronRight,
  Download,
  FileSpreadsheet,
  Flame,
  Globe,
  Mail,
  MessageCircle,
  MousePointerClick,
  Phone,
  QrCode,
  ScanLine,
  Trash2,
  Building2,
  User,
  Users,
  XCircle,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

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
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { apiFetch, buildAuthHeaders, downloadAuthenticatedFile, getApiBaseUrl } from "@/lib/api";
import { scoreBadgeClass, titleScore, type LeadScoreLabel } from "@/lib/lead-score";
import { cn } from "@/lib/utils";

const SCORE_COLORS: Record<LeadScoreLabel, string> = {
  Hot: "#f43f5e",
  Warm: "#f59e0b",
  Cold: "#0ea5e9",
};

type LeadAnswer = {
  question_key?: string;
  question_label?: string;
  question_prompt?: string;
  answer_text?: string | null;
  original_text?: string | null;
  answer_text_en?: string | null;
  answer_source?: string | null;
  step_order?: number;
  audio_url?: string | null;
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

function inferChannel(lead: LeadRow): { label: string; isWhatsApp: boolean } {
  const ch = String(lead.channel || "").trim().toLowerCase();
  if (ch === "web") return { label: "Web", isWhatsApp: false };
  if (ch === "whatsapp" || ch === "wa") return { label: "WhatsApp", isWhatsApp: true };

  // Fallback for older leads without session.channel on the API payload
  const phone = String(lead.visitor_phone || "").trim();
  const email = String(lead.visitor_email || "").trim().toLowerCase();
  if (
    phone.startsWith("web-pending-") ||
    phone.startsWith("web-card-") ||
    phone.startsWith("web:") ||
    email.endsWith("@expo.local")
  ) {
    return { label: "Web", isWhatsApp: false };
  }
  // Unknown / missing channel — do not assume WhatsApp
  if (!phone && !email) return { label: "Web", isWhatsApp: false };
  return { label: "WhatsApp", isWhatsApp: true };
}

function CatalogueCell({
  sentCount,
  openedCount,
  isWhatsApp,
}: {
  sentCount: number;
  openedCount: number;
  isWhatsApp: boolean;
}) {
  if (openedCount > 0) {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400">
        <CheckCircle2 className="size-3.5" /> Downloaded ({openedCount})
      </span>
    );
  }
  if (sentCount > 0) {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400">
        <CheckCircle2 className="size-3.5" /> Sent ({sentCount})
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
      <XCircle className="size-3.5" /> {isWhatsApp ? "Not sent" : "Not opened"}
    </span>
  );
}

function countryOrBooth(lead: LeadRow): string {
  return lead.country_hint || lead.booth_code || lead.booth_name || "—";
}

function AuthenticatedAudio({ src }: { src: string }) {
  const [blobUrl, setBlobUrl] = React.useState<string | null>(null);
  const [failed, setFailed] = React.useState(false);
  React.useEffect(() => {
    let revoked: string | null = null;
    let cancelled = false;
    setBlobUrl(null);
    setFailed(false);
    const path = String(src || "").trim();
    if (!path) return;
    if (path.startsWith("http://") || path.startsWith("https://")) {
      setBlobUrl(path);
      return;
    }
    (async () => {
      try {
        const base = getApiBaseUrl().replace(/\/+$/, "");
        const res = await fetch(`${base}${path}`, { headers: buildAuthHeaders() });
        if (!res.ok) {
          if (!cancelled) setFailed(true);
          return;
        }
        const blob = await res.blob();
        if (cancelled) return;
        const url = URL.createObjectURL(blob);
        revoked = url;
        setBlobUrl(url);
      } catch {
        if (!cancelled) setFailed(true);
      }
    })();
    return () => {
      cancelled = true;
      if (revoked) URL.revokeObjectURL(revoked);
    };
  }, [src]);
  if (failed) {
    return <p className="mt-3 text-xs text-amber-700 dark:text-amber-400">Recording unavailable</p>;
  }
  if (!blobUrl) {
    return <p className="mt-3 text-xs text-muted-foreground">Loading recording…</p>;
  }
  return (
    <audio controls preload="metadata" className="mt-3 w-full" src={blobUrl}>
      Your browser does not support audio playback.
    </audio>
  );
}

function CardCell({
  on,
  onView,
}: {
  on: boolean;
  onView?: () => void;
}) {
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

function FollowUpCell({ status }: { status?: string | null }) {
  const s = String(status || "none").toLowerCase();
  if (s === "done" || s === "closed") {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400" title="Follow-up done">
        <CheckCircle2 className="size-3.5" />
      </span>
    );
  }
  if (s === "open" || s === "pending") {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-amber-600 dark:text-amber-400" title="Needs follow-up">
        <Flame className="size-3.5" />
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 text-xs text-muted-foreground" title="No follow-up">
      <XCircle className="size-3.5" />
    </span>
  );
}

type AssetSentItem =
  | string
  | {
      asset_id?: string;
      asset_key?: string;
      purpose?: string;
      title?: string;
      sent_at?: string;
    };

type AssetOpenedItem = {
  asset_id?: string;
  asset_key?: string;
  purpose?: string;
  title?: string;
  opened_at?: string;
};

type LeadRow = {
  id: string;
  channel?: string | null;
  created_at?: string | null;
  detected_language?: string | null;
  detected_language_label?: string | null;
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
  email_sent_at?: string | null;
  offer_interested?: boolean;
  follow_up_status?: string | null;
  assets_sent?: AssetSentItem[];
  assets_sent_count?: number;
  assets_opened?: AssetOpenedItem[];
  assets_opened_count?: number;
  catalogue_requested?: boolean;
  price_list_requested?: boolean;
  consent_acknowledged?: boolean;
  business_card_url?: string | null;
  answers?: LeadAnswer[];
};

function assetLabel(item: AssetSentItem | AssetOpenedItem): string {
  if (typeof item === "string") return item;
  const purpose = String(item.purpose || "").replace("_", " ");
  const title = String(item.title || item.asset_key || item.asset_id || "File").trim();
  return purpose ? `${title} (${purpose})` : title;
}

export const Route = createFileRoute("/_app/expo/leads")({
  head: () => ({ meta: [{ title: "Leads & scoring — VoxBulk Expo" }] }),
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
  const [catalogueFilter, setCatalogueFilter] = React.useState("all");
  const [priceListFilter, setPriceListFilter] = React.useState("all");
  const [openedFilter, setOpenedFilter] = React.useState("all");
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
    ...(catalogueFilter !== "all" ? { catalogue_requested: catalogueFilter } : {}),
    ...(priceListFilter !== "all" ? { price_list_requested: priceListFilter } : {}),
    ...(openedFilter !== "all" ? { asset_opened: openedFilter } : {}),
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
        catalogue_requested?: number;
        assets_opened?: number;
        daily?: Array<{ day: string; scans: number; leads: number; hot: number }>;
      }>(`/expo/results/summary${boothId !== "all" ? `?booth_id=${boothId}` : ""}`),
  });

  const leadsQ = useQuery({
    queryKey: ["expo", "leads", boothId, score, catalogueFilter, priceListFilter, openedFilter],
    queryFn: () => apiFetch<{ items: LeadRow[] }>(`/expo/results/leads${qs ? `?${qs}` : ""}`),
  });

  const detailQ = useQuery({
    queryKey: ["expo", "lead", selected?.id],
    enabled: Boolean(selected?.id),
    queryFn: () => apiFetch<{ item: LeadRow }>(`/expo/results/leads/${selected!.id}`),
  });

  const detail = detailQ.data?.item || selected;
  const [cardSrc, setCardSrc] = React.useState<string | null>(null);
  const [cardFailed, setCardFailed] = React.useState(false);

  React.useEffect(() => {
    let revoked: string | null = null;
    let cancelled = false;
    setCardSrc(null);
    setCardFailed(false);
    const path = detail?.business_card_url;
    if (!path) return;
    (async () => {
      try {
        const base = getApiBaseUrl().replace(/\/+$/, "");
        const res = await fetch(`${base}${path}`, { headers: buildAuthHeaders() });
        if (!res.ok) {
          if (!cancelled) setCardFailed(true);
          return;
        }
        const blob = await res.blob();
        if (cancelled) return;
        const url = URL.createObjectURL(blob);
        revoked = url;
        setCardSrc(url);
      } catch {
        if (!cancelled) setCardFailed(true);
      }
    })();
    return () => {
      cancelled = true;
      if (revoked) URL.revokeObjectURL(revoked);
    };
  }, [detail?.business_card_url, detail?.id]);

  const summary = summaryQ.data;
  const leads = leadsQ.data?.items || [];

  const mix = summary
    ? (["Hot", "Warm", "Cold"] as LeadScoreLabel[]).map((name) => ({
        name,
        value: name === "Hot" ? summary.hot : name === "Warm" ? summary.warm : summary.cold,
      }))
    : [];

  const dailyChart = summary?.daily?.length ? summary.daily : null;

  async function handleExport(scope: "all" | "lead" = "all") {
    try {
      const params = new URLSearchParams();
      params.set("format", "xlsx");
      if (boothId !== "all") params.set("booth_id", boothId);
      if (scope === "lead") {
        const id = selected?.id || detail?.id;
        if (!id) {
          toast.error("Open a lead first");
          return;
        }
        params.set("lead_id", id);
      }
      const filename = scope === "lead" ? "expo-lead.xlsx" : "expo-leads.xlsx";
      await downloadAuthenticatedFile(`/expo/results/export?${params.toString()}`, filename);
      toast.success(scope === "lead" ? "This lead downloaded" : "All leads exported");
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
        title="Leads & scoring"
        description="Every scan, scored and sortable. Export to Excel or push straight to your sales team."
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
          value={catalogueFilter}
          onChange={(e) => setCatalogueFilter(e.target.value)}
        >
          <option value="all">Catalogue: all</option>
          <option value="true">Catalogue requested</option>
          <option value="false">Catalogue not requested</option>
        </select>
        <select
          className="h-9 rounded-lg border bg-background px-3 text-sm shadow-sm"
          value={priceListFilter}
          onChange={(e) => setPriceListFilter(e.target.value)}
        >
          <option value="all">Price list: all</option>
          <option value="true">Price list requested</option>
          <option value="false">Price list not requested</option>
        </select>
        <select
          className="h-9 rounded-lg border bg-background px-3 text-sm shadow-sm"
          value={openedFilter}
          onChange={(e) => setOpenedFilter(e.target.value)}
        >
          <option value="all">Opened: all</option>
          <option value="true">Opened files</option>
          <option value="false">Not opened</option>
        </select>
      </div>

      {summaryQ.isLoading ? (
        <Skeleton className="h-20 rounded-2xl" />
      ) : summary ? (
        <div className="grid gap-3 sm:grid-cols-4">
          <Kpi icon={ScanLine} label="Scans" value={String(summary.scans)} tone="text-sky-500" />
          <Kpi icon={Users} label="Leads" value={String(summary.completed_leads)} tone="text-primary" />
          <Kpi icon={Flame} label="Hot" value={String(summary.hot)} tone="text-rose-500" />
          <Kpi
            icon={Download}
            label="Catalogue downloads"
            value={`${summary.catalogue_requested ?? 0}/${summary.completed_leads}`}
            tone="text-violet-500"
          />
        </div>
      ) : null}

      {summaryQ.isLoading ? (
        <Skeleton className="h-[220px] rounded-2xl" />
      ) : summary ? (
        <div className="grid gap-4 lg:grid-cols-3">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Lead quality mix</CardTitle>
              <CardDescription>Hot, warm, and cold across filtered booths</CardDescription>
            </CardHeader>
            <CardContent className="h-[220px]">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={mix} dataKey="value" nameKey="name" innerRadius={50} outerRadius={80} paddingAngle={3}>
                    {mix.map((m) => (
                      <Cell key={m.name} fill={SCORE_COLORS[m.name]} />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {dailyChart ? (
            <Card className="lg:col-span-2">
              <CardHeader>
                <CardTitle className="text-base">Leads per show day</CardTitle>
                <CardDescription>Last 7 days — total vs hot</CardDescription>
              </CardHeader>
              <CardContent className="h-[220px]">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={dailyChart}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} className="stroke-border" />
                    <XAxis dataKey="day" tickLine={false} axisLine={false} className="text-xs" />
                    <YAxis tickLine={false} axisLine={false} className="text-xs" allowDecimals={false} />
                    <Tooltip />
                    <Bar dataKey="leads" radius={[6, 6, 0, 0]} fill="#6366f1" />
                    <Bar dataKey="hot" radius={[6, 6, 0, 0]} fill="#f43f5e" />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          ) : null}
        </div>
      ) : null}

      <Card>
        <CardHeader className="gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <CardTitle className="text-base">All leads</CardTitle>
            <CardDescription className="flex items-center gap-1.5">
              {leads.length} shown
              <span className="inline-flex items-center gap-1 text-primary">
                <MousePointerClick className="size-3" /> click a row for the full lead
              </span>
            </CardDescription>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {(["all", "hot", "warm", "cold"] as const).map((f) => (
              <button
                key={f}
                type="button"
                onClick={() => setScore(f)}
                className={cn(
                  "rounded-full border px-3 py-1 text-xs capitalize transition",
                  score === f
                    ? "border-primary bg-primary/10 text-primary"
                    : "border-border text-muted-foreground hover:border-primary/40",
                )}
              >
                {f === "all" ? "All" : f}
              </button>
            ))}
          </div>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          {leadsQ.isLoading ? (
            <Skeleton className="h-24 w-full" />
          ) : leadsQ.isError ? (
            <p className="py-10 text-center text-sm text-destructive">
              {leadsQ.error instanceof Error ? leadsQ.error.message : "Unable to load leads."}
            </p>
          ) : (
            <table className="w-full min-w-[1040px] text-sm">
              <thead>
                <tr className="border-b border-border text-left text-[11px] uppercase tracking-wider text-muted-foreground">
                  <th className="py-2 pr-3">Lead</th>
                  <th className="py-2 pr-3">Company</th>
                  <th className="py-2 pr-3">Country / booth</th>
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
                {leads.length === 0 ? (
                  <tr>
                    <td colSpan={10} className="py-8 text-center text-xs text-muted-foreground">
                      No leads yet — share your Expo QR at the stand.
                    </td>
                  </tr>
                ) : (
                  leads.map((lead) => {
                    const channel = inferChannel(lead);
                    const sentCount = Number(
                      lead.assets_sent_count ?? (Array.isArray(lead.assets_sent) ? lead.assets_sent.length : 0),
                    );
                    const openedCount = Number(lead.assets_opened_count || 0);
                    return (
                      <tr
                        key={lead.id}
                        className="group cursor-pointer border-b border-border/60 transition hover:bg-muted/50 last:border-0"
                        onClick={() => setSelected(lead)}
                      >
                        <td className="py-2.5 pr-3">
                          <p className="font-medium">{lead.name || "Unknown"}</p>
                          <p className="text-[11px] text-muted-foreground">{displayInterest(lead.interest)}</p>
                        </td>
                        <td className="py-2.5 pr-3 text-muted-foreground">{lead.company || "—"}</td>
                        <td className="py-2.5 pr-3 text-muted-foreground">{countryOrBooth(lead)}</td>
                        <td className="py-2.5 pr-3">
                          <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                            {channel.isWhatsApp ? (
                              <MessageCircle className="size-3.5 text-emerald-500" />
                            ) : (
                              <Globe className="size-3.5 text-primary" />
                            )}
                            {channel.label}
                          </span>
                        </td>
                        <td className="py-2.5 pr-3">
                          <CardCell on={Boolean(lead.business_card_url)} onView={() => setSelected(lead)} />
                        </td>
                        <td className="py-2.5 pr-3">
                          <CatalogueCell
                            sentCount={sentCount}
                            openedCount={openedCount}
                            isWhatsApp={channel.isWhatsApp}
                          />
                        </td>
                        <td className="py-2.5 pr-3">
                          <FollowUpCell status={lead.follow_up_status} />
                        </td>
                        <td className="py-2.5 pr-3">
                          <ScoreBadge score={lead.lead_score} />
                        </td>
                        <td className="py-2.5 pr-3 text-xs text-muted-foreground">{formatTs(lead.created_at)}</td>
                        <td className="py-2.5 text-right" onClick={(e) => e.stopPropagation()}>
                          <div className="flex items-center justify-end gap-1">
                            <Button
                              size="icon"
                              variant="ghost"
                              className="size-8 text-muted-foreground hover:text-destructive"
                              onClick={() => setDeleteTarget(lead)}
                              aria-label="Delete lead"
                            >
                              <Trash2 className="size-4" />
                            </Button>
                            <ChevronRight className="size-4 text-muted-foreground transition group-hover:translate-x-0.5 group-hover:text-primary" />
                          </div>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

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
                      <FileSpreadsheet className="size-3.5" /> Export this lead
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
                ) : detail.business_card_url && cardFailed ? (
                  <section>
                    <p className="text-[11px] font-medium uppercase tracking-[0.16em] text-muted-foreground">
                      Business card
                    </p>
                    <p className="mt-2 text-sm text-amber-700 dark:text-amber-400">
                      Card on file but image unavailable.
                    </p>
                  </section>
                ) : detail.business_card_url ? (
                  <Skeleton className="h-44 w-full rounded-xl" />
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
                  <Badge variant="outline" className="gap-1 text-[10px]">
                    {Number(detail.assets_opened_count || 0) > 0 ? (
                      <>
                        <CheckCircle2 className="size-3 text-emerald-500" />{" "}
                        {detail.assets_opened_count} file(s) downloaded
                      </>
                    ) : Number(detail.assets_sent_count ?? detail.assets_sent?.length ?? 0) > 0 ? (
                      <>
                        <CheckCircle2 className="size-3 text-emerald-500" />{" "}
                        {detail.assets_sent_count ?? detail.assets_sent?.length} file(s) sent
                      </>
                    ) : (
                      <>
                        <XCircle className="size-3 text-muted-foreground" /> No catalogue sent
                      </>
                    )}
                  </Badge>
                  <Badge variant="outline" className="gap-1 text-[10px]">
                    {inferChannel(detail).isWhatsApp ? (
                      <>
                        <MessageCircle className="size-3 text-emerald-500" /> WhatsApp
                      </>
                    ) : (
                      <>
                        <Globe className="size-3 text-primary" /> Web
                      </>
                    )}
                  </Badge>
                  {detail.business_card_url ? (
                    <Badge variant="outline" className="gap-1 text-[10px]">
                      <ScanLine className="size-3 text-sky-500" /> Business card scanned
                    </Badge>
                  ) : null}
                </div>

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
                    <DetailRow
                      label="Language"
                      value={detail.detected_language_label || detail.detected_language || detail.country_hint}
                    />
                    <DetailRow
                      label="Email sent"
                      value={
                        detail.email_sent_at || detail.offer_sent_at
                          ? formatTs(detail.email_sent_at || detail.offer_sent_at)
                          : "No"
                      }
                    />
                    <DetailRow label="Offer interested" value={detail.offer_interested ? "Yes" : "No"} />
                    <DetailRow label="Catalogue requested" value={detail.catalogue_requested ? "Yes" : "No"} />
                    <DetailRow label="Price list requested" value={detail.price_list_requested ? "Yes" : "No"} />
                    <DetailRow
                      label="Files opened"
                      value={
                        Number(detail.assets_opened_count || 0) > 0
                          ? `Yes (${detail.assets_opened_count})`
                          : "No"
                      }
                    />
                    <DetailRow label="Follow-up" value={detail.follow_up_status || "none"} />
                  </div>
                </section>

                {detail.assets_sent && detail.assets_sent.length > 0 ? (
                  <section>
                    <p className="text-[11px] font-medium uppercase tracking-[0.16em] text-muted-foreground">
                      Assets sent
                    </p>
                    <ul className="mt-2 space-y-1.5 text-sm">
                      {detail.assets_sent.map((a, idx) => (
                        <li
                          key={typeof a === "string" ? a : `${a.asset_id || a.asset_key || idx}`}
                          className="rounded-lg border bg-muted/40 px-3 py-2"
                        >
                          {assetLabel(a)}
                        </li>
                      ))}
                    </ul>
                  </section>
                ) : null}

                {detail.assets_opened && detail.assets_opened.length > 0 ? (
                  <section>
                    <p className="text-[11px] font-medium uppercase tracking-[0.16em] text-muted-foreground">
                      Assets opened
                    </p>
                    <ul className="mt-2 space-y-1.5 text-sm">
                      {detail.assets_opened.map((a, idx) => (
                        <li
                          key={`${a.asset_id || a.asset_key || idx}-opened`}
                          className="rounded-lg border bg-muted/40 px-3 py-2"
                        >
                          {assetLabel(a)}
                          {a.opened_at ? (
                            <span className="mt-0.5 block text-xs text-muted-foreground">
                              {formatTs(a.opened_at)}
                            </span>
                          ) : null}
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
                      const langLabel =
                        detail.detected_language_label || detail.detected_language || null;
                      const differs =
                        Boolean(original) &&
                        Boolean(english) &&
                        original.toLowerCase() !== english.toLowerCase();
                      return (
                        <div key={`${a.question_key}-${i}`} className="rounded-xl border bg-card p-4 text-sm shadow-sm">
                          <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
                            {a.question_label || a.question_key || "Question"}
                            {a.answer_source === "voice" ? " · Voice" : null}
                          </p>
                          {a.question_prompt ? (
                            <p className="mt-1.5 text-[13px] font-medium text-foreground">{a.question_prompt}</p>
                          ) : null}
                          {a.answer_source === "voice" && a.audio_url ? (
                            <AuthenticatedAudio src={a.audio_url} />
                          ) : a.answer_source === "voice" ? (
                            <p className="mt-3 text-xs text-amber-700 dark:text-amber-400">
                              Voice answer — recording not available for playback
                            </p>
                          ) : null}
                          <div className="mt-3 space-y-3">
                            <div>
                              <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
                                Original{langLabel ? ` · ${langLabel}` : ""}
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
        <div className={cn("grid size-10 place-items-center rounded-xl bg-background shadow-sm ring-1 ring-border", tone)}>
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
  const label = titleScore(score);
  if (label === "Unscored") return <span className="text-muted-foreground">—</span>;
  return (
    <Badge variant="outline" className={scoreBadgeClass(score)}>
      {label}
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
