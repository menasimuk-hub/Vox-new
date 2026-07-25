import { createFileRoute, Link } from "@tanstack/react-router";
import { Download, Eye, Plus, QrCode, Trash2 } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

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
import { useQuery, useQueryClient } from "@tanstack/react-query";

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
  activated_at?: string | null;
};

export const Route = createFileRoute("/_app/expo/")({
  head: () => ({ meta: [{ title: "Saved Expo booths — VoxBulk" }] }),
  component: ExpoHub,
});

function ExpoHub() {
  const queryClient = useQueryClient();
  const boothsQ = useQuery({
    queryKey: ["expo", "booths"],
    queryFn: () => apiFetch<{ ok: boolean; items: ExpoBooth[] }>("/expo/booths"),
  });
  const summaryQ = useQuery({
    queryKey: ["expo", "summary"],
    queryFn: () =>
      apiFetch<{
        ok: boolean;
        scans: number;
        sessions_started: number;
        completed_leads: number;
        hot: number;
        warm: number;
        cold: number;
        offers_sent: number;
      }>("/expo/results/summary"),
  });
  const [deleteTarget, setDeleteTarget] = React.useState<ExpoBooth | null>(null);
  const [deleting, setDeleting] = React.useState(false);
  const items = boothsQ.data?.items || [];
  const summary = summaryQ.data;

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

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="VoxBulk Expo"
        title="Saved booths"
        description="Print these QR codes at your stand — visitors scan, WhatsApp opens, and leads are captured automatically."
        actions={
          <Button asChild className="gap-1.5">
            <Link to="/expo/new">
              <Plus className="size-4" /> Create Expo booth
            </Link>
          </Button>
        }
      />

      {summary ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Kpi title="Scans" value={summary.scans} />
          <Kpi title="Completed leads" value={summary.completed_leads} />
          <Kpi title="Hot leads" value={summary.hot} />
          <Kpi title="Offers sent" value={summary.offers_sent} />
        </div>
      ) : summaryQ.isLoading ? (
        <Skeleton className="h-24 rounded-xl" />
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
            const live = !expired && String(it.status || "").toLowerCase() === "active";
            const untilLabel = it.expires_at
              ? new Date(it.expires_at).toLocaleString("en-GB", {
                  day: "numeric",
                  month: "short",
                  year: "numeric",
                  hour: "2-digit",
                  minute: "2-digit",
                })
              : null;
            return (
              <Card key={it.id} className="overflow-hidden">
                <CardHeader className="flex flex-row items-start justify-between gap-2">
                  <div>
                    <CardTitle className="text-base">{it.name}</CardTitle>
                    <p className="mt-0.5 text-xs text-muted-foreground">{it.exhibition_name || "—"}</p>
                    <p className="mt-0.5 text-[11px] text-muted-foreground">{it.company_display_name}</p>
                    {untilLabel ? (
                      <p className="mt-1 text-[11px] text-muted-foreground">
                        {expired ? "Expired" : "Active until"} {untilLabel}
                      </p>
                    ) : null}
                  </div>
                  <Badge variant={expired ? "secondary" : live ? "default" : "secondary"}>
                    {expired ? "Expired" : live ? "Live" : it.status || "Paused"}
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
                    {it.whatsapp_url ? (
                      <a
                        href={it.whatsapp_url}
                        target="_blank"
                        rel="noreferrer"
                        className="truncate rounded-md border bg-emerald-50 px-2 py-1.5 font-medium text-emerald-800 hover:bg-emerald-100"
                      >
                        WhatsApp link (print QR uses this)
                      </a>
                    ) : null}
                    {it.web_url ? (
                      <a
                        href={it.web_url}
                        target="_blank"
                        rel="noreferrer"
                        className="truncate rounded-md border bg-sky-50 px-2 py-1.5 font-medium text-sky-800 hover:bg-sky-100"
                      >
                        Web questionnaire link
                      </a>
                    ) : null}
                    <p className="px-0.5 text-[10px] leading-snug text-muted-foreground">
                      On WhatsApp visitors reply with a business-card photo or type their name — there is no separate
                      button; the first bot message explains both options.
                    </p>
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
                  <div className="flex flex-wrap items-center gap-2">
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

function Kpi({ title, value }: { title: string; value: number }) {
  return (
    <Card>
      <CardContent className="p-4">
        <p className="text-[11px] uppercase tracking-wider text-muted-foreground">{title}</p>
        <p className="mt-1 text-2xl font-semibold tabular-nums">{value.toLocaleString()}</p>
      </CardContent>
    </Card>
  );
}
