import { createFileRoute } from "@tanstack/react-router";
import * as React from "react";
import { Upload, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useServices } from "@/lib/services";
import {
  useCancelAccountDeletion,
  useDeleteOrgLogo,
  useDeletionStatus,
  useOrganisation,
  useRequestAccountDeletion,
  useUpdateOrganisation,
  useUploadOrgLogo,
} from "@/lib/queries";
import { PROFILE_COUNTRIES } from "@/lib/billing/market";
import { useOrgLogoPreview } from "@/lib/use-org-logo";

export const Route = createFileRoute("/_app/settings/profile")({
  head: () => ({ meta: [{ title: "Profile settings — VoxBulk" }] }),
  component: ProfileSettings,
});

function ProfileSettings() {
  const { visible } = useServices();
  const orgQ = useOrganisation();
  const saveM = useUpdateOrganisation();
  const uploadLogoM = useUploadOrgLogo();
  const deleteLogoM = useDeleteOrgLogo();
  const logoInputRef = React.useRef<HTMLInputElement>(null);

  const [name, setName] = React.useState("");
  const [contactName, setContactName] = React.useState("");
  const [contactEmail, setContactEmail] = React.useState("");
  const [contactPhone, setContactPhone] = React.useState("");
  const [website, setWebsite] = React.useState("");
  const [country, setCountry] = React.useState("United Kingdom");
  const [deleteConfirm, setDeleteConfirm] = React.useState("");
  const deletionQ = useDeletionStatus();
  const requestDeletionM = useRequestAccountDeletion();
  const cancelDeletionM = useCancelAccountDeletion();
  const deletionStatus = deletionQ.data?.deletion_status || "active";
  const logoPreview = useOrgLogoPreview(orgQ.data?.logo_url);

  React.useEffect(() => {
    const org = orgQ.data;
    if (!org) return;
    setName(org.name || "");
    setContactName(String(org.contact_name || ""));
    setContactEmail(String(org.contact_email || ""));
    setContactPhone(String(org.contact_phone || ""));
    setWebsite(String(org.website || ""));
    setCountry(String(org.country || "United Kingdom"));
  }, [orgQ.data]);

  const onLogoSelected = async (file: File | null) => {
    if (!file) return;
    try {
      await uploadLogoM.mutateAsync(file);
      toast.success("Logo updated");
    } catch (e) {
      const errorMsg = e instanceof Error ? e.message : "Could not upload logo";
      toast.error(errorMsg);
    } finally {
      if (logoInputRef.current) logoInputRef.current.value = "";
    }
  };

  const onRemoveLogo = async () => {
    try {
      await deleteLogoM.mutateAsync();
      toast.success("Logo removed");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not remove logo");
    }
  };


  const onSave = async (overrides?: Partial<{ country: string }>) => {
    const nextCountry = overrides?.country ?? country;
    try {
      await saveM.mutateAsync({
        name,
        contact_name: contactName || null,
        contact_email: contactEmail || null,
        contact_phone: contactPhone || null,
        website: website || null,
        country: nextCountry || "United Kingdom",
      });
      const locked = Boolean(orgQ.data?.billing_currency_locked);
      if (overrides?.country) {
        toast.success(
          locked
            ? `Country set to ${nextCountry}. Billing currency stays fixed after your first payment — contact support to change.`
            : `Country set to ${nextCountry} — prices updated`,
        );
      } else {
        toast.success("Profile saved");
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not save profile");
    }
  };

  const onCountryChange = (value: string) => {
    setCountry(value);
    void onSave({ country: value });
  };

  const onDeleteAccount = async () => {
    if (deleteConfirm.trim().toUpperCase() !== "DELETE") {
      toast.error("Type DELETE to confirm account deletion");
      return;
    }
    try {
      const res = await requestDeletionM.mutateAsync({ confirm: "DELETE" });
      setDeleteConfirm("");
      toast.success(res.pending_message || "You have requested account deletion.");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not submit deletion request");
    }
  };

  const onCancelDeletion = async () => {
    try {
      await cancelDeletionM.mutateAsync();
      toast.success("Deletion request cancelled");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not cancel deletion request");
    }
  };

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader eyebrow="Settings" title="Profile" description="Company branding, caller ID, and revenue values for ROI." />

      <Card>
        <CardHeader><CardTitle>Company</CardTitle></CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          {orgQ.isLoading ? (
            <Skeleton className="md:col-span-2 h-40 w-full" />
          ) : (
            <>
              <Field label="Company name" value={name} onChange={setName} />
              <Field label="Contact name" value={contactName} onChange={setContactName} />
              <Field label="Contact email" value={contactEmail} onChange={setContactEmail} type="email" />
              <Field label="Phone" value={contactPhone} onChange={setContactPhone} />
              <Field label="Website" value={website} onChange={setWebsite} />
              <div className="space-y-1.5">
                <Label className="text-xs">Country</Label>
                <Select value={country} onValueChange={onCountryChange} disabled={saveM.isPending}>
                  <SelectTrigger><SelectValue placeholder="Select country" /></SelectTrigger>
                  <SelectContent>
                    {PROFILE_COUNTRIES.map((c) => (
                      <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-[11px] text-muted-foreground">Saved immediately. Pricing across the dashboard uses this country.</p>
              </div>
              <Field label="Caller ID" value={name.slice(0, 12).toUpperCase()} onChange={() => undefined} readOnly />
              <div className="md:col-span-2 flex items-center gap-3 rounded-lg border border-dashed border-border bg-background/50 p-4">
                {logoPreview ? (
                  <img src={logoPreview} alt="Company logo" className="size-12 rounded-lg object-contain bg-white p-1" />
                ) : (
                  <div className="grid size-12 place-items-center rounded-lg bg-accent text-accent-foreground font-semibold">
                    {(name || "VB").slice(0, 2).toUpperCase()}
                  </div>
                )}
                <div className="flex-1">
                  <p className="text-sm font-medium">Logo</p>
                  <p className="text-xs text-muted-foreground">PNG, JPG, WEBP or SVG — max 2 MB.</p>
                </div>
                <input
                  ref={logoInputRef}
                  type="file"
                  accept="image/png,image/jpeg,image/webp,image/svg+xml"
                  className="hidden"
                  onChange={(e) => void onLogoSelected(e.target.files?.[0] || null)}
                />
                <Button
                  variant="outline"
                  className="gap-1.5"
                  disabled={uploadLogoM.isPending}
                  onClick={() => logoInputRef.current?.click()}
                >
                  <Upload className="size-4" /> {uploadLogoM.isPending ? "Uploading…" : logoPreview ? "Replace" : "Upload"}
                </Button>
                {logoPreview && (
                  <Button variant="ghost" size="icon" className="text-destructive" disabled={deleteLogoM.isPending} onClick={() => void onRemoveLogo()}>
                    <Trash2 className="size-4" />
                  </Button>
                )}
              </div>
            </>
          )}
        </CardContent>
      </Card>

      <Card className="border-destructive/30">
        <CardHeader>
          <CardTitle className="text-destructive">Delete my account</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {deletionStatus !== "active" ? (
            <div className="rounded-lg border border-border bg-muted/40 px-3 py-2 text-sm">
              <span className="font-medium">Status: </span>
              {deletionQ.isLoading ? "Loading…" : deletionQ.data?.deletion_label}
              {deletionQ.data?.deletion_requested_at ? (
                <span className="block text-xs text-muted-foreground mt-1">
                  Requested {new Date(deletionQ.data.deletion_requested_at).toLocaleString()}
                </span>
              ) : null}
            </div>
          ) : null}

          {deletionStatus === "pending" ? (
            <>
              <p className="text-sm font-medium">{deletionQ.data?.pending_message || "You have requested account deletion."}</p>
              <p className="text-sm text-muted-foreground">{deletionQ.data?.sla_message || "This may take up to 2 working days."}</p>
              <p className="text-xs text-muted-foreground">
                Invoices and legally required billing records are retained; personal data is anonymized when processed.
              </p>
              <Button variant="outline" disabled={cancelDeletionM.isPending} onClick={() => void onCancelDeletion()}>
                {cancelDeletionM.isPending ? "Cancelling…" : "Cancel delete request"}
              </Button>
            </>
          ) : deletionStatus === "cancelled" ? (
            <>
              <p className="text-sm text-muted-foreground">Your deletion request was cancelled. You can submit a new request below.</p>
              <Field label="Type DELETE to confirm" value={deleteConfirm} onChange={setDeleteConfirm} />
              <Button variant="destructive" disabled={requestDeletionM.isPending} onClick={() => void onDeleteAccount()}>
                {requestDeletionM.isPending ? "Submitting…" : "Delete my account"}
              </Button>
            </>
          ) : deletionStatus === "archived" ? (
            <p className="text-sm text-muted-foreground">This account has been deleted.</p>
          ) : (
            <>
              <p className="text-sm text-muted-foreground">
                Request deletion of your organisation account. Invoices and legally required billing records are retained; personal data is anonymized.
              </p>
              <Field label="Type DELETE to confirm" value={deleteConfirm} onChange={setDeleteConfirm} />
              <Button variant="destructive" disabled={requestDeletionM.isPending} onClick={() => void onDeleteAccount()}>
                {requestDeletionM.isPending ? "Submitting…" : "Delete my account"}
              </Button>
            </>
          )}
        </CardContent>
      </Card>

      <div className="flex justify-end">
        <Button onClick={() => void onSave()} disabled={saveM.isPending}>{saveM.isPending ? "Saving…" : "Save profile"}</Button>
      </div>
    </div>
  );
}

function Field({ label, value, onChange, readOnly, type = "text" }: { label: string; value: string; onChange: (v: string) => void; readOnly?: boolean; type?: string }) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs">{label}</Label>
      <Input type={type} value={value} onChange={(e) => onChange(e.target.value)} readOnly={readOnly} />
    </div>
  );
}
