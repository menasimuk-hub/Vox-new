import { createFileRoute, Link } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Package, Plus } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import {
  emptyRepresentativeForm,
  RepresentativeFields,
  socialLinksPayload,
  type RepresentativeFormValue,
  type SocialLinks,
} from "@/components/smart-card/representative-fields";
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
  landline?: string | null;
  extension?: string | null;
  website?: string | null;
  social_links?: SocialLinks | null;
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
type Category = { id: string; name: string; products: Product[] };

export const Route = createFileRoute("/_app/smart-card/qrs/$repId")({
  head: () => ({ meta: [{ title: "Edit QR — Smart Card QR" }] }),
  component: SmartCardEditQrPage,
});

function SmartCardEditQrPage() {
  const { repId } = Route.useParams();
  const qc = useQueryClient();
  const { session } = useSession();
  const canEdit = canManageTeam(normalizeOrgRole(session?.profile?.role));

  const [repForm, setRepForm] = React.useState<RepresentativeFormValue>(() => emptyRepresentativeForm());
  const [productIds, setProductIds] = React.useState<string[]>([]);
  const [fg, setFg] = React.useState("000000");
  const [bg, setBg] = React.useState("ffffff");
  const [transparent, setTransparent] = React.useState(false);
  const [newCatName, setNewCatName] = React.useState("");
  const [newProductName, setNewProductName] = React.useState("");
  const [newProductCat, setNewProductCat] = React.useState("");

  const repQ = useQuery({
    queryKey: ["smart-card", "rep", repId],
    queryFn: () => apiFetch<{ ok: boolean; item: Rep }>(`/smart-card/representatives/${repId}`),
  });

  const catalogueQ = useQuery({
    queryKey: ["smart-card", "catalogue"],
    queryFn: () => apiFetch<{ ok: boolean; categories: Category[] }>("/smart-card/catalogue"),
  });

  React.useEffect(() => {
    const r = repQ.data?.item;
    if (!r) return;
    const social = r.social_links || {};
    setRepForm({
      name: r.name || "",
      email: r.email || "",
      mobile: r.mobile || "",
      landline: r.landline || "",
      extension: r.extension || "",
      website: r.website || "",
      social_links: {
        x: social.x || "",
        instagram: social.instagram || "",
        facebook: social.facebook || "",
        tiktok: social.tiktok || "",
        linkedin: social.linkedin || "",
      },
    });
    setProductIds(r.product_ids || []);
    setFg((r.qr_fg_color || "000000").replace("#", ""));
    setBg((r.qr_bg_color || "ffffff").replace("#", ""));
    setTransparent(Boolean(r.qr_transparent));
  }, [repQ.data]);

  const categories = catalogueQ.data?.categories || [];
  const products = React.useMemo(() => {
    const out: Product[] = [];
    for (const cat of categories) {
      for (const p of cat.products || []) out.push(p);
    }
    return out;
  }, [categories]);

  React.useEffect(() => {
    if (!newProductCat && categories[0]?.id) setNewProductCat(categories[0].id);
  }, [categories, newProductCat]);

  const saveMut = useMutation({
    mutationFn: () =>
      apiFetch(`/smart-card/representatives/${repId}`, {
        method: "PATCH",
        body: JSON.stringify({
          name: repForm.name.trim(),
          email: repForm.email.trim() || null,
          mobile: repForm.mobile.trim() || null,
          landline: repForm.landline.trim() || null,
          extension: repForm.extension.trim() || null,
          website: repForm.website.trim() || null,
          social_links: socialLinksPayload(repForm.social_links),
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

  const addCatMut = useMutation({
    mutationFn: () =>
      apiFetch<{ ok: boolean; item?: { id: string } }>("/smart-card/catalogue/categories", {
        method: "POST",
        body: JSON.stringify({ name: newCatName.trim() }),
      }),
    onSuccess: async (res) => {
      setNewCatName("");
      const id = res?.item?.id;
      if (id) setNewProductCat(id);
      toast.success("Category added");
      await qc.invalidateQueries({ queryKey: ["smart-card", "catalogue"] });
    },
    onError: (e: Error) => toast.error(e.message || "Could not add category"),
  });

  const addProductMut = useMutation({
    mutationFn: () =>
      apiFetch<{ ok: boolean; item?: { id: string } }>("/smart-card/catalogue/products", {
        method: "POST",
        body: JSON.stringify({ name: newProductName.trim(), category_id: newProductCat }),
      }),
    onSuccess: async (res) => {
      setNewProductName("");
      const id = res?.item?.id;
      if (id) setProductIds((prev) => (prev.includes(id) ? prev : [...prev, id]));
      toast.success("Product added");
      await qc.invalidateQueries({ queryKey: ["smart-card", "catalogue"] });
    },
    onError: (e: Error) => toast.error(e.message || "Could not add product"),
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
    <div className="mx-auto max-w-3xl space-y-6">
      <PageHeader
        eyebrow="Smart Card QR"
        title={rep.name}
        description={`${rep.scan_count || 0} scans · Representative`}
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
              <CardTitle className="text-base">Representative</CardTitle>
            </CardHeader>
            <CardContent>
              <RepresentativeFields value={repForm} onChange={setRepForm} disabled={!canEdit} />
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
              <CardTitle className="flex items-center gap-2 text-base">
                <Package className="size-4" /> Catalogue & assign products
              </CardTitle>
              <CardDescription>Add a category or product, then tick products for this representative.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {canEdit ? (
                <div className="grid gap-3 rounded-xl border bg-muted/20 p-3 sm:grid-cols-2">
                  <div className="flex gap-2">
                    <Input
                      value={newCatName}
                      onChange={(e) => setNewCatName(e.target.value)}
                      placeholder="New category"
                    />
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      disabled={!newCatName.trim() || addCatMut.isPending}
                      onClick={() => addCatMut.mutate()}
                    >
                      <Plus className="size-4" /> Add
                    </Button>
                  </div>
                  <div className="space-y-2">
                    <select
                      className="h-9 w-full rounded-md border bg-background px-2 text-sm"
                      value={newProductCat}
                      onChange={(e) => setNewProductCat(e.target.value)}
                    >
                      <option value="">Category…</option>
                      {categories.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.name}
                        </option>
                      ))}
                    </select>
                    <div className="flex gap-2">
                      <Input
                        value={newProductName}
                        onChange={(e) => setNewProductName(e.target.value)}
                        placeholder="New product"
                      />
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        disabled={!newProductName.trim() || !newProductCat || addProductMut.isPending}
                        onClick={() => addProductMut.mutate()}
                      >
                        <Plus className="size-4" /> Add
                      </Button>
                    </div>
                  </div>
                </div>
              ) : null}

              {products.length === 0 ? (
                <p className="text-sm text-muted-foreground">No catalogue products yet.</p>
              ) : (
                <div className="space-y-2">
                  {categories.map((cat) =>
                    (cat.products || []).length === 0 ? null : (
                      <div key={cat.id} className="space-y-1.5">
                        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                          {cat.name}
                        </p>
                        {(cat.products || []).map((p) => {
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
                        })}
                      </div>
                    ),
                  )}
                </div>
              )}
            </CardContent>
          </Card>

          {canEdit ? (
            <Button disabled={saveMut.isPending || !repForm.name.trim()} onClick={() => saveMut.mutate()}>
              {saveMut.isPending ? "Saving…" : "Save changes"}
            </Button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
