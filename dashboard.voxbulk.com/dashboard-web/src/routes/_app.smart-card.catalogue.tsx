import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api";
import { canManageTeam, normalizeOrgRole } from "@/lib/org-roles";
import { useSession } from "@/lib/session";

type Asset = { id: string; title: string; external_url?: string | null; purpose?: string };
type Product = { id: string; name: string; short_description?: string | null; assets: Asset[] };
type Category = { id: string; name: string; products: Product[]; assets: Asset[] };

export const Route = createFileRoute("/_app/smart-card/catalogue")({
  component: SmartCardCataloguePage,
});

function SmartCardCataloguePage() {
  const { session } = useSession();
  const canEdit = canManageTeam(normalizeOrgRole(session?.profile?.role));
  const qc = useQueryClient();
  const [catName, setCatName] = React.useState("");
  const [productName, setProductName] = React.useState("");
  const [productCat, setProductCat] = React.useState("");
  const [pdfTitle, setPdfTitle] = React.useState("");
  const [pdfUrl, setPdfUrl] = React.useState("");
  const [pdfProduct, setPdfProduct] = React.useState("");

  const treeQ = useQuery({
    queryKey: ["smart-card", "catalogue"],
    queryFn: () => apiFetch<{ ok: boolean; categories: Category[] }>("/smart-card/catalogue"),
  });

  const addCat = useMutation({
    mutationFn: () =>
      apiFetch("/smart-card/catalogue/categories", { method: "POST", body: JSON.stringify({ name: catName }) }),
    onSuccess: async () => {
      setCatName("");
      toast.success("Category added");
      await qc.invalidateQueries({ queryKey: ["smart-card", "catalogue"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const addProduct = useMutation({
    mutationFn: () =>
      apiFetch("/smart-card/catalogue/products", {
        method: "POST",
        body: JSON.stringify({ name: productName, category_id: productCat }),
      }),
    onSuccess: async () => {
      setProductName("");
      toast.success("Product added");
      await qc.invalidateQueries({ queryKey: ["smart-card", "catalogue"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const addPdf = useMutation({
    mutationFn: () =>
      apiFetch("/smart-card/catalogue/assets", {
        method: "POST",
        body: JSON.stringify({
          title: pdfTitle,
          external_url: pdfUrl,
          product_id: pdfProduct || undefined,
          purpose: "catalogue",
        }),
      }),
    onSuccess: async () => {
      setPdfTitle("");
      setPdfUrl("");
      toast.success("PDF link added");
      await qc.invalidateQueries({ queryKey: ["smart-card", "catalogue"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const cats = treeQ.data?.categories || [];

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Smart Card QR"
        title="Catalogue"
        description="Categories, products, and PDF links. Assign products to representatives from the reps page (product_ids)."
      />

      {canEdit ? (
        <div className="grid gap-3 lg:grid-cols-3">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Add category</CardTitle>
            </CardHeader>
            <CardContent className="flex gap-2">
              <Input value={catName} onChange={(e) => setCatName(e.target.value)} placeholder="Category" />
              <Button disabled={!catName.trim()} onClick={() => addCat.mutate()}>
                Add
              </Button>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Add product</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <select
                className="h-9 w-full rounded-md border bg-background px-2 text-sm"
                value={productCat}
                onChange={(e) => setProductCat(e.target.value)}
              >
                <option value="">Category…</option>
                {cats.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
              <div className="flex gap-2">
                <Input value={productName} onChange={(e) => setProductName(e.target.value)} placeholder="Product" />
                <Button disabled={!productName.trim() || !productCat} onClick={() => addProduct.mutate()}>
                  Add
                </Button>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Add PDF URL</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <select
                className="h-9 w-full rounded-md border bg-background px-2 text-sm"
                value={pdfProduct}
                onChange={(e) => setPdfProduct(e.target.value)}
              >
                <option value="">Product…</option>
                {cats.flatMap((c) => c.products).map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
              <Input value={pdfTitle} onChange={(e) => setPdfTitle(e.target.value)} placeholder="Title" />
              <Input value={pdfUrl} onChange={(e) => setPdfUrl(e.target.value)} placeholder="https://…" />
              <Button disabled={!pdfTitle.trim() || !pdfUrl.trim() || !pdfProduct} onClick={() => addPdf.mutate()}>
                Add PDF
              </Button>
            </CardContent>
          </Card>
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">View only — request changes from your organisation admin.</p>
      )}

      <div className="space-y-4">
        {cats.map((c) => (
          <Card key={c.id}>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">{c.name}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {c.products.map((p) => (
                <div key={p.id} className="rounded-md border p-3">
                  <p className="font-medium">{p.name}</p>
                  {p.short_description ? <p className="text-sm text-muted-foreground">{p.short_description}</p> : null}
                  <ul className="mt-2 space-y-1 text-sm">
                    {p.assets.map((a) => (
                      <li key={a.id}>
                        {a.external_url ? (
                          <a className="text-sky-600 hover:underline" href={a.external_url} target="_blank" rel="noreferrer">
                            {a.title}
                          </a>
                        ) : (
                          a.title
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
              {!c.products.length ? <p className="text-sm text-muted-foreground">No products</p> : null}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
