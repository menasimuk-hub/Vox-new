import { createFileRoute, Link } from "@tanstack/react-router";
import {
  ArrowDownRight,
  ArrowUpRight,
  CreditCard,
  Download,
  Eye,
  Flame,
  Minus,
  Plus,
  QrCode,
  Trash2,
  User,
  Mail,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import {
  Area,
  AreaChart,
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
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { ExpoPayDialog } from "@/components/expo-pay-dialog";
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
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { apiFetch } from "@/lib/api";
import { cn } from "@/lib/utils";

type ExpoBooth = {
  id: string;
  name: string;
  company_display_name: string;
  booth_code?: string | null;
  exhibition_name?: string;
  status?: string;
  scan_count?: number;
  lead_count?: number;
  hot_count?: number;
  qr_image_url?: string;
  whatsapp_url?: string;
  web_url?: string;
  expires_at?: string | null;
  is_expired?: boolean;
  is_before_start?: boolean;
  is_live?: boolean;
  is_paid?: boolean;
  payment_status?: string;
  activated_at?: string | null;
  preview_tests_remaining?: number;
  preview_tests_limit?: number;
};

type ExpoSummary = {
  ok?: boolean;
  scans: number;
  scans_today?: number;
  scans_yesterday?: number;
  sessions_started: number;
  sessions_today?: number;
  completed_leads: number;
  leads_today?: number;
  leads_yesterday?: number;
  hot: number;
  warm: number;
  cold: number;
  offers_sent: number;
  booths_total?: number;
  booths_live?: number;
  daily?: Array<{ day: string; scans: number; leads: number; hot: number }>;
};

export const Route = createFileRoute("/_app/expo/")({
  head: () => ({ meta: [{ title: "Saved Expo booths — VoxBulk" }] }),
  component: ExpoHub,
});

function deltaMeta(today: number, yesterday: number) {
  const diff = today - yesterday;
  if (diff > 0) return { trend: "up" as const, labelDelta: `+${diff} vs yesterday` };
  if (diff < 0) return { trend: "down" as const, labelDelta: `${diff} vs yesterday` };
  return { trend: "flat" as const, labelDelta: "Same as yesterday" };
}

function ExpoHub() {
  const queryClient = useQueryClient();
  const boothsQ = useQuery({
    queryKey: ["expo", "booths"],
    queryFn: () => apiFetch<{ ok: boolean; items: ExpoBooth[] }>("/expo/booths"),
    refetchOnMount: "always",
  });
  const summaryQ = useQuery({
    queryKey: ["expo", "summary"],
    queryFn: () => apiFetch<ExpoSummary>("/expo/results/summary"),
    refetchOnMount: "always",
  });
  const [deleteTarget, setDeleteTarget] = React.useState<ExpoBooth | null>(null);
  const [payTarget, setPayTarget] = React.useState<ExpoBooth | null>(null);
  const [deleting, setDeleting] = React.useState(false);
  const items = boothsQ.data?.items || [];
  const summary = summaryQ.data;
  const daily = summary?.daily || [];

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await apiFetch(`/expo/booths/${deleteTarget.id}`, { method: "DELETE" });
      toast.success(`Deleted “${deleteTarget.name}”`);
      setDeleteTarget(null);
      await queryClient.invalidateQueries({ queryKey: ["expo"] });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not delete booth");
    } finally {
      setDeleting(false);
    }
  };

  const scorePie = [
    { name: "Hot", value: summary?.hot || 0, color: "#ea580c" },
    { name: "Warm", value: summary?.warm || 0, color: "#d97706" },
    { name: "Cold", value: summary?.cold || 0, color: "#0ea5e9" },
  ].filter((d) => d.value > 0);

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="VoxBulk Expo"
        title="Saved booths"
        description="Print these QR codes at your stand — visitors scan, choose WhatsApp or web, and leads are captured automatically."
        actions={
          <Button asChild className="gap-1.5">
            <Link to="/expo/new">
              <Plus className="size-4" /> Create Expo booth
            </Link>
          </Button>
        }
      />

      {summaryQ.isLoading ? (
        <Skeleton className="h-40 rounded-2xl" />
      ) : summary ? (
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <RichKpi
              label="Scans total"
              value={summary.scans}
              sub={`${summary.booths_live ?? 0} live · ${summary.booths_total ?? items.length} booths`}
              {...deltaMeta(summary.scans_today ?? 0, summary.scans_yesterday ?? 0)}
              todayLabel={`${summary.scans_today ?? 0} today`}
              icon={<QrCode className="size-4" />}
              spark={daily.map((d) => d.scans)}
              accent="sky"
            />
            <RichKpi
              label="Leads total"
              value={summary.completed_leads}
              sub={`${summary.sessions_started} sessions started`}
              {...deltaMeta(summary.leads_today ?? 0, summary.leads_yesterday ?? 0)}
              todayLabel={`${summary.leads_today ?? 0} today`}
              icon={<User className="size-4" />}
              spark={daily.map((d) => d.leads)}
              accent="emerald"
            />
            <RichKpi
              label="Hot leads"
              value={summary.hot}
              sub={`${summary.warm} warm · ${summary.cold} cold`}
              trend="up"
              labelDelta={`${summary.hot} hot`}
              todayLabel="Priority follow-up"
              icon={<Flame className="size-4" />}
              spark={daily.map((d) => d.hot)}
              accent="orange"
            />
            <RichKpi
              label="Offers sent"
              value={summary.offers_sent}
              sub="Product packs delivered"
              trend="flat"
              labelDelta="In-session"
              todayLabel={`${summary.sessions_today ?? 0} chats today`}
              icon={<Mail className="size-4" />}
              spark={daily.map((d) => d.leads)}
              accent="violet"
            />
          </div>

          <div className="grid gap-4 lg:grid-cols-[1.6fr_1fr]">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Last 7 days</CardTitle>
                <p className="text-xs text-muted-foreground">Scans and completed leads (UK calendar days)</p>
              </CardHeader>
              <CardContent className="h-[220px]">
                {daily.length === 0 ? (
                  <p className="grid h-full place-items-center text-sm text-muted-foreground">No activity yet</p>
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={daily} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
                      <defs>
                        <linearGradient id="expoScans" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="#0ea5e9" stopOpacity={0.35} />
                          <stop offset="100%" stopColor="#0ea5e9" stopOpacity={0} />
                        </linearGradient>
                        <linearGradient id="expoLeads" x1="0" y1="0" x2="0" y2="1">
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
                      <Area type="monotone" dataKey="scans" name="Scans" stroke="#0ea5e9" strokeWidth={2} fill="url(#expoScans)" />
                      <Area type="monotone" dataKey="leads" name="Leads" stroke="#10b981" strokeWidth={2} fill="url(#expoLeads)" />
                    </AreaChart>
                  </ResponsiveContainer>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Lead temperature</CardTitle>
                <p className="text-xs text-muted-foreground">Hot · Warm · Cold</p>
              </CardHeader>
              <CardContent className="h-[220px]">
                {scorePie.length === 0 ? (
                  <p className="grid h-full place-items-center text-sm text-muted-foreground">No scored leads yet</p>
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie data={scorePie} dataKey="value" innerRadius={52} outerRadius={78} paddingAngle={3} stroke="transparent">
                        {scorePie.map((d) => (
                          <Cell key={d.name} fill={d.color} />
                        ))}
                      </Pie>
                      <Tooltip
                        contentStyle={{
                          background: "hsl(var(--card))",
                          border: "1px solid hsl(var(--border))",
                          borderRadius: 8,
                          fontSize: 12,
                        }}
                      />
                    </PieChart>
                  </ResponsiveContainer>
                )}
                <div className="mt-1 flex flex-wrap justify-center gap-3 text-[11px] text-muted-foreground">
                  <span className="inline-flex items-center gap-1">
                    <span className="size-2 rounded-full bg-orange-600" /> Hot {summary.hot}
                  </span>
                  <span className="inline-flex items-center gap-1">
                    <span className="size-2 rounded-full bg-amber-600" /> Warm {summary.warm}
                  </span>
                  <span className="inline-flex items-center gap-1">
                    <span className="size-2 rounded-full bg-sky-500" /> Cold {summary.cold}
                  </span>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      ) : null}

      {boothsQ.isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-80 rounded-xl" />
          ))}
        </div>
      ) : boothsQ.isError ? (
        <Card>
          <CardContent className="p-8 text-center text-sm text-destructive">
            Could not load booths
            {boothsQ.error instanceof Error ? `: ${boothsQ.error.message}` : ""}.
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((it) => {
            const expired = Boolean(it.is_expired);
            const beforeStart = Boolean(it.is_before_start);
            const paid = Boolean(it.is_paid) || String(it.payment_status || "").toLowerCase() === "paid";
            const live = Boolean(it.is_live) || (paid && !expired && !beforeStart && String(it.status || "").toLowerCase() === "active");
            const unpaid = !paid && !expired;
            const badgeLabel = expired
              ? "Expired"
              : unpaid
                ? "Unpaid"
                : beforeStart
                  ? "Preview"
                  : live
                    ? "Live"
                    : it.status || "Paused";
            const fmtDay = (iso?: string | null) =>
              iso
                ? new Date(iso).toLocaleDateString("en-GB", {
                    day: "numeric",
                    month: "short",
                    year: "numeric",
                  })
                : null;
            const startLabel = fmtDay(it.activated_at);
            const endLabel = fmtDay(it.expires_at);
            const previewLeft = typeof it.preview_tests_remaining === "number" ? it.preview_tests_remaining : null;
            const showPreviewQuota = (unpaid || beforeStart) && previewLeft !== null;
            return (
              <Card key={it.id} className="overflow-hidden">
                <CardHeader className="flex flex-row items-start justify-between gap-2">
                  <div>
                    <CardTitle className="text-base">{it.name}</CardTitle>
                    <p className="mt-0.5 text-xs text-muted-foreground">{it.exhibition_name || "—"}</p>
                    <p className="mt-0.5 text-[11px] text-muted-foreground">{it.company_display_name}</p>
                    {startLabel || endLabel ? (
                      <p className="mt-1 text-[11px] text-muted-foreground">
                        {expired
                          ? `Expired ${endLabel || ""}`.trim()
                          : unpaid
                            ? `Pay to go live${startLabel ? ` from ${startLabel}` : ""}${endLabel ? ` · ends ${endLabel}` : ""}`
                            : beforeStart
                              ? `Starts ${startLabel || "soon"}${endLabel ? ` · ends ${endLabel}` : ""}`
                              : `Live ${startLabel || ""}${endLabel ? ` → ${endLabel}` : ""}`.trim()}
                      </p>
                    ) : null}
                    {showPreviewQuota ? (
                      <p className="mt-0.5 text-[11px] text-muted-foreground">
                        Preview tests left: {previewLeft}/{it.preview_tests_limit || 15}
                      </p>
                    ) : null}
                  </div>
                  <Badge variant={expired || unpaid ? "secondary" : live ? "default" : "secondary"}>
                    {badgeLabel}
                  </Badge>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="flex items-center justify-center rounded-xl border border-dashed border-border bg-background/40 p-3">
                    {it.qr_image_url ? (
                      <img src={it.qr_image_url} alt={`QR for ${it.name}`} className="size-28 rounded-md bg-white p-1" />
                    ) : (
                      <QrCode className="size-12 text-muted-foreground" />
                    )}
                  </div>
                  <div className="grid gap-1.5 text-xs">
                    {it.web_url ? (
                      <a
                        href={it.web_url}
                        target="_blank"
                        rel="noreferrer"
                        className="truncate rounded-md border bg-sky-50 px-2 py-1.5 font-medium text-sky-800 hover:bg-sky-100"
                      >
                        Scan landing (WhatsApp or Web)
                      </a>
                    ) : null}
                    {it.whatsapp_url ? (
                      <a
                        href={it.whatsapp_url}
                        target="_blank"
                        rel="noreferrer"
                        className="truncate rounded-md border bg-emerald-50 px-2 py-1.5 font-medium text-emerald-800 hover:bg-emerald-100"
                      >
                        Direct WhatsApp link
                      </a>
                    ) : null}
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-center">
                    <div className="rounded-lg border border-border bg-background/40 p-2">
                      <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Scans</p>
                      <p className="text-lg font-semibold tabular-nums">{it.scan_count ?? 0}</p>
                    </div>
                    <div className="rounded-lg border border-border bg-background/40 p-2">
                      <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Leads</p>
                      <p className="text-lg font-semibold tabular-nums">{it.lead_count ?? 0}</p>
                    </div>
                  </div>
                  {daily.length > 0 ? (
                    <div className="h-12">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={daily} margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
                          <Bar dataKey="scans" fill="#0ea5e9" radius={[2, 2, 0, 0]} />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  ) : null}
                  <div className="flex flex-wrap items-center gap-2">
                    {unpaid ? (
                      <Button size="sm" className="gap-1.5" onClick={() => setPayTarget(it)}>
                        <CreditCard className="size-3.5" /> Pay
                      </Button>
                    ) : null}
                    {it.qr_image_url ? (
                      <Button size="sm" variant="outline" className="gap-1.5" asChild>
                        <a href={it.qr_image_url} download={`expo-qr-${it.id}.png`}>
                          <Download className="size-3.5" /> Download QR
                        </a>
                      </Button>
                    ) : null}
                    <Button size="sm" variant="ghost" className="gap-1.5" asChild>
                      <Link to="/expo/leads" search={{ booth_id: it.id }}>
                        <Eye className="size-3.5" /> Results
                      </Link>
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="gap-1.5 text-destructive hover:text-destructive"
                      onClick={() => setDeleteTarget(it)}
                    >
                      <Trash2 className="size-3.5" /> Delete
                    </Button>
                  </div>
                </CardContent>
              </Card>
            );
          })}

          <Link
            to="/expo/new"
            className="grid place-items-center rounded-xl border-2 border-dashed border-border bg-background/30 p-8 text-center text-sm text-muted-foreground transition hover:border-primary/50 hover:bg-primary/5 hover:text-primary"
          >
            <div className="flex flex-col items-center gap-2">
              <div className="grid size-12 place-items-center rounded-xl bg-primary/10 text-primary">
                <QrCode className="size-6" />
              </div>
              <p className="font-medium">Create new Expo booth</p>
            </div>
          </Link>
        </div>
      )}

      <ExpoPayDialog
        boothId={payTarget?.id || null}
        boothName={payTarget?.name}
        open={payTarget != null}
        onOpenChange={(open) => !open && setPayTarget(null)}
        onPaid={() => {
          setPayTarget(null);
          void queryClient.invalidateQueries({ queryKey: ["expo"] });
        }}
      />

      <AlertDialog open={deleteTarget != null} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete “{deleteTarget?.name}”?</AlertDialogTitle>
            <AlertDialogDescription>
              This removes the QR code and Expo leads for this booth. This cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleting}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              disabled={deleting}
              onClick={(e) => {
                e.preventDefault();
                void confirmDelete();
              }}
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
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
      <CardContent className="flex flex-col gap-3 p-4">
        <div className="flex items-start justify-between gap-2">
          <span className={cn("grid size-9 place-items-center rounded-lg", iconBg)}>{icon}</span>
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
          <p className="mt-0.5 text-2xl font-semibold tracking-tight tabular-nums">{value.toLocaleString()}</p>
          {sub ? <p className="mt-0.5 text-[11px] text-muted-foreground">{sub}</p> : null}
          <p className="mt-1 text-xs font-medium text-foreground/80">{todayLabel}</p>
        </div>
        <div className="-mx-1 -mb-1 h-10">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={(spark.length ? spark : [0, 0, 0]).map((v, i) => ({ i, v }))} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
              <Area type="monotone" dataKey="v" stroke={meta.stroke} strokeWidth={1.75} fill={meta.stroke} fillOpacity={0.12} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}
