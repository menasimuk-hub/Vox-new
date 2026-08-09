import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import {
  Briefcase,
  ChevronLeft,
  ChevronRight,
  Eye,
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
import { type CategoryDraft } from "@/components/expo-booth-sections";
import {
  emptyRepresentativeForm,
  RepresentativeFields,
  socialLinksPayload,
  type RepresentativeFormValue,
} from "@/components/smart-card/representative-fields";
import { SmartCardThemePicker } from "@/components/smart-card/smart-card-theme-picker";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { CheckoutConfirmDialog, type CheckoutConfirmDetails } from "@/components/billing/checkout-confirm-dialog";
import { StripeCardCheckoutDialog } from "@/components/billing/stripe-card-checkout-dialog";
import { SERVICE_TINTS } from "@/components/billing/service-package-shell";
import { countryToMarket, marketCurrencySymbol, orgCountryToCurrencyCode } from "@/lib/billing/market";
import {
  clearSmartCardCardCheckoutState,
  completeSmartCardSeatCheckout,
  startSmartCardGoCardless,
  startSmartCardSeatCheckout,
} from "@/lib/billing/smart-card-subscription-payment";
import {
  availablePaymentMethods,
  isStripeElementsCheckout,
  primarySubscriptionProvider,
  type PaymentMethodChoice,
  type StripeElementsCheckout,
} from "@/lib/billing/subscription-payment";
import { apiFetch, buildAuthHeaders, getApiBaseUrl } from "@/lib/api";
import { useOrganisation } from "@/lib/queries";
import { canManageTeam, normalizeOrgRole } from "@/lib/org-roles";
import { useSession } from "@/lib/session";
import {
  normalizeSmartCardThemeId,
  type SmartCardThemeId,
} from "@/lib/smart-card-themes";
import { cn } from "@/lib/utils";

type Step = 1 | 2 | 3 | 4 | 5 | 6;

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
  { id: 2, title: "Questions", icon: Target },
  { id: 3, title: "Offers", icon: Gift },
  { id: 4, title: "Preview", icon: Eye },
  { id: 5, title: "Package", icon: Package },
  { id: 6, title: "Activate", icon: Rocket },
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
  const subscription = session?.subscription as Record<string, unknown> | null | undefined;
  const paymentMethods = availablePaymentMethods(subscription);
  const primaryProvider = primarySubscriptionProvider(subscription);
  const defaultPayMethod: PaymentMethodChoice =
    (paymentMethods.includes(primaryProvider as PaymentMethodChoice)
      ? (primaryProvider as PaymentMethodChoice)
      : paymentMethods[0]) || "gocardless";
  const currencySym = marketCurrencySymbol(countryToMarket(orgQ.data?.country));
  const currencyCode = orgCountryToCurrencyCode(orgQ.data?.country);

  const [step, setStep] = React.useState<Step>(1);
  const [saving, setSaving] = React.useState(false);

  const [companyName, setCompanyName] = React.useState("");
  const [website, setWebsite] = React.useState("");
  const [contactEmail, setContactEmail] = React.useState("");
  const [contactPhone, setContactPhone] = React.useState("");
  const [address, setAddress] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [themeId, setThemeId] = React.useState<SmartCardThemeId>("smartcard");
  const [rep, setRep] = React.useState<RepresentativeFormValue>(() => emptyRepresentativeForm());
  const [repId, setRepId] = React.useState<string | null>(null);
  const [repPhotoFile, setRepPhotoFile] = React.useState<File | null>(null);
  const [repPhotoPreview, setRepPhotoPreview] = React.useState<string | null>(null);
  const [remoteRepPhoto, setRemoteRepPhoto] = React.useState<string | null>(null);
  const [repHydrated, setRepHydrated] = React.useState(false);
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
  const [stripeCheckout, setStripeCheckout] = React.useState<StripeElementsCheckout | null>(null);

  React.useEffect(() => {
    if (!repPhotoFile) {
      setRepPhotoPreview(null);
      return;
    }
    const url = URL.createObjectURL(repPhotoFile);
    setRepPhotoPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [repPhotoFile]);

  type ExistingRep = {
    id: string;
    name?: string;
    email?: string | null;
    mobile?: string | null;
    landline?: string | null;
    extension?: string | null;
    website?: string | null;
    status?: string;
    photo_url?: string | null;
    social_links?: RepresentativeFormValue["social_links"] | null;
    extra?: { job_title?: string; title?: string; role?: string; location?: string; address?: string } | null;
    qr_token?: string;
    qr_image_url?: string;
    web_url?: string;
  };

  const repsQ = useQuery({
    queryKey: ["smart-card", "reps", ""],
    queryFn: () => apiFetch<{ ok: boolean; items: ExistingRep[] }>("/smart-card/representatives"),
  });

  React.useEffect(() => {
    if (repHydrated) return;
    const items = (repsQ.data?.items || []).filter((r) => String(r.status || "") !== "archived");
    if (!items.length) {
      if (repsQ.isFetched) setRepHydrated(true);
      return;
    }
    const r = items[0];
    const social = r.social_links || {};
    const extra = r.extra || {};
    setRepId(r.id);
    setRep({
      name: r.name || "",
      job_title: String(extra.job_title || extra.title || extra.role || ""),
      email: r.email || "",
      mobile: r.mobile || "",
      landline: r.landline || "",
      extension: r.extension || "",
      website: r.website || "",
      location: String(extra.location || ""),
      address: String(extra.address || ""),
      social_links: {
        x: social.x || "",
        instagram: social.instagram || "",
        facebook: social.facebook || "",
        tiktok: social.tiktok || "",
        linkedin: social.linkedin || "",
      },
    });
    if (r.mobile) setNotifyMobile(String(r.mobile));
    if (r.qr_image_url || r.web_url || r.qr_token) {
      setDraftRep({
        id: r.id,
        name: r.name || "",
        email: r.email,
        mobile: r.mobile,
        qr_image_url: r.qr_image_url,
        web_url: r.web_url,
        qr_token: r.qr_token,
      });
    }
    setRepHydrated(true);
  }, [repsQ.data, repsQ.isFetched, repHydrated]);

  React.useEffect(() => {
    let revoked: string | null = null;
    let cancelled = false;
    setRemoteRepPhoto(null);
    if (repPhotoFile || !repId) return;
    const item = (repsQ.data?.items || []).find((r) => r.id === repId);
    const path = item?.photo_url;
    if (!path) return;
    (async () => {
      try {
        const base = getApiBaseUrl().replace(/\/+$/, "");
        const res = await fetch(`${base}${path}`, { headers: buildAuthHeaders() });
        if (!res.ok) return;
        const blob = await res.blob();
        if (cancelled) return;
        const url = URL.createObjectURL(blob);
        revoked = url;
        setRemoteRepPhoto(url);
      } catch {
        /* ignore */
      }
    })();
    return () => {
      cancelled = true;
      if (revoked) URL.revokeObjectURL(revoked);
    };
  }, [repId, repsQ.data, repPhotoFile]);

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
    const brand = c.brand_defaults as { address?: string; theme_id?: string } | null;
    if (brand?.address) setAddress(String(brand.address));
    setThemeId(normalizeSmartCardThemeId(c.theme_id ?? brand?.theme_id));
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
    if (step === 2) {
      return selectedQKeys.length > 0 && Boolean(contactCapture);
    }
    if (step === 5) {
      return Boolean(planId) && seatQty >= 1;
    }
    return true;
  }, [step, companyName, rep.name, selectedQKeys, contactCapture, planId, seatQty]);

  const buildPayload = () => ({
    name: companyName.trim(),
    website: website.trim() || null,
    contact_email: contactEmail.trim() || null,
    contact_phone: contactPhone.trim() || notifyMobile.trim() || null,
    description: description.trim().slice(0, 150) || null,
    address: address.trim() || null,
    theme_id: themeId,
    brand_defaults: { address: address.trim() || null, theme_id: themeId },
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
      ...(repId ? { id: repId } : {}),
      name: rep.name.trim(),
      email: rep.email.trim() || null,
      mobile: (rep.mobile || notifyMobile).trim() || null,
      landline: rep.landline.trim() || null,
      extension: rep.extension.trim() || null,
      website: (rep.website || website).trim() || null,
      social_links: socialLinksPayload(rep.social_links),
      extra: {
        ...(rep.job_title.trim() ? { job_title: rep.job_title.trim() } : {}),
        ...(rep.location.trim() ? { location: rep.location.trim() } : {}),
        ...(rep.address.trim() ? { address: rep.address.trim() } : {}),
      },
    },
  });

  const uploadRepPhoto = async (repId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
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
  };

  const goNext = async () => {
    if (!canEdit) {
      toast.error("You need manager access to set up Smart Card QR");
      return;
    }
    if (!canNext) {
      if (step === 1) toast.error("Company name and first representative are required");
      if (step === 2) toast.error("Select contact mode and at least one question");
      return;
    }
    if (step === 3) {
      // Offers done — persist draft for preview
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
        if (res.representative?.id) setRepId(res.representative.id);
        if (repPhotoFile && res.representative?.id) {
          try {
            await uploadRepPhoto(res.representative.id, repPhotoFile);
            toast.success("Preview ready — profile photo uploaded");
          } catch (photoErr) {
            toast.error(photoErr instanceof Error ? photoErr.message : "Preview ready, but photo upload failed");
          }
        } else {
          toast.success("Preview ready — scan the QR to test (up to 15 free tests)");
        }
        await qc.invalidateQueries({ queryKey: ["smart-card"] });
        setStep(4);
      } catch (e) {
        toast.error(e instanceof Error ? e.message : "Could not create preview");
      } finally {
        setSaving(false);
      }
      return;
    }
    if (step === 4) {
      setStep(5);
      return;
    }
    if (step === 5) {
      setStep(6);
      return;
    }
    if (step < 6) setStep((s) => (s + 1) as Step);
  };

  const activate = async (paymentMethod?: PaymentMethodChoice) => {
    if (!planId || seatQty < 1) {
      toast.error("Choose a plan and seat quantity");
      return;
    }
    if (paymentMethods.length === 0) {
      toast.error("No subscription payment method is configured for your region.");
      return;
    }
    setSaving(true);
    try {
      await apiFetch("/smart-card/setup/preview-draft", {
        method: "POST",
        body: JSON.stringify(buildPayload()),
      });
      const method = paymentMethod || defaultPayMethod;
      if (method === "gocardless") {
        await startSmartCardGoCardless(planId, seatQty, "yearly");
      } else {
        const result = await startSmartCardSeatCheckout(planId, seatQty, "yearly", "stripe", {
          returnPath: "/smart-card/new",
        });
        if (isStripeElementsCheckout(result)) {
          setStripeCheckout(result);
          setSaving(false);
        } else if (result.provider === "promo_discount" && result.paid) {
          toast.success("Seats activated with promo");
          setSaving(false);
          await qc.invalidateQueries({ queryKey: ["smart-card"] });
          void navigate({ to: "/smart-card" });
        }
      }
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
    if (paymentMethods.length === 0) {
      toast.error("No subscription payment method is configured for your region.");
      return;
    }
    const selected = (packagesQ.data?.items || []).find((p) => p.plan_id === planId);
    const priced = selected?.prices.find((p) => p.currency === currencyCode) || selected?.prices.find((p) => p.currency === "USD");
    const unit = priced?.yearly_price_minor;
    const total = unit != null ? (unit * seatQty) / 100 : null;
    const sym = priced?.currency === currencyCode ? currencySym : "$";
    setCheckoutDetails({
      planName: selected?.name || "Smart Card seats",
      intervalLabel: "Yearly billing (20% off)",
      amountDisplay: total != null ? `${sym}${total.toFixed(0)}` : "See checkout",
      seats: seatQty,
      unitDisplay: unit != null ? `${sym}${(unit / 100).toFixed(0)}` : null,
      amountNote: "Ex-VAT. VAT may be added at checkout when applicable.",
      amountMinor: total != null ? Math.round(total * 100) : null,
      serviceKind: "smart_card",
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
        title={repId ? "Edit Smart Card setup" : "Create Smart Card QR"}
        description={
          repId
            ? "Your saved representative and company details are loaded below. Change anything, then continue — empty fields will not wipe existing data."
            : "Set up your company, qualifying questions, and first representative QR — then choose seats."
        }
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
                    onChange={(e) => setDescription(e.target.value.slice(0, 150))}
                    rows={3}
                    maxLength={150}
                    placeholder="What your company does"
                  />
                  <p className="text-[11px] text-muted-foreground">{description.length}/150 · max 3 lines</p>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <User className="size-4" /> {repId ? "Representative" : "First representative"}
                </CardTitle>
                <CardDescription>
                  {repId
                    ? "Loaded from your saved Smart Card. Edit here or use Saved QR codes → Edit for full QR options."
                    : "Required for Preview — create one QR so you can test the scan → WhatsApp/web contact form."}
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
                  photoPreviewUrl={repPhotoPreview || remoteRepPhoto}
                  photoFileName={repPhotoFile?.name}
                  onPhotoChange={setRepPhotoFile}
                />
              </CardContent>
            </Card>
          </div>
        )}

        {step === 2 && (
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

        {step === 3 && (
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

        {step === 4 && (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <QrCode className="size-4" /> Preview QR
              </CardTitle>
              <CardDescription>
                Scan opens the digital smart card first. Then tap Get in touch to choose WhatsApp or the web
                contact form (card photo, details, voice). Up to 15 free preview tests before a paid seat.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="flex flex-col items-center gap-4 sm:flex-row sm:items-start">
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
                      Open digital card (scan landing)
                    </a>
                  ) : null}
                  <p className="text-muted-foreground">
                    After activate you can add more representative QRs up to your seat count.
                  </p>
                </div>
              </div>
              <div className="space-y-2">
                <Label className="text-xs">Digital card theme</Label>
                <SmartCardThemePicker
                  value={themeId}
                  onChange={(id) => {
                    setThemeId(id);
                    if (!draftRep) return;
                    void apiFetch("/smart-card/company", {
                      method: "PATCH",
                      body: JSON.stringify({ theme_id: id }),
                    }).catch(() => {
                      /* preview still holds selection locally until activate */
                    });
                  }}
                  companyName={companyName}
                  personName={draftRep?.name || rep.name}
                  qrToken={draftRep?.qr_token}
                />
              </div>
            </CardContent>
          </Card>
        )}

        {step === 5 && (
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

        {step === 6 && (
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
        confirmLabel="Continue to payment"
        paymentMethods={paymentMethods}
        defaultPaymentMethod={defaultPayMethod}
        loading={saving}
        onConfirm={async (paymentMethod) => {
          setCheckoutOpen(false);
          await activate(paymentMethod);
        }}
      />

      <StripeCardCheckoutDialog
        open={Boolean(stripeCheckout)}
        onOpenChange={(open) => {
          if (!open) {
            setStripeCheckout(null);
            setSaving(false);
          }
        }}
        session={stripeCheckout}
        title="Pay for Smart Card seats"
        onPaid={async (paymentIntentId) => {
          try {
            await completeSmartCardSeatCheckout(paymentIntentId);
            clearSmartCardCardCheckoutState();
            toast.success("Seats activated");
            await qc.invalidateQueries({ queryKey: ["smart-card"] });
            void navigate({ to: "/smart-card" });
          } catch (e) {
            toast.error(e instanceof Error ? e.message : "Could not activate seats");
            throw e;
          } finally {
            setSaving(false);
          }
        }}
      />

      {step < 6 ? (
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
            {saving ? "Saving…" : step === 3 ? "Save & preview" : "Next"}
            <ChevronRight className="size-4" />
          </Button>
        </div>
      ) : null}
    </div>
  );
}
