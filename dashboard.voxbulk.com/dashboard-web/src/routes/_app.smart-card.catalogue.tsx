import { createFileRoute, Link } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
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
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiFetch, apiUploadFiles } from "@/lib/api";
import { canManageTeam, normalizeOrgRole } from "@/lib/org-roles";
import { useSession } from "@/lib/session";

type Asset = {
  id: string;
  title: string;
  external_url?: string | null;
  storage_path?: string | null;
  purpose?: string;
};
type Product = { id: string; name: string; short_description?: string | null; assets: Asset[] };
type Category = { id: string; name: string; products: Product[]; assets: Asset[] };

export const Route = createFileRoute("/_app/smart-card/catalogue")({
  head: () => ({ meta: [{ title: "Manage products — Smart Card QR" }] }),
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
  const [uploadPath, setUploadPath] = React.useState("");
  const [uploadKind, setUploadKind] = React.useState("pdf");
  const [uploadName, setUploadName] = React.useState("");
  const [uploading, setUploading] = React.useState(false);
  const [deleteTarget, setDeleteTarget] = React.useState<
    | { kind: "category"; id: string; name: string }
    | { kind: "product"; id: string; name: string }
    | null
  >(null);

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
          ...(uploadPath
            ? { storage_path: uploadPath, kind: uploadKind || "pdf" }
            : { external_url: pdfUrl }),
          product_id: pdfProduct || undefined,
          purpose: "catalogue",
        }),
      }),
    onSuccess: async () => {
      setPdfTitle("");
      setPdfUrl("");
      setUploadPath("");
      setUploadKind("pdf");
      setUploadName("");
      toast.success("Asset added");
      await qc.invalidateQueries({ queryKey: ["smart-card", "catalogue"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const deleteMut = useMutation({
    mutationFn: async () => {
      if (!deleteTarget) return;
      if (deleteTarget.kind === "category") {
        await apiFetch(`/smart-card/catalogue/categories/${deleteTarget.id}`, { method: "DELETE" });
      } else {
        await apiFetch(`/smart-card/catalogue/products/${deleteTarget.id}`, { method: "DELETE" });
      }
    },
    onSuccess: async () => {
      toast.success(deleteTarget?.kind === "category" ? "Category removed" : "Product removed");
      setDeleteTarget(null);
      await qc.invalidateQueries({ queryKey: ["smart-card", "catalogue"] });
    },
    onError: (e: Error) => toast.error(e.message || "Could not remove"),
  });

  const onFileSelected = async (file: File | null) => {
    if (!file) return;
    setUploading(true);
    try {
      const res = (await apiUploadFiles("/smart-card/catalogue/assets/upload", [file], "file")) as {
        item?: { storage_path?: string; original_filename?: string; kind?: string };
      };
      const item = res?.item || {};
      setUploadPath(String(item.storage_path || ""));
      setUploadKind(String(item.kind || "pdf"));
      setUploadName(String(item.original_filename || file.name));
      if (!pdfTitle.trim()) setPdfTitle(String(item.original_filename || file.name));
      setPdfUrl("");
      toast.success("File uploaded");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const cats = treeQ.data?.categories || [];
  const canAddAsset = Boolean(pdfTitle.trim() && pdfProduct && (uploadPath || pdfUrl.trim()));

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Smart Card QR"
        title="Manage products"
        description="Add or remove categories and products. Assign them to each representative when you edit a QR code."
        actions={
          <Button asChild variant="outline" size="sm">
            <Link to="/smart-card">Saved QR codes</Link>
          </Button>
        }
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
              <CardTitle className="text-sm">Add PDF / file</CardTitle>
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
              <Input
                type="file"
                accept=".pdf,.png,.jpg,.jpeg,.webp,.gif,.xls,.xlsx,.csv,application/pdf,image/*"
                disabled={uploading}
                onChange={(e) => void onFileSelected(e.target.files?.[0] || null)}
              />
              {uploadPath ? (
                <p className="text-xs text-muted-foreground">
                  Uploaded: {uploadName || uploadPath}
                  <button
                    type="button"
                    className="ml-2 text-sky-600 hover:underline"
                    onClick={() => {
                      setUploadPath("");
                      setUploadName("");
                      setUploadKind("pdf");
                    }}
                  >
                    Clear
                  </button>
                </p>
              ) : (
                <Input
                  value={pdfUrl}
                  onChange={(e) => setPdfUrl(e.target.value)}
                  placeholder="Or paste https://…"
                />
              )}
              <Button disabled={!canAddAsset || uploading} onClick={() => addPdf.mutate()}>
                {uploading ? "Uploading…" : "Add asset"}
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
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-base">{c.name}</CardTitle>
              {canEdit ? (
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-8 text-destructive hover:text-destructive"
                  onClick={() => setDeleteTarget({ kind: "category", id: c.id, name: c.name })}
                >
                  <Trash2 className="size-3.5" /> Remove category
                </Button>
              ) : null}
            </CardHeader>
            <CardContent className="space-y-3">
              {c.products.map((p) => (
                <div key={p.id} className="flex items-start justify-between gap-2 rounded-md border p-3">
                  <div className="min-w-0">
                    <p className="font-medium">{p.name}</p>
                    {p.short_description ? <p className="text-sm text-muted-foreground">{p.short_description}</p> : null}
                    <ul className="mt-2 space-y-1 text-sm">
                      {p.assets.map((a) => (
                        <li key={a.id}>
                          {a.external_url ? (
                            <a className="text-sky-600 hover:underline" href={a.external_url} target="_blank" rel="noreferrer">
                              {a.title}
                            </a>
                          ) : a.storage_path ? (
                            <span>
                              {a.title} <span className="text-muted-foreground">(uploaded)</span>
                            </span>
                          ) : (
                            a.title
                          )}
                        </li>
                      ))}
                    </ul>
                  </div>
                  {canEdit ? (
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-7 shrink-0 px-2 text-destructive hover:text-destructive"
                      onClick={() => setDeleteTarget({ kind: "product", id: p.id, name: p.name })}
                    >
                      <Trash2 className="size-3.5" />
                    </Button>
                  ) : null}
                </div>
              ))}
              {!c.products.length ? <p className="text-sm text-muted-foreground">No products</p> : null}
            </CardContent>
          </Card>
        ))}
      </div>

      <AlertDialog open={deleteTarget != null} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              Remove {deleteTarget?.kind === "category" ? "category" : "product"} “{deleteTarget?.name}”?
            </AlertDialogTitle>
            <AlertDialogDescription>
              {deleteTarget?.kind === "category"
                ? "This removes the category and its products from the catalogue."
                : "This product will no longer be available to assign on QR codes."}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleteMut.isPending}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              disabled={deleteMut.isPending || !deleteTarget}
              onClick={(e) => {
                e.preventDefault();
                deleteMut.mutate();
              }}
            >
              {deleteMut.isPending ? "Removing…" : "Remove"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
