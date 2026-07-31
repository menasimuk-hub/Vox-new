import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Plus, QrCode, Search } from "lucide-react";
import * as React from "react";

import { PageHeader } from "@/components/page-header";
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
  const { session } = useSession();
  const canEdit = canManageTeam(normalizeOrgRole(session?.profile?.role));
  const [q, setQ] = React.useState("");

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

  const items = listQ.data?.items || [];
  const seats = entQ.data?.seat_quantity || 0;
  const active = entQ.data?.active_reps || items.filter((r) => r.status !== "archived").length;
  const canAdd = canEdit && (seats === 0 || active < seats || seats > 0);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Smart Card QR"
        title="Saved QR codes"
        description="Your salesman QR codes — edit products, colours, and download PNGs."
        actions={
          <div className="flex flex-wrap gap-2">
            {canEdit ? (
              <>
                <Button asChild variant="outline" size="sm">
                  <Link to="/smart-card/new">
                    <Plus className="size-4" /> Create setup
                  </Link>
                </Button>
                <Button asChild size="sm" disabled={seats > 0 && active >= seats}>
                  <Link to="/smart-card/qrs/new">
                    <QrCode className="size-4" /> Add QR
                  </Link>
                </Button>
              </>
            ) : null}
            <Button asChild variant="outline" size="sm">
              <Link to="/smart-card/leads">Lead results</Link>
            </Button>
          </div>
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
          placeholder="Search by name, email, mobile…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      </div>

      {listQ.isLoading ? (
        <Skeleton className="h-40 rounded-2xl" />
      ) : items.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 p-10 text-center">
            <QrCode className="size-10 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">No Smart Card QR codes yet.</p>
            {canEdit ? (
              <Button asChild>
                <Link to="/smart-card/new">Create Smart Card QR</Link>
              </Button>
            ) : null}
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((rep) => (
            <Card key={rep.id} className="overflow-hidden">
              <CardContent className="space-y-3 p-4">
                <div className="flex items-start gap-3">
                  {rep.qr_image_url ? (
                    <img
                      src={rep.qr_image_url}
                      alt=""
                      className="size-16 shrink-0 rounded-lg border bg-white p-1"
                    />
                  ) : (
                    <div className="grid size-16 place-items-center rounded-lg border bg-muted/30">
                      <QrCode className="size-6 text-muted-foreground" />
                    </div>
                  )}
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium">{rep.name}</p>
                    <p className="truncate text-xs text-muted-foreground">{rep.email || rep.mobile || "—"}</p>
                    <p className="mt-1 text-xs text-muted-foreground">{rep.scan_count || 0} scans</p>
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button asChild size="sm" variant="outline">
                    <Link to="/smart-card/qrs/$repId" params={{ repId: rep.id }}>
                      Edit
                    </Link>
                  </Button>
                  {rep.web_url ? (
                    <Button asChild size="sm" variant="ghost">
                      <a href={rep.web_url} target="_blank" rel="noreferrer">
                        Open
                      </a>
                    </Button>
                  ) : null}
                  <Button asChild size="sm" variant="ghost">
                    <Link to="/smart-card/leads">Leads</Link>
                  </Button>
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
    </div>
  );
}
