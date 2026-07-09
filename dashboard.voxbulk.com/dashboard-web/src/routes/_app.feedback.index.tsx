import { createFileRoute, Link } from "@tanstack/react-router";
import { Copy, Download, Eye, Pencil, Plus, QrCode, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { AnimatedAllowanceKpi } from "@/components/billing/animated-allowance-kpi";
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
import { canDuplicateFeedbackSurvey } from "@/lib/feedback-plan";
import { useUsageAllowances } from "@/lib/billing/use-usage-allowances";
import {
  useDeleteFeedbackLocation,
  useFeedbackLocations,
  useFeedbackSubscription,
  type FeedbackLocation,
} from "@/lib/queries";
import { assistantHighlightClass, useAssistantHighlight } from "@/lib/assistant-highlight";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/feedback/")({
  head: () => ({ meta: [{ title: "Saved QR surveys — VoxBulk" }] }),
  component: SavedFeedback,
});

function SavedFeedback() {
  const locationsQ = useFeedbackLocations();
  const subscriptionQ = useFeedbackSubscription();
  const deleteLocationM = useDeleteFeedbackLocation();
  const allowancesState = useUsageAllowances();
  const waAllowance = allowancesState.feedbackRows.find((r) => r.key === "feedback_wa");
  const webAllowance = allowancesState.feedbackRows.find((r) => r.key === "feedback_web");
  const highlight = useAssistantHighlight().highlight;
  const items = locationsQ.data || [];
  const canDuplicate = canDuplicateFeedbackSurvey(subscriptionQ.data, items.length);
  const [deleteTarget, setDeleteTarget] = useState<FeedbackLocation | null>(null);

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    try {
      await deleteLocationM.mutateAsync(deleteTarget.id);
      toast.success(`Deleted “${deleteTarget.name}”`);
      setDeleteTarget(null);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not delete location");
    }
  };

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="Customer feedback"
        title="Saved QR surveys"
        description="Print these QR codes in your venue — customers scan, send the message, and the WhatsApp survey starts automatically."
        actions={
          <Button asChild className="gap-1.5">
            <Link to="/feedback/new">
              <Plus className="size-4" /> Create QR survey
            </Link>
          </Button>
        }
      />

      {(waAllowance || webAllowance) && !allowancesState.loading ? (
        <div className="grid max-w-2xl gap-3 sm:grid-cols-2">
          {waAllowance ? <AnimatedAllowanceKpi row={waAllowance} compact /> : null}
          {webAllowance ? <AnimatedAllowanceKpi row={webAllowance} compact /> : null}
        </div>
      ) : allowancesState.loading ? (
        <Skeleton className="h-20 max-w-2xl rounded-xl" />
      ) : null}

      {locationsQ.isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-80 rounded-xl" />
          ))}
        </div>
      ) : locationsQ.isError ? (
        <Card>
          <CardContent className="p-8 text-center text-sm text-destructive">
            Could not load locations
            {locationsQ.error instanceof Error ? `: ${locationsQ.error.message}` : ""}.
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((it) => {
            const live = String(it.status || "").toLowerCase() === "active";
            return (
              <Card
                key={it.id}
                data-assistant-highlight={it.id}
                className={cn("overflow-hidden", assistantHighlightClass(it.id, highlight))}
              >
                <CardHeader className="flex flex-row items-start justify-between gap-2">
                  <div>
                    <CardTitle className="text-base">{it.name}</CardTitle>
                    <p className="mt-0.5 text-xs text-muted-foreground">{it.industry_name || "—"}</p>
                    {it.survey_type_name ? (
                      <p className="mt-0.5 text-[11px] text-muted-foreground">{it.survey_type_name}</p>
                    ) : null}
                  </div>
                  <Badge variant={live ? "default" : "secondary"}>{live ? "Live" : it.status || "Paused"}</Badge>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="flex items-center justify-center rounded-xl border border-dashed border-border bg-background/40 p-3">
                    <img src={it.qr_image_url} alt={`QR for ${it.name}`} className="size-40 rounded-md bg-white p-1" />
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-center">
                    <div className="rounded-lg border border-border bg-background/40 p-2">
                      <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Scans</p>
                      <p className="text-lg font-semibold tabular-nums">{it.scan_count ?? 0}</p>
                    </div>
                    <div className="rounded-lg border border-border bg-background/40 p-2">
                      <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Topic</p>
                      <p className="text-sm font-semibold leading-tight">{it.survey_type_name || "—"}</p>
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Button size="sm" variant="outline" className="gap-1.5" asChild>
                      <a href={it.qr_image_url} download={`qr-${it.id}.png`}>
                        <Download className="size-3.5" /> Download QR
                      </a>
                    </Button>
                    <Button size="sm" variant="ghost" className="gap-1.5" asChild>
                      <Link to="/feedback/results" search={{ location_id: it.id }}>
                        <Eye className="size-3.5" /> Results
                      </Link>
                    </Button>
                    <Button size="sm" variant="ghost" className="gap-1.5" asChild>
                      <Link to="/feedback/$locationId/edit" params={{ locationId: it.id }}>
                        <Pencil className="size-3.5" /> Edit survey
                      </Link>
                    </Button>
                    {canDuplicate ? (
                      <Button size="sm" variant="ghost" className="gap-1.5" asChild>
                        <Link to="/feedback/new" search={{ duplicate_from: it.id }}>
                          <Copy className="size-3.5" /> Duplicate
                        </Link>
                      </Button>
                    ) : null}
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
            to="/feedback/new"
            className="grid place-items-center rounded-xl border-2 border-dashed border-border bg-background/30 p-8 text-center text-sm text-muted-foreground transition hover:border-primary/50 hover:bg-primary/5 hover:text-primary"
          >
            <div className="flex flex-col items-center gap-2">
              <div className="grid size-12 place-items-center rounded-xl bg-primary/10 text-primary">
                <QrCode className="size-6" />
              </div>
              <p className="font-medium">Create new QR survey</p>
            </div>
          </Link>
        </div>
      )}

      <AlertDialog open={deleteTarget != null} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete “{deleteTarget?.name}”?</AlertDialogTitle>
            <AlertDialogDescription>
              This removes the QR code and all feedback results for this branch. This cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleteLocationM.isPending}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              disabled={deleteLocationM.isPending}
              onClick={(e) => {
                e.preventDefault();
                void confirmDelete();
              }}
            >
              {deleteLocationM.isPending ? "Deleting…" : "Delete location"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
