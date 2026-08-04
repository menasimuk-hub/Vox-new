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
import { toast } from "sonner";

/* ------------------------------------------------------------------ palette */

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
const colorOf = (id: ColorId) => catalogueColors.find((c) => c.id === id) ?? catalogueColors[0];

/* -------------------------------------------------------------------- types */

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
};

type Category = { id: string; name: string; color: ColorId; frozen: boolean };

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

const uid = () => Math.random().toString(36).slice(2, 9);

const seedCategories: Category[] = [
  { id: "c1", name: "Core range", color: "sky", frozen: false },
  { id: "c2", name: "Premium range", color: "lilac", frozen: false },
  { id: "c3", name: "Spare parts", color: "sand", frozen: true },
];

const seedProducts: Product[] = [
  { id: "p1", categoryId: "c1", name: "Master catalogue 2026", description: "Full product line with specs and pricing tiers.", fileName: "catalogue-2026.pdf", fileKind: "pdf", fileSize: "8.2 MB", frozen: false },
  { id: "p2", categoryId: "c1", name: "Core range photo pack", description: "High-res product photography for retail partners.", fileName: "core-photos.png", fileKind: "image", fileSize: "12 MB", frozen: false },
  { id: "p3", categoryId: "c2", name: "Premium price list", description: "Distributor pricing, valid until Q4.", fileName: "premium-prices.xlsx", fileKind: "excel", fileSize: "240 KB", frozen: false },
  { id: "p4", categoryId: "c3", name: "Installation guide", description: "Step-by-step fitting instructions.", fileName: "install-guide.docx", fileKind: "word", fileSize: "1.4 MB", frozen: true },
];

/* ---------------------------------------------------------------- component */

export function CatalogueManager({ eyebrow }: { eyebrow: string }) {
  const [categories, setCategories] = React.useState<Category[]>(seedCategories);
  const [products, setProducts] = React.useState<Product[]>(seedProducts);
  const [active, setActive] = React.useState<string | "all">("all");
  const [query, setQuery] = React.useState("");

  const [catOpen, setCatOpen] = React.useState(false);
  const [catDraft, setCatDraft] = React.useState<Category | null>(null);
  const [prodOpen, setProdOpen] = React.useState(false);
  const [prodDraft, setProdDraft] = React.useState<Product | null>(null);
  const [confirm, setConfirm] = React.useState<{ kind: "category" | "product"; id: string; name: string } | null>(null);

  const visible = products.filter((p) => {
    if (active !== "all" && p.categoryId !== active) return false;
    if (!query.trim()) return true;
    const q = query.toLowerCase();
    return p.name.toLowerCase().includes(q) || p.description.toLowerCase().includes(q);
  });

  const countIn = (id: string) => products.filter((p) => p.categoryId === id).length;

  /* actions */
  const saveCategory = (c: Category) => {
    setCategories((s) => (s.some((x) => x.id === c.id) ? s.map((x) => (x.id === c.id ? c : x)) : [...s, c]));
    setCatOpen(false);
    toast.success(`Category "${c.name}" saved`);
  };
  const saveProduct = (p: Product) => {
    setProducts((s) => (s.some((x) => x.id === p.id) ? s.map((x) => (x.id === p.id ? p : x)) : [...s, p]));
    setProdOpen(false);
    toast.success(`Product "${p.name}" saved`);
  };
  const doDelete = () => {
    if (!confirm) return;
    if (confirm.kind === "category") {
      setCategories((s) => s.filter((c) => c.id !== confirm.id));
      setProducts((s) => s.filter((p) => p.categoryId !== confirm.id));
      if (active === confirm.id) setActive("all");
    } else {
      setProducts((s) => s.filter((p) => p.id !== confirm.id));
    }
    toast.success(`"${confirm.name}" deleted`);
    setConfirm(null);
  };

  return (
    <div className="relative flex w-full flex-col gap-6">
      <PageHeader
        eyebrow={eyebrow}
        title="Add catalogues"
        description="Group everything you send to prospects into colour-coded categories, then drop in the files — Excel, Word, PDF or images."
        actions={
          <div className="flex gap-2">
            <Button
              variant="outline"
              className="group gap-1.5"
              onClick={() => { setCatDraft({ id: uid(), name: "", color: "sky", frozen: false }); setCatOpen(true); }}
            >
              <Layers className="size-4 transition-transform duration-300 group-hover:-rotate-12" />
              New category
            </Button>
            <Button
              className="group gap-1.5"
              disabled={categories.length === 0}
              onClick={() => {
                setProdDraft({ id: uid(), categoryId: active !== "all" ? active : categories[0].id, name: "", description: "", fileName: "", fileKind: "other", fileSize: "", frozen: false });
                setProdOpen(true);
              }}
            >
              <Plus className="size-4 transition-transform duration-300 group-hover:rotate-90" />
              Add product
            </Button>
          </div>
        }
      />

      {/* stats */}
      <div className="grid gap-3 sm:grid-cols-3">
        <StatTile Icon={Layers} label="Categories" value={categories.length} />
        <StatTile Icon={Package} label="Products" value={products.length} />
        <StatTile Icon={Snowflake} label="Frozen items" value={categories.filter((c) => c.frozen).length + products.filter((p) => p.frozen).length} />
      </div>

      {/* categories */}
      <Card className="relative overflow-hidden">
        <CardContent className="p-4">
          <div className="mb-3 flex items-center justify-between">
            <p className="flex items-center gap-2 text-sm font-semibold"><FolderOpen className="size-4 text-primary" /> Categories</p>
            <div className="relative w-52">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search products" className="h-8 pl-8 text-xs" />
            </div>
          </div>

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
                    <IconAction title={c.frozen ? "Unfreeze" : "Freeze"} onClick={() => setCategories((s) => s.map((x) => (x.id === c.id ? { ...x, frozen: !x.frozen } : x)))}>
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
              onClick={() => { setCatDraft({ id: uid(), name: "", color: "sky", frozen: false }); setCatOpen(true); }}
              className="group flex items-center gap-1.5 rounded-full border border-dashed border-border px-3 py-1.5 text-xs font-medium text-muted-foreground transition-all duration-200 hover:-translate-y-0.5 hover:border-primary hover:text-primary"
            >
              <Plus className="size-3.5 transition-transform duration-300 group-hover:rotate-90" /> Add
            </button>
          </div>
        </CardContent>
      </Card>

      {/* products */}
      {visible.length === 0 ? (
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
                      <IconAction title={p.frozen ? "Unfreeze" : "Freeze"} onClick={() => setProducts((s) => s.map((x) => (x.id === p.id ? { ...x, frozen: !x.frozen } : x)))}>
                        {p.frozen ? <Play className="size-3.5" /> : <Snowflake className="size-3.5" />}
                      </IconAction>
                      <IconAction title="Edit" onClick={() => { setProdDraft(p); setProdOpen(true); }}><Pencil className="size-3.5" /></IconAction>
                      <IconAction title="Delete" onClick={() => setConfirm({ kind: "product", id: p.id, name: p.name })}><Trash2 className="size-3.5" /></IconAction>
                    </span>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      <CategoryDialog open={catOpen} onOpenChange={setCatOpen} draft={catDraft} onSave={saveCategory} />
      <ProductDialog open={prodOpen} onOpenChange={setProdOpen} draft={prodDraft} categories={categories} onSave={saveProduct} />

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
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={doDelete}>Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

/* ------------------------------------------------------------------- pieces */

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
  open, onOpenChange, draft, onSave,
}: { open: boolean; onOpenChange: (v: boolean) => void; draft: Category | null; onSave: (c: Category) => void }) {
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
          <DialogTitle>{draft?.name ? "Edit category" : "New category"}</DialogTitle>
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
          <Button disabled={!name.trim()} onClick={() => draft && onSave({ ...draft, name: name.trim(), color, frozen })}>Save category</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ProductDialog({
  open, onOpenChange, draft, categories, onSave,
}: {
  open: boolean; onOpenChange: (v: boolean) => void; draft: Product | null;
  categories: Category[]; onSave: (p: Product) => void;
}) {
  const [name, setName] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [categoryId, setCategoryId] = React.useState("");
  const [fileName, setFileName] = React.useState("");
  const [fileSize, setFileSize] = React.useState("");
  const [frozen, setFrozen] = React.useState(false);
  const [drag, setDrag] = React.useState(false);
  const inputRef = React.useRef<HTMLInputElement>(null);

  React.useEffect(() => {
    if (!draft) return;
    setName(draft.name); setDescription(draft.description); setCategoryId(draft.categoryId);
    setFileName(draft.fileName); setFileSize(draft.fileSize); setFrozen(draft.frozen);
  }, [draft]);

  const take = (f: File | undefined) => {
    if (!f) return;
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
          <DialogTitle>{draft?.name ? "Edit product" : "Add product"}</DialogTitle>
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
                <p className="text-xs text-muted-foreground">{fileName ? `${kindMeta[kind].label}${fileSize ? ` · ${fileSize}` : ""}` : "XLSX, DOCX, PDF, PNG, JPEG"}</p>
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
            disabled={!name.trim() || !categoryId}
            onClick={() => draft && onSave({ ...draft, name: name.trim(), description: description.trim(), categoryId, fileName, fileKind: kindOf(fileName), fileSize, frozen })}
          >
            Save product
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
