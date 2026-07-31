import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiFetch } from "@/lib/api";
import { canManageTeam, normalizeOrgRole } from "@/lib/org-roles";
import { useSession } from "@/lib/session";

type Product = { id: string; name: string };

export const Route = createFileRoute("/_app/smart-card/qrs/new")({
  head: () => ({ meta: [{ title: "Add QR — Smart Card QR" }] }),
  component: SmartCardAddQrPage,
});

function SmartCardAddQrPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { session } = useSession();
  const canEdit = canManageTeam(normalizeOrgRole(session?.profile?.role));

  const [name, setName] = React.useState("");
  const [email, setEmail] = React.useState("");
  const [mobile, setMobile] = React.useState("");
  const [productIds, setProductIds] = React.useState<string[]>([]);
  const [fg, setFg] = React.useState("000000");
  const [bg, setBg] = React.useState("ffffff");

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
      apiFetch<{ ok: boolean; item: { id: string } }>("/smart-card/representatives", {
        method: "POST",
        body: JSON.stringify({
          name,
          email: email || null,
          mobile: mobile || null,
          product_ids: productIds,
          qr_fg_color: fg,
          qr_bg_color: bg,
        }),
      }),
    onSuccess: async (res) => {
      toast.success("QR created");
      await qc.invalidateQueries({ queryKey: ["smart-card"] });
      void navigate({ to: "/smart-card/qrs/$repId", params: { repId: res.item.id } });
    },
    onError: (e: Error) => toast.error(e.message || "Could not create QR"),
  });

  if (!canEdit) {
    return (
      <div className="space-y-4">
        <PageHeader eyebrow="Smart Card QR" title="Add QR" />
        <p className="text-sm text-muted-foreground">Managers only.</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-xl space-y-6">
      <PageHeader
        eyebrow="Smart Card QR"
        title="Add salesman QR"
        description="Create another QR up to your seat package. Assign products to this salesman."
        actions={
          <Button asChild variant="outline" size="sm">
            <Link to="/smart-card">Back</Link>
          </Button>
        }
      />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Representative</CardTitle>
          <CardDescription>One QR per salesman.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4">
          <div className="space-y-2">
            <Label>
              Name <span className="text-destructive">*</span>
            </Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>Email</Label>
            <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>Mobile</Label>
            <Input value={mobile} onChange={(e) => setMobile(e.target.value)} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label>QR colour</Label>
              <Input type="color" value={`#${fg}`} onChange={(e) => setFg(e.target.value.replace("#", ""))} />
            </div>
            <div className="space-y-2">
              <Label>Background</Label>
              <Input type="color" value={`#${bg}`} onChange={(e) => setBg(e.target.value.replace("#", ""))} />
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Assign products</CardTitle>
          <CardDescription>Optional — which catalogue products this salesman represents.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {products.length === 0 ? (
            <p className="text-sm text-muted-foreground">No products in catalogue yet.</p>
          ) : (
            products.map((p) => {
              const checked = productIds.includes(p.id);
              return (
                <label key={p.id} className="flex items-center gap-2 text-sm">
                  <Checkbox
                    checked={checked}
                    onCheckedChange={(v) =>
                      setProductIds((prev) => (v ? [...prev, p.id] : prev.filter((id) => id !== p.id)))
                    }
                  />
                  {p.name}
                </label>
              );
            })
          )}
        </CardContent>
      </Card>

      <Button
        disabled={!name.trim() || createMut.isPending}
        onClick={() => createMut.mutate()}
      >
        {createMut.isPending ? "Creating…" : "Create QR"}
      </Button>
    </div>
  );
}
