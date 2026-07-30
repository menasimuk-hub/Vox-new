import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Search } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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

export const Route = createFileRoute("/_app/smart-card/representatives")({
  component: SmartCardRepsPage,
});

function SmartCardRepsPage() {
  const { session } = useSession();
  const canEdit = canManageTeam(normalizeOrgRole(session?.profile?.role));
  const qc = useQueryClient();
  const [q, setQ] = React.useState("");
  const [name, setName] = React.useState("");
  const [email, setEmail] = React.useState("");

  const listQ = useQuery({
    queryKey: ["smart-card", "reps", q],
    queryFn: () =>
      apiFetch<{ ok: boolean; items: Rep[] }>(
        `/smart-card/representatives${q.trim() ? `?q=${encodeURIComponent(q.trim())}` : ""}`,
      ),
  });

  const createMut = useMutation({
    mutationFn: () =>
      apiFetch("/smart-card/representatives", {
        method: "POST",
        body: JSON.stringify({ name, email }),
      }),
    onSuccess: async () => {
      toast.success("Representative created");
      setName("");
      setEmail("");
      await qc.invalidateQueries({ queryKey: ["smart-card", "reps"] });
      await qc.invalidateQueries({ queryKey: ["smart-card", "entitlement"] });
    },
    onError: (e: Error) => toast.error(e.message || "Create failed"),
  });

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Smart Card QR"
        title="Representatives"
        description="Each representative gets one QR. Assign products later; members see only their own leads."
      />

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-[200px] flex-1">
          <Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
          <Input className="pl-8" placeholder="Search…" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
      </div>

      {canEdit ? (
        <Card>
          <CardContent className="flex flex-wrap items-end gap-3 p-4">
            <div className="space-y-1.5">
              <Label>Name</Label>
              <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Sales name" />
            </div>
            <div className="space-y-1.5">
              <Label>Email (invite)</Label>
              <Input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="rep@company.com" />
            </div>
            <Button
              className="gap-1.5"
              disabled={!name.trim() || createMut.isPending}
              onClick={() => createMut.mutate()}
            >
              <Plus className="size-4" /> Add
            </Button>
          </CardContent>
        </Card>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {(listQ.data?.items || []).map((rep) => (
          <Card key={rep.id} className="overflow-hidden">
            <CardContent className="flex gap-3 p-3">
              {rep.qr_image_url ? (
                <img src={rep.qr_image_url} alt="" className="size-20 rounded-md border bg-white object-contain" />
              ) : (
                <div className="size-20 rounded-md border bg-muted" />
              )}
              <div className="min-w-0 flex-1 space-y-1">
                <p className="truncate font-medium">{rep.name}</p>
                <p className="truncate text-xs text-muted-foreground">{rep.email || "—"}</p>
                <p className="text-xs text-muted-foreground">
                  {rep.status} · {rep.scan_count ?? 0} scans
                </p>
                {rep.web_url ? (
                  <a className="text-xs text-sky-600 hover:underline" href={rep.web_url} target="_blank" rel="noreferrer">
                    Open public link
                  </a>
                ) : null}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
      {!listQ.isLoading && !(listQ.data?.items || []).length ? (
        <p className="text-sm text-muted-foreground">No representatives yet.</p>
      ) : null}
    </div>
  );
}
