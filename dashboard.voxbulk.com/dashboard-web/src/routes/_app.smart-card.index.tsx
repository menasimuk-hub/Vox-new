import { createFileRoute, Link } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CreditCard,
  Download,
  ExternalLink,
  Mail,
  Package,
  Pencil,
  Plus,
  QrCode,
  Search,
  Trash2,
  Upload,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { SmartCardBulkInviteDialog } from "@/components/smart-card/bulk-invite-dialog";
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
import { cn } from "@/lib/utils";

type Rep = {
  id: string;
  name: string;
  email?: string | null;
  mobile?: string | null;
  qr_image_url?: string;
  web_url?: string;
  status?: string;
  scan_count?: number;
  linked_user_id?: string | null;
  invite_id?: string | null;
  invite_status?: string;
  card_incomplete?: boolean;
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

function inviteStatusLabel(status?: string) {
  switch (status) {
    case "linked":
      return "Linked";
    case "pending_invite":
      return "Pending invite";
    case "needs_email":
      return "Needs email";
    case "needs_invite":
      return "Needs invite";
    default:
      return null;
  }
}

function SmartCardSavedQrsPage() {
  const qc = useQueryClient();
  const { session } = useSession();
  const canEdit = canManageTeam(normalizeOrgRole(session?.profile?.role));
  const [q, setQ] = React.useState("");
  const [archiveTarget, setArchiveTarget] = React.useState<Rep | null>(null);
  const [bulkOpen, setBulkOpen] = React.useState(false);

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

  const resendMut = useMutation({
    mutationFn: (id: string) =>
      apiFetch(`/smart-card/representatives/${id}/resend-invite`, {
        method: "POST",
        body: JSON.stringify({}),
      }),
    onSuccess: async () => {
      toast.success("Invite sent");
      await qc.invalidateQueries({ queryKey: ["smart-card"] });
    },
    onError: (e: Error) => toast.error(e.message || "Could not resend invite"),
  });

  const items = (listQ.data?.items || []).filter((r) => r.status !== "archived");
  const seats = entQ.data?.seat_quantity || 0;
  const active = entQ.data?.active_reps || items.length;
  const canAdd = canEdit && (seats === 0 || active < seats || seats > 0);
  const mode = entQ.data?.mode || "";
  const needsPayActivate = Boolean(canEdit && mode && mode !== "live");
  const incompleteOwn = !canEdit && items.some((r) => r.card_incomplete);

  return (
    <div className="space-y-6" data-demo-target="smart-card-list">
      <PageHeader
        eyebrow="Smart Card QR"
        title="Saved QR codes"
        description={
          canEdit
            ? "Your representative QR codes — scan opens the digital card, then Get in touch (WhatsApp or web). Download, open, edit, or invite your team by Excel."
            : "Your Smart Card QR and leads. Complete your card details so customers can reach you."
        }
        actions={
          canEdit ? (
            <div className="flex flex-wrap gap-2">
              {needsPayActivate ? (
                <Button asChild size="sm" className="gap-1.5">
                  <Link to="/account/packages" search={{ tab: "smartCard" }}>
                    <CreditCard className="size-4" /> Pay &amp; Activate
                  </Link>
                </Button>
              ) : null}
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="gap-1.5"
                disabled={seats > 0 && active >= seats}
                onClick={() => setBulkOpen(true)}
              >
                <Upload className="size-4" /> Invite team (Excel)
              </Button>
              <Button asChild variant="outline" size="sm">
                <Link to="/smart-card/catalogue">
                  <Package className="size-4" /> Manage products
                </Link>
              </Button>
              <Button
                asChild
                size="sm"
                variant={needsPayActivate ? "outline" : "default"}
                disabled={seats > 0 && active >= seats}
              >
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
          ) : incompleteOwn && items[0] ? (
            <Button asChild size="sm">
              <Link to="/smart-card/qrs/$repId" params={{ repId: items[0].id }}>
                <Pencil className="size-4" /> Complete your Smart Card
              </Link>
            </Button>
          ) : null
        }
      />

      {!canEdit && incompleteOwn ? (
        <Card className="border-amber-500/40 bg-amber-500/5">
          <CardContent className="flex flex-wrap items-center justify-between gap-3 p-4 text-sm">
            <p>Your card is incomplete — add mobile or website so customers can contact you.</p>
            {items[0] ? (
              <Button asChild size="sm">
                <Link to="/smart-card/qrs/$repId" params={{ repId: items[0].id }}>
                  Complete your Smart Card
                </Link>
              </Button>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      {entQ.data ? (
        <Card className={cn(needsPayActivate && "border-amber-500/40 bg-amber-500/5")}>
          <CardContent className="flex flex-wrap items-center gap-4 p-4 text-sm">
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
              <span className="font-medium text-amber-700 dark:text-amber-400">
                {Math.max(
                  0,
                  (entQ.data.preview_tests_limit || 15) - (entQ.data.preview_tests_used || 0),
                )}{" "}
                of {entQ.data.preview_tests_limit || 15} free scans left
              </span>
            ) : null}
            {needsPayActivate ? (
              <Button asChild size="sm" className="gap-1.5">
                <Link to="/account/packages" search={{ tab: "smartCard" }}>
                  <CreditCard className="size-4" /> Pay &amp; Activate
                </Link>
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
            <p className="text-sm text-muted-foreground">
              {canEdit ? "No representative QR codes yet." : "No Smart Card linked to your account yet."}
            </p>
            {canEdit ? (
              <div className="flex flex-wrap justify-center gap-2">
                <Button type="button" variant="outline" onClick={() => setBulkOpen(true)}>
                  Invite team (Excel)
                </Button>
                <Button asChild>
                  <Link to="/smart-card/new">Create Smart Card QR</Link>
                </Button>
              </div>
            ) : (
              <p className="max-w-sm text-xs text-muted-foreground">
                Ask your organisation admin to invite your email. After you accept and set a password, your card appears
                here so you can complete it.
              </p>
            )}
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((rep) => {
            const previewLeft =
              entQ.data && (entQ.data.mode === "preview" || entQ.data.mode === "preview_exhausted")
                ? Math.max(0, (entQ.data.preview_tests_limit || 15) - (entQ.data.preview_tests_used || 0))
                : null;
            const statusLabel = inviteStatusLabel(rep.invite_status);
            return (
              <Card key={rep.id} className="overflow-hidden transition hover:-translate-y-0.5 hover:shadow-md">
                <CardContent className="flex flex-col gap-3 p-4">
                  <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed bg-background/50 p-3">
                    {rep.qr_image_url ? (
                      <img
                        src={rep.qr_image_url}
                        alt={`QR for ${rep.name}`}
                        className="size-44 shrink-0 rounded-lg border bg-white p-2 sm:size-48"
                      />
                    ) : (
                      <div className="grid size-44 place-items-center rounded-lg border bg-muted/30 sm:size-48">
                        <QrCode className="size-12 text-muted-foreground" />
                      </div>
                    )}
                    {previewLeft !== null ? (
                      <p className="text-center text-[11px] font-medium text-amber-700 dark:text-amber-400">
                        {previewLeft} of {entQ.data?.preview_tests_limit || 15} free scans left
                      </p>
                    ) : entQ.data?.mode === "live" ? (
                      <p className="text-center text-[11px] font-medium text-emerald-700 dark:text-emerald-400">
                        Live
                      </p>
                    ) : null}
                  </div>
                  <div className="min-w-0 text-center">
                    <p className="truncate text-sm font-medium">{rep.name}</p>
                    <p className="truncate text-[11px] text-muted-foreground">
                      {rep.email || rep.mobile || "Representative"}
                    </p>
                    {canEdit && statusLabel ? (
                      <p
                        className={cn(
                          "mt-0.5 text-[11px] font-medium",
                          rep.invite_status === "linked"
                            ? "text-emerald-700 dark:text-emerald-400"
                            : "text-amber-700 dark:text-amber-400",
                        )}
                      >
                        {statusLabel}
                        {rep.card_incomplete ? " · Incomplete card" : null}
                      </p>
                    ) : null}
                    <p className="mt-0.5 text-[11px] tabular-nums text-muted-foreground">
                      {rep.scan_count || 0} scans
                    </p>
                  </div>
                  <div className="flex flex-wrap justify-center gap-1">
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
                    {canEdit &&
                    rep.email &&
                    (rep.invite_status === "pending_invite" ||
                      rep.invite_status === "needs_invite" ||
                      !rep.linked_user_id) ? (
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-7 px-2 text-xs"
                        disabled={resendMut.isPending}
                        onClick={() => resendMut.mutate(rep.id)}
                      >
                        <Mail className="size-3" /> Resend
                      </Button>
                    ) : null}
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
                </CardContent>
              </Card>
            );
          })}
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

      <SmartCardBulkInviteDialog open={bulkOpen} onOpenChange={setBulkOpen} />

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
