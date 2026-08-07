import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";
import { toast } from "sonner";

import { SmartCardThemePicker } from "@/components/smart-card/smart-card-theme-picker";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch } from "@/lib/api";
import { canManageTeam, normalizeOrgRole } from "@/lib/org-roles";
import { useSession } from "@/lib/session";
import {
  normalizeSmartCardThemeId,
  type SmartCardThemeId,
} from "@/lib/smart-card-themes";

type Company = {
  name: string;
  website?: string | null;
  description?: string | null;
  products_summary?: string | null;
  pricing_notes?: string | null;
  contact_email?: string | null;
  contact_phone?: string | null;
  theme_id?: string | null;
  brand_defaults?: { theme_id?: string } | null;
};

export const Route = createFileRoute("/_app/smart-card/company")({
  component: SmartCardCompanyPage,
});

function SmartCardCompanyPage() {
  const { session } = useSession();
  const canEdit = canManageTeam(normalizeOrgRole(session?.profile?.role));
  const qc = useQueryClient();
  const companyQ = useQuery({
    queryKey: ["smart-card", "company"],
    queryFn: () => apiFetch<{ ok: boolean; company: Company }>("/smart-card/company"),
  });
  const repsQ = useQuery({
    queryKey: ["smart-card", "representatives"],
    queryFn: () =>
      apiFetch<{ ok: boolean; items: { qr_token?: string; name?: string }[] }>("/smart-card/representatives"),
  });
  const [form, setForm] = React.useState<Company | null>(null);
  const [themeId, setThemeId] = React.useState<SmartCardThemeId>("smartcard");
  const sampleToken = repsQ.data?.items?.find((r) => r.qr_token)?.qr_token;
  const sampleName = repsQ.data?.items?.find((r) => r.qr_token)?.name;

  React.useEffect(() => {
    const c = companyQ.data?.company;
    if (!c) return;
    setForm(c);
    setThemeId(normalizeSmartCardThemeId(c.theme_id ?? c.brand_defaults?.theme_id));
  }, [companyQ.data]);

  const saveMut = useMutation({
    mutationFn: (body: Company & { theme_id: SmartCardThemeId }) =>
      apiFetch("/smart-card/company", { method: "PATCH", body: JSON.stringify(body) }),
    onSuccess: async () => {
      toast.success("Company saved");
      await qc.invalidateQueries({ queryKey: ["smart-card", "company"] });
    },
    onError: (e: Error) => toast.error(e.message || "Save failed"),
  });

  if (!form) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Smart Card QR"
        title="Company"
        description="Profile shown with representative Smart Card QR scans."
        actions={
          canEdit ? (
            <Button
              disabled={saveMut.isPending}
              onClick={() => saveMut.mutate({ ...form, theme_id: themeId })}
            >
              Save
            </Button>
          ) : null
        }
      />
      <Card>
        <CardContent className="grid gap-4 p-4 sm:grid-cols-2">
          <Field label="Company name">
            <Input
              disabled={!canEdit}
              value={form.name || ""}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </Field>
          <Field label="Website">
            <Input
              disabled={!canEdit}
              value={form.website || ""}
              onChange={(e) => setForm({ ...form, website: e.target.value })}
            />
          </Field>
          <Field label="Contact email">
            <Input
              disabled={!canEdit}
              value={form.contact_email || ""}
              onChange={(e) => setForm({ ...form, contact_email: e.target.value })}
            />
          </Field>
          <Field label="Contact phone">
            <Input
              disabled={!canEdit}
              value={form.contact_phone || ""}
              onChange={(e) => setForm({ ...form, contact_phone: e.target.value })}
            />
          </Field>
          <div className="sm:col-span-2">
            <Field label="Description">
              <Textarea
                disabled={!canEdit}
                rows={4}
                value={form.description || ""}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
              />
            </Field>
          </div>
          <div className="sm:col-span-2">
            <Field label="Products summary">
              <Textarea
                disabled={!canEdit}
                rows={3}
                value={form.products_summary || ""}
                onChange={(e) => setForm({ ...form, products_summary: e.target.value })}
              />
            </Field>
          </div>
          <div className="sm:col-span-2">
            <Field label="Pricing notes">
              <Textarea
                disabled={!canEdit}
                rows={2}
                value={form.pricing_notes || ""}
                onChange={(e) => setForm({ ...form, pricing_notes: e.target.value })}
              />
            </Field>
          </div>
          {!canEdit ? (
            <p className="sm:col-span-2 text-sm text-muted-foreground">
              View only — request changes from your organisation admin.
            </p>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Digital card theme</CardTitle>
          <CardDescription>
            Choose how the public smart card looks when someone scans a representative QR.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <SmartCardThemePicker
            value={themeId}
            onChange={setThemeId}
            companyName={form.name}
            personName={sampleName}
            qrToken={sampleToken}
            className={canEdit ? undefined : "pointer-events-none opacity-70"}
          />
        </CardContent>
      </Card>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      {children}
    </div>
  );
}
