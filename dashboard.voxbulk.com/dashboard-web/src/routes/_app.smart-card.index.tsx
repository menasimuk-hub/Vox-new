import { createFileRoute, Link } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, ExternalLink, Package, Pencil, Plus, QrCode, Search, Trash2 } from "lucide-react";
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
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { apiFetch } from "@/lib/api";
import { canManageTeam, normalizeOrgRole } from "@/lib/org-roles";
import { useSession } from "@/lib/session";

type Rep = {
  id: string;
  name: string;
  email?: string | null;
  mobile?: string | null;
  qr_image_url?: string;
  web_url?: string;
  status?: string;
  scan_count?: number;
};

type Entitlement = {
  mode: string;
  seat_quantity: number;
  active_reps: number;
  period_end?: string | null;
  preview_tests_used?: number;
  preview_tests_limit?: number;
};

export const Route = createFileRoute("/_app/smart-card/")({
  head: () => ({ meta: [{ title: "Saved QR codes — Smart Card QR" }] }),
  component: SmartCardSavedQrsPage,
});

function SmartCardSavedQrsPage() {
  const qc = useQueryClient();
  const { session } = useSession();
  const canEdit = canManageTeam(normalizeOrgRole(session?.profile?.role));
  const [q, setQ] = React.useState("");
  const [archiveTarget, setArchiveTarget] = React.useState<Rep | null>(null);

  const listQ = useQuery({
    queryKey: ["smart-card", "reps", q],
    queryFn: () =>
      apiFetch<{ ok: boolean; items: Rep[] }>(
        `/smart-card/representatives${q.trim() ? `?q=${encodeURIComponent(q.trim())}` : ""}`,
      ),
  });

  const entQ = useQuery({
    queryKey: ["smart-card", "entitlement"],
    queryFn: () => apiFetch<{ ok: boolean } & Entitlement>("/smart-card/entitlement"),
  });

  const archiveMut = useMutation({
    mutationFn: (id: string) =>
      apiFetch(`/smart-card/representatives/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ status: "archived" }),
      }),
    onSuccess: async () => {
      toast.success("QR archived");
      setArchiveTarget(null);
      await qc.invalidateQueries({ queryKey: ["smart-card"] });
    },
    onError: (e: Error) => toast.error(e.message || "Could not archive"),
  });

  const items = (listQ.data?.items || []).filter((r) => r.status !== "archived");
  const seats = entQ.data?.seat_quantity || 0;
  const active = entQ.data?.active_reps || items.length;
  const canAdd = canEdit && (seats === 0 || active < seats || seats > 0);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Smart Card QR"
        title="Saved QR codes"
        description="Your representative QR codes — download, open, edit, or manage the product catalogue."
        actions={
          canEdit ? (
            <div className="flex flex-wrap gap-2">
              <Button asChild variant="outline" size="sm">
                <Link to="/smart-card/catalogue">
                  <Package className="size-4" /> Manage products
                </Link>
              </Button>
              <Button asChild size="sm" disabled={seats > 0 && active >= seats}>
                <Link to="/smart-card/qrs/new">
                  <QrCode className="size-4" /> Add QR
                </Link>
              </Button>
              <Button asChild variant="outline" size="sm">
                <Link to="/smart-card/new">
                  <Plus className="size-4" /> Create setup
                </Link>
              </Button>
            </div>
          ) : null
        }
      />

      {entQ.data ? (
        <Card>
          <CardContent className="flex flex-wrap gap-4 p-4 text-sm">
            <span>
              Status: <span className="font-medium capitalize">{entQ.data.mode.replace(/_/g, " ")}</span>
            </span>
            <span>
              Seats: {active} / {seats || "preview"}
            </span>
            {entQ.data.period_end ? (
              <span>Expires: {new Date(entQ.data.period_end).toLocaleDateString()}</span>
            ) : null}
            {entQ.data.mode === "preview" || entQ.data.mode === "preview_exhausted" ? (
              <span>
                Preview tests: {entQ.data.preview_tests_used}/{entQ.data.preview_tests_limit}
              </span>
            ) : null}
            {(entQ.data.mode === "expired" || seats < 1) && canEdit ? (
              <Button asChild size="sm" variant="outline">
                <Link to="/account/smart-card/packages">Buy seats</Link>
              </Button>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      <div className="relative max-w-md">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input
          className="pl-8"
          placeholder="Search representatives…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      </div>

      {listQ.isLoading ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-28 rounded-2xl" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 p-10 text-center">
            <QrCode className="size-10 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">No representative QR codes yet.</p>
            {canEdit ? (
              <Button asChild>
                <Link to="/smart-card/new">Create Smart Card QR</Link>
              </Button>
            ) : null}
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {items.map((rep) => (
            <Card key={rep.id} className="overflow-hidden transition hover:-translate-y-0.5 hover:shadow-md">
              <CardContent className="flex gap-3 p-3">
                {rep.qr_image_url ? (
                  <img
                    src={rep.qr_image_url}
                    alt=""
                    className="size-14 shrink-0 rounded-lg border bg-white p-1"
                  />
                ) : (
                  <div className="grid size-14 place-items-center rounded-lg border bg-muted/30">
                    <QrCode className="size-5 text-muted-foreground" />
                  </div>
                )}
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{rep.name}</p>
                  <p className="truncate text-[11px] text-muted-foreground">
                    {rep.email || rep.mobile || "Representative"}
                  </p>
                  <p className="mt-0.5 text-[11px] tabular-nums text-muted-foreground">
                    {rep.scan_count || 0} scans
                  </p>
                  <div className="mt-2 flex flex-wrap gap-1">
                    {rep.qr_image_url ? (
                      <Button asChild size="sm" variant="outline" className="h-7 px-2 text-xs">
                        <a
                          href={rep.qr_image_url}
                          download={`smart-card-${(rep.name || "qr").replace(/\s+/g, "-").toLowerCase()}.png`}
                        >
                          <Download className="size-3" /> Download
                        </a>
                      </Button>
                    ) : null}
                    {rep.web_url ? (
                      <Button asChild size="sm" variant="outline" className="h-7 px-2 text-xs">
                        <a href={rep.web_url} target="_blank" rel="noreferrer">
                          <ExternalLink className="size-3" /> Open
                        </a>
                      </Button>
                    ) : null}
                    <Button asChild size="sm" variant="outline" className="h-7 px-2 text-xs">
                      <Link to="/smart-card/qrs/$repId" params={{ repId: rep.id }}>
                        <Pencil className="size-3" /> Edit
                      </Link>
                    </Button>
                    {canEdit ? (
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-7 px-2 text-xs text-destructive hover:text-destructive"
                        onClick={() => setArchiveTarget(rep)}
                      >
                        <Trash2 className="size-3" /> Delete
                      </Button>
                    ) : null}
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {!canAdd && seats > 0 && active >= seats ? (
        <p className="text-sm text-muted-foreground">
          Seat limit reached.{" "}
          <Link to="/account/smart-card/packages" className="text-primary underline">
            Buy more seats
          </Link>{" "}
          to add QR codes.
        </p>
      ) : null}

      <AlertDialog open={archiveTarget != null} onOpenChange={(open) => !open && setArchiveTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete “{archiveTarget?.name}”?</AlertDialogTitle>
            <AlertDialogDescription>
              This archives the representative QR. It will disappear from Saved QR codes and free a seat.
              Public scans for this QR will stop working.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={archiveMut.isPending}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              disabled={archiveMut.isPending || !archiveTarget}
              onClick={(e) => {
                e.preventDefault();
                if (archiveTarget) archiveMut.mutate(archiveTarget.id);
              }}
            >
              {archiveMut.isPending ? "Deleting…" : "Delete"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
