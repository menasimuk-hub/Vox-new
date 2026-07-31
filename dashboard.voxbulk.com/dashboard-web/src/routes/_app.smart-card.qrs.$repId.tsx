import { createFileRoute, Link } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { apiFetch } from "@/lib/api";
import { canManageTeam, normalizeOrgRole } from "@/lib/org-roles";
import { useSession } from "@/lib/session";

type Rep = {
  id: string;
  name: string;
  email?: string | null;
  mobile?: string | null;
  website?: string | null;
  qr_image_url?: string;
  web_url?: string;
  scan_count?: number;
  product_ids?: string[];
  qr_fg_color?: string;
  qr_bg_color?: string;
  qr_transparent?: boolean;
  status?: string;
};

type Product = { id: string; name: string };

export const Route = createFileRoute("/_app/smart-card/qrs/$repId")({
  head: () => ({ meta: [{ title: "Edit QR — Smart Card QR" }] }),
  component: SmartCardEditQrPage,
});

function SmartCardEditQrPage() {
  const { repId } = Route.useParams();
  const qc = useQueryClient();
  const { session } = useSession();
  const canEdit = canManageTeam(normalizeOrgRole(session?.profile?.role));

  const [name, setName] = React.useState("");
  const [email, setEmail] = React.useState("");
  const [mobile, setMobile] = React.useState("");
  const [productIds, setProductIds] = React.useState<string[]>([]);
  const [fg, setFg] = React.useState("000000");
  const [bg, setBg] = React.useState("ffffff");
  const [transparent, setTransparent] = React.useState(false);

  const repQ = useQuery({
    queryKey: ["smart-card", "rep", repId],
    queryFn: () => apiFetch<{ ok: boolean; item: Rep }>(`/smart-card/representatives/${repId}`),
  });

  const catalogueQ = useQuery({
    queryKey: ["smart-card", "catalogue"],
    queryFn: () =>
      apiFetch<{ ok: boolean; categories: Array<{ products: Product[] }> }>("/smart-card/catalogue"),
  });

  React.useEffect(() => {
    const r = repQ.data?.item;
    if (!r) return;
    setName(r.name || "");
    setEmail(r.email || "");
    setMobile(r.mobile || "");
    setProductIds(r.product_ids || []);
    setFg((r.qr_fg_color || "000000").replace("#", ""));
    setBg((r.qr_bg_color || "ffffff").replace("#", ""));
    setTransparent(Boolean(r.qr_transparent));
  }, [repQ.data]);

  const products = React.useMemo(() => {
    const out: Product[] = [];
    for (const cat of catalogueQ.data?.categories || []) {
      for (const p of cat.products || []) out.push(p);
    }
    return out;
  }, [catalogueQ.data]);

  const saveMut = useMutation({
    mutationFn: () =>
      apiFetch(`/smart-card/representatives/${repId}`, {
        method: "PATCH",
        body: JSON.stringify({
          name,
          email: email || null,
          mobile: mobile || null,
          product_ids: productIds,
          qr_fg_color: fg,
          qr_bg_color: bg,
          qr_transparent: transparent,
        }),
      }),
    onSuccess: async () => {
      toast.success("Saved");
      await qc.invalidateQueries({ queryKey: ["smart-card"] });
    },
    onError: (e: Error) => toast.error(e.message || "Save failed"),
  });

  const rep = repQ.data?.item;

  if (repQ.isLoading) {
    return <Skeleton className="h-64 rounded-2xl" />;
  }

  if (!rep) {
    return (
      <div className="space-y-4">
        <PageHeader eyebrow="Smart Card QR" title="QR not found" />
        <Button asChild variant="outline">
          <Link to="/smart-card">Back to Saved QR codes</Link>
        </Button>
      </div>
    );
  }

  const pngUrl = rep.qr_image_url || "";

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <PageHeader
        eyebrow="Smart Card QR"
        title={rep.name}
        description={`${rep.scan_count || 0} scans`}
        actions={
          <Button asChild variant="outline" size="sm">
            <Link to="/smart-card">Saved QR codes</Link>
          </Button>
        }
      />

      <div className="flex flex-col gap-4 sm:flex-row">
        <Card className="sm:w-56">
          <CardContent className="flex flex-col items-center gap-3 p-4">
            {pngUrl ? (
              <img src={pngUrl} alt="QR" className="size-40 rounded-lg border bg-white p-2" />
            ) : null}
            {pngUrl ? (
              <Button asChild size="sm" variant="outline" className="w-full">
                <a href={pngUrl} download={`smart-card-${rep.name || "qr"}.png`}>
                  <Download className="size-4" /> Download PNG
                </a>
              </Button>
            ) : null}
            {rep.web_url ? (
              <a className="text-xs text-primary underline" href={rep.web_url} target="_blank" rel="noreferrer">
                Open link
              </a>
            ) : null}
          </CardContent>
        </Card>

        <div className="min-w-0 flex-1 space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Details</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-3">
              <div className="space-y-2">
                <Label>Name</Label>
                <Input value={name} onChange={(e) => setName(e.target.value)} disabled={!canEdit} />
              </div>
              <div className="space-y-2">
                <Label>Email</Label>
                <Input value={email} onChange={(e) => setEmail(e.target.value)} disabled={!canEdit} />
              </div>
              <div className="space-y-2">
                <Label>Mobile</Label>
                <Input value={mobile} onChange={(e) => setMobile(e.target.value)} disabled={!canEdit} />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">QR style</CardTitle>
              <CardDescription>Foreground, background, and PNG download.</CardDescription>
            </CardHeader>
            <CardContent className="grid grid-cols-2 gap-3">
              <div className="space-y-2">
                <Label>Colour</Label>
                <Input
                  type="color"
                  value={`#${fg}`}
                  disabled={!canEdit}
                  onChange={(e) => setFg(e.target.value.replace("#", ""))}
                />
              </div>
              <div className="space-y-2">
                <Label>Background</Label>
                <Input
                  type="color"
                  value={`#${bg}`}
                  disabled={!canEdit || transparent}
                  onChange={(e) => setBg(e.target.value.replace("#", ""))}
                />
              </div>
              <label className="col-span-2 flex items-center gap-2 text-sm">
                <Checkbox
                  checked={transparent}
                  disabled={!canEdit}
                  onCheckedChange={(v) => setTransparent(Boolean(v))}
                />
                Transparent background
              </label>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Assign products</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {products.length === 0 ? (
                <p className="text-sm text-muted-foreground">No catalogue products yet.</p>
              ) : (
                products.map((p) => {
                  const checked = productIds.includes(p.id);
                  return (
                    <label key={p.id} className="flex items-center gap-2 text-sm">
                      <Checkbox
                        checked={checked}
                        disabled={!canEdit}
                        onCheckedChange={(v) =>
                          setProductIds((prev) =>
                            v ? [...prev, p.id] : prev.filter((id) => id !== p.id),
                          )
                        }
                      />
                      {p.name}
                    </label>
                  );
                })
              )}
            </CardContent>
          </Card>

          {canEdit ? (
            <Button disabled={saveMut.isPending || !name.trim()} onClick={() => saveMut.mutate()}>
              {saveMut.isPending ? "Saving…" : "Save changes"}
            </Button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
