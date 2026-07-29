import * as React from "react";
import { Building2, Globe, Link2, Mail, Palette, Pencil, Phone, Plus, Trash2, Upload, User, X } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { apiUploadFiles } from "@/lib/api";
import { cn } from "@/lib/utils";

export type AssetPurpose = "catalogue" | "product_sheet" | "price_list" | "product" | "other";

export const PURPOSE_LABELS: Record<AssetPurpose, string> = {
  catalogue: "Catalogue",
  product_sheet: "Product sheet",
  price_list: "Price list",
  product: "Product",
  other: "Other",
};

const PURPOSE_ORDER: AssetPurpose[] = ["catalogue", "product_sheet", "price_list", "other"];

function randomId(prefix: string) {
  return `${prefix}-${Math.random().toString(36).slice(2, 10)}`;
}

/* ------------------------------------------------------------------ */
/* Representatives                                                     */
/* ------------------------------------------------------------------ */

export type RepresentativeDraft = {
  id: string;
  name: string;
  company_name: string;
  email: string;
  mobile: string;
  telephone: string;
  website: string;
};

export function emptyRepresentative(companyName = ""): RepresentativeDraft {
  return {
    id: randomId("rep"),
    name: "",
    company_name: companyName,
    email: "",
    mobile: "",
    telephone: "",
    website: "",
  };
}

export function representativesFromApi(
  items: Array<Record<string, unknown>> | null | undefined,
): RepresentativeDraft[] {
  if (!Array.isArray(items) || items.length === 0) return [];
  // One stand contact only — keep the first if legacy data has more.
  const r = items[0];
  return [
    {
      id: randomId("rep"),
      name: String(r.name || ""),
      company_name: String(r.company_name || ""),
      email: String(r.email || ""),
      mobile: String(r.mobile || ""),
      telephone: String(r.telephone || ""),
      website: String(r.website || ""),
    },
  ];
}

export function representativesToPayload(reps: RepresentativeDraft[]) {
  return reps
    .slice(0, 1)
    .filter((r) => r.name.trim() || r.email.trim() || r.mobile.trim())
    .map((r) => ({
      name: r.name.trim(),
      company_name: r.company_name.trim(),
      email: r.email.trim(),
      mobile: r.mobile.trim(),
      telephone: r.telephone.trim(),
      website: r.website.trim() || undefined,
    }));
}

export function RepresentativesEditor({
  representatives,
  onChange,
  companyWebsite,
  onCompanyWebsiteChange,
  notifyMobile,
  onNotifyMobileChange,
  maxRepresentatives = 1,
}: {
  representatives: RepresentativeDraft[];
  onChange: (next: RepresentativeDraft[]) => void;
  companyWebsite: string;
  onCompanyWebsiteChange: (v: string) => void;
  notifyMobile: string;
  onNotifyMobileChange: (v: string) => void;
  /** Cap stand contacts (default 1). */
  maxRepresentatives?: number;
}) {
  const capped = representatives.slice(0, Math.max(1, maxRepresentatives));
  const updateRep = (id: string, patch: Partial<RepresentativeDraft>) => {
    onChange(capped.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  };
  const firstMobile = capped.find((r) => r.mobile.trim())?.mobile || "";

  return (
    <div className="space-y-4">
      <div className="space-y-3">
        {capped.map((rep) => (
          <div key={rep.id} className="rounded-xl border p-3">
            <div className="mb-2 flex items-center justify-between">
              <p className="text-xs font-medium text-muted-foreground">Representative</p>
            </div>
            <div className="grid gap-2.5 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label className="text-xs">Name</Label>
                <div className="relative">
                  <User className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    className="pl-8"
                    value={rep.name}
                    onChange={(e) => updateRep(rep.id, { name: e.target.value })}
                    placeholder="Jane Smith"
                  />
                </div>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Company name</Label>
                <div className="relative">
                  <Building2 className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    className="pl-8"
                    value={rep.company_name}
                    onChange={(e) => updateRep(rep.id, { company_name: e.target.value })}
                    placeholder="Acme Supplies"
                  />
                </div>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Email</Label>
                <div className="relative">
                  <Mail className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    className="pl-8"
                    type="email"
                    value={rep.email}
                    onChange={(e) => updateRep(rep.id, { email: e.target.value })}
                    placeholder="jane@acme.com"
                  />
                </div>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Mobile</Label>
                <div className="relative">
                  <Phone className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    className="pl-8"
                    value={rep.mobile}
                    onChange={(e) => updateRep(rep.id, { mobile: e.target.value })}
                    placeholder="+44 7700 900123"
                  />
                </div>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Telephone (optional)</Label>
                <div className="relative">
                  <Phone className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    className="pl-8"
                    value={rep.telephone}
                    onChange={(e) => updateRep(rep.id, { telephone: e.target.value })}
                    placeholder="+44 20 7946 0000"
                  />
                </div>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Website (optional)</Label>
                <div className="relative">
                  <Globe className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    className="pl-8"
                    value={rep.website}
                    onChange={(e) => updateRep(rep.id, { website: e.target.value })}
                    placeholder="https://acme.com"
                  />
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="grid gap-4 border-t pt-4 sm:grid-cols-2">
        <div className="space-y-2">
          <Label>Company website (optional)</Label>
          <Input
            value={companyWebsite}
            onChange={(e) => onCompanyWebsiteChange(e.target.value)}
            placeholder="https://acme.com"
          />
        </div>
        <div className="space-y-2">
          <Label>Notify mobile (optional)</Label>
          <Input
            value={notifyMobile}
            onChange={(e) => onNotifyMobileChange(e.target.value)}
            placeholder={firstMobile || "+44 7700 900123"}
          />
          <p className="text-xs text-muted-foreground">
            Gets a WhatsApp alert on hot leads. Defaults to the representative&apos;s mobile if left blank.
          </p>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Categories & products                                               */
/* ------------------------------------------------------------------ */

export type AssetItem = {
  id: string;
  purpose: AssetPurpose;
  title: string;
  source: "link" | "upload";
  external_url: string;
  storage_path: string;
  original_filename: string;
  kind: string;
};

export type ProductDraftForm = {
  name: string;
  short_description: string;
  assets: AssetItem[];
};

export type ProductRow = {
  id: string;
  name: string;
  short_description: string;
  assets: AssetItem[];
};

export type CategoryDraft = {
  id: string;
  name: string;
  accent_color: string;
  products: ProductRow[];
};

export const ACCENT_PALETTE = [
  "#E8F0FE",
  "#FCE8E6",
  "#FEF3E0",
  "#E6F4EA",
  "#F3E8FD",
  "#FFE8F0",
  "#E0F7FA",
  "#F1F0EC",
];

function emptyProductDraft(): ProductDraftForm {
  return { name: "", short_description: "", assets: [] };
}

type AssetComposeState = {
  purpose: AssetPurpose;
  title: string;
  source: "upload" | "link";
  external_url: string;
  storage_path: string;
  original_filename: string;
  kind: string;
};

function emptyAssetCompose(purpose: AssetPurpose = "catalogue"): AssetComposeState {
  return {
    purpose,
    title: "",
    source: "upload",
    external_url: "",
    storage_path: "",
    original_filename: "",
    kind: "pdf",
  };
}

export function newCategory(name = "", accent = ACCENT_PALETTE[0]): CategoryDraft {
  return { id: randomId("cat"), name, accent_color: accent, products: [] };
}

export function categoriesFromApi(
  items:
    | Array<{
        id?: string;
        name?: string;
        accent_color?: string;
        products?: Array<{
          id?: string;
          name?: string;
          short_description?: string | null;
          assets?: Array<{
            id?: string;
            title?: string;
            purpose?: string;
            storage_path?: string | null;
            external_url?: string | null;
            kind?: string;
          }>;
        }>;
      }>
    | null
    | undefined,
): CategoryDraft[] {
  if (!Array.isArray(items)) return [];
  return items.map((c) => ({
    id: c.id || randomId("cat"),
    name: String(c.name || ""),
    accent_color: String(c.accent_color || ACCENT_PALETTE[0]),
    products: (c.products || []).map((p) => ({
      id: p.id || randomId("prod"),
      name: String(p.name || ""),
      short_description: String(p.short_description || ""),
      assets: (p.assets || []).map((a) => ({
        id: a.id || randomId("asset"),
        purpose: (a.purpose as AssetPurpose) || "catalogue",
        title: String(a.title || ""),
        source: a.storage_path ? "upload" : "link",
        external_url: String(a.external_url || ""),
        storage_path: String(a.storage_path || ""),
        original_filename: String(a.title || ""),
        kind: String(a.kind || (a.storage_path ? "pdf" : "link")),
      })),
    })),
  }));
}

export function categoriesToPayload(categories: CategoryDraft[]) {
  return categories
    .filter((c) => c.name.trim())
    .map((c, cIdx) => ({
      name: c.name.trim(),
      accent_color: c.accent_color,
      sort_order: (cIdx + 1) * 10,
      products: c.products.map((p, pIdx) => ({
        name: p.name.trim(),
        short_description: p.short_description.trim() || null,
        sort_order: (pIdx + 1) * 10,
        assets: p.assets.map((a, aIdx) => ({
          title: (a.title || p.name).trim(),
          purpose: a.purpose,
          storage_path: a.source === "upload" ? a.storage_path.trim() || null : null,
          external_url: a.source === "link" ? a.external_url.trim() || null : null,
          kind: a.kind || (a.source === "upload" ? "pdf" : "link"),
          sort_order: (aIdx + 1) * 10,
        })),
      })),
    }));
}

export function categoryLimitHint(
  maxCategories: number | null | undefined,
  packages: Array<{ name: string; max_categories?: number | null }>,
): string {
  if (maxCategories === null) return "This package allows unlimited product categories.";
  if (typeof maxCategories === "number") {
    return `This package allows ${maxCategories === 1 ? "1 category" : `up to ${maxCategories} categories`}.`;
  }
  if (packages.length > 0) {
    const parts = packages.map(
      (p) => `${p.name}: ${p.max_categories == null ? "unlimited" : p.max_categories}`,
    );
    return `Category limit depends on your package (chosen later) — ${parts.join(" · ")}.`;
  }
  return "Category limit depends on the package you choose.";
}

function AccentSwatchPicker({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {ACCENT_PALETTE.map((hex) => (
        <button
          key={hex}
          type="button"
          aria-label={`Colour ${hex}`}
          onClick={() => onChange(hex)}
          className={cn(
            "size-6 rounded-full border-2 transition",
            value.toLowerCase() === hex.toLowerCase()
              ? "border-primary ring-2 ring-primary/30"
              : "border-border/60 hover:border-primary/40",
          )}
          style={{ backgroundColor: hex }}
        />
      ))}
      <label className="relative flex size-6 cursor-pointer items-center justify-center rounded-full border-2 border-dashed border-border/60 text-muted-foreground hover:border-primary/40">
        <Palette className="size-3" />
        <input
          type="color"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="absolute inset-0 size-full cursor-pointer opacity-0"
        />
      </label>
    </div>
  );
}

export function CategoryProductsEditor({
  categories,
  onChange,
  maxCategories,
  packages,
}: {
  categories: CategoryDraft[];
  onChange: (next: CategoryDraft[]) => void;
  maxCategories: number | null | undefined;
  packages: Array<{ name: string; max_categories?: number | null }>;
}) {
  const [newCatName, setNewCatName] = React.useState("");
  const [newCatColor, setNewCatColor] = React.useState(ACCENT_PALETTE[0]);
  const fileInputRef = React.useRef<HTMLInputElement>(null);
  const [uploadTarget, setUploadTarget] = React.useState<string | null>(null);
  const [uploading, setUploading] = React.useState(false);
  const [productDraftByCat, setProductDraftByCat] = React.useState<Record<string, ProductDraftForm>>({});
  const [assetComposeByCat, setAssetComposeByCat] = React.useState<Record<string, AssetComposeState>>({});
  const [editingProductByCat, setEditingProductByCat] = React.useState<Record<string, string | null>>({});

  const atLimit = typeof maxCategories === "number" && categories.length >= maxCategories;
  const hint = categoryLimitHint(maxCategories, packages);

  const draftFor = (catId: string) => productDraftByCat[catId] || emptyProductDraft();
  const composeFor = (catId: string) => assetComposeByCat[catId] || emptyAssetCompose();

  const setDraft = (catId: string, patch: Partial<ProductDraftForm>) => {
    setProductDraftByCat((prev) => ({ ...prev, [catId]: { ...draftFor(catId), ...patch } }));
  };
  const setCompose = (catId: string, patch: Partial<AssetComposeState>) => {
    setAssetComposeByCat((prev) => ({ ...prev, [catId]: { ...composeFor(catId), ...patch } }));
  };

  const addCategory = () => {
    const name = newCatName.trim();
    if (!name) {
      toast.error("Name the category first");
      return;
    }
    if (atLimit) {
      toast.error(hint);
      return;
    }
    onChange([...categories, newCategory(name, newCatColor)]);
    setNewCatName("");
    setNewCatColor(ACCENT_PALETTE[(categories.length + 1) % ACCENT_PALETTE.length]);
  };

  const removeCategory = (id: string) => {
    onChange(categories.filter((c) => c.id !== id));
  };

  const addAssetToCompose = (catId: string) => {
    const compose = composeFor(catId);
    const ready = compose.source === "upload" ? Boolean(compose.storage_path) : Boolean(compose.external_url.trim());
    if (!ready) {
      toast.error("Upload a file or paste a link first");
      return;
    }
    const item: AssetItem = {
      id: randomId("asset"),
      purpose: compose.purpose,
      title: compose.title.trim() || compose.original_filename || PURPOSE_LABELS[compose.purpose],
      source: compose.source,
      external_url: compose.external_url,
      storage_path: compose.storage_path,
      original_filename: compose.original_filename,
      kind: compose.kind,
    };
    setDraft(catId, { assets: [...draftFor(catId).assets, item] });
    const nextPurposeIdx = (PURPOSE_ORDER.indexOf(compose.purpose) + 1) % PURPOSE_ORDER.length;
    setAssetComposeByCat((prev) => ({ ...prev, [catId]: emptyAssetCompose(PURPOSE_ORDER[nextPurposeIdx]) }));
  };

  const removeAssetFromDraft = (catId: string, assetId: string) => {
    setDraft(catId, { assets: draftFor(catId).assets.filter((a) => a.id !== assetId) });
  };

  const saveProduct = (catId: string) => {
    const draft = draftFor(catId);
    if (!draft.name.trim()) {
      toast.error("Give the product a name");
      return;
    }
    const editingId = editingProductByCat[catId] || null;
    onChange(
      categories.map((c) => {
        if (c.id !== catId) return c;
        if (editingId) {
          return {
            ...c,
            products: c.products.map((p) => (p.id === editingId ? { ...p, ...draft } : p)),
          };
        }
        return { ...c, products: [...c.products, { id: randomId("prod"), ...draft }] };
      }),
    );
    setProductDraftByCat((prev) => ({ ...prev, [catId]: emptyProductDraft() }));
    setEditingProductByCat((prev) => ({ ...prev, [catId]: null }));
    toast.success(editingId ? "Product updated" : "Product added");
  };

  const editProduct = (catId: string, product: ProductRow) => {
    setProductDraftByCat((prev) => ({
      ...prev,
      [catId]: { name: product.name, short_description: product.short_description, assets: product.assets },
    }));
    setEditingProductByCat((prev) => ({ ...prev, [catId]: product.id }));
  };

  const cancelEditProduct = (catId: string) => {
    setProductDraftByCat((prev) => ({ ...prev, [catId]: emptyProductDraft() }));
    setEditingProductByCat((prev) => ({ ...prev, [catId]: null }));
  };

  const deleteProduct = (catId: string, productId: string) => {
    onChange(
      categories.map((c) => (c.id === catId ? { ...c, products: c.products.filter((p) => p.id !== productId) } : c)),
    );
  };

  const triggerUpload = (catId: string) => {
    setUploadTarget(catId);
    setCompose(catId, { source: "upload" });
    fileInputRef.current?.click();
  };

  const handleFileChosen = async (file: File) => {
    const catId = uploadTarget;
    if (!catId) return;
    setUploading(true);
    try {
      const res = (await apiUploadFiles("/expo/assets/upload", [file], "file")) as {
        item?: { storage_path?: string; original_filename?: string; kind?: string };
      };
      const item = res?.item || {};
      setCompose(catId, {
        source: "upload",
        storage_path: String(item.storage_path || ""),
        original_filename: String(item.original_filename || file.name),
        kind: String(item.kind || "pdf"),
        title: composeFor(catId).title.trim() || String(item.original_filename || file.name),
        external_url: "",
      });
      toast.success("File uploaded");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  return (
    <div className="space-y-5">
      <input
        ref={fileInputRef}
        type="file"
        className="hidden"
        accept=".pdf,.png,.jpg,.jpeg,.webp,.gif,.xls,.xlsx,.csv,application/pdf,image/*,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) void handleFileChosen(file);
        }}
      />

      <div className="rounded-xl border p-4">
        <p className="text-sm font-medium">Add a category</p>
        <p className="mt-0.5 text-xs text-muted-foreground">{hint}</p>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <Input
            value={newCatName}
            onChange={(e) => setNewCatName(e.target.value)}
            placeholder="e.g. Kitchen appliances"
            className="max-w-xs"
          />
          <AccentSwatchPicker value={newCatColor} onChange={setNewCatColor} />
          <Button type="button" size="sm" onClick={addCategory} disabled={atLimit} className="gap-1.5">
            <Plus className="size-3.5" /> Add category
          </Button>
        </div>
        {atLimit ? (
          <p className="mt-2 text-xs font-medium text-destructive">
            Category limit reached — remove one or choose a bigger package.
          </p>
        ) : null}
      </div>

      {categories.length === 0 ? (
        <p className="rounded-xl border border-dashed p-6 text-center text-sm text-muted-foreground">
          No categories yet — optional. Skip to capture leads only, or add a category to offer catalogues, price
          lists and product sheets.
        </p>
      ) : null}

      {categories.map((cat) => {
        const draft = draftFor(cat.id);
        const compose = composeFor(cat.id);
        const editingId = editingProductByCat[cat.id] || null;
        return (
          <div
            key={cat.id}
            className="rounded-2xl border p-4"
            style={{ backgroundColor: `${cat.accent_color}55` }}
          >
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="size-3 rounded-full border" style={{ backgroundColor: cat.accent_color }} />
                <Input
                  value={cat.name}
                  onChange={(e) =>
                    onChange(categories.map((c) => (c.id === cat.id ? { ...c, name: e.target.value } : c)))
                  }
                  className="h-8 max-w-[220px] bg-background/80 font-medium"
                />
                <AccentSwatchPicker
                  value={cat.accent_color}
                  onChange={(hex) =>
                    onChange(categories.map((c) => (c.id === cat.id ? { ...c, accent_color: hex } : c)))
                  }
                />
              </div>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                className="gap-1.5 text-destructive hover:text-destructive"
                onClick={() => removeCategory(cat.id)}
              >
                <Trash2 className="size-3.5" /> Remove category
              </Button>
            </div>

            {cat.products.length > 0 ? (
              <div className="mb-3 overflow-hidden rounded-lg border bg-background/70">
                <table className="min-w-full text-left text-sm">
                  <thead>
                    <tr className="border-b bg-muted/40 text-[11px] uppercase tracking-wide text-muted-foreground">
                      <th className="px-3 py-2 font-medium">Product</th>
                      <th className="px-3 py-2 font-medium">Files</th>
                      <th className="px-3 py-2 font-medium text-right"> </th>
                    </tr>
                  </thead>
                  <tbody>
                    {cat.products.map((p) => (
                      <tr key={p.id} className="border-t">
                        <td className="px-3 py-2">
                          <p className="font-medium">{p.name}</p>
                          {p.short_description ? (
                            <p className="truncate text-xs text-muted-foreground">{p.short_description}</p>
                          ) : null}
                        </td>
                        <td className="px-3 py-2 text-muted-foreground">
                          {p.assets.length === 0 ? "—" : `${p.assets.length} file${p.assets.length === 1 ? "" : "s"}`}
                        </td>
                        <td className="px-3 py-2 text-right">
                          <div className="flex justify-end gap-1">
                            <Button
                              type="button"
                              size="icon"
                              variant="ghost"
                              aria-label="Edit product"
                              onClick={() => editProduct(cat.id, p)}
                            >
                              <Pencil className="size-3.5" />
                            </Button>
                            <Button
                              type="button"
                              size="icon"
                              variant="ghost"
                              aria-label="Delete product"
                              onClick={() => deleteProduct(cat.id, p.id)}
                            >
                              <Trash2 className="size-3.5" />
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}

            <div className="rounded-lg border bg-background/70 p-3">
              <div className="mb-2 flex items-center justify-between">
                <p className="text-xs font-medium">{editingId ? "Edit product" : "Add a product"}</p>
                {editingId ? (
                  <Button type="button" size="sm" variant="ghost" onClick={() => cancelEditProduct(cat.id)}>
                    <X className="mr-1 size-3.5" /> Cancel
                  </Button>
                ) : null}
              </div>
              <div className="grid gap-2 sm:grid-cols-2">
                <Input
                  value={draft.name}
                  onChange={(e) => setDraft(cat.id, { name: e.target.value })}
                  placeholder="Product name"
                />
                <Input
                  value={draft.short_description}
                  onChange={(e) => setDraft(cat.id, { short_description: e.target.value })}
                  placeholder="Short description (optional)"
                />
              </div>

              {draft.assets.length > 0 ? (
                <ul className="mt-2 space-y-1">
                  {draft.assets.map((a) => (
                    <li
                      key={a.id}
                      className="flex items-center justify-between gap-2 rounded-md border bg-background px-2.5 py-1.5 text-xs"
                    >
                      <span className="truncate">
                        <span className="font-medium">{PURPOSE_LABELS[a.purpose]}</span>
                        {" · "}
                        {a.source === "upload" ? a.original_filename || a.title : a.external_url}
                      </span>
                      <button
                        type="button"
                        aria-label="Remove file"
                        onClick={() => removeAssetFromDraft(cat.id, a.id)}
                        className="text-muted-foreground hover:text-destructive"
                      >
                        <X className="size-3.5" />
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}

              <div className="mt-2 flex flex-wrap items-center gap-2">
                <select
                  className="h-8 rounded-md border border-input bg-background px-2 text-xs shadow-sm"
                  value={compose.purpose}
                  onChange={(e) => setCompose(cat.id, { purpose: e.target.value as AssetPurpose })}
                >
                  <option value="catalogue">Catalogue</option>
                  <option value="product_sheet">Product sheet</option>
                  <option value="price_list">Price list</option>
                  <option value="other">Other</option>
                </select>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={uploading}
                  onClick={() => triggerUpload(cat.id)}
                >
                  <Upload className="mr-1.5 size-3.5" />
                  {uploading && uploadTarget === cat.id
                    ? "Uploading…"
                    : compose.source === "upload" && compose.storage_path
                      ? "Replace file"
                      : "Upload file"}
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => setCompose(cat.id, { source: "link", storage_path: "", original_filename: "" })}
                >
                  <Link2 className="mr-1.5 size-3.5" /> Paste link
                </Button>
                <Button type="button" size="sm" variant="secondary" onClick={() => addAssetToCompose(cat.id)}>
                  <Plus className="mr-1 size-3.5" /> Attach
                </Button>
              </div>
              {compose.source === "link" ? (
                <Input
                  className="mt-2"
                  value={compose.external_url}
                  onChange={(e) => setCompose(cat.id, { external_url: e.target.value })}
                  placeholder="https://…"
                />
              ) : compose.storage_path ? (
                <p className="mt-1.5 text-xs text-muted-foreground">Ready: {compose.original_filename}</p>
              ) : null}

              <Button
                type="button"
                size="sm"
                className="mt-3"
                onClick={() => saveProduct(cat.id)}
              >
                {editingId ? "Save changes" : "Save product"}
              </Button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
