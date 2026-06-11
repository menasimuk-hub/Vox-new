import { createFileRoute, Link } from "@tanstack/react-router";
import { Download, Eye, Plus, QrCode } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useFeedbackLocations } from "@/lib/queries";

export const Route = createFileRoute("/_app/feedback/")({
  head: () => ({ meta: [{ title: "Saved QR surveys — VoxBulk" }] }),
  component: SavedFeedback,
});

function SavedFeedback() {
  const locationsQ = useFeedbackLocations();
  const items = locationsQ.data || [];

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
              <Card key={it.id} className="overflow-hidden">
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
    </div>
  );
}
