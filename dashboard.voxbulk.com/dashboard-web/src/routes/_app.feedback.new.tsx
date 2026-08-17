import { createFileRoute, Link } from "@tanstack/react-router";
import * as React from "react";
import {
  ArrowRight,
  Briefcase,
  ChartBar as BarChart3,
  Check,
  ChevronLeft,
  ChevronRight,
  CircleCheck as CheckCircle2,
  Download,
  Hotel,
  LayoutDashboard,
  Lock,
  MapPin,
  MessageSquarePlus,
  Plus,
  Printer,
  QrCode,
  Rocket,
  Scissors,
  ShoppingBag,
  Sparkles,
  Sparkles as SparkIcon,
  Target,
  Trash2,
  UtensilsCrossed,
  Dumbbell,
  CalendarDays,
  Palette,
  PhoneCall,
} from "lucide-react";
import { toast } from "sonner";

import { AiFollowUpStep, aiFollowUpFromApi, aiFollowUpToApi, defaultAiFollowUp, type AiFollowUpConfig } from "@/components/ai-follow-up-step";
import { FeedbackTopicPicker } from "@/components/feedback-topic-picker";
import { FeedbackWebThemePicker } from "@/components/feedback-web-theme-picker";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import {
  useCreateFeedbackLocation,
  usePreviewFeedbackLocation,
  useFeedbackIndustries,
  useFeedbackMarketingSubscriberCount,
  useFeedbackSurveyTypes,
  useFeedbackSubscription,
  useFeedbackEntitlement,
  useFeedbackLocations,
  useOrganisation,
  type FeedbackIndustry,
  type FeedbackLocation,
  type FeedbackSurveyType,
} from "@/lib/queries";
import { cn } from "@/lib/utils";
import { feedbackRemainingSummary } from "@/lib/feedback-usage";
import { canDuplicateFeedbackSurvey, isMultiLocationFeedbackPlan } from "@/lib/feedback-plan";
import {
  BASE_TEMPLATE,
  CATEGORY_TEMPLATES,
  SEASON_TEMPLATES,
  EVENT_TEMPLATES,
} from "@/lib/feedback-templates";
import { buildWebThemePayload, webThemeFromApi, type WebThemeWizardState } from "@/lib/feedback-theme-preview";

export const Route = createFileRoute("/_app/feedback/new")({
  head: () => ({ meta: [{ title: "Create QR survey — VoxBulk" }] }),
  validateSearch: (search: Record<string, unknown>) => ({
    duplicate_from: typeof search.duplicate_from === "string" ? search.duplicate_from : undefined,
  }),
  component: CreateFeedback,
});

const INDUSTRY_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  restaurant: UtensilsCrossed,
  retail: ShoppingBag,
  salon: Scissors,
  hotel: Hotel,
  fitness: Dumbbell,
  events: CalendarDays,
  others: SparkIcon,
};

function industryIcon(industry: FeedbackIndustry) {
  return INDUSTRY_ICONS[industry.slug] || SparkIcon;
}

function previewTrigger(company: string, branch?: string) {
  const branchLabel = branch?.trim() || "Main branch";
  const slug = (part: string) =>
    part
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "")
      .slice(0, 20) || "location";
  const token = `${slug(company)}-${slug(branchLabel)}-preview`;
  return `Hi! I'd like to share feedback for ${company} at ${branchLabel}. ${token}`;
}

function buildQrImageUrl(waUrl: string, size = 320) {
  return `https://api.qrserver.com/v1/create-qr-code/?size=${size}x${size}&margin=8&data=${encodeURIComponent(waUrl)}`;
}

type Step = 1 | 2 | 3 | 4 | 5 | 6;
type Branch = { id: string; name: string };

const STEPS = [
  { id: 1, title: "Industry", icon: Briefcase },
  { id: 2, title: "Survey type", icon: Target },
  { id: 3, title: "Look & feel", icon: Palette },
  { id: 4, title: "QR & branches", icon: QrCode },
  { id: 5, title: "AI follow-up", icon: PhoneCall },
  { id: 6, title: "Launch", icon: Rocket },
] as const;

function CreateFeedback() {
  const { duplicate_from: duplicateFrom } = Route.useSearch();
  const orgQ = useOrganisation();
  const subscriptionQ = useFeedbackSubscription();
  const entitlementQ = useFeedbackEntitlement();
  const liveEntitled = Boolean(
    subscriptionQ.data?.active ||
      entitlementQ.data?.can_activate_without_payment ||
      entitlementQ.data?.mode === "live",
  );
  const locationsQ = useFeedbackLocations();
  const industriesQ = useFeedbackIndustries();
  const createM = useCreateFeedbackLocation();
  const previewM = usePreviewFeedbackLocation();

  const [step, setStep] = React.useState<Step>(1);
  const [industryId, setIndustryId] = React.useState("");
  const [selectedTypeIds, setSelectedTypeIds] = React.useState<string[]>([]);
  const [openQuestion, setOpenQuestion] = React.useState(true);
  const [branches, setBranches] = React.useState<Branch[]>([{ id: "b1", name: "Main branch" }]);
  const [marketingOptIn, setMarketingOptIn] = React.useState(false);
  const marketingCountQ = useFeedbackMarketingSubscriberCount();
  const [consent, setConsent] = React.useState(false);
  const [previewQr, setPreviewQr] = React.useState<{ wa_url: string; qr_image_url: string; trigger_text: string } | null>(null);
  const [done, setDone] = React.useState(false);
  const [createdLocations, setCreatedLocations] = React.useState<FeedbackLocation[]>([]);
  const [duplicateMode, setDuplicateMode] = React.useState(false);
  const [duplicateSourceName, setDuplicateSourceName] = React.useState("");
  const [aiFollowUp, setAiFollowUp] = React.useState<AiFollowUpConfig>(defaultAiFollowUp);
  const [webTheme, setWebTheme] = React.useState<WebThemeWizardState>({
    baseTemplateId: "auto",
    overlayIds: [],
    overlayMode: "auto",
    customEventLabel: "",
  });

  const duplicateInitialized = React.useRef(false);
  React.useEffect(() => {
    if (!duplicateFrom || duplicateInitialized.current || !locationsQ.data) return;
    const source = locationsQ.data.find((l) => l.id === duplicateFrom);
    if (!source) {
      toast.error("Source survey not found.");
      return;
    }
    if (!isMultiLocationFeedbackPlan(subscriptionQ.data)) {
      toast.error("Upgrade to a multi-location plan to duplicate surveys.");
      window.location.assign("/account/feedback/packages");
      return;
    }
    if (!canDuplicateFeedbackSurvey(subscriptionQ.data, locationsQ.data.length)) {
      toast.error("Location limit reached. Upgrade your plan or remove a location.");
      return;
    }
    duplicateInitialized.current = true;
    setDuplicateMode(true);
    setDuplicateSourceName(source.name);
    setIndustryId(source.industry_id);
    setSelectedTypeIds(
      source.selected_survey_type_ids?.length
        ? source.selected_survey_type_ids
        : [source.survey_type_id],
    );
    setOpenQuestion(source.open_question_enabled !== false);
    setBranches([{ id: "dup1", name: "" }]);
    setWebTheme(webThemeFromApi(source.web_theme as Record<string, unknown> | undefined));
    setAiFollowUp(aiFollowUpFromApi(source.ai_follow_up as Record<string, unknown> | undefined));
    setStep(4);
  }, [duplicateFrom, locationsQ.data, subscriptionQ.data]);

  const typesQ = useFeedbackSurveyTypes(industryId);
  const industries = industriesQ.data || [];
  const surveyTypes = typesQ.data || [];
  const industry = industries.find((i) => i.id === industryId);
  const companyName = String(orgQ.data?.name || "Your business").trim();
  const selectedTypes = surveyTypes.filter((t) => selectedTypeIds.includes(t.id));

  React.useEffect(() => {
    if (!industryId || !typesQ.isFetched) return;
    const validTypeIds = new Set(surveyTypes.map((row) => String(row.id)));
    setSelectedTypeIds((prev) => {
      const next = prev.filter((id) => validTypeIds.has(id));
      if (next.length === prev.length && next.every((id, idx) => id === prev[idx])) return prev;
      return next;
    });
  }, [industryId, typesQ.isFetched, surveyTypes]);

  const canNext: Record<Step, boolean> = {
    1: !!industryId,
    2: selectedTypeIds.length >= 1,
    3: true,
    4: branches.length >= 1 && branches.every((b) => b.name.trim().length > 0),
    5: true,
    6: consent,
  };

  const webThemePayload = React.useMemo(() => buildWebThemePayload(webTheme), [webTheme]);
  const { baseTemplateId, overlayIds, overlayMode, customEventLabel } = webTheme;

  React.useEffect(() => {
    if ((step !== 4 && step !== 5 && step !== 6) || !industryId || selectedTypeIds.length === 0) return;
    const branch = branches[0]?.name?.trim() || "Main branch";
    previewM
      .mutateAsync({
        industry_id: industryId,
        selected_survey_type_ids: selectedTypeIds,
        name: branch,
        open_question_enabled: openQuestion,
        marketing_opt_in_enabled: marketingOptIn,
      })
      .then((res) => {
        if (res.item) {
          setPreviewQr({
            wa_url: res.item.wa_url,
            qr_image_url: res.item.qr_image_url,
            trigger_text: res.item.trigger_text,
          });
        }
      })
      .catch(() => setPreviewQr(null));
  }, [step, industryId, selectedTypeIds, branches, openQuestion, marketingOptIn]);

  const onSave = async (asLive: boolean) => {
    if (!industryId || selectedTypeIds.length === 0) return;
    if (asLive && !liveEntitled) {
      toast.error("Activate your package first, or save as a demo QR.");
      window.location.assign("/account/feedback/packages");
      return;
    }
    try {
      const created: FeedbackLocation[] = [];
      for (const branch of branches) {
        const res = await createM.mutateAsync({
          industry_id: industryId,
          survey_type_id: selectedTypeIds[0],
          selected_survey_type_ids: selectedTypeIds,
          name: branch.name.trim(),
          open_question_enabled: openQuestion,
          marketing_opt_in_enabled: marketingOptIn,
          web_theme: webThemePayload,
          ai_follow_up: aiFollowUpToApi(aiFollowUp),
          ...(asLive ? { status: "active" } : { status: "preview" }),
        });
        if (res.item) created.push(res.item);
      }
      setCreatedLocations(created);
      toast.success(
        asLive
          ? "QR survey is live"
          : "QR survey saved for demo testing (20 scans). Pay later to activate.",
      );
      setDone(true);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not save QR survey");
    }
  };

  if (done) {
    return <LaunchSuccess locations={createdLocations} company={companyName} />;
  }

  return (
    <div className="flex w-full flex-col gap-6" data-demo-target="feedback-new">
      <PageHeader
        eyebrow="Customer feedback"
        title={duplicateMode ? "Duplicate QR survey" : "Create QR feedback survey"}
        description={
          duplicateMode
            ? `Copying survey settings from “${duplicateSourceName}”. Name the new location and launch.`
            : "Customers scan the QR in your venue → WhatsApp opens with the trigger message → survey runs automatically."
        }
      />

      <Stepper
        current={step}
        duplicateMode={duplicateMode}
        onJump={(n) => {
          if (duplicateMode && n < 4) return;
          if (n < step) setStep(n as Step);
        }}
      />

      <div key={step} className="animate-fade-in">
        {step === 1 && (
          <Card data-demo-target="wizard-industry">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Briefcase className="size-4 text-primary" /> Step 1 · Choose your industry
              </CardTitle>
              <CardDescription>Tailors the suggested feedback topics.</CardDescription>
            </CardHeader>
            <CardContent>
              {industriesQ.isLoading ? (
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
                  {Array.from({ length: 5 }).map((_, i) => (
                    <Skeleton key={i} className="h-28 rounded-xl" />
                  ))}
                </div>
              ) : industriesQ.isError ? (
                <p className="text-sm text-destructive">Could not load industries.</p>
              ) : (
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
                  {industries.map((ind) => {
                    const Icon = industryIcon(ind);
                    const active = industryId === ind.id;
                    return (
                      <button
                        key={ind.id}
                        type="button"
                        onClick={() => {
                          setIndustryId(ind.id);
                          setSelectedTypeIds([]);
                        }}
                        className={cn(
                          "group flex flex-col items-start gap-2 rounded-xl border p-4 text-left transition-all hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md",
                          active ? "border-primary bg-primary/5 shadow-md ring-1 ring-primary/30" : "border-border bg-background/40",
                        )}
                      >
                        <div className="flex items-center gap-2">
                          <div
                            className={cn(
                              "grid size-9 place-items-center rounded-lg ring-1 transition-transform group-hover:scale-105",
                              active ? "bg-primary text-primary-foreground ring-primary/40" : "bg-primary/10 text-primary ring-primary/20",
                            )}
                          >
                            <Icon className="size-4" />
                          </div>
                          <p className="text-sm font-semibold leading-tight">{ind.name}</p>
                        </div>
                        <p className="text-[11px] text-muted-foreground">Survey topics</p>
                        {active ? (
                          <span className="inline-flex items-center gap-1 text-[11px] font-medium text-primary">
                            <Check className="size-3" /> Selected
                          </span>
                        ) : null}
                      </button>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {step === 2 && industry && (
          <Card data-demo-target="wizard-topics">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Target className="size-4 text-primary" /> Step 2 · What do you want to measure?
              </CardTitle>
              <CardDescription>
                Pick 1–6 topics from {industry.name}, then drag to set the ask order. Short surveys get 3× more replies.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-start gap-3 rounded-xl border border-primary/15 bg-primary/5 p-4">
                <div className="grid size-7 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary ring-1 ring-primary/20">
                  <Sparkles className="size-3.5" />
                </div>
                <div>
                  <p className="text-sm font-medium text-primary">Tip — keep it under 5</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">Walk-in customers complete short surveys far more often.</p>
                </div>
              </div>
              {typesQ.isLoading ? (
                <Skeleton className="h-24 w-full" />
              ) : typesQ.isError ? (
                <p className="text-sm text-destructive">Could not load survey topics.</p>
              ) : (
                <FeedbackTopicPicker
                  topics={surveyTypes}
                  selectedIds={selectedTypeIds}
                  onChange={setSelectedTypeIds}
                />
              )}

              <div
                className={cn(
                  "flex items-start gap-3 rounded-xl border p-4 transition",
                  marketingOptIn ? "border-primary/40 bg-primary/5" : "border-border bg-background/40",
                )}
              >
                <div className="grid size-9 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary ring-1 ring-primary/20">
                  <Sparkles className="size-4" />
                </div>
                <div className="flex-1">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-sm font-semibold">
                      Promo opt-in after survey{" "}
                      <span className="text-xs font-normal text-muted-foreground">(optional)</span>
                    </p>
                    <Switch checked={marketingOptIn} onCheckedChange={setMarketingOptIn} />
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Ask customers on WhatsApp if they want occasional offers. Replying STOP unsubscribes them from the VoxBulk feedback number (handled by WhatsApp/Telnyx) and removes them from your promo list.
                  </p>
                  {marketingOptIn ? (
                    <p className="mt-2 text-xs font-medium text-primary">
                      Current promo subscribers: {marketingCountQ.isLoading ? "…" : marketingCountQ.data ?? 0}
                    </p>
                  ) : null}
                </div>
              </div>

              <div
                className={cn(
                  "flex items-start gap-3 rounded-xl border p-4 transition",
                  openQuestion ? "border-primary/40 bg-primary/5" : "border-border bg-background/40",
                )}
              >
                <div className="grid size-9 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary ring-1 ring-primary/20">
                  <MessageSquarePlus className="size-4" />
                </div>
                <div className="flex-1">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-sm font-semibold">
                      Tell us more about your experience{" "}
                      <span className="text-xs font-normal text-muted-foreground">(optional)</span>
                    </p>
                    <Switch checked={openQuestion} onCheckedChange={setOpenQuestion} />
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Adds a final open question. Responses appear in feedback results under more details.
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {step === 3 && (
          <Card data-demo-target="wizard-look">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Palette className="size-4 text-primary" /> Step 3 · Survey look &amp; feel
              </CardTitle>
              <CardDescription>
                Pick the web survey skin customers see when they open the link. Scan a preview QR on your phone before you launch.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <FeedbackWebThemePicker
                value={webTheme}
                onChange={setWebTheme}
                companyName={companyName}
                industryName={industry?.name}
                industrySlug={industry?.slug}
                radioName="createFeedbackOverlayMode"
              />
            </CardContent>
          </Card>
        )}

        {step === 4 && (
          <Card data-demo-target="wizard-branches">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <QrCode className="size-4 text-primary" /> Step 4 · {duplicateMode ? "New location" : "Branches & QR codes"}
              </CardTitle>
              <CardDescription>
                {duplicateMode
                  ? "Survey questions and settings are copied from your existing location. Enter a name for this new location."
                  : "Each branch gets its own QR code and trigger message so results can be tracked per location."}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              {duplicateMode ? (
                <div className="rounded-xl border border-primary/30 bg-primary/5 p-4 text-sm">
                  Duplicating from <span className="font-semibold">{duplicateSourceName}</span>. Industry and survey topics are locked to match the source.
                </div>
              ) : null}
              {previewM.isError && !previewQr ? (
                <div className="rounded-xl border border-warning/40 bg-warning/5 p-3 text-sm text-warning-foreground">
                  Live QR preview unavailable — trigger messages below still work. Configure WhatsApp in admin or continue to step 5.
                </div>
              ) : null}
              <div className="rounded-xl border border-border bg-muted/30 p-4">
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-muted-foreground">
                    <Lock className="size-3.5" /> Business name (from profile)
                  </div>
                  <Button asChild size="sm" variant="ghost" className="h-7 text-xs">
                    <Link to="/settings/profile">Edit in profile</Link>
                  </Button>
                </div>
                <p className="mt-1 text-base font-semibold">{companyName}</p>
              </div>

              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <Label>{duplicateMode ? "Location name" : "Branches / locations"}</Label>
                  {!duplicateMode ? (
                    <Button
                      size="sm"
                      variant="outline"
                      className="gap-1.5"
                      onClick={() => setBranches((b) => [...b, { id: `b${Date.now()}`, name: "" }])}
                    >
                      <Plus className="size-3.5" /> Add branch
                    </Button>
                  ) : null}
                </div>

                <div className="grid gap-3 md:grid-cols-2">
                  {branches.map((b, idx) => {
                    const trigger = idx === 0 && previewQr?.trigger_text
                      ? previewQr.trigger_text
                      : previewTrigger(companyName, b.name || undefined);
                    const qrSrc = idx === 0 && previewQr?.qr_image_url
                      ? previewQr.qr_image_url
                      : previewQr?.wa_url
                        ? buildQrImageUrl(
                            previewQr.wa_url.replace(/[a-z0-9]{2,24}-[a-z0-9]{2,24}-[a-z0-9]{6}/i, "acme-branch-preview"),
                            220,
                          )
                        : null;
                    return (
                      <div key={b.id} className="flex flex-col gap-3 rounded-xl border border-border bg-background/40 p-4">
                        <div className="flex items-center gap-2">
                          <MapPin className="size-4 text-primary" />
                          <Input
                            value={b.name}
                            placeholder={`Branch ${idx + 1} (e.g. Marina, Downtown)`}
                            onChange={(e) =>
                              setBranches((arr) => arr.map((x) => (x.id === b.id ? { ...x, name: e.target.value } : x)))
                            }
                          />
                          {branches.length > 1 ? (
                            <Button
                              size="icon"
                              variant="ghost"
                              className="size-8 text-muted-foreground hover:text-destructive"
                              onClick={() => setBranches((arr) => arr.filter((x) => x.id !== b.id))}
                            >
                              <Trash2 className="size-4" />
                            </Button>
                          ) : null}
                        </div>

                        <div className="flex items-start gap-4">
                          <div className="rounded-xl border-2 border-primary/20 bg-white p-2 shadow-sm">
                            {qrSrc ? (
                              <img src={qrSrc} alt={`QR ${b.name}`} className="size-32" />
                            ) : previewM.isPending ? (
                              <div className="grid size-32 place-items-center text-center text-[10px] text-muted-foreground">
                                Loading QR…
                              </div>
                            ) : (
                              <div className="grid size-32 place-items-center text-center text-[10px] text-muted-foreground px-2">
                                QR after WhatsApp is configured
                              </div>
                            )}
                          </div>
                          <div className="flex-1 space-y-2">
                            <p className="text-xs text-muted-foreground">
                              Preview QR for{" "}
                              <b>
                                {companyName}
                                {b.name ? ` — ${b.name}` : ""}
                              </b>
                              . Opens your WhatsApp business number with the message pre-filled. Final QR includes a unique reference after launch.
                            </p>
                            <div className="rounded-lg border border-border bg-muted/40 p-2">
                              <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Pre-filled WhatsApp message</p>
                              <p className="mt-0.5 text-xs">{trigger}</p>
                            </div>
                            <div className="flex gap-2">
                              {qrSrc ? (
                                <Button size="sm" variant="outline" className="h-7 gap-1.5" asChild>
                                  <a href={qrSrc} download={`qr-${b.name || "branch"}-preview.png`}>
                                    <Download className="size-3" /> PNG
                                  </a>
                                </Button>
                              ) : null}
                              <Button size="sm" variant="outline" className="h-7 gap-1.5" onClick={() => window.print()}>
                                <Printer className="size-3" /> Print
                              </Button>
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {step === 5 && (
          <div data-demo-target="wizard-followup">
            <AiFollowUpStep stepLabel="Step 5" config={aiFollowUp} onChange={setAiFollowUp} />
          </div>
        )}

        {step === 6 && (
          <Card data-demo-target="wizard-launch">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Rocket className="size-4 text-primary" /> Step 6 · Activate QR survey
              </CardTitle>
              <CardDescription>
                Review your setup, then activate. An active Customer Feedback subscription is required. Style the QR
                later from the saved survey edit page.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              {subscriptionQ.isLoading ? (
                <Skeleton className="h-14 w-full" />
              ) : subscriptionQ.data?.active ? (
                <div className="rounded-lg border border-success/30 bg-success/5 px-4 py-3 text-sm">
                  <p className="font-medium text-success">Customer feedback subscription active</p>
                  <p className="text-xs text-muted-foreground">
                    {subscriptionQ.data.plan_name || "Plan"} ·{" "}
                    {feedbackRemainingSummary(subscriptionQ.data)}
                  </p>
                </div>
              ) : (
                <div className="rounded-lg border border-warning/40 bg-warning/5 px-4 py-3 text-sm">
                  <p className="font-medium">Customer feedback subscription required</p>
                  <p className="text-xs text-muted-foreground">
                    Subscribe to a package before activating QR surveys.
                  </p>
                </div>
              )}
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
                <Summary label="Business" value={companyName} />
                <Summary label="Industry" value={industry?.name || "—"} />
                <Summary label="Topics" value={`${selectedTypeIds.length} selected${openQuestion ? " + open" : ""}`} />
                <Summary label="Branches" value={`${branches.length}`} />
                <Summary
                  label="Theme"
                  value={(() => {
                    const base =
                      baseTemplateId === "auto"
                        ? `Auto — ${industry?.name ?? "category"}`
                        : [BASE_TEMPLATE, ...CATEGORY_TEMPLATES].find((t) => t.id === baseTemplateId)?.label ?? "Default";
                    const overlays = overlayIds
                      .map((id) => [...SEASON_TEMPLATES, ...EVENT_TEMPLATES].find((t) => t.id === id)?.label ?? id)
                      .join(", ");
                    const custom = customEventLabel ? ` + ${customEventLabel}` : "";
                    return overlays
                      ? `${base} · ${overlayMode === "auto" ? "auto-swap" : "fixed"}: ${overlays}${custom}`
                      : `${base}${custom}`;
                  })()}
                />
              </div>

              <div className="flex justify-center">
                <div className="rounded-xl border-4 border-primary/20 bg-white p-3 shadow-md">
                  <img
                    src={previewQr?.qr_image_url || buildQrImageUrl(previewQr?.wa_url || "https://wa.me/", 320)}
                    alt="QR"
                    className="size-40"
                  />
                </div>
              </div>

              {branches.length > 1 ? (
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {branches.map((b) => (
                    <div key={b.id} className="rounded-xl border border-border bg-background/40 px-3 py-2.5">
                      <p className="truncate text-sm font-medium">{b.name || "Unnamed branch"}</p>
                      <p className="truncate text-[11px] text-muted-foreground">
                        {previewTrigger(companyName, b.name || undefined)}
                      </p>
                    </div>
                  ))}
                </div>
              ) : null}

              {aiFollowUp.enabled ? (
                <div className="rounded-xl border border-primary/25 bg-primary/5 p-3 text-xs text-muted-foreground">
                  <b className="text-foreground">AI follow-up is ON:</b> unhappy customers without a written reason will get a callback after {aiFollowUp.delayHours}h
                  {aiFollowUp.promoEnabled && aiFollowUp.promoCode ? ` — promo code ${aiFollowUp.promoCode} available` : ""}.
                </div>
              ) : null}

              <label
                className={cn(
                  "flex cursor-pointer items-start gap-3 rounded-xl border p-4 transition",
                  consent ? "border-primary bg-primary/5" : "border-warning/50 bg-warning/5",
                )}
              >
                <Checkbox checked={consent} onCheckedChange={(v) => setConsent(!!v)} className="mt-0.5" />
                <div>
                  <p className="text-sm font-medium">
                    I confirm the QR will only be shown to customers in my own venue with their implicit opt-in.
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Required before save. Customers must scan &amp; send the message themselves to start the survey.
                    Without a package you get 20 demo scans for testing.
                  </p>
                </div>
              </label>

              <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
                <Button
                  size="lg"
                  variant={liveEntitled ? "outline" : "default"}
                  className="gap-1.5"
                  disabled={!canNext[6] || createM.isPending}
                  onClick={() => void onSave(false)}
                >
                  <QrCode className="size-4" /> {createM.isPending ? "Saving…" : "Save QR survey"}
                </Button>
                {liveEntitled ? (
                  <Button
                    size="lg"
                    className="gap-1.5"
                    disabled={!canNext[6] || createM.isPending}
                    onClick={() => void onSave(true)}
                  >
                    <Rocket className="size-4" /> {createM.isPending ? "Activating…" : "Activate QR survey"}
                  </Button>
                ) : (
                  <Button asChild size="lg" variant="outline" className="gap-1.5">
                    <Link to="/account/feedback/packages">Pay and activate</Link>
                  </Button>
                )}
              </div>
            </CardContent>
          </Card>
        )}
      </div>

      <div className="flex items-center justify-between">
        <Button
          variant="outline"
          className="gap-1.5"
          onClick={() => setStep((s) => Math.max(duplicateMode ? 4 : 1, s - 1) as Step)}
          disabled={step === 1}
        >
          <ChevronLeft className="size-4" /> Back
        </Button>
        {step < 6 ? (
          <Button
            className="gap-1.5"
            data-demo-target="wizard-next"
            onClick={() => setStep((s) => Math.min(6, s + 1) as Step)}
            disabled={!canNext[step]}
          >
            Next <ChevronRight className="size-4" />
          </Button>
        ) : null}
      </div>
    </div>
  );
}

function Stepper({ current, onJump, duplicateMode }: { current: Step; onJump: (n: number) => void; duplicateMode?: boolean }) {
  const progress = ((current - 1) / (STEPS.length - 1)) * 100;
  return (
    <div className="rounded-2xl border border-border bg-gradient-to-br from-background/80 via-background/40 to-accent/10 p-5 shadow-sm" data-demo-target="wizard-stepper">
      <div className="relative">
        <div className="absolute left-5 right-5 top-5 hidden h-0.5 bg-border sm:block" />
        <div
          className="absolute left-5 top-5 hidden h-0.5 bg-gradient-to-r from-primary to-primary/60 transition-all duration-500 sm:block"
          style={{ width: `calc((100% - 2.5rem) * ${progress / 100})` }}
        />
        <ol className="relative grid gap-2" style={{ gridTemplateColumns: `repeat(${STEPS.length}, minmax(0, 1fr))` }}>
          {STEPS.map((s) => {
            const isDone = s.id < current;
            const isActive = s.id === current;
            const Icon = s.icon;
            const isLocked = duplicateMode && s.id < 4;
            return (
              <li key={s.id} className="flex flex-col items-center text-center">
                <button
                  type="button"
                  disabled={isLocked}
                  onClick={() => onJump(s.id)}
                  className={cn(
                    "relative grid size-10 place-items-center rounded-full border transition-all",
                    isActive && "scale-110 border-primary bg-primary text-primary-foreground shadow-lg shadow-primary/30",
                    isDone && "border-primary bg-primary/15 text-primary",
                    !isActive && !isDone && "border-border bg-background text-muted-foreground hover:border-primary/40",
                    isLocked && "cursor-not-allowed opacity-50 hover:border-border",
                  )}
                >
                  {isActive ? <span className="absolute inset-0 rounded-full bg-primary/30 motion-safe:animate-ping" /> : null}
                  <span className="relative">{isDone ? <Check className="size-5" /> : <Icon className="size-5" />}</span>
                </button>
                <p className={cn("mt-2 text-xs font-semibold sm:text-sm", isActive ? "text-foreground" : "text-muted-foreground")}>
                  {s.id}. {s.title}
                </p>
              </li>
            );
          })}
        </ol>
      </div>
    </div>
  );
}

function Summary({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border bg-background/40 px-3 py-2">
      <p className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</p>
      <p className="mt-0.5 break-words text-sm font-medium">{value}</p>
    </div>
  );
}

function LaunchSuccess({ locations, company }: { locations: FeedbackLocation[]; company: string }) {
  const allDemo = locations.length > 0 && locations.every((l) => String(l.status || "").toLowerCase() === "preview");
  return (
    <Card className="animate-scale-in">
      <CardContent className="flex flex-col items-center gap-5 py-12 text-center">
        <div className="relative">
          <div className="absolute inset-0 animate-ping rounded-full bg-success/30" />
          <div className="relative grid size-16 place-items-center rounded-full bg-success text-success-foreground">
            <CheckCircle2 className="size-8" />
          </div>
        </div>
        <div>
          <h2 className="text-xl font-semibold">
            {allDemo ? "Your QR surveys are saved for demo testing" : "Your QR surveys are live"}
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {allDemo
              ? "You can print and test with up to 20 demo scans. Use Activate on the saved list when your package is ready."
              : "Print these QR codes and place them in each venue. Responses appear in real-time per branch."}
          </p>
        </div>
        <div className="grid w-full max-w-3xl gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {locations.map((loc) => (
            <div key={loc.id} className="flex flex-col items-center gap-2 rounded-xl border border-border bg-background/40 p-4">
              <div className="rounded-xl border-4 border-primary/20 bg-white p-2 shadow-md">
                <img src={loc.qr_image_url} alt="QR" className="size-32" />
              </div>
              <p className="text-sm font-semibold">{loc.name || "Branch"}</p>
              <p className="text-center text-[11px] text-muted-foreground">
                Scan to start the survey for {company}
                {loc.name ? ` — ${loc.name}` : ""}.
              </p>
              <Button asChild size="sm" variant="outline" className="h-7 gap-1.5">
                <a href={loc.qr_image_url} download={`qr-${loc.name || loc.id}.png`}>
                  <Download className="size-3" /> PNG
                </a>
              </Button>
            </div>
          ))}
        </div>
        <div className="flex flex-col gap-2 sm:flex-row">
          <Button asChild className="gap-1.5">
            <Link to="/feedback/results">
              <BarChart3 className="size-4" /> View live results <ArrowRight className="size-4" />
            </Link>
          </Button>
          <Button asChild variant="ghost" className="gap-1.5">
            <Link to="/feedback">
              <QrCode className="size-4" /> Saved QR surveys
            </Link>
          </Button>
          <Button asChild variant="ghost" className="gap-1.5">
            <Link to="/">
              <LayoutDashboard className="size-4" /> Dashboard
            </Link>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
