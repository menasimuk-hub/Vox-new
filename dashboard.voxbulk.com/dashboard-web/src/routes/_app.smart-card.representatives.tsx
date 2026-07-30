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
  product_ids?: string[];
  qr_fg_color?: string;
  qr_bg_color?: string;
  qr_transparent?: boolean;
};

type Product = { id: string; name: string };

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
  const [editingId, setEditingId] = React.useState<string | null>(null);

  const listQ = useQuery({
    queryKey: ["smart-card", "reps", q],
    queryFn: () =>
      apiFetch<{ ok: boolean; items: Rep[] }>(
        `/smart-card/representatives${q.trim() ? `?q=${encodeURIComponent(q.trim())}` : ""}`,
      ),
  });

  const catalogueQ = useQuery({
    queryKey: ["smart-card", "catalogue"],
    queryFn: () =>
      apiFetch<{ ok: boolean; categories: Array<{ products: Product[] }> }>("/smart-card/catalogue"),
    enabled: canEdit,
  });

  const products = React.useMemo(() => {
    const out: Product[] = [];
    for (const cat of catalogueQ.data?.categories || []) {
      for (const p of cat.products || []) out.push(p);
    }
    return out;
  }, [catalogueQ.data]);

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

  const patchMut = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) =>
      apiFetch(`/smart-card/representatives/${id}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    onSuccess: async () => {
      toast.success("Saved");
      setEditingId(null);
      await qc.invalidateQueries({ queryKey: ["smart-card", "reps"] });
    },
    onError: (e: Error) => toast.error(e.message || "Save failed"),
  });

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Smart Card QR"
        title="Representatives"
        description="Each representative gets one QR. Assign catalogue products; members see only their own leads."
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
            <CardContent className="flex flex-col gap-3 p-3">
              <div className="flex gap-3">
                {rep.qr_image_url ? (
                  <a href={rep.qr_image_url} target="_blank" rel="noreferrer" download>
                    <img
                      src={rep.qr_image_url}
                      alt=""
                      className="size-20 rounded-md border bg-white object-contain"
                    />
                  </a>
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
                    <a
                      className="text-xs text-sky-600 hover:underline"
                      href={rep.web_url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Open public link
                    </a>
                  ) : null}
                </div>
              </div>

              {canEdit ? (
                <div className="space-y-2 border-t pt-2">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setEditingId(editingId === rep.id ? null : rep.id)}
                  >
                    {editingId === rep.id ? "Close" : "Assign & QR"}
                  </Button>
                  {editingId === rep.id ? (
                    <RepEditPanel
                      rep={rep}
                      products={products}
                      busy={patchMut.isPending}
                      onSave={(body) => patchMut.mutate({ id: rep.id, body })}
                    />
                  ) : null}
                </div>
              ) : null}
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

function RepEditPanel({
  rep,
  products,
  busy,
  onSave,
}: {
  rep: Rep;
  products: Product[];
  busy: boolean;
  onSave: (body: Record<string, unknown>) => void;
}) {
  const [selected, setSelected] = React.useState<string[]>(rep.product_ids || []);
  const [fg, setFg] = React.useState(rep.qr_fg_color || "000000");
  const [bg, setBg] = React.useState(rep.qr_bg_color || "ffffff");
  const [transparent, setTransparent] = React.useState(Boolean(rep.qr_transparent));

  const toggle = (id: string) => {
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  return (
    <div className="space-y-2 text-sm">
      <p className="text-xs font-medium text-muted-foreground">Assigned products</p>
      <div className="max-h-28 space-y-1 overflow-y-auto rounded border p-2">
        {products.length ? (
          products.map((p) => (
            <label key={p.id} className="flex items-center gap-2">
              <input type="checkbox" checked={selected.includes(p.id)} onChange={() => toggle(p.id)} />
              <span className="truncate">{p.name}</span>
            </label>
          ))
        ) : (
          <p className="text-xs text-muted-foreground">Add products in Catalogue first.</p>
        )}
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div className="space-y-1">
          <Label className="text-xs">QR foreground</Label>
          <Input value={fg} onChange={(e) => setFg(e.target.value.replace("#", ""))} />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">QR background</Label>
          <Input value={bg} onChange={(e) => setBg(e.target.value.replace("#", ""))} disabled={transparent} />
        </div>
      </div>
      <label className="flex items-center gap-2 text-xs">
        <input type="checkbox" checked={transparent} onChange={(e) => setTransparent(e.target.checked)} />
        Transparent background (download)
      </label>
      <Button
        size="sm"
        disabled={busy}
        onClick={() =>
          onSave({
            product_ids: selected,
            qr_fg_color: fg,
            qr_bg_color: bg,
            qr_transparent: transparent,
          })
        }
      >
        Save
      </Button>
    </div>
  );
}
