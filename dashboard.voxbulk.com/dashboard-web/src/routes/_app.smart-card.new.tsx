import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import {
  Briefcase,
  ChevronLeft,
  ChevronRight,
  Eye,
  FileUp,
  Gift,
  Package,
  QrCode,
  Rocket,
  Target,
  User,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { Stepper, type WizardStepDef } from "@/components/create-wizard/stepper";
import { CategoryProductsEditor, newCategory, type CategoryDraft } from "@/components/expo-booth-sections";
import {
  emptyRepresentativeForm,
  RepresentativeFields,
  socialLinksPayload,
  type RepresentativeFormValue,
} from "@/components/smart-card/representative-fields";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { CheckoutConfirmDialog, type CheckoutConfirmDetails } from "@/components/billing/checkout-confirm-dialog";
import { SERVICE_TINTS } from "@/components/billing/service-package-shell";
import { startSmartCardSeatCheckout } from "@/lib/billing/smart-card-subscription-payment";
import { apiFetch } from "@/lib/api";
import { useOrganisation } from "@/lib/queries";
import { canManageTeam, normalizeOrgRole } from "@/lib/org-roles";
import { useSession } from "@/lib/session";
import { cn } from "@/lib/utils";

type Step = 1 | 2 | 3 | 4 | 5 | 6 | 7;

type QuestionOpt = {
  key: string;
  prompt: string;
  label: string;
  description?: string;
  matches_products?: boolean;
};

type PackageItem = {
  id: string;
  plan_id: string;
  name: string;
  description?: string | null;
  prices: Array<{ currency: string; monthly_price_minor?: number | null; yearly_price_minor?: number | null }>;
};

type DraftRep = {
  id: string;
  name: string;
  email?: string | null;
  mobile?: string | null;
  qr_image_url?: string;
  web_url?: string;
  qr_token?: string;
};

const STEPS: WizardStepDef[] = [
  { id: 1, title: "Company", icon: Briefcase },
  { id: 2, title: "Products", icon: FileUp },
  { id: 3, title: "Questions", icon: Target },
  { id: 4, title: "Offers", icon: Gift },
  { id: 5, title: "Preview", icon: Eye },
  { id: 6, title: "Package", icon: Package },
  { id: 7, title: "Activate", icon: Rocket },
];

const DEFAULT_Q_KEYS = ["interest", "role", "timeline", "follow_up", "consent_info"];

export const Route = createFileRoute("/_app/smart-card/new")({
  head: () => ({ meta: [{ title: "Create Smart Card QR — VoxBulk" }] }),
  component: SmartCardNewWizard,
});

function SmartCardNewWizard() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { session } = useSession();
  const canEdit = canManageTeam(normalizeOrgRole(session?.profile?.role));
  const orgQ = useOrganisation();

  const [step, setStep] = React.useState<Step>(1);
  const [saving, setSaving] = React.useState(false);

  const [companyName, setCompanyName] = React.useState("");
  const [website, setWebsite] = React.useState("");
  const [contactEmail, setContactEmail] = React.useState("");
  const [contactPhone, setContactPhone] = React.useState("");
  const [address, setAddress] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [rep, setRep] = React.useState<RepresentativeFormValue>(() => emptyRepresentativeForm());
  const [notifyMobile, setNotifyMobile] = React.useState("");

  const [categories, setCategories] = React.useState<CategoryDraft[]>([]);
  const [selectedQKeys, setSelectedQKeys] = React.useState<string[]>([...DEFAULT_Q_KEYS]);
  const [contactCapture, setContactCapture] = React.useState<"offer_both" | "manual_only" | "card_only">(
    "offer_both",
  );

  const [offerEnabled, setOfferEnabled] = React.useState(false);
  const [offerTitle, setOfferTitle] = React.useState("");
  const [offerDescription, setOfferDescription] = React.useState("");

  const [draftRep, setDraftRep] = React.useState<DraftRep | null>(null);
  const [planId, setPlanId] = React.useState("");
  const [seatQty, setSeatQty] = React.useState(1);
  const [checkoutOpen, setCheckoutOpen] = React.useState(false);
  const [checkoutDetails, setCheckoutDetails] = React.useState<CheckoutConfirmDetails | null>(null);

  React.useEffect(() => {
    const org = orgQ.data;
    if (!org) return;
    setCompanyName((prev) => prev || org.name || "");
    setWebsite((prev) => prev || org.website || "");
    setContactEmail((prev) => prev || String(org.contact_email || ""));
    setContactPhone((prev) => prev || String(org.contact_phone || ""));
  }, [orgQ.data]);

  const companyQ = useQuery({
    queryKey: ["smart-card", "company"],
    queryFn: () => apiFetch<{ ok: boolean; company: Record<string, unknown> }>("/smart-card/company"),
  });

  React.useEffect(() => {
    const c = companyQ.data?.company;
    if (!c) return;
    if (c.name) setCompanyName(String(c.name));
    if (c.website) setWebsite(String(c.website));
    if (c.contact_email) setContactEmail(String(c.contact_email));
    if (c.contact_phone) setContactPhone(String(c.contact_phone));
    if (c.description) setDescription(String(c.description));
    const brand = c.brand_defaults as { address?: string } | null;
    if (brand?.address) setAddress(String(brand.address));
    const cfg = c.question_config as { selected_keys?: string[]; contact_capture?: string } | null;
    if (cfg?.selected_keys?.length) setSelectedQKeys(cfg.selected_keys.map(String));
    if (cfg?.contact_capture === "manual_only" || cfg?.contact_capture === "card_only" || cfg?.contact_capture === "offer_both") {
      setContactCapture(cfg.contact_capture);
    }
  }, [companyQ.data]);

  const questionsQ = useQuery({
    queryKey: ["smart-card", "catalog-questions"],
    queryFn: () => apiFetch<{ ok: boolean; items: QuestionOpt[] }>("/smart-card/catalog/questions"),
  });

  const packagesQ = useQuery({
    queryKey: ["smart-card", "packages"],
    queryFn: () => apiFetch<{ ok: boolean; items: PackageItem[] }>("/smart-card/packages"),
  });

  React.useEffect(() => {
    const first = packagesQ.data?.items?.[0];
    if (first && !planId) setPlanId(first.plan_id);
  }, [packagesQ.data, planId]);

  const questions = questionsQ.data?.items || [];

  const canNext = React.useMemo(() => {
    if (step === 1) {
      return Boolean(companyName.trim() && rep.name.trim());
    }
    if (step === 3) {
      return selectedQKeys.length > 0 && Boolean(contactCapture);
    }
    if (step === 6) {
      return Boolean(planId) && seatQty >= 1;
    }
    return true;
  }, [step, companyName, rep.name, selectedQKeys, contactCapture, planId, seatQty]);

  const buildPayload = () => ({
    name: companyName.trim(),
    website: website.trim() || null,
    contact_email: contactEmail.trim() || null,
    contact_phone: contactPhone.trim() || notifyMobile.trim() || null,
    description: description.trim() || null,
    address: address.trim() || null,
    brand_defaults: { address: address.trim() || null },
    notify_mobile: notifyMobile.trim() || rep.mobile || null,
    contact_capture: contactCapture,
    selected_keys: selectedQKeys,
    offer_enabled: offerEnabled,
    offer: offerEnabled
      ? { enabled: true, title: offerTitle, description: offerDescription }
      : { enabled: false },
    categories: categories.map((c) => ({
      name: c.name,
      products: (c.products || []).map((p) => ({
        name: p.name,
        short_description: p.short_description || "",
      })),
    })),
    representative: {
      name: rep.name.trim(),
      email: rep.email.trim() || null,
      mobile: (rep.mobile || notifyMobile).trim() || null,
      landline: rep.landline.trim() || null,
      extension: rep.extension.trim() || null,
      website: (rep.website || website).trim() || null,
      social_links: socialLinksPayload(rep.social_links),
    },
  });

  const goNext = async () => {
    if (!canEdit) {
      toast.error("You need manager access to set up Smart Card QR");
      return;
    }
    if (!canNext) {
      if (step === 1) toast.error("Company name and first representative are required");
      if (step === 3) toast.error("Select contact mode and at least one question");
      return;
    }
    if (step === 4) {
      // Preview step next — persist draft
      setSaving(true);
      try {
        const res = await apiFetch<{
          ok: boolean;
          representative: DraftRep;
        }>("/smart-card/setup/preview-draft", {
          method: "POST",
          body: JSON.stringify(buildPayload()),
        });
        setDraftRep(res.representative);
        await qc.invalidateQueries({ queryKey: ["smart-card"] });
        setStep(5);
        toast.success("Preview ready — scan the QR to test (up to 15 free tests)");
      } catch (e) {
        toast.error(e instanceof Error ? e.message : "Could not create preview");
      } finally {
        setSaving(false);
      }
      return;
    }
    if (step === 5) {
      setStep(6);
      return;
    }
    if (step === 6) {
      setStep(7);
      return;
    }
    if (step < 7) setStep((s) => (s + 1) as Step);
  };

  const activate = async () => {
    if (!planId || seatQty < 1) {
      toast.error("Choose a plan and seat quantity");
      return;
    }
    setSaving(true);
    try {
      await apiFetch("/smart-card/setup/preview-draft", {
        method: "POST",
        body: JSON.stringify(buildPayload()),
      });
      await startSmartCardSeatCheckout(planId, seatQty, "yearly");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Checkout failed");
      setSaving(false);
    }
  };

  const openActivateCheckout = () => {
    if (!planId || seatQty < 1) {
      toast.error("Choose a plan and seat quantity");
      return;
    }
    const selected = (packagesQ.data?.items || []).find((p) => p.plan_id === planId);
    const usd = selected?.prices.find((p) => p.currency === "USD");
    const unit = usd?.yearly_price_minor;
    const total = unit != null ? (unit * seatQty) / 100 : null;
    setCheckoutDetails({
      planName: selected?.name || "Smart Card seats",
      intervalLabel: "Yearly billing (20% off)",
      amountDisplay: total != null ? `$${total.toFixed(0)}` : "See checkout",
      seats: seatQty,
      unitDisplay: unit != null ? `$${(unit / 100).toFixed(0)}` : null,
      amountNote: "Ex-VAT. VAT may be added at checkout when applicable.",
      providerHint: "You will continue to secure card payment.",
    });
    setCheckoutOpen(true);
  };

  const skipPay = () => {
    toast.success("Saved in preview mode — buy seats when ready to go live");
    void navigate({ to: "/smart-card" });
  };

  if (!canEdit) {
    return (
      <div className="space-y-4">
        <PageHeader eyebrow="Smart Card QR" title="Create Smart Card QR" />
        <Card>
          <CardContent className="p-6 text-sm text-muted-foreground">
            Only owners and managers can create Smart Card QR setup.
          </CardContent>
        </Card>
      </div>
    );
  }

  const selectedPkg = (packagesQ.data?.items || []).find((p) => p.plan_id === planId);

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="Smart Card QR"
        title="Create Smart Card QR"
        description="Set up your company, qualifying questions, and first representative QR — then choose seats."
      />

      <Stepper steps={STEPS} current={step} onStepClick={(n) => n <= step && setStep(n as Step)} />

      <div key={step} className="animate-fade-in">
        {step === 1 && (
          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Company profile</CardTitle>
                <CardDescription>
                  Prefills from Settings → Profile when available. Edit here — changes save with your Smart Card
                  setup.
                </CardDescription>
              </CardHeader>
              <CardContent className="grid gap-3">
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="space-y-1.5">
                    <Label className="text-xs">
                      Company name <span className="text-destructive">*</span>
                    </Label>
                    <Input
                      value={companyName}
                      onChange={(e) => setCompanyName(e.target.value)}
                      placeholder="Acme Supplies Ltd"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs">Website</Label>
                    <Input value={website} onChange={(e) => setWebsite(e.target.value)} placeholder="https://" />
                  </div>
                </div>
                <div className="grid gap-3 sm:grid-cols-3">
                  <div className="space-y-1.5">
                    <Label className="text-xs">Contact email</Label>
                    <Input
                      type="email"
                      value={contactEmail}
                      onChange={(e) => setContactEmail(e.target.value)}
                      placeholder="hello@acme.com"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs">Contact phone</Label>
                    <Input
                      value={contactPhone}
                      onChange={(e) => setContactPhone(e.target.value)}
                      placeholder="+44…"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs">Address</Label>
                    <Input
                      value={address}
                      onChange={(e) => setAddress(e.target.value)}
                      placeholder="Street, city, postcode"
                    />
                  </div>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Short description (optional)</Label>
                  <Textarea
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    rows={3}
                    placeholder="What your company does"
                  />
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <User className="size-4" /> First representative
                </CardTitle>
                <CardDescription>
                  Required for Preview — create one QR so you can test the scan → WhatsApp/web questionnaire.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <RepresentativeFields
                  value={{ ...rep, mobile: rep.mobile || notifyMobile }}
                  onChange={(next) => {
                    setRep(next);
                    setNotifyMobile(next.mobile);
                  }}
                  mobileHint="Mobile (hot-lead WhatsApp)"
                />
              </CardContent>
            </Card>
          </div>
        )}

        {step === 2 && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Products & catalogue</CardTitle>
              <CardDescription>Optional — add categories and products. Skip if you only want leads.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <CategoryProductsEditor
                categories={categories}
                onChange={setCategories}
                maxCategories={null}
                packages={[]}
              />
              {categories.length === 0 ? (
                <p className="rounded-xl border border-dashed p-4 text-center text-sm text-muted-foreground">
                  Skip — no catalogue yet. You can assign products later when editing a QR.
                </p>
              ) : null}
              <Button type="button" variant="outline" size="sm" onClick={() => setCategories([newCategory("General")])}>
                Add a category
              </Button>
            </CardContent>
          </Card>
        )}

        {step === 3 && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Qualifying questions</CardTitle>
              <CardDescription>
                Required — contact capture first (scan card or type company info), then choose questions.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="rounded-xl border bg-muted/20 p-4">
                <p className="text-sm font-medium">Fixed · Contact capture</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Visitors start with a business-card photo or typed name / company — same idea as Expo.
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {(
                    [
                      ["offer_both", "Photo or type details"],
                      ["manual_only", "Name / company only"],
                      ["card_only", "Business card photo only"],
                    ] as const
                  ).map(([value, label]) => (
                    <Button
                      key={value}
                      type="button"
                      size="sm"
                      variant={contactCapture === value ? "default" : "outline"}
                      onClick={() => setContactCapture(value)}
                    >
                      {label}
                    </Button>
                  ))}
                </div>
              </div>

              <div className="space-y-2">
                <p className="text-sm font-medium">Select questions</p>
                <div className="grid gap-2 sm:grid-cols-2">
                  {questions.map((q) => {
                    const checked = selectedQKeys.includes(q.key);
                    return (
                      <label
                        key={q.key}
                        className={cn(
                          "flex cursor-pointer items-start gap-3 rounded-xl border p-3 transition",
                          checked ? "border-primary bg-primary/5" : "border-border",
                        )}
                      >
                        <Checkbox
                          checked={checked}
                          onCheckedChange={(v) => {
                            setSelectedQKeys((prev) =>
                              v ? [...prev, q.key] : prev.filter((k) => k !== q.key),
                            );
                          }}
                          className="mt-0.5"
                        />
                        <span>
                          <span className="block text-sm font-medium">{q.label}</span>
                          <span className="mt-0.5 block text-xs text-muted-foreground">{q.prompt}</span>
                        </span>
                      </label>
                    );
                  })}
                </div>
                {questions.length === 0 ? (
                  <p className="text-sm text-muted-foreground">Loading question bank…</p>
                ) : null}
              </div>
            </CardContent>
          </Card>
        )}

        {step === 4 && (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Gift className="size-4 text-primary" /> Offer
              </CardTitle>
              <CardDescription>Optional — add a promo visitors can claim. Skip if none.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <label className="flex items-start gap-3 rounded-xl border p-4">
                <Checkbox
                  checked={offerEnabled}
                  onCheckedChange={(v) => setOfferEnabled(Boolean(v))}
                  className="mt-0.5"
                />
                <span>
                  <span className="font-medium">Add an offer</span>
                  <span className="mt-0.5 block text-xs text-muted-foreground">
                    Adds an “interested in offer?” question when enabled.
                  </span>
                </span>
              </label>
              {offerEnabled ? (
                <div className="grid gap-4">
                  <div className="space-y-2">
                    <Label>Offer title</Label>
                    <Input
                      value={offerTitle}
                      onChange={(e) => setOfferTitle(e.target.value)}
                      placeholder="10% off first order"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Description</Label>
                    <Textarea
                      value={offerDescription}
                      onChange={(e) => setOfferDescription(e.target.value)}
                      rows={3}
                    />
                  </div>
                </div>
              ) : (
                <p className="rounded-xl border border-dashed p-4 text-center text-sm text-muted-foreground">
                  Skip — no offer question will be shown.
                </p>
              )}
            </CardContent>
          </Card>
        )}

        {step === 5 && (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <QrCode className="size-4" /> Preview QR
              </CardTitle>
              <CardDescription>
                Scan to test the questionnaire. Preview uses up to 15 free tests before a paid seat package.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col items-center gap-4 sm:flex-row sm:items-start">
              {draftRep?.qr_image_url ? (
                <img
                  src={draftRep.qr_image_url}
                  alt="Smart Card QR preview"
                  className="size-48 rounded-xl border bg-white p-2"
                />
              ) : (
                <div className="grid size-48 place-items-center rounded-xl border border-dashed text-sm text-muted-foreground">
                  Generating…
                </div>
              )}
              <div className="space-y-2 text-sm">
                <p>
                  <span className="font-medium">{draftRep?.name || rep.name}</span>
                </p>
                {draftRep?.web_url ? (
                  <a className="text-primary underline" href={draftRep.web_url} target="_blank" rel="noreferrer">
                    Open web questionnaire
                  </a>
                ) : null}
                <p className="text-muted-foreground">
                  After activate you can add more representative QRs up to your seat count.
                </p>
              </div>
            </CardContent>
          </Card>
        )}

        {step === 6 && (
          <div className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Pricing</CardTitle>
                <CardDescription>$5 per seat per month, billed annually ($60/seat/year).</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto rounded-xl border">
                  <table className="w-full text-left text-sm">
                    <thead className="border-b bg-muted/40">
                      <tr>
                        <th className="px-3 py-2 font-medium">Plan</th>
                        <th className="px-3 py-2 font-medium">Per seat / year</th>
                        <th className="px-3 py-2 font-medium">Per seat / month</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(packagesQ.data?.items || []).map((pkg) => {
                        const usd = pkg.prices.find((p) => p.currency === "USD");
                        const yearly = usd?.yearly_price_minor;
                        const monthly = usd?.monthly_price_minor;
                        return (
                          <tr key={pkg.id} className="border-b last:border-0">
                            <td className="px-3 py-2">{pkg.name}</td>
                            <td className="px-3 py-2">
                              {yearly != null ? `$${(yearly / 100).toFixed(0)}` : "—"}
                            </td>
                            <td className="px-3 py-2">
                              {monthly != null ? `$${(monthly / 100).toFixed(0)}` : "—"}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">How many seats?</CardTitle>
                <CardDescription>Each seat = one representative QR code.</CardDescription>
              </CardHeader>
              <CardContent className="grid max-w-sm gap-4">
                {(packagesQ.data?.items || []).map((pkg) => (
                  <label
                    key={pkg.id}
                    className={cn(
                      "flex cursor-pointer items-center gap-3 rounded-xl border p-3",
                      planId === pkg.plan_id ? "border-primary bg-primary/5" : "",
                    )}
                  >
                    <input
                      type="radio"
                      name="sc-plan"
                      checked={planId === pkg.plan_id}
                      onChange={() => setPlanId(pkg.plan_id)}
                    />
                    <span className="text-sm font-medium">{pkg.name}</span>
                  </label>
                ))}
                <div className="space-y-2">
                  <Label>Seats</Label>
                  <Input
                    type="number"
                    min={1}
                    max={500}
                    value={seatQty}
                    onChange={(e) => setSeatQty(Math.max(1, Math.min(500, Number(e.target.value) || 1)))}
                  />
                </div>
                {selectedPkg ? (
                  <p className="text-sm text-muted-foreground">
                    {(() => {
                      const usd = selectedPkg.prices.find((p) => p.currency === "USD");
                      const unit = usd?.yearly_price_minor;
                      if (unit == null) return null;
                      return `Total due today: $${((unit * seatQty) / 100).toFixed(0)} / year`;
                    })()}
                  </p>
                ) : null}
              </CardContent>
            </Card>
          </div>
        )}

        {step === 7 && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Activate</CardTitle>
              <CardDescription>
                Pay for {seatQty} seat{seatQty === 1 ? "" : "s"} to go live, or continue in preview with your first QR.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              <div className="flex flex-wrap gap-3">
              <Button disabled={saving} onClick={openActivateCheckout}>
                {saving ? "Starting checkout…" : "Buy seats & activate"}
              </Button>
              <Button variant="outline" disabled={saving} onClick={skipPay}>
                Stay in preview
              </Button>
              <Button asChild variant="ghost">
                <Link to="/smart-card">Open Saved QR codes</Link>
              </Button>
              </div>
            </CardContent>
          </Card>
        )}
      </div>

      <CheckoutConfirmDialog
        open={checkoutOpen}
        onOpenChange={(open) => {
          setCheckoutOpen(open);
          if (!open) setCheckoutDetails(null);
        }}
        details={checkoutDetails}
        serviceHint="Smart Card"
        tintClass={SERVICE_TINTS.smartCard.soft}
        confirmLabel="Pay with card"
        loading={saving}
        onConfirm={async () => {
          setCheckoutOpen(false);
          await activate();
        }}
      />

      {step < 7 ? (
        <div className="flex items-center justify-between gap-3 border-t pt-4">
          <Button
            type="button"
            variant="outline"
            disabled={step === 1 || saving}
            onClick={() => setStep((s) => (s - 1) as Step)}
          >
            <ChevronLeft className="size-4" /> Back
          </Button>
          <Button type="button" disabled={!canNext || saving} onClick={() => void goNext()}>
            {saving ? "Saving…" : step === 4 ? "Save & preview" : "Next"}
            <ChevronRight className="size-4" />
          </Button>
        </div>
      ) : null}
    </div>
  );
}
