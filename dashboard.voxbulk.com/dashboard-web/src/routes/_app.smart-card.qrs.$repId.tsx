import { createFileRoute, Link } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Package } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import {
  emptyRepresentativeForm,
  RepresentativeFields,
  socialLinksPayload,
  type RepresentativeFormValue,
  type SocialLinks,
} from "@/components/smart-card/representative-fields";
import { SmartCardThemePicker } from "@/components/smart-card/smart-card-theme-picker";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { apiFetch, buildAuthHeaders, getApiBaseUrl } from "@/lib/api";
import { canManageTeam, normalizeOrgRole } from "@/lib/org-roles";
import { useSession } from "@/lib/session";
import {
  normalizeSmartCardThemeId,
  type SmartCardThemeId,
} from "@/lib/smart-card-themes";

type Rep = {
  id: string;
  name: string;
  email?: string | null;
  mobile?: string | null;
  landline?: string | null;
  extension?: string | null;
  website?: string | null;
  social_links?: SocialLinks | null;
  extra?: { job_title?: string; title?: string; role?: string } | null;
  photo_url?: string | null;
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

type CompanyPayload = {
  ok: boolean;
  company: {
    name?: string;
    theme_id?: string;
    brand_defaults?: { theme_id?: string } | null;
  };
};

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
  const [themeId, setThemeId] = React.useState<SmartCardThemeId>("smartcard");
  const [photoFile, setPhotoFile] = React.useState<File | null>(null);
  const [photoLocalPreview, setPhotoLocalPreview] = React.useState<string | null>(null);
  const [photoUploading, setPhotoUploading] = React.useState(false);
  const [remotePhotoSrc, setRemotePhotoSrc] = React.useState<string | null>(null);

  const repQ = useQuery({
    queryKey: ["smart-card", "rep", repId],
    queryFn: () => apiFetch<{ ok: boolean; item: Rep }>(`/smart-card/representatives/${repId}`),
  });

  const companyQ = useQuery({
    queryKey: ["smart-card", "company"],
    queryFn: () => apiFetch<CompanyPayload>("/smart-card/company"),
  });

  const catalogueQ = useQuery({
    queryKey: ["smart-card", "catalogue"],
    queryFn: () => apiFetch<{ ok: boolean; categories: Category[] }>("/smart-card/catalogue"),
  });

  React.useEffect(() => {
    if (!photoFile) {
      setPhotoLocalPreview(null);
      return;
    }
    const url = URL.createObjectURL(photoFile);
    setPhotoLocalPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [photoFile]);

  React.useEffect(() => {
    let revoked: string | null = null;
    let cancelled = false;
    setRemotePhotoSrc(null);
    const path = repQ.data?.item?.photo_url;
    if (!path || photoFile) return;
    (async () => {
      try {
        const base = getApiBaseUrl().replace(/\/+$/, "");
        const res = await fetch(`${base}${path}`, { headers: buildAuthHeaders() });
        if (!res.ok) return;
        const blob = await res.blob();
        if (cancelled) return;
        const url = URL.createObjectURL(blob);
        revoked = url;
        setRemotePhotoSrc(url);
      } catch {
        /* ignore */
      }
    })();
    return () => {
      cancelled = true;
      if (revoked) URL.revokeObjectURL(revoked);
    };
  }, [repQ.data?.item?.photo_url, photoFile]);

  React.useEffect(() => {
    const r = repQ.data?.item;
    if (!r) return;
    const social = r.social_links || {};
    const extra = r.extra || {};
    setRepForm({
      name: r.name || "",
      job_title: String(extra.job_title || extra.title || extra.role || ""),
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

  React.useEffect(() => {
    const c = companyQ.data?.company;
    if (!c) return;
    setThemeId(normalizeSmartCardThemeId(c.theme_id ?? c.brand_defaults?.theme_id));
  }, [companyQ.data]);

  const categories = catalogueQ.data?.categories || [];
  const products = React.useMemo(() => {
    const out: Product[] = [];
    for (const cat of categories) {
      for (const p of cat.products || []) out.push(p);
    }
    return out;
  }, [categories]);

  const companyName = companyQ.data?.company?.name || "";

  const saveMut = useMutation({
    mutationFn: async () => {
      await apiFetch(`/smart-card/representatives/${repId}`, {
        method: "PATCH",
        body: JSON.stringify({
          name: repForm.name.trim(),
          email: repForm.email.trim() || null,
          mobile: repForm.mobile.trim() || null,
          landline: repForm.landline.trim() || null,
          extension: repForm.extension.trim() || null,
          website: repForm.website.trim() || null,
          social_links: socialLinksPayload(repForm.social_links),
          extra: {
            ...(repQ.data?.item?.extra || {}),
            job_title: repForm.job_title.trim() || null,
          },
          product_ids: productIds,
          qr_fg_color: fg,
          qr_bg_color: bg,
          qr_transparent: transparent,
        }),
      });
      await apiFetch("/smart-card/company", {
        method: "PATCH",
        body: JSON.stringify({ theme_id: themeId }),
      });
      if (photoFile) {
        setPhotoUploading(true);
        try {
          const form = new FormData();
          form.append("file", photoFile);
          const base = getApiBaseUrl().replace(/\/+$/, "");
          const res = await fetch(`${base}/smart-card/representatives/${repId}/photo`, {
            method: "POST",
            headers: buildAuthHeaders(),
            body: form,
          });
          if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(typeof err?.detail === "string" ? err.detail : "Photo upload failed");
          }
          setPhotoFile(null);
        } finally {
          setPhotoUploading(false);
        }
      }
    },
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
    <div className="space-y-6">
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

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(280px,380px)] lg:items-start">
        <div className="min-w-0 space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Representative</CardTitle>
            </CardHeader>
            <CardContent>
              <RepresentativeFields
                value={repForm}
                onChange={setRepForm}
                disabled={!canEdit || saveMut.isPending || photoUploading}
                photoPreviewUrl={photoLocalPreview || remotePhotoSrc}
                photoFileName={photoFile?.name}
                onPhotoChange={setPhotoFile}
              />
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
                <Package className="size-4" /> Assign products
              </CardTitle>
              <CardDescription>
                Tick products for this representative. Add or remove catalogue items under{" "}
                <Link to="/smart-card/catalogue" className="text-primary underline">
                  Add catalogues
                </Link>{" "}
                or reopen Create setup.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {products.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No catalogue products yet.{" "}
                  {canEdit ? (
                    <Link to="/smart-card/catalogue" className="text-primary underline">
                      Add catalogues
                    </Link>
                  ) : null}
                </p>
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

        <div className="space-y-4 lg:sticky lg:top-4">
          <Card>
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

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Digital card theme</CardTitle>
              <CardDescription>Applies to all Smart Card scans for this company.</CardDescription>
            </CardHeader>
            <CardContent>
              <SmartCardThemePicker
                value={themeId}
                onChange={setThemeId}
                companyName={companyName}
                personName={repForm.name || rep.name}
                className="sm:grid-cols-1 lg:grid-cols-1 xl:grid-cols-1"
              />
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
