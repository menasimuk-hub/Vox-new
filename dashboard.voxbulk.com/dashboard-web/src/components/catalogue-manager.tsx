import * as React from "react";
import {
  Plus, Pencil, Trash2, Snowflake, Play, FolderOpen, FileText, FileSpreadsheet,
  FileImage, File as FileIcon, UploadCloud, Search, Package, Layers,
} from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { apiFetch, apiUploadFiles } from "@/lib/api";
import { toast } from "sonner";

export const catalogueColors = [
  { id: "sky", label: "Sky", chip: "bg-sky-100 dark:bg-sky-500/20", text: "text-sky-700 dark:text-sky-300", ring: "ring-sky-400/50", dot: "bg-sky-400" },
  { id: "mint", label: "Mint", chip: "bg-emerald-100 dark:bg-emerald-500/20", text: "text-emerald-700 dark:text-emerald-300", ring: "ring-emerald-400/50", dot: "bg-emerald-400" },
  { id: "sand", label: "Sand", chip: "bg-amber-100 dark:bg-amber-500/20", text: "text-amber-700 dark:text-amber-300", ring: "ring-amber-400/50", dot: "bg-amber-400" },
  { id: "rose", label: "Rose", chip: "bg-rose-100 dark:bg-rose-500/20", text: "text-rose-700 dark:text-rose-300", ring: "ring-rose-400/50", dot: "bg-rose-400" },
  { id: "lilac", label: "Lilac", chip: "bg-violet-100 dark:bg-violet-500/20", text: "text-violet-700 dark:text-violet-300", ring: "ring-violet-400/50", dot: "bg-violet-400" },
  { id: "peach", label: "Peach", chip: "bg-orange-100 dark:bg-orange-500/20", text: "text-orange-700 dark:text-orange-300", ring: "ring-orange-400/50", dot: "bg-orange-400" },
  { id: "aqua", label: "Aqua", chip: "bg-teal-100 dark:bg-teal-500/20", text: "text-teal-700 dark:text-teal-300", ring: "ring-teal-400/50", dot: "bg-teal-400" },
  { id: "slate", label: "Slate", chip: "bg-slate-100 dark:bg-slate-500/20", text: "text-slate-700 dark:text-slate-300", ring: "ring-slate-400/50", dot: "bg-slate-400" },
] as const;

type ColorId = (typeof catalogueColors)[number]["id"];
const colorOf = (id: string) => catalogueColors.find((c) => c.id === id) ?? catalogueColors[0];

type FileKind = "excel" | "word" | "pdf" | "image" | "other";

type Product = {
  id: string;
  categoryId: string;
  name: string;
  description: string;
  fileName: string;
  fileKind: FileKind;
  fileSize: string;
  frozen: boolean;
  assetId?: string | null;
  isNew?: boolean;
  pendingFile?: File | null;
};

type Category = { id: string; name: string; color: ColorId; frozen: boolean; isNew?: boolean };

const kindOf = (name: string): FileKind => {
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  if (["xls", "xlsx", "csv"].includes(ext)) return "excel";
  if (["doc", "docx"].includes(ext)) return "word";
  if (ext === "pdf") return "pdf";
  if (["png", "jpg", "jpeg", "webp", "gif"].includes(ext)) return "image";
  return "other";
};

const kindMeta: Record<FileKind, { Icon: typeof FileText; tone: string; label: string }> = {
  excel: { Icon: FileSpreadsheet, tone: "text-emerald-600 dark:text-emerald-400", label: "Excel" },
  word: { Icon: FileText, tone: "text-sky-600 dark:text-sky-400", label: "Word" },
  pdf: { Icon: FileText, tone: "text-rose-600 dark:text-rose-400", label: "PDF" },
  image: { Icon: FileImage, tone: "text-violet-600 dark:text-violet-400", label: "Image" },
  other: { Icon: FileIcon, tone: "text-muted-foreground", label: "File" },
};

const prettySize = (bytes: number) =>
  bytes > 1_048_576 ? `${(bytes / 1_048_576).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;

const uid = () => `tmp-${Math.random().toString(36).slice(2, 9)}`;

type ApiCategory = {
  id: string;
  name: string;
  accent_color?: string;
  color?: string;
  is_frozen?: boolean;
  frozen?: boolean;
  products?: Array<{
    id: string;
    category_id: string;
    name: string;
    short_description?: string | null;
    description?: string | null;
    is_frozen?: boolean;
    frozen?: boolean;
    assets?: Array<{
      id: string;
      title?: string;
      kind?: string;
      original_filename?: string | null;
      file_size_bytes?: number | null;
    }>;
  }>;
};

function mapTree(categories: ApiCategory[]): { cats: Category[]; products: Product[] } {
  const cats: Category[] = [];
  const products: Product[] = [];
  for (const c of categories) {
    const color = (c.accent_color || c.color || "sky") as ColorId;
    cats.push({
      id: c.id,
      name: c.name,
      color: catalogueColors.some((x) => x.id === color) ? color : "sky",
      frozen: Boolean(c.is_frozen ?? c.frozen),
    });
    for (const p of c.products || []) {
      const asset = (p.assets || [])[0];
      const fileName = asset?.original_filename || asset?.title || "";
      products.push({
        id: p.id,
        categoryId: p.category_id || c.id,
        name: p.name,
        description: p.short_description || p.description || "",
        fileName,
        fileKind: kindOf(fileName || asset?.kind || ""),
        fileSize: asset?.file_size_bytes != null ? prettySize(Number(asset.file_size_bytes)) : "",
        frozen: Boolean(p.is_frozen ?? p.frozen),
        assetId: asset?.id || null,
      });
    }
  }
  return { cats, products };
}

export function CatalogueManager({
  eyebrow,
  apiBase,
}: {
  eyebrow: string;
  apiBase: "/smart-card/catalogue" | "/expo/catalogue";
}) {
  const [categories, setCategories] = React.useState<Category[]>([]);
  const [products, setProducts] = React.useState<Product[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [busy, setBusy] = React.useState(false);
  const [active, setActive] = React.useState<string | "all">("all");
  const [query, setQuery] = React.useState("");

  const [catOpen, setCatOpen] = React.useState(false);
  const [catDraft, setCatDraft] = React.useState<Category | null>(null);
  const [prodOpen, setProdOpen] = React.useState(false);
  const [prodDraft, setProdDraft] = React.useState<Product | null>(null);
  const [confirm, setConfirm] = React.useState<{ kind: "category" | "product"; id: string; name: string } | null>(null);

  const reload = React.useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiFetch<{ categories?: ApiCategory[] }>(apiBase);
      const mapped = mapTree(res.categories || []);
      setCategories(mapped.cats);
      setProducts(mapped.products);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not load catalogues");
    } finally {
      setLoading(false);
    }
  }, [apiBase]);

  React.useEffect(() => {
    void reload();
  }, [reload]);

  const visible = products.filter((p) => {
    if (active !== "all" && p.categoryId !== active) return false;
    if (!query.trim()) return true;
    const q = query.toLowerCase();
    return p.name.toLowerCase().includes(q) || p.description.toLowerCase().includes(q);
  });

  const countIn = (id: string) => products.filter((p) => p.categoryId === id).length;

  const saveCategory = async (c: Category) => {
    setBusy(true);
    try {
      if (c.isNew || c.id.startsWith("tmp-")) {
        await apiFetch(`${apiBase}/categories`, {
          method: "POST",
          body: JSON.stringify({ name: c.name, accent_color: c.color, color: c.color, is_frozen: c.frozen, frozen: c.frozen }),
        });
      } else {
        await apiFetch(`${apiBase}/categories/${c.id}`, {
          method: "PATCH",
          body: JSON.stringify({ name: c.name, accent_color: c.color, color: c.color, is_frozen: c.frozen, frozen: c.frozen }),
        });
      }
      setCatOpen(false);
      toast.success(`Category "${c.name}" saved`);
      await reload();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not save category");
    } finally {
      setBusy(false);
    }
  };

  const saveProduct = async (p: Product) => {
    setBusy(true);
    try {
      let productId = p.id;
      const body = {
        name: p.name,
        category_id: p.categoryId,
        short_description: p.description,
        description: p.description,
        is_frozen: p.frozen,
        frozen: p.frozen,
      };
      if (p.isNew || p.id.startsWith("tmp-")) {
        const res = await apiFetch<{ item: { id: string } }>(`${apiBase}/products`, {
          method: "POST",
          body: JSON.stringify(body),
        });
        productId = res.item.id;
      } else {
        await apiFetch(`${apiBase}/products/${p.id}`, {
          method: "PATCH",
          body: JSON.stringify(body),
        });
      }

      if (p.pendingFile) {
        const uploaded = await apiUploadFiles(`${apiBase}/assets/upload`, [p.pendingFile], "file");
        const item = (uploaded as { item?: Record<string, unknown> })?.item || {};
        if (p.assetId) {
          await apiFetch(`${apiBase}/assets/${p.assetId}`, { method: "DELETE" }).catch(() => undefined);
        }
        await apiFetch(`${apiBase}/assets`, {
          method: "POST",
          body: JSON.stringify({
            product_id: productId,
            title: p.name || p.pendingFile.name,
            kind: kindOf(p.pendingFile.name) === "image" ? "image" : "pdf",
            purpose: "catalogue",
            storage_path: item.storage_path,
            original_filename: p.pendingFile.name,
            file_size_bytes: p.pendingFile.size,
          }),
        });
      }

      setProdOpen(false);
      toast.success(`Product "${p.name}" saved`);
      await reload();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not save product");
    } finally {
      setBusy(false);
    }
  };

  const doDelete = async () => {
    if (!confirm) return;
    setBusy(true);
    try {
      if (confirm.kind === "category") {
        await apiFetch(`${apiBase}/categories/${confirm.id}`, { method: "DELETE" });
        if (active === confirm.id) setActive("all");
      } else {
        await apiFetch(`${apiBase}/products/${confirm.id}`, { method: "DELETE" });
      }
      toast.success(`"${confirm.name}" deleted`);
      setConfirm(null);
      await reload();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not delete");
    } finally {
      setBusy(false);
    }
  };

  const toggleCategoryFrozen = async (c: Category) => {
    try {
      await apiFetch(`${apiBase}/categories/${c.id}`, {
        method: "PATCH",
        body: JSON.stringify({ is_frozen: !c.frozen, frozen: !c.frozen }),
      });
      await reload();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not update category");
    }
  };

  const toggleProductFrozen = async (p: Product) => {
    try {
      await apiFetch(`${apiBase}/products/${p.id}`, {
        method: "PATCH",
        body: JSON.stringify({ is_frozen: !p.frozen, frozen: !p.frozen }),
      });
      await reload();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not update product");
    }
  };

  return (
    <div className="relative flex w-full flex-col gap-6">
      <PageHeader
        eyebrow={eyebrow}
        title="Add catalogues"
        description="Group everything you send to prospects into colour-coded categories, then drop in the files — Excel, Word, PDF or images. Changes are saved to your account."
        actions={
          <div className="flex gap-2">
            <Button
              variant="outline"
              className="group gap-1.5"
              disabled={busy}
              onClick={() => { setCatDraft({ id: uid(), name: "", color: "sky", frozen: false, isNew: true }); setCatOpen(true); }}
            >
              <Layers className="size-4 transition-transform duration-300 group-hover:-rotate-12" />
              New category
            </Button>
            <Button
              className="group gap-1.5"
              disabled={busy || categories.length === 0}
              onClick={() => {
                setProdDraft({
                  id: uid(),
                  categoryId: active !== "all" ? active : categories[0].id,
                  name: "",
                  description: "",
                  fileName: "",
                  fileKind: "other",
                  fileSize: "",
                  frozen: false,
                  isNew: true,
                  pendingFile: null,
                });
                setProdOpen(true);
              }}
            >
              <Plus className="size-4 transition-transform duration-300 group-hover:rotate-90" />
              Add product
            </Button>
          </div>
        }
      />

      <div className="grid gap-3 sm:grid-cols-3">
        <StatTile Icon={Layers} label="Categories" value={loading ? 0 : categories.length} />
        <StatTile Icon={Package} label="Products" value={loading ? 0 : products.length} />
        <StatTile Icon={Snowflake} label="Frozen items" value={categories.filter((c) => c.frozen).length + products.filter((p) => p.frozen).length} />
      </div>

      <Card className="relative overflow-hidden">
        <CardContent className="p-4">
          <div className="mb-3 flex items-center justify-between">
            <p className="flex items-center gap-2 text-sm font-semibold"><FolderOpen className="size-4 text-primary" /> Categories</p>
            <div className="relative w-52">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search products" className="h-8 pl-8 text-xs" />
            </div>
          </div>

          {loading ? (
            <p className="py-6 text-center text-sm text-muted-foreground">Loading catalogues…</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => setActive("all")}
                className={`rounded-full border px-3 py-1.5 text-xs font-medium transition-all duration-200 hover:-translate-y-0.5 ${active === "all" ? "border-primary bg-primary text-primary-foreground shadow-sm" : "border-border bg-background text-muted-foreground hover:text-foreground"}`}
              >
                All · {products.length}
              </button>

              {categories.map((c) => {
                const col = colorOf(c.color);
                const on = active === c.id;
                return (
                  <div
                    key={c.id}
                    className={`group flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium transition-all duration-200 hover:-translate-y-0.5 hover:shadow-sm ${col.chip} ${col.text} ${on ? `ring-2 ${col.ring} border-transparent` : "border-transparent"} ${c.frozen ? "opacity-60" : ""}`}
                  >
                    <button type="button" onClick={() => setActive(c.id)} className="flex items-center gap-1.5">
                      <span className={`size-2 rounded-full ${col.dot} ${on ? "animate-pulse" : ""}`} />
                      {c.name}
                      <span className="opacity-70">· {countIn(c.id)}</span>
                      {c.frozen && <Snowflake className="size-3" />}
                    </button>
                    <span className="flex items-center gap-0.5 opacity-0 transition-opacity duration-200 group-hover:opacity-100">
                      <IconAction title={c.frozen ? "Unfreeze" : "Freeze"} onClick={() => void toggleCategoryFrozen(c)}>
                        {c.frozen ? <Play className="size-3" /> : <Snowflake className="size-3" />}
                      </IconAction>
                      <IconAction title="Edit" onClick={() => { setCatDraft(c); setCatOpen(true); }}><Pencil className="size-3" /></IconAction>
                      <IconAction title="Delete" onClick={() => setConfirm({ kind: "category", id: c.id, name: c.name })}><Trash2 className="size-3" /></IconAction>
                    </span>
                  </div>
                );
              })}

              <button
                type="button"
                onClick={() => { setCatDraft({ id: uid(), name: "", color: "sky", frozen: false, isNew: true }); setCatOpen(true); }}
                className="group flex items-center gap-1.5 rounded-full border border-dashed border-border px-3 py-1.5 text-xs font-medium text-muted-foreground transition-all duration-200 hover:-translate-y-0.5 hover:border-primary hover:text-primary"
              >
                <Plus className="size-3.5 transition-transform duration-300 group-hover:rotate-90" /> Add
              </button>
            </div>
          )}
        </CardContent>
      </Card>

      {!loading && visible.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="flex flex-col items-center gap-2 p-10 text-center">
            <UploadCloud className="size-8 animate-bounce text-muted-foreground/60" />
            <p className="text-sm font-medium">No products here yet</p>
            <p className="text-xs text-muted-foreground">Add a product and attach an Excel, Word, PDF or image file.</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {visible.map((p) => {
            const cat = categories.find((c) => c.id === p.categoryId);
            const col = colorOf(cat?.color ?? "sky");
            const meta = kindMeta[p.fileKind];
            return (
              <Card
                key={p.id}
                className={`group relative overflow-hidden transition-all duration-300 hover:-translate-y-1 hover:shadow-lg ${p.frozen ? "opacity-60" : ""}`}
              >
                <span className={`absolute inset-x-0 top-0 h-1 ${col.dot}`} />
                <CardContent className="space-y-2.5 p-4">
                  <div className="flex items-start gap-3">
                    <div className={`grid size-10 shrink-0 place-items-center rounded-xl ${col.chip} transition-transform duration-300 group-hover:scale-110 group-hover:-rotate-6`}>
                      <meta.Icon className={`size-5 ${meta.tone}`} />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-semibold">{p.name}</p>
                      <p className="line-clamp-2 text-xs text-muted-foreground">{p.description || "No description"}</p>
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center gap-1.5">
                    {cat && <Badge variant="outline" className={`border-transparent ${col.chip} ${col.text}`}>{cat.name}</Badge>}
                    <Badge variant="outline" className="text-[10px]">{meta.label}</Badge>
                    {p.fileSize && <span className="text-[10px] text-muted-foreground">{p.fileSize}</span>}
                    {p.frozen && <Badge variant="outline" className="gap-1 text-[10px]"><Snowflake className="size-3" /> Frozen</Badge>}
                  </div>

                  <div className="flex items-center justify-between border-t border-border pt-2">
                    <span className="truncate text-[11px] text-muted-foreground">{p.fileName || "No file attached"}</span>
                    <span className="flex items-center gap-1 opacity-0 transition-opacity duration-200 group-hover:opacity-100">
                      <IconAction title={p.frozen ? "Unfreeze" : "Freeze"} onClick={() => void toggleProductFrozen(p)}>
                        {p.frozen ? <Play className="size-3.5" /> : <Snowflake className="size-3.5" />}
                      </IconAction>
                      <IconAction title="Edit" onClick={() => { setProdDraft({ ...p, pendingFile: null }); setProdOpen(true); }}><Pencil className="size-3.5" /></IconAction>
                      <IconAction title="Delete" onClick={() => setConfirm({ kind: "product", id: p.id, name: p.name })}><Trash2 className="size-3.5" /></IconAction>
                    </span>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      <CategoryDialog open={catOpen} onOpenChange={setCatOpen} draft={catDraft} busy={busy} onSave={(c) => void saveCategory(c)} />
      <ProductDialog open={prodOpen} onOpenChange={setProdOpen} draft={prodDraft} categories={categories} busy={busy} onSave={(p) => void saveProduct(p)} />

      <AlertDialog open={!!confirm} onOpenChange={(o) => !o && setConfirm(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete "{confirm?.name}"?</AlertDialogTitle>
            <AlertDialogDescription>
              {confirm?.kind === "category"
                ? "This also removes every product inside this category. This can't be undone."
                : "This removes the product and its attached file. This can't be undone."}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={busy}>Cancel</AlertDialogCancel>
            <AlertDialogAction disabled={busy} onClick={() => void doDelete()}>Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function StatTile({ Icon, label, value }: { Icon: typeof Layers; label: string; value: number }) {
  return (
    <Card className="group transition-all duration-300 hover:-translate-y-0.5 hover:shadow-md">
      <CardContent className="flex items-center gap-3 p-4">
        <div className="grid size-10 place-items-center rounded-xl bg-primary/10 text-primary transition-transform duration-300 group-hover:scale-110">
          <Icon className="size-5" />
        </div>
        <div>
          <p className="text-xl font-semibold tabular-nums">{value}</p>
          <p className="text-xs text-muted-foreground">{label}</p>
        </div>
      </CardContent>
    </Card>
  );
}

function IconAction({ title, onClick, children }: { title: string; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      title={title}
      aria-label={title}
      onClick={onClick}
      className="grid size-6 place-items-center rounded-md text-muted-foreground transition-all duration-200 hover:scale-110 hover:bg-accent hover:text-foreground"
    >
      {children}
    </button>
  );
}

function CategoryDialog({
  open, onOpenChange, draft, onSave, busy,
}: { open: boolean; onOpenChange: (v: boolean) => void; draft: Category | null; onSave: (c: Category) => void; busy?: boolean }) {
  const [name, setName] = React.useState("");
  const [color, setColor] = React.useState<ColorId>("sky");
  const [frozen, setFrozen] = React.useState(false);

  React.useEffect(() => {
    if (!draft) return;
    setName(draft.name); setColor(draft.color); setFrozen(draft.frozen);
  }, [draft]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{draft && !draft.isNew && draft.name ? "Edit category" : "New category"}</DialogTitle>
          <DialogDescription>Pick a light background colour so products are easy to scan.</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="cat-name">Category name</Label>
            <Input id="cat-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Premium range" />
          </div>

          <div className="space-y-1.5">
            <Label>Background colour</Label>
            <div className="flex flex-wrap gap-2">
              {catalogueColors.map((c) => (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => setColor(c.id)}
                  title={c.label}
                  aria-label={c.label}
                  className={`size-8 rounded-lg transition-all duration-200 hover:scale-110 ${c.chip} ${color === c.id ? `ring-2 ring-offset-2 ring-offset-background ${c.ring} scale-110` : ""}`}
                />
              ))}
            </div>
          </div>

          <div className="flex items-center justify-between rounded-lg border border-border p-3">
            <div>
              <p className="text-sm font-medium">Frozen</p>
              <p className="text-xs text-muted-foreground">Hidden from prospects, kept in your library.</p>
            </div>
            <Switch checked={frozen} onCheckedChange={setFrozen} />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button disabled={busy || !name.trim()} onClick={() => draft && onSave({ ...draft, name: name.trim(), color, frozen })}>
            {busy ? "Saving…" : "Save category"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ProductDialog({
  open, onOpenChange, draft, categories, onSave, busy,
}: {
  open: boolean; onOpenChange: (v: boolean) => void; draft: Product | null;
  categories: Category[]; onSave: (p: Product) => void; busy?: boolean;
}) {
  const [name, setName] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [categoryId, setCategoryId] = React.useState("");
  const [fileName, setFileName] = React.useState("");
  const [fileSize, setFileSize] = React.useState("");
  const [pendingFile, setPendingFile] = React.useState<File | null>(null);
  const [frozen, setFrozen] = React.useState(false);
  const [drag, setDrag] = React.useState(false);
  const inputRef = React.useRef<HTMLInputElement>(null);

  React.useEffect(() => {
    if (!draft) return;
    setName(draft.name); setDescription(draft.description); setCategoryId(draft.categoryId);
    setFileName(draft.fileName); setFileSize(draft.fileSize); setFrozen(draft.frozen);
    setPendingFile(null);
  }, [draft]);

  const take = (f: File | undefined) => {
    if (!f) return;
    setPendingFile(f);
    setFileName(f.name);
    setFileSize(prettySize(f.size));
    if (!name.trim()) setName(f.name.replace(/\.[^.]+$/, ""));
  };

  const kind = fileName ? kindOf(fileName) : "other";
  const KindIcon = kindMeta[kind].Icon;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{draft && !draft.isNew && draft.name ? "Edit product" : "Add product"}</DialogTitle>
          <DialogDescription>Attach an Excel, Word, PDF, PNG or JPEG file and describe it.</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label>Category</Label>
            <div className="flex flex-wrap gap-2">
              {categories.map((c) => {
                const col = colorOf(c.color);
                return (
                  <button
                    key={c.id}
                    type="button"
                    onClick={() => setCategoryId(c.id)}
                    className={`rounded-full px-3 py-1.5 text-xs font-medium transition-all duration-200 hover:scale-105 ${col.chip} ${col.text} ${categoryId === c.id ? `ring-2 ${col.ring}` : ""}`}
                  >
                    {c.name}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="prod-name">Product name</Label>
            <Input id="prod-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Master catalogue 2026" />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="prod-desc">Description</Label>
            <Textarea id="prod-desc" rows={3} value={description} onChange={(e) => setDescription(e.target.value)} placeholder="What is this file and who is it for?" />
          </div>

          <div className="space-y-1.5">
            <Label>File</Label>
            <div
              onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
              onDragLeave={() => setDrag(false)}
              onDrop={(e) => { e.preventDefault(); setDrag(false); take(e.dataTransfer.files?.[0]); }}
              onClick={() => inputRef.current?.click()}
              className={`flex cursor-pointer items-center gap-3 rounded-xl border border-dashed p-4 transition-all duration-200 ${drag ? "border-primary bg-primary/5 scale-[1.01]" : "border-border hover:border-primary/60 hover:bg-accent/40"}`}
            >
              <div className="grid size-10 place-items-center rounded-lg bg-primary/10 text-primary">
                {fileName ? <KindIcon className="size-5" /> : <UploadCloud className="size-5 animate-pulse" />}
              </div>
              <div className="min-w-0">
                <p className="truncate text-sm font-medium">{fileName || "Drop a file or click to browse"}</p>
                <p className="text-xs text-muted-foreground">{fileName ? `${kindMeta[kind].label}${fileSize ? ` · ${fileSize}` : ""}${pendingFile ? " · new upload" : ""}` : "XLSX, DOCX, PDF, PNG, JPEG"}</p>
              </div>
            </div>
            <input
              ref={inputRef}
              type="file"
              className="hidden"
              accept=".xls,.xlsx,.csv,.doc,.docx,.pdf,.png,.jpg,.jpeg"
              onChange={(e) => take(e.target.files?.[0])}
            />
          </div>

          <div className="flex items-center justify-between rounded-lg border border-border p-3">
            <div>
              <p className="text-sm font-medium">Frozen</p>
              <p className="text-xs text-muted-foreground">Keep it stored but stop sending it to prospects.</p>
            </div>
            <Switch checked={frozen} onCheckedChange={setFrozen} />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button
            disabled={busy || !name.trim() || !categoryId}
            onClick={() => draft && onSave({
              ...draft,
              name: name.trim(),
              description: description.trim(),
              categoryId,
              fileName,
              fileKind: kindOf(fileName),
              fileSize,
              frozen,
              pendingFile,
            })}
          >
            {busy ? "Saving…" : "Save product"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
