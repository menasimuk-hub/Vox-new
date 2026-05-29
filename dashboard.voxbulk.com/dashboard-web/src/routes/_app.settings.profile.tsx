import { createFileRoute } from "@tanstack/react-router";
import * as React from "react";
import { Upload, Plus, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { SortHeader, useTableSort } from "@/components/sortable-table";
import { useServices } from "@/lib/services";
import { useOrganisation, useUpdateOrganisation } from "@/lib/queries";
import { PROFILE_COUNTRIES } from "@/lib/billing/market";

export const Route = createFileRoute("/_app/settings/profile")({
  head: () => ({ meta: [{ title: "Profile settings — VoxBulk" }] }),
  component: ProfileSettings,
});

function ProfileSettings() {
  const { visible } = useServices();
  const orgQ = useOrganisation();
  const saveM = useUpdateOrganisation();

  const [name, setName] = React.useState("");
  const [contactName, setContactName] = React.useState("");
  const [contactPhone, setContactPhone] = React.useState("");
  const [website, setWebsite] = React.useState("");
  const [country, setCountry] = React.useState("United Kingdom");

  React.useEffect(() => {
    const org = orgQ.data;
    if (!org) return;
    setName(org.name || "");
    setContactName(String(org.contact_name || ""));
    setContactPhone(String(org.contact_phone || ""));
    setWebsite(String(org.website || ""));
    setCountry(String(org.country || "United Kingdom"));
  }, [orgQ.data]);

  const treatments = [
    { treatment: "Hygiene", price: "£75" },
    { treatment: "Check-up", price: "£55" },
    { treatment: "White filling", price: "£180" },
    { treatment: "Whitening", price: "£399" },
  ];
  const t = useTableSort(treatments);

  const onSave = async (overrides?: Partial<{ country: string }>) => {
    const nextCountry = overrides?.country ?? country;
    try {
      await saveM.mutateAsync({
        name,
        contact_name: contactName || null,
        contact_phone: contactPhone || null,
        website: website || null,
        country: nextCountry || "United Kingdom",
      });
      toast.success(overrides?.country ? `Country set to ${nextCountry} — prices updated` : "Profile saved");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not save profile");
    }
  };

  const onCountryChange = (value: string) => {
    setCountry(value);
    void onSave({ country: value });
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
              <Field label="Survey organiser" value={contactName} onChange={setContactName} />
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
                <div className="grid size-12 place-items-center rounded-lg bg-accent text-accent-foreground font-semibold">
                  {(name || "VB").slice(0, 2).toUpperCase()}
                </div>
                <div className="flex-1">
                  <p className="text-sm font-medium">Logo</p>
                  <p className="text-xs text-muted-foreground">PNG or SVG, transparent background recommended.</p>
                </div>
                <Button variant="outline" className="gap-1.5" disabled><Upload className="size-4" /> Upload</Button>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      {visible.recovery ? (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>Revenue for ROI</CardTitle>
                <p className="mt-1 text-xs text-muted-foreground">Used by Clinic recovery to calculate recovered revenue and ROI per call.</p>
              </div>
              <Button variant="outline" size="sm" className="gap-1.5"><RefreshCw className="size-3.5" /> Sync prices</Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              <Field label="Avg. appointment value" value="£120" onChange={() => undefined} readOnly />
              <div className="flex items-center justify-between rounded-lg border border-border p-3">
                <div>
                  <p className="text-sm font-medium">Per-treatment values</p>
                  <p className="text-xs text-muted-foreground">Use per-treatment instead of average</p>
                </div>
                <Switch defaultChecked />
              </div>
            </div>
            <div className="rounded-lg border border-border">
              <Table>
                <TableHeader><TableRow>
                  <SortHeader label="Treatment" sortKey="treatment" active={t.sortKey} dir={t.sortDir} onToggle={t.toggleSort} className="pl-4" />
                  <SortHeader label="Price" sortKey="price" active={t.sortKey} dir={t.sortDir} onToggle={t.toggleSort} />
                  <TableHead className="pr-4 text-right"></TableHead>
                </TableRow></TableHeader>
                <TableBody>
                  {t.sorted.map((row) => (
                    <TableRow key={row.treatment}>
                      <TableCell className="pl-4">{row.treatment}</TableCell>
                      <TableCell><Input defaultValue={row.price} className="h-8 w-28" readOnly /></TableCell>
                      <TableCell className="pr-4 text-right"><Button size="sm" variant="ghost" disabled>Remove</Button></TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
            <Button variant="outline" size="sm" className="gap-1.5" disabled><Plus className="size-3.5" /> Add treatment type</Button>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="flex items-start gap-3 p-5 text-sm text-muted-foreground">
            <div className="grid size-9 place-items-center rounded-lg bg-muted text-foreground/70">£</div>
            <div>
              <p className="text-sm font-medium text-foreground">Revenue for ROI is part of Clinic recovery</p>
              <p className="mt-1 text-xs">Enable the <span className="font-medium text-foreground">Recovery</span> service in Settings → Services to configure treatment prices and ROI calculations.</p>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="flex justify-end">
        <Button onClick={() => void onSave()} disabled={saveM.isPending}>{saveM.isPending ? "Saving…" : "Save profile"}</Button>
      </div>
    </div>
  );
}

function Field({ label, value, onChange, readOnly }: { label: string; value: string; onChange: (v: string) => void; readOnly?: boolean }) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs">{label}</Label>
      <Input value={value} onChange={(e) => onChange(e.target.value)} readOnly={readOnly} />
    </div>
  );
}
