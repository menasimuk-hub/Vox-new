import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";
import { toast } from "sonner";

import {
  emptyRepresentativeForm,
  RepresentativeFields,
  socialLinksPayload,
  type RepresentativeFormValue,
} from "@/components/smart-card/representative-fields";
import { QrStyleControls, qrStylePayload, type QrStyleValue } from "@/components/qr-style-controls";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { apiFetch, buildAuthHeaders, getApiBaseUrl } from "@/lib/api";
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

  const [rep, setRep] = React.useState<RepresentativeFormValue>(() => emptyRepresentativeForm());
  const [productIds, setProductIds] = React.useState<string[]>([]);
  const [qrStyle, setQrStyle] = React.useState<QrStyleValue>({
    fg: "000000",
    bg: "ffffff",
    transparent: false,
    moduleStyle: "square",
    cornerStyle: "square",
    showArrow: false,
    frameRound: "none",
  });
  const [photoFile, setPhotoFile] = React.useState<File | null>(null);
  const [photoPreview, setPhotoPreview] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!photoFile) {
      setPhotoPreview(null);
      return;
    }
    const url = URL.createObjectURL(photoFile);
    setPhotoPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [photoFile]);

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
    mutationFn: async () => {
      const res = await apiFetch<{ ok: boolean; item: { id: string } }>("/smart-card/representatives", {
        method: "POST",
        body: JSON.stringify({
          name: rep.name.trim(),
          email: rep.email.trim() || null,
          mobile: rep.mobile.trim() || null,
          landline: rep.landline.trim() || null,
          extension: rep.extension.trim() || null,
          website: rep.website.trim() || null,
          social_links: socialLinksPayload(rep.social_links),
          extra: rep.job_title.trim() ? { job_title: rep.job_title.trim() } : {},
          product_ids: productIds,
          ...qrStylePayload(qrStyle, { includeTransparent: true }),
        }),
      });
      if (photoFile && res.item?.id) {
        const form = new FormData();
        form.append("file", photoFile);
        const base = getApiBaseUrl().replace(/\/+$/, "");
        const up = await fetch(`${base}/smart-card/representatives/${res.item.id}/photo`, {
          method: "POST",
          headers: buildAuthHeaders(),
          body: form,
        });
        if (!up.ok) {
          const err = await up.json().catch(() => ({}));
          throw new Error(typeof err?.detail === "string" ? err.detail : "QR created but photo upload failed");
        }
      }
      return res;
    },
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
    <div className="mx-auto max-w-3xl space-y-6">
      <PageHeader
        eyebrow="Smart Card QR"
        title="Add representative QR"
        description="Create another QR up to your seat package. Assign products to this representative."
        actions={
          <Button asChild variant="outline" size="sm">
            <Link to="/smart-card">Back</Link>
          </Button>
        }
      />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Representative</CardTitle>
          <CardDescription>One QR per representative.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4">
          <RepresentativeFields
            value={rep}
            onChange={setRep}
            photoPreviewUrl={photoPreview}
            photoFileName={photoFile?.name}
            onPhotoChange={setPhotoFile}
          />
          <QrStyleControls value={qrStyle} onChange={setQrStyle} showTransparent />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Assign products</CardTitle>
          <CardDescription>Optional — which catalogue products this representative represents.</CardDescription>
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

      <Button disabled={!rep.name.trim() || createMut.isPending} onClick={() => createMut.mutate()}>
        {createMut.isPending ? "Creating…" : "Create QR"}
      </Button>
    </div>
  );
}
