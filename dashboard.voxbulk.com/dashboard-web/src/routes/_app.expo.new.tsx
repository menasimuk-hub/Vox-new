import { createFileRoute, Link } from "@tanstack/react-router";
import {
  Briefcase,
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  Eye,
  Gift,
  Mail,
  Package,
  QrCode,
  Rocket,
  Target,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Stepper, type WizardStepDef } from "@/components/create-wizard/stepper";
import { ExpoBoothPrintCard } from "@/components/expo-booth-print-card";
import { ExpoPayDialog } from "@/components/expo-pay-dialog";
import {
  categoriesToPayload,
  emptyRepresentative,
  RepresentativesEditor,
  representativesFromApi,
  representativesToPayload,
  type CategoryDraft,
  type RepresentativeDraft,
} from "@/components/expo-booth-sections";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch } from "@/lib/api";
import { buildExpoQrImageUrl, resolveExpoWebUrl } from "@/lib/expo-qr";
import { canLaunchCampaigns, normalizeOrgRole } from "@/lib/org-roles";
import { useSession } from "@/lib/session";
import { cn } from "@/lib/utils";
import { waIndustryIcon } from "@/lib/wa-industry-icon";
import { useQuery, useQueryClient } from "@tanstack/react-query";

type Step = 1 | 2 | 3 | 4 | 5 | 6 | 7;

type Industry = { id: string; slug: string; name: string; addon_question?: string | null };
type Package = {
  id: string;
  name: string;
  tier: string;
  duration_days?: number;
  price_minor: number;
  currency: string;
  features: string[];
  is_featured?: boolean;
  lead_scoring_enabled?: boolean;
  max_categories?: number | null;
};
type QuestionOpt = {
  key: string;
  prompt: string;
  label: string;
  description?: string;
  matches_products?: boolean;
};

type BoothResult = {
  id: string;
  qr_image_url?: string;
  web_url?: string;
  qr_token?: string;
  trigger_text?: string;
  whatsapp_url?: string;
  is_paid?: boolean;
  is_live?: boolean;
  payment_status?: string;
  activated_at?: string | null;
};

type ExpoProfile = {
  visitor_contact_email?: string | null;
  representatives?: Array<Record<string, unknown>>;
  company_website?: string | null;
  notify_mobile?: string | null;
};

const EXPO_STEPS: WizardStepDef[] = [
  { id: 1, title: "Industry", icon: Briefcase },
  { id: 2, title: "Event", icon: CalendarDays },
  { id: 3, title: "Offers", icon: Gift },
  { id: 4, title: "Questions", icon: Target },
  { id: 5, title: "Preview", icon: Eye },
  { id: 6, title: "Package", icon: Package },
  { id: 7, title: "Activate", icon: Rocket },
];

const DEFAULT_Q_KEYS = ["interest", "role", "timeline", "follow_up", "consent_info"];
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function todayIso() {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function defaultFreeGiftText(companyName: string) {
  const name = companyName.trim();
  if (!name) {
    return "Please collect your free gift from our stand team — thanks for completing the short questionnaire!";
  }
  return `Please collect your free gift from ${name}'s stand team — thanks for completing the short questionnaire!`;
}

export const Route = createFileRoute("/_app/expo/new")({
  head: () => ({ meta: [{ title: "Create Expo booth — VoxBulk" }] }),
  component: CreateExpoBooth,
});

function CreateExpoBooth() {
  const { session } = useSession();
  const queryClient = useQueryClient();
  const role = normalizeOrgRole(session?.profile?.role);
  const canCreate = canLaunchCampaigns(role);

  const industriesQ = useQuery({
    queryKey: ["expo", "industries"],
    queryFn: () => apiFetch<{ items: Industry[] }>("/expo/catalog/industries"),
  });
  const packagesQ = useQuery({
    queryKey: ["expo", "packages"],
    queryFn: () => apiFetch<{ items: Package[] }>("/expo/packages?zone=gb"),
  });
  const questionsQ = useQuery({
    queryKey: ["expo", "questions"],
    queryFn: () => apiFetch<{ items: QuestionOpt[] }>("/expo/catalog/questions"),
  });

  const [step, setStep] = React.useState<Step>(1);
  const [industryId, setIndustryId] = React.useState("");
  const [exhibitionName, setExhibitionName] = React.useState("");
  const [venue, setVenue] = React.useState("");
  const [boothCode, setBoothCode] = React.useState("");
  const [company, setCompany] = React.useState(session?.org?.name || "");
  const [visitorContactEmail, setVisitorContactEmail] = React.useState("");
  const [exhibitionStartsAt, setExhibitionStartsAt] = React.useState("");
  const [exhibitionEndsAt, setExhibitionEndsAt] = React.useState("");
  const [selectedQKeys, setSelectedQKeys] = React.useState<string[]>([...DEFAULT_Q_KEYS]);
  const [includeAddon, setIncludeAddon] = React.useState(true);
  const [contactCapture, setContactCapture] = React.useState<"offer_both" | "manual_only" | "card_only">(
    "offer_both",
  );
  const [freeGiftEnabled, setFreeGiftEnabled] = React.useState(false);
  const [freeGiftCustomized, setFreeGiftCustomized] = React.useState(false);
  const [freeGiftText, setFreeGiftText] = React.useState(() =>
    defaultFreeGiftText(session?.org?.name || ""),
  );

  React.useEffect(() => {
    if (freeGiftCustomized) return;
    setFreeGiftText(defaultFreeGiftText(company));
  }, [company, freeGiftCustomized]);

  const [representatives, setRepresentatives] = React.useState<RepresentativeDraft[]>(() => [
    emptyRepresentative(session?.org?.name || ""),
  ]);
  const [companyWebsite, setCompanyWebsite] = React.useState("");
  const [notifyMobile, setNotifyMobile] = React.useState("");

  const [offerEnabled, setOfferEnabled] = React.useState(false);
  const [offerTitle, setOfferTitle] = React.useState("");
  const [offerDescription, setOfferDescription] = React.useState("");
  const [offerClaimUrl, setOfferClaimUrl] = React.useState("");
  const [offerCode, setOfferCode] = React.useState("");

  const [categories, setCategories] = React.useState<CategoryDraft[]>([]);
  const [packageId, setPackageId] = React.useState("");
  const [packageStartDate, setPackageStartDateRaw] = React.useState(() => todayIso());
  const [packageStartDateTouched, setPackageStartDateTouched] = React.useState(false);
  const setPackageStartDate = (v: string) => {
    setPackageStartDateTouched(true);
    setPackageStartDateRaw(v);
  };

  const [saving, setSaving] = React.useState(false);
  const [previewSaving, setPreviewSaving] = React.useState(false);
  const [draftBooth, setDraftBooth] = React.useState<BoothResult | null>(null);
  const [created, setCreated] = React.useState<BoothResult | null>(null);
  const [payOpen, setPayOpen] = React.useState(false);

  // Prefill from org Expo profile (contact email, reps, website, notify mobile).
  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await apiFetch<{ ok: boolean; item: ExpoProfile }>("/expo/profile");
        if (cancelled) return;
        const item = res?.item || {};
        if (item.visitor_contact_email) {
          setVisitorContactEmail((prev) => prev || String(item.visitor_contact_email));
        }
        if (Array.isArray(item.representatives) && item.representatives.length > 0) {
          setRepresentatives(representativesFromApi(item.representatives));
        }
        if (item.company_website) {
          setCompanyWebsite((prev) => prev || String(item.company_website));
        }
        if (item.notify_mobile) {
          setNotifyMobile((prev) => prev || String(item.notify_mobile));
        }
      } catch {
        // Optional prefill — ignore failures silently.
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Keep the package start date synced to the event start date until the user edits it.
  React.useEffect(() => {
    if (packageStartDateTouched || !exhibitionStartsAt) return;
    setPackageStartDateRaw(exhibitionStartsAt.slice(0, 10));
  }, [exhibitionStartsAt, packageStartDateTouched]);

  // Auto-include the trade-show offer question once an offer is configured.
  React.useEffect(() => {
    if (!offerEnabled) return;
    setSelectedQKeys((keys) => (keys.includes("offer_interest") ? keys : [...keys, "offer_interest"]));
  }, [offerEnabled]);

  const industries = industriesQ.data?.items || [];
  const packages = packagesQ.data?.items || [];
  const industry = industries.find((i) => i.id === industryId);

  const questionBank = React.useMemo(() => {
    const base = questionsQ.data?.items || [];
    const addon = String(industry?.addon_question || "").trim();
    if (!addon) return base;
    if (base.some((q) => q.key === "industry_addon")) {
      return base.map((q) => (q.key === "industry_addon" ? { ...q, prompt: addon, label: "Industry question" } : q));
    }
    return [
      ...base.slice(0, 2),
      { key: "industry_addon", prompt: addon, label: "Industry question" },
      ...base.slice(2),
    ];
  }, [questionsQ.data?.items, industry?.addon_question]);

  const selectedPackage = packages.find((p) => p.id === packageId);
  const packageDays = Math.max(1, selectedPackage?.duration_days || 1);
  const packageEndDate = React.useMemo(() => {
    if (!packageStartDate) return "";
    const start = new Date(`${packageStartDate}T12:00:00`);
    if (Number.isNaN(start.getTime())) return "";
    start.setDate(start.getDate() + packageDays - 1);
    const y = start.getFullYear();
    const m = String(start.getMonth() + 1).padStart(2, "0");
    const day = String(start.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  }, [packageDays, packageStartDate]);

  const eventDatesLabel = React.useMemo(() => {
    const start = exhibitionStartsAt ? exhibitionStartsAt.slice(0, 10) : "";
    const end = exhibitionEndsAt ? exhibitionEndsAt.slice(0, 10) : "";
    if (start && end) return `${start} → ${end}`;
    return start || null;
  }, [exhibitionStartsAt, exhibitionEndsAt]);

  const canNext: Record<Step, boolean> = {
    1: Boolean(industryId),
    2: Boolean(exhibitionName.trim() && company.trim() && EMAIL_RE.test(visitorContactEmail.trim())),
    3: true,
    4: selectedQKeys.length > 0,
    5: true,
    6: Boolean(packageId),
    7: true,
  };

  function nextBlockedReason(s: Step): string | null {
    if (canNext[s]) return null;
    if (s === 1) return "Choose an industry to continue";
    if (s === 2) {
      if (!exhibitionName.trim()) return "Enter the exhibition name to continue";
      if (!company.trim()) return "Enter the company name on WhatsApp to continue";
      if (!visitorContactEmail.trim()) return "Enter a contact email to continue";
      if (!EMAIL_RE.test(visitorContactEmail.trim())) return "Enter a valid contact email to continue";
      return "Fill the required event fields to continue";
    }
    if (s === 4) return "Select at least one qualifying question to continue";
    if (s === 6) return "Choose a package to continue";
    return null;
  }

  const contactEmailInvalid =
    Boolean(visitorContactEmail.trim()) && !EMAIL_RE.test(visitorContactEmail.trim());

  function buildPayload(extra?: Record<string, unknown>) {
    const keys = [...selectedQKeys];
    if (includeAddon && industry?.addon_question && !keys.includes("industry_addon")) {
      keys.splice(Math.max(0, keys.indexOf("consent_info")), 0, "industry_addon");
    }
    if (offerEnabled && offerTitle.trim() && !keys.includes("offer_interest")) {
      keys.splice(Math.max(0, keys.indexOf("consent_info")), 0, "offer_interest");
    }
    return {
      industry_id: industryId,
      exhibition_name: exhibitionName.trim(),
      venue: venue.trim() || null,
      booth_code: boothCode.trim() || exhibitionName.trim(),
      name: boothCode.trim() || exhibitionName.trim(),
      company_display_name: company.trim(),
      visitor_contact_email: visitorContactEmail.trim(),
      exhibition_starts_at: exhibitionStartsAt || packageStartDate,
      exhibition_ends_at: exhibitionEndsAt || null,
      include_industry_addon: includeAddon,
      selected_question_keys: keys,
      contact_capture: contactCapture,
      free_gift_enabled: freeGiftEnabled,
      free_gift_text: freeGiftEnabled ? freeGiftText.trim() : null,
      package_id: packageId || undefined,
      start_date: packageStartDate || exhibitionStartsAt?.slice(0, 10),
      representatives: representativesToPayload(representatives),
      company_website: companyWebsite.trim() || null,
      notify_mobile: notifyMobile.trim() || null,
      categories: categoriesToPayload(categories),
      offer:
        offerEnabled && offerTitle.trim()
          ? {
              title: offerTitle.trim(),
              description: offerDescription.trim() || null,
              claim_url: offerClaimUrl.trim() || null,
              code: offerCode.trim() || null,
            }
          : null,
      draft_booth_id: draftBooth?.id,
      ...extra,
    };
  }

  async function runPreviewDraft() {
    setPreviewSaving(true);
    try {
      const payload = buildPayload({ is_preview_draft: true });
      const res = await apiFetch<{ ok: boolean; item: BoothResult }>("/expo/booths/preview-draft", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setDraftBooth(res.item);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not generate the preview");
    } finally {
      setPreviewSaving(false);
    }
  }

  React.useEffect(() => {
    if (step === 5) {
      void runPreviewDraft();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step]);

  const draftWebUrlBase = resolveExpoWebUrl({ web_url: draftBooth?.web_url, qr_token: draftBooth?.qr_token });
  const draftWebUrl = React.useMemo(() => {
    if (!draftWebUrlBase) return "";
    try {
      const u = new URL(draftWebUrlBase);
      u.searchParams.set("preview", "1");
      return u.toString();
    } catch {
      return draftWebUrlBase.includes("?") ? `${draftWebUrlBase}&preview=1` : `${draftWebUrlBase}?preview=1`;
    }
  }, [draftWebUrlBase]);
  const draftQrSrc = draftWebUrl ? buildExpoQrImageUrl(draftWebUrl, 280) : "";

  if (!canCreate) {
    return (
      <Card>
        <CardContent className="p-8 text-center text-sm text-muted-foreground">
          Your role cannot create Expo booths. Ask an owner or manager.
        </CardContent>
      </Card>
    );
  }

  const activate = async () => {
    if (
      selectedPackage &&
      typeof selectedPackage.max_categories === "number" &&
      categories.length > selectedPackage.max_categories
    ) {
      toast.error(
        `${selectedPackage.name} allows up to ${selectedPackage.max_categories} categor${
          selectedPackage.max_categories === 1 ? "y" : "ies"
        }. Remove a category or choose a bigger package.`,
      );
      setStep(6);
      return;
    }
    setSaving(true);
    try {
      const payload = buildPayload({ is_preview_draft: false, draft_booth_id: draftBooth?.id });
      const res = await apiFetch<{ ok: boolean; item: BoothResult }>("/expo/booths", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setCreated(res.item);
      setStep(7);
      // Seed Saved booths cache so the new QR appears immediately
      queryClient.setQueryData<{ ok: boolean; items: Array<typeof res.item> }>(["expo", "booths"], (prev) => {
        const items = prev?.items ? [...prev.items] : [];
        if (!items.some((b) => b.id === res.item.id)) {
          items.unshift(res.item);
        }
        return { ok: true, items };
      });
      await queryClient.invalidateQueries({ queryKey: ["expo"] });
      toast.success("Booth saved — pay to go live, or use up to 15 preview tests unpaid");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not create booth");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="VoxBulk Expo"
        title="Create Expo booth"
        description="Set up your exhibition QR, qualifying questions, and product PDF library."
      />

      <Stepper
        steps={EXPO_STEPS}
        current={step}
        onStepClick={(n) => n <= step && setStep(n as Step)}
      />

      <div key={step} className="animate-fade-in">
        {step === 1 && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Choose your industry</CardTitle>
              <CardDescription>We'll tailor a suggested qualifying question for your stand.</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {industries.map((ind) => {
                const Icon = waIndustryIcon(ind.name, ind.slug);
                const selected = industryId === ind.id;
                return (
                  <button
                    key={ind.id}
                    type="button"
                    onClick={() => setIndustryId(ind.id)}
                    className={cn(
                      "group rounded-xl border p-4 text-left transition-all duration-200",
                      "hover:-translate-y-0.5 hover:border-primary/50 hover:shadow-md",
                      selected
                        ? "border-primary bg-primary/5 shadow-md shadow-primary/10 ring-2 ring-primary/20"
                        : "border-border bg-background",
                    )}
                  >
                    <div className="flex items-start gap-3">
                      <span
                        className={cn(
                          "grid size-10 place-items-center rounded-xl border transition",
                          selected
                            ? "border-primary/30 bg-primary text-primary-foreground"
                            : "border-border bg-muted/40 text-muted-foreground group-hover:border-primary/30 group-hover:text-primary",
                        )}
                      >
                        <Icon className="size-5" />
                      </span>
                      <div className="min-w-0">
                        <p className="font-medium">{ind.name}</p>
                        {ind.addon_question ? (
                          <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{ind.addon_question}</p>
                        ) : null}
                      </div>
                    </div>
                  </button>
                );
              })}
            </CardContent>
          </Card>
        )}

        {step === 2 && (
          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Event & booth</CardTitle>
                <CardDescription>
                  Two fields per row — keep stand details clear for the QR message and visitor contact.
                </CardDescription>
              </CardHeader>
              <CardContent className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label>
                    Exhibition name <span className="text-destructive">*</span>
                  </Label>
                  <Input
                    value={exhibitionName}
                    onChange={(e) => setExhibitionName(e.target.value)}
                    placeholder="UK Construction Week"
                  />
                </div>
                <div className="space-y-2">
                  <Label>Venue</Label>
                  <Input value={venue} onChange={(e) => setVenue(e.target.value)} placeholder="Excel London" />
                </div>
                <div className="space-y-2">
                  <Label>Booth / stand code</Label>
                  <Input value={boothCode} onChange={(e) => setBoothCode(e.target.value)} placeholder="H45" />
                </div>
                <div className="space-y-2">
                  <Label>
                    Company name on WhatsApp <span className="text-destructive">*</span>
                  </Label>
                  <Input value={company} onChange={(e) => setCompany(e.target.value)} placeholder="Acme Supplies" />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="expo-event-starts">Exhibition starts</Label>
                  <Input
                    id="expo-event-starts"
                    type="datetime-local"
                    value={exhibitionStartsAt}
                    onChange={(e) => setExhibitionStartsAt(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="expo-event-ends">Exhibition ends</Label>
                  <Input
                    id="expo-event-ends"
                    type="datetime-local"
                    value={exhibitionEndsAt}
                    onChange={(e) => setExhibitionEndsAt(e.target.value)}
                  />
                </div>
                <div className="space-y-2 sm:col-span-2">
                  <Label htmlFor="expo-contact-email">
                    Contact email (shown to visitors) <span className="text-destructive">*</span>
                  </Label>
                  <div className="relative">
                    <Mail className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
                    <Input
                      id="expo-contact-email"
                      className={cn("pl-8", contactEmailInvalid ? "border-destructive" : "")}
                      type="email"
                      required
                      value={visitorContactEmail}
                      onChange={(e) => setVisitorContactEmail(e.target.value)}
                      placeholder="hello@acme.com"
                      aria-invalid={contactEmailInvalid}
                    />
                  </div>
                  {contactEmailInvalid ? (
                    <p className="text-xs text-destructive">Enter a valid email address</p>
                  ) : (
                    <p className="text-xs text-muted-foreground">
                      Required — printed on the booth card and used if a visitor needs to reach you by email.
                    </p>
                  )}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Representative</CardTitle>
                <CardDescription>
                  One stand contact for the digital business card and hot-lead WhatsApp alerts. Visitor emails use the
                  contact email above.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <RepresentativesEditor
                  representatives={representatives}
                  onChange={setRepresentatives}
                  companyWebsite={companyWebsite}
                  onCompanyWebsiteChange={setCompanyWebsite}
                  notifyMobile={notifyMobile}
                  onNotifyMobileChange={setNotifyMobile}
                  maxRepresentatives={1}
                />
              </CardContent>
            </Card>
          </div>
        )}

        {step === 3 && (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Gift className="size-4 text-primary" /> Trade-show offer
              </CardTitle>
              <CardDescription>
                Optional — give visitors an exclusive show-only deal. Skip this step if you don't want one.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <label className="flex items-start gap-3 rounded-xl border p-4">
                <Checkbox
                  checked={offerEnabled}
                  onCheckedChange={(v) => setOfferEnabled(Boolean(v))}
                  className="mt-0.5"
                />
                <span>
                  <span className="font-medium">Add a trade-show offer</span>
                  <span className="mt-0.5 block text-xs text-muted-foreground">
                    Adds a qualifying question asking visitors if they're interested — interested visitors get the
                    offer details.
                  </span>
                </span>
              </label>

              {offerEnabled ? (
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="space-y-2 sm:col-span-2">
                    <Label>Offer title</Label>
                    <Input
                      value={offerTitle}
                      onChange={(e) => setOfferTitle(e.target.value)}
                      placeholder="20% off your first order"
                    />
                  </div>
                  <div className="space-y-2 sm:col-span-2">
                    <Label>Offer description (optional)</Label>
                    <Textarea
                      value={offerDescription}
                      onChange={(e) => setOfferDescription(e.target.value)}
                      rows={3}
                      placeholder="Valid for orders placed within 30 days of the show — mention this code at checkout."
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Claim URL (optional)</Label>
                    <Input
                      value={offerClaimUrl}
                      onChange={(e) => setOfferClaimUrl(e.target.value)}
                      placeholder="https://acme.com/offer"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Offer code (optional)</Label>
                    <Input
                      value={offerCode}
                      onChange={(e) => setOfferCode(e.target.value)}
                      placeholder="EXPO20"
                    />
                  </div>
                </div>
              ) : (
                <p className="rounded-xl border border-dashed p-4 text-center text-sm text-muted-foreground">
                  Skip — no offer question will be shown to visitors. You can add one later by editing this booth.
                </p>
              )}
            </CardContent>
          </Card>
        )}

        {step === 4 && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Qualifying questions</CardTitle>
              <CardDescription>
                Fixed contact first — visitors see this as the first WhatsApp / web message:
                <span className="font-medium text-foreground"> photo of a business card</span>, or type name /
                company (and mobile on web). Choose which options are allowed below.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="rounded-xl border bg-muted/20 p-4">
                <p className="text-sm font-medium">Fixed · Contact capture</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  WhatsApp & web: visitor can send a business-card photo (skips name, company, mobile) or type
                  details. Web always collects mobile when typing.
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

              <div>
                <p className="mb-2 text-sm font-medium">Select more questions</p>
                <div className="grid gap-2 sm:grid-cols-2">
                  {questionBank.map((q) => {
                    const checked = selectedQKeys.includes(q.key);
                    const lockedOn = q.key === "offer_interest" && offerEnabled;
                    return (
                      <label
                        key={q.key}
                        className={cn(
                          "flex cursor-pointer gap-3 rounded-xl border p-3 transition hover:border-primary/40",
                          checked && "border-primary bg-primary/5",
                          lockedOn && "cursor-default opacity-90",
                        )}
                      >
                        <Checkbox
                          checked={checked}
                          disabled={lockedOn}
                          onCheckedChange={(v) => {
                            setSelectedQKeys((keys) =>
                              v ? [...keys, q.key] : keys.filter((k) => k !== q.key),
                            );
                          }}
                        />
                        <span className="min-w-0">
                          <span className="flex flex-wrap items-center gap-2 text-sm font-medium">
                            {q.label}
                            {q.matches_products ? (
                              <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-normal text-primary">
                                Matches products
                              </span>
                            ) : null}
                            {lockedOn ? (
                              <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-[10px] font-normal text-amber-700">
                                Auto-added · you set an offer
                              </span>
                            ) : null}
                          </span>
                          <span className="mt-0.5 block text-xs text-muted-foreground">{q.prompt}</span>
                          {q.description ? (
                            <span className="mt-1 block text-[11px] text-muted-foreground/80">{q.description}</span>
                          ) : null}
                        </span>
                      </label>
                    );
                  })}
                </div>
                {industry?.addon_question ? (
                  <label className="mt-3 flex items-center gap-2 text-sm">
                    <Checkbox checked={includeAddon} onCheckedChange={(v) => setIncludeAddon(Boolean(v))} />
                    Include industry question: {industry.addon_question}
                  </label>
                ) : null}
              </div>

              <div className="rounded-xl border p-4">
                <label className="flex items-start gap-3">
                  <Checkbox
                    checked={freeGiftEnabled}
                    onCheckedChange={(v) => {
                      const on = Boolean(v);
                      setFreeGiftEnabled(on);
                      if (on && !freeGiftCustomized) {
                        setFreeGiftText(defaultFreeGiftText(company));
                      }
                    }}
                    className="mt-0.5"
                  />
                  <span>
                    <span className="font-medium">Offer a free gift after the questionnaire</span>
                    <span className="mt-0.5 block text-xs text-muted-foreground">
                      After the thank-you message, tell visitors how to collect their gift. Default text includes your
                      company name so visitors know which stand it is — you can edit it anytime.
                    </span>
                  </span>
                </label>
                {freeGiftEnabled ? (
                  <Textarea
                    className="mt-3"
                    value={freeGiftText}
                    onChange={(e) => {
                      setFreeGiftCustomized(true);
                      setFreeGiftText(e.target.value);
                    }}
                    rows={2}
                  />
                ) : null}
              </div>
            </CardContent>
          </Card>
        )}

        {step === 5 && (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Eye className="size-4 text-primary" /> Preview journey
              </CardTitle>
              <CardDescription>
                This is exactly what visitors will see when they scan — nothing here is saved as a live booth.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900">
                Preview only — scan to try the journey. Nothing is saved. Go back to edit.
              </div>

              {previewSaving && !draftBooth ? (
                <div className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">
                  Generating your preview…
                </div>
              ) : draftBooth ? (
                <ExpoBoothPrintCard
                  boothId={draftBooth.id}
                  qrSrc={draftQrSrc}
                  webUrl={draftWebUrl}
                  qrToken={draftBooth.qr_token}
                  company={company}
                  boothCode={boothCode || exhibitionName}
                  eventName={exhibitionName}
                  eventDates={eventDatesLabel}
                  companyWebsite={companyWebsite}
                  contactEmail={visitorContactEmail}
                />
              ) : (
                <div className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">
                  <p>Could not generate a preview.</p>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    className="mt-3"
                    onClick={() => void runPreviewDraft()}
                  >
                    Try again
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {step === 6 && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Choose package</CardTitle>
              <CardDescription>How many days should this booth QR stay active?</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-3 sm:grid-cols-3">
              {packages.map((pkg) => {
                const days = pkg.duration_days || 1;
                const featured = Boolean(pkg.is_featured);
                return (
                  <button
                    key={pkg.id}
                    type="button"
                    onClick={() => setPackageId(pkg.id)}
                    className={cn(
                      "relative rounded-xl border p-4 text-left transition hover:-translate-y-0.5 hover:shadow-md",
                      packageId === pkg.id
                        ? "border-primary bg-primary/5 ring-2 ring-primary/20"
                        : "hover:border-primary/40",
                      featured && packageId !== pkg.id && "border-primary/25",
                    )}
                  >
                    {featured ? (
                      <span className="absolute -top-2 left-3 rounded-full bg-primary px-2 py-0.5 text-[10px] font-semibold text-primary-foreground">
                        Most popular
                      </span>
                    ) : null}
                    <p className="font-medium">{pkg.name}</p>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      Active for {days} day{days === 1 ? "" : "s"}
                    </p>
                    <p className="mt-2 text-lg font-semibold">
                      £{(pkg.price_minor / 100).toFixed(0)}
                      <span className="text-sm font-normal text-muted-foreground"> / exhibition</span>
                    </p>
                    <ul className="mt-2 space-y-1 text-xs text-muted-foreground">
                      {(pkg.features || []).slice(0, 4).map((f) => (
                        <li key={f} className="flex gap-1.5">
                          <span className="text-primary">✓</span> {f}
                        </li>
                      ))}
                    </ul>
                  </button>
                );
              })}
            </CardContent>
          </Card>
        )}

        {step === 7 && (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <QrCode className="size-4 text-primary" /> Activate QR
              </CardTitle>
              <CardDescription>
                Set when the package starts. End date is calculated from the package length. Before the start
                date you get 15 mobile preview tests.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {!created ? (
                <>
                  {eventDatesLabel ? (
                    <p className="text-xs text-muted-foreground">
                      Event dates: <span className="font-medium text-foreground">{eventDatesLabel}</span>
                    </p>
                  ) : null}
                  <div className="grid gap-3 sm:grid-cols-2">
                    <div className="space-y-1.5">
                      <Label htmlFor="expo-start-date">Package start date</Label>
                      <Input
                        id="expo-start-date"
                        type="date"
                        value={packageStartDate}
                        onChange={(e) => setPackageStartDate(e.target.value)}
                      />
                    </div>
                    <div className="space-y-1.5">
                      <Label htmlFor="expo-end-date">Auto end date</Label>
                      <Input id="expo-end-date" type="date" value={packageEndDate} readOnly disabled />
                      <p className="text-xs text-muted-foreground">
                        {selectedPackage
                          ? `${selectedPackage.name} · ${packageDays} day${packageDays === 1 ? "" : "s"}`
                          : "Choose a package first"}
                      </p>
                    </div>
                  </div>
                  <div className="rounded-lg border bg-muted/40 px-3 py-2 text-sm text-muted-foreground">
                    <p className="font-medium text-foreground">Save unpaid · pay to go live</p>
                    <p className="mt-0.5 text-xs">
                      Save your design and QR now. You get up to 15 preview tests unpaid. The booth goes live for
                      the package window only after Stripe or Airwallex payment.
                    </p>
                  </div>
                  <p className="text-sm text-muted-foreground">
                    Creates your booth, WhatsApp trigger text, and downloadable QR (status: Unpaid).
                  </p>
                  <Button onClick={() => void activate()} disabled={saving || !packageId || !packageStartDate}>
                    {saving ? "Saving…" : "Save Expo booth"}
                  </Button>
                </>
              ) : (
                <div className="space-y-6">
                  {(() => {
                    const webUrl = resolveExpoWebUrl({
                      web_url: created.web_url,
                      qr_token: created.qr_token,
                    });
                    const qrSrc =
                      (created.qr_image_url && String(created.qr_image_url).trim()) ||
                      (webUrl ? buildExpoQrImageUrl(webUrl, 280) : "");
                    return (
                      <>
                        <div className="border-b pb-6">
                          <h3 className="mb-3 text-sm font-semibold">Print booth card</h3>
                          <ExpoBoothPrintCard
                            boothId={created.id}
                            qrSrc={qrSrc}
                            webUrl={webUrl}
                            qrToken={created.qr_token}
                            company={company}
                            boothCode={boothCode || exhibitionName}
                            eventName={exhibitionName}
                            eventDates={
                              packageStartDate
                                ? packageEndDate
                                  ? `${packageStartDate} → ${packageEndDate}`
                                  : packageStartDate
                                : null
                            }
                            companyWebsite={companyWebsite}
                            contactEmail={
                              visitorContactEmail || representatives.find((r) => r.email?.trim())?.email || null
                            }
                          />
                        </div>

                        <div className="flex flex-col items-start gap-4 sm:flex-row">
                          {qrSrc ? (
                            <img
                              src={qrSrc}
                              alt="Expo QR"
                              className="size-40 rounded-xl border bg-white p-2"
                              referrerPolicy="no-referrer"
                            />
                          ) : null}
                          <div className="space-y-2 text-sm">
                            <p className="font-medium">
                              {created.is_paid || created.payment_status === "paid"
                                ? created.is_live
                                  ? "Booth live"
                                  : "Booth paid — waiting for start date"
                                : "Booth saved (unpaid)"}
                            </p>
                            <p className="text-muted-foreground">
                              Window {packageStartDate}
                              {packageEndDate ? ` → ${packageEndDate}` : ""} ·{" "}
                              {created.is_paid || created.payment_status === "paid"
                                ? "Paid — live after start date"
                                : "Pay to go live · 15 preview tests unpaid"}
                            </p>
                            {webUrl ? (
                              <a
                                href={webUrl}
                                target="_blank"
                                rel="noreferrer"
                                className="block break-all text-sky-700 hover:underline"
                              >
                                {webUrl}
                              </a>
                            ) : null}
                            <p className="max-w-md text-muted-foreground">{created.trigger_text}</p>
                            <div className="flex flex-wrap gap-2">
                              {!(created.is_paid || created.payment_status === "paid") ? (
                                <Button size="sm" onClick={() => setPayOpen(true)}>
                                  Pay with card
                                </Button>
                              ) : null}
                              <Button asChild variant="outline" size="sm">
                                <Link to="/expo">View saved booths</Link>
                              </Button>
                              <Button asChild size="sm" variant={created.is_paid ? "outline" : "ghost"}>
                                <Link to="/expo/leads" search={{ booth_id: created.id }}>
                                  View leads
                                </Link>
                              </Button>
                            </div>
                          </div>
                        </div>
                      </>
                    );
                  })()}
                </div>
              )}
            </CardContent>
          </Card>
        )}
      </div>

      <ExpoPayDialog
        boothId={created?.id || null}
        boothName={boothCode.trim() || exhibitionName.trim() || company.trim() || "Expo booth"}
        open={payOpen}
        onOpenChange={setPayOpen}
        onPaid={(booth) => {
          if (booth && created) {
            setCreated({
              ...created,
              is_paid: Boolean(booth.is_paid ?? true),
              is_live: Boolean(booth.is_live),
              payment_status: String(booth.payment_status || "paid"),
              activated_at: (booth.activated_at as string | null | undefined) ?? created.activated_at,
            });
          }
          void queryClient.invalidateQueries({ queryKey: ["expo"] });
        }}
      />

      {step < 7 || !created ? (
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between gap-3">
            <Button
              type="button"
              variant="outline"
              disabled={step === 1}
              onClick={() => setStep((s) => (s > 1 ? ((s - 1) as Step) : s))}
            >
              <ChevronLeft className="mr-1 size-4" /> Back
            </Button>
            {step < 7 ? (
              <div className="flex flex-col items-end gap-1">
                {nextBlockedReason(step) ? (
                  <p className="max-w-xs text-right text-xs text-muted-foreground">{nextBlockedReason(step)}</p>
                ) : null}
                <Button
                  type="button"
                  disabled={!canNext[step]}
                  onClick={() => {
                    const reason = nextBlockedReason(step);
                    if (reason) {
                      toast.message(reason);
                      return;
                    }
                    setStep((s) => (s < 7 ? ((s + 1) as Step) : s));
                  }}
                >
                  Next <ChevronRight className="ml-1 size-4" />
                </Button>
              </div>
            ) : (
              <Button type="button" disabled={saving || !packageId || Boolean(created)} onClick={() => void activate()}>
                {saving ? "Saving…" : "Save booth"}
              </Button>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}
