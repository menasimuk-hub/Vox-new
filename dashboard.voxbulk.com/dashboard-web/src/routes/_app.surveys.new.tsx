import { createFileRoute, useNavigate } from "@tanstack/react-router";
import * as React from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { ChannelPicker } from "@/components/create-wizard";
import { SurveyPhoneWizard } from "@/components/create-wizard/survey-phone-wizard";
import { SurveyWaWizard } from "@/components/create-wizard/survey-wa-wizard";
import { pageCountFromSelectedTypes } from "@/components/create-wizard/survey-wa-template-step";
import { SurveyLaunchQuoteModal } from "@/components/modals";
import { apiFetch, apiUploadFiles, downloadAuthenticatedFile } from "@/lib/api";
import { gocardlessAvailable, GC_ORDER_ID_KEY, startGoCardlessOrderPayment } from "@/lib/billing/gocardless";
import { surveyTitleFromGoal } from "@/lib/survey-title";
import { formatWaSurveyGenerateError, parseWaSurveyGenerateErrors } from "@/lib/wa-survey-generate-error";
import {
  useCreateServiceOrder,
  useGenerateWaSurvey,
  useLaunchSurveyCampaign,
  useOrderRecipients,
  useOrganisation,
  usePatchServiceOrder,
  useSendWaSurveyTest,
  useSurveyLaunchEligibility,
  useSurveyPackages,
  useWaSurveyIndustries,
  useWaSurveyLibraryTemplates,
  useWaSurveyStepBank,
  useWaSurveySystemTemplates,
  useWaSurveyTypes,
} from "@/lib/queries";
import { useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "@/lib/queries/index";
import { useSession } from "@/lib/session";

export const Route = createFileRoute("/_app/surveys/new")({
  head: () => ({ meta: [{ title: "Create survey — VoxBulk" }] }),
  validateSearch: (search: Record<string, unknown>) => ({
    channel:
      search.channel === "whatsapp" ? ("whatsapp" as const) : search.channel === "phone" ? ("phone" as const) : undefined,
    industry_slug: typeof search.industry_slug === "string" ? search.industry_slug.trim() : undefined,
    order_id: typeof search.order_id === "string" ? search.order_id.trim() : undefined,
  }),
  component: CreateSurvey,
});

const PAGE_COUNT_TO_LENGTH: Record<3 | 4 | 5 | 6, "short" | "standard" | "detailed"> = {
  3: "short",
  4: "short",
  5: "standard",
  6: "detailed",
};

type Channel = "whatsapp" | "phone" | null;

function normalizeSurveyTypeId(id: unknown): string {
  return String(id ?? "").trim();
}

function industryMatchesSlugSearch(ind: Record<string, unknown>, needle: string): boolean {
  const slug = String(ind.slug || ind.industry_slug || "")
    .trim()
    .toLowerCase()
    .replace(/-/g, "_");
  const name = String(ind.name || ind.label || "").trim().toLowerCase();
  const nameNorm = name.replace(/&/g, "and").replace(/[^a-z0-9]+/g, " ").trim();
  const needleNorm = needle.replace(/_/g, " ").trim();

  if (slug === needle) return true;
  if (slug.replace(/_/g, "") === needle.replace(/_/g, "")) return true;
  if (name === needle) return true;
  if (nameNorm.includes(needleNorm)) return true;
  if (needle === "hospitality_food" && nameNorm.includes("hospitality") && nameNorm.includes("food")) return true;
  return false;
}

function CreateSurvey() {
  const { channel: channelSearch, industry_slug: industrySlugSearch, order_id: orderIdSearch } = Route.useSearch();
  const navigate = useNavigate();
  const { session } = useSession();
  const orgQ = useOrganisation();
  const packagesQ = useSurveyPackages();
  const createM = useCreateServiceOrder();
  const patchM = usePatchServiceOrder();
  const generateWaM = useGenerateWaSurvey();
  const sendTestWaM = useSendWaSurveyTest();

  const [channel, setChannel] = React.useState<Channel>(null);
  const [waPreview, setWaPreview] = React.useState<Record<string, unknown> | null>(null);
  const [industryId, setIndustryId] = React.useState("");
  const [selectedServiceTagIds, setSelectedServiceTagIds] = React.useState<string[]>([]);
  const [orderedServiceTagIds, setOrderedServiceTagIds] = React.useState<string[]>([]);
  const [welcomeTemplateId, setWelcomeTemplateId] = React.useState("");
  const [thankYouTemplateId, setThankYouTemplateId] = React.useState("");
  const [selectedServiceTemplateIds, setSelectedServiceTemplateIds] = React.useState<Record<string, string>>({});
  const [privacyMode, setPrivacyMode] = React.useState<"off" | "on">("off");
  const [allowFinalAdditionalFeedback, setAllowFinalAdditionalFeedback] = React.useState(false);
  const surveyVariant = privacyMode === "on" ? "anonymous" : "standard";
  const [pageCount, setPageCount] = React.useState<3 | 4 | 5 | 6>(5);
  const [autoSelectSteps, setAutoSelectSteps] = React.useState(true);
  const [manualMiddleRoles, setManualMiddleRoles] = React.useState<string[]>([]);
  const [generating, setGenerating] = React.useState(false);
  const [generateErrors, setGenerateErrors] = React.useState<string[]>([]);
  const waIndustriesQ = useWaSurveyIndustries();
  const waTypesQ = useWaSurveyTypes(industryId || null);
  const systemTemplatesQ = useWaSurveySystemTemplates();
  const primarySurveyTypeId = orderedServiceTagIds[0] || selectedServiceTagIds[0] || "";
  const stepBankQ = useWaSurveyStepBank(channel === "whatsapp" ? primarySurveyTypeId : null, privacyMode);
  const libraryTemplateQueries = useWaSurveyLibraryTemplates(
    orderedServiceTagIds,
    privacyMode,
    channel === "whatsapp",
  );
  const [approved, setApproved] = React.useState(false);
  const [anonymous, setAnonymous] = React.useState(false);
  const [goal, setGoal] = React.useState(
    "Measure satisfaction with our new hygienist team and identify the top improvement.",
  );
  const [script, setScript] = React.useState(
    "1. On a scale of 0-10, how likely are you to recommend us?\n2. What stood out about your visit?\n3. Anything we could improve?",
  );
  const [startAt, setStartAt] = React.useState("");
  const [endAt, setEndAt] = React.useState("");
  const [packageId, setPackageId] = React.useState("");
  const [orderId, setOrderId] = React.useState<string | null>(null);
  const [launchOpen, setLaunchOpen] = React.useState(false);
  const [launchMode, setLaunchMode] = React.useState<"now" | "schedule" | "recurring">("now");
  const [payBusy, setPayBusy] = React.useState(false);
  const fileRef = React.useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = React.useState(false);
  const qc = useQueryClient();
  const recipientsQ = useOrderRecipients(orderId);
  const uploadedContacts = React.useMemo(() => {
    const rows = recipientsQ.data?.recipients || [];
    return rows.map((row) => ({
      name: String(row.name || "").trim(),
      phone: String(row.phone || "").trim(),
      language: String(row.language || row.locale || "").trim(),
    }));
  }, [recipientsQ.data?.recipients]);
  const contactsCount = uploadedContacts.filter((c) => c.phone).length;
  const gcReady = gocardlessAvailable(session?.subscription as Record<string, unknown> | null);
  const launchM = useLaunchSurveyCampaign(orderId);
  const eligibilityQ = useSurveyLaunchEligibility(orderId, launchOpen);

  React.useEffect(() => {
    const restored = (orderIdSearch || "").trim();
    if (restored && !orderId) setOrderId(restored);
  }, [orderIdSearch, orderId]);

  React.useEffect(() => {
    if (orderId) return;
    try {
      const fromStorage = (sessionStorage.getItem(GC_ORDER_ID_KEY) || "").trim();
      if (fromStorage) setOrderId(fromStorage);
    } catch {
      /* ignore */
    }
  }, [orderId]);

  const channelLabel = channel === "whatsapp" ? "WhatsApp" : channel === "phone" ? "AI phone call" : "—";
  const launchModeLabel =
    launchMode === "now"
      ? "Send now"
      : launchMode === "schedule"
        ? `Scheduled · ${startAt || "—"}`
        : `Recurring · starting ${endAt || startAt || "—"}`;

  const persistDraftForLaunch = async () => {
    const id = await ensureOrder();
    const baseConfig =
      channel === "whatsapp"
        ? {
            goal,
            delivery: "whatsapp" as const,
            survey_channel: "whatsapp" as const,
            channels: ["whatsapp"],
            anonymous_responses: anonymous,
            script,
            package_id: packageId || undefined,
            industry_id: industryId,
            survey_type_id: primarySurveyTypeId || undefined,
            selected_survey_type_ids: orderedServiceTagIds.length ? orderedServiceTagIds : selectedServiceTagIds,
            welcome_template_id: welcomeTemplateId ? Number(welcomeTemplateId) : undefined,
            thank_you_template_id: thankYouTemplateId ? Number(thankYouTemplateId) : undefined,
            survey_length: PAGE_COUNT_TO_LENGTH[pageCount],
            page_count: pageCount,
            privacy_mode: privacyMode,
            survey_variant: surveyVariant,
          }
        : {
            goal,
            delivery: "ai_call" as const,
            survey_channel: "ai_call" as const,
            anonymous_responses: anonymous,
            script,
            package_id: packageId || undefined,
          };
    await patchM.mutateAsync({
      orderId: id,
      body: {
        title: surveyTitleFromGoal(goal),
        scheduled_start_at: startAt || null,
        scheduled_end_at: endAt || null,
        run_mode: launchMode === "now" ? "manual" : "scheduled",
        config: baseConfig,
      },
    });
    return id;
  };

  const onOpenLaunch = async (mode: "now" | "schedule" | "recurring") => {
    try {
      await persistDraftForLaunch();
      setLaunchMode(mode);
      setLaunchOpen(true);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not save draft before launch");
    }
  };

  const refreshLaunchEligibility = () => {
    if (!orderId) return;
    void eligibilityQ.refetch();
  };

  const onLaunchSurvey = async () => {
    if (!orderId) throw new Error("Save your draft before launch");
    setPayBusy(true);
    try {
      await persistDraftForLaunch();
      const runMode = launchMode === "now" ? "now" : "schedule";
      const result = await launchM.mutateAsync({ run_mode: runMode });
      toast.success(result.message || (runMode === "now" ? "Survey launched" : "Survey scheduled"));
      setLaunchOpen(false);
      void navigate({ to: "/surveys/results", search: { orderId } });
    } finally {
      setPayBusy(false);
    }
  };

  const onPayLaunchSurvey = async () => {
    if (!orderId) throw new Error("Save your draft before paying");
    if (!gcReady) throw new Error("GoCardless checkout is not configured");
    setPayBusy(true);
    try {
      await persistDraftForLaunch();
      await startGoCardlessOrderPayment(orderId);
    } catch (e) {
      setPayBusy(false);
      throw e instanceof Error ? e : new Error("Could not start GoCardless checkout");
    }
  };

  const userTestPhone = React.useMemo(() => {
    const profile = session?.profile as Record<string, unknown> | undefined;
    const phone = profile?.phone as Record<string, unknown> | undefined;
    const fromUser = String(phone?.phone_e164 || phone?.phone_number || "").trim();
    if (fromUser) return fromUser;
    return String(orgQ.data?.contact_phone || "").trim();
  }, [session?.profile, orgQ.data?.contact_phone]);

  const businessName = React.useMemo(() => {
    const org = orgQ.data;
    return String(org?.display_name || org?.name || "").trim();
  }, [orgQ.data]);

  const delivery = channel === "whatsapp" ? "whatsapp" : "ai_call";

  const packages = React.useMemo(() => {
    const data = packagesQ.data || {};
    const channelKey = channel === "whatsapp" ? "whatsapp" : "ai_call";
    const list = (data.packages as Record<string, unknown[]>)?.[channelKey] || [];
    return list as Array<Record<string, unknown>>;
  }, [packagesQ.data, channel]);

  React.useEffect(() => {
    if (!channel || !packages.length) return;
    const next = String(packages[0].id || packages[0].rule_id || "");
    if (!next) return;
    setPackageId((prev) => {
      const stillValid = packages.some((pkg) => String(pkg.id || pkg.rule_id || "") === prev);
      return stillValid ? prev : next;
    });
  }, [channel, packages]);

  const ensureOrder = async () => {
    if (orderId) return orderId;
    const created = await createM.mutateAsync({
      service_code: "survey",
      title: surveyTitleFromGoal(goal) || "New survey",
      config: {
        goal,
        delivery,
        anonymous_responses: anonymous,
        script,
        package_id: packageId || undefined,
      },
    });
    setOrderId(created.id);
    return created.id;
  };

  React.useEffect(() => {
    if (channelSearch === "whatsapp" || channelSearch === "phone") setChannel(channelSearch);
  }, [channelSearch]);

  React.useEffect(() => {
    const industries = (waIndustriesQ.data?.industries || []) as Array<Record<string, unknown>>;
    if (!industrySlugSearch || !industries.length) return;
    const needle = industrySlugSearch.toLowerCase();
    const match = industries.find((ind) => industryMatchesSlugSearch(ind, needle));
    if (match) setIndustryId(String(match.id));
  }, [waIndustriesQ.data, industrySlugSearch]);

  React.useEffect(() => {
    const industries = (waIndustriesQ.data?.industries || []) as Array<Record<string, unknown>>;
    if (industrySlugSearch) return;
    if (industries[0] && !industryId) setIndustryId(String(industries[0].id));
  }, [waIndustriesQ.data, industryId, industrySlugSearch]);

  React.useEffect(() => {
    setSelectedServiceTagIds([]);
    setOrderedServiceTagIds([]);
    setWelcomeTemplateId("");
    setThankYouTemplateId("");
    setSelectedServiceTemplateIds({});
    setApproved(false);
    setGenerateErrors([]);
  }, [industryId]);

  React.useEffect(() => {
    setSelectedServiceTemplateIds((prev) => {
      const next: Record<string, string> = {};
      for (const id of selectedServiceTagIds) {
        if (prev[id]) next[id] = prev[id];
      }
      return next;
    });
  }, [selectedServiceTagIds]);

  const serviceTypes = React.useMemo(
    () => (waTypesQ.data?.types || []) as Array<Record<string, unknown>>,
    [waTypesQ.data],
  );

  const libraryTemplatesByTypeId = React.useMemo(() => {
    const map: Record<string, Array<Record<string, unknown>>> = {};
    orderedServiceTagIds.forEach((typeId, index) => {
      map[typeId] = (libraryTemplateQueries[index]?.data?.templates || []) as Array<Record<string, unknown>>;
    });
    return map;
  }, [orderedServiceTagIds, libraryTemplateQueries]);

  const libraryTemplatesLoading = libraryTemplateQueries.some((q) => q.isLoading);

  React.useEffect(() => {
    setSelectedServiceTemplateIds((prev) => {
      let changed = false;
      const next = { ...prev };
      for (const typeId of orderedServiceTagIds) {
        const rows = libraryTemplatesByTypeId[typeId] || [];
        const validIds = new Set(rows.map((row) => String(row.id)));
        if (next[typeId] && !validIds.has(next[typeId])) {
          delete next[typeId];
          changed = true;
        }
        if (rows.length === 1 && !next[typeId]) {
          next[typeId] = String(rows[0].id);
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [orderedServiceTagIds, libraryTemplatesByTypeId]);

  React.useEffect(() => {
    if (orderedServiceTagIds.length < 1) return;
    setPageCount(pageCountFromSelectedTypes(orderedServiceTagIds.length));
  }, [orderedServiceTagIds]);

  React.useEffect(() => {
    setOrderedServiceTagIds((prev) => {
      const next = prev.filter((id) => selectedServiceTagIds.includes(id));
      for (const id of selectedServiceTagIds) {
        if (!next.includes(id)) next.push(id);
      }
      return next;
    });
  }, [selectedServiceTagIds]);

  const welcomeTemplates = React.useMemo(
    () => (systemTemplatesQ.data?.templates?.welcome || []) as Array<Record<string, unknown>>,
    [systemTemplatesQ.data],
  );
  const thankYouTemplates = React.useMemo(
    () => (systemTemplatesQ.data?.templates?.thank_you || []) as Array<Record<string, unknown>>,
    [systemTemplatesQ.data],
  );

  const toggleServiceTag = (typeId: string) => {
    setSelectedServiceTagIds((prev) => {
      if (prev.includes(typeId)) return prev.filter((id) => id !== typeId);
      if (prev.length >= 4) {
        toast.error("You can select at most 4 services");
        return prev;
      }
      return [...prev, typeId];
    });
  };

  const orderedTypeIds = React.useMemo(
    () => (orderedServiceTagIds.length ? orderedServiceTagIds : selectedServiceTagIds).map(normalizeSurveyTypeId),
    [orderedServiceTagIds, selectedServiceTagIds],
  );

  const serviceTagErrors = React.useMemo(() => {
    const errors: string[] = [];
    if (selectedServiceTagIds.length < 1) errors.push("Select at least 1 service (max 4).");
    if (selectedServiceTagIds.length > 4) errors.push("Select at most 4 services.");
    for (const id of selectedServiceTagIds) {
      const row = serviceTypes.find((t) => normalizeSurveyTypeId(t.id) === normalizeSurveyTypeId(id));
      if (!row) continue;
      if (!row.has_wa_template) {
        errors.push(`"${String(row.name)}" has no WhatsApp template yet.`);
      }
    }
    return errors;
  }, [selectedServiceTagIds, serviceTypes]);

  const step3SelectionErrors = React.useMemo(() => {
    const errors: string[] = [];
    if (!welcomeTemplateId) errors.push("Select a welcome template.");
    if (!thankYouTemplateId) errors.push("Select a thank-you template.");
    for (const id of orderedTypeIds) {
      const row = serviceTypes.find((t) => normalizeSurveyTypeId(t.id) === id);
      const templateId = selectedServiceTemplateIds[id];
      if (!row) continue;
      if (!templateId) errors.push(`Select a template for "${String(row.name)}".`);
    }
    return errors;
  }, [orderedTypeIds, serviceTypes, welcomeTemplateId, thankYouTemplateId, selectedServiceTemplateIds]);

  React.useEffect(() => {
    if (generateErrors.length && step3SelectionErrors.length === 0) {
      setGenerateErrors([]);
    }
  }, [generateErrors.length, step3SelectionErrors.length]);

  React.useEffect(() => {
    if (privacyMode === "on") setAnonymous(true);
    else setAnonymous(false);
  }, [privacyMode]);

  const stepBankByRole = React.useMemo(
    () => (stepBankQ.data?.by_role || {}) as Record<string, { title?: string; body?: string; display_name?: string }>,
    [stepBankQ.data],
  );
  const suggestedRoles = React.useMemo(
    () => (stepBankQ.data?.suggested_page_roles || {}) as Record<string, string[]>,
    [stepBankQ.data],
  );
  const availableMiddleRoles = React.useMemo(
    () => ((stepBankQ.data?.middle_roles || []) as string[]).filter((r) => r !== "start" && r !== "completion"),
    [stepBankQ.data],
  );

  React.useEffect(() => {
    const suggested = suggestedRoles[String(pageCount)] || [];
    const middle = suggested.filter((r) => r !== "start" && r !== "completion");
    setManualMiddleRoles(middle.slice(0, Math.max(0, pageCount - 2)));
  }, [pageCount, primarySurveyTypeId, surveyVariant, suggestedRoles]);

  const resolvedPageRoles = React.useMemo(() => {
    const auto = suggestedRoles[String(pageCount)];
    if (autoSelectSteps && auto?.length === pageCount) return auto;
    const middle = manualMiddleRoles.slice(0, Math.max(0, pageCount - 2));
    return ["start", ...middle, "completion"];
  }, [autoSelectSteps, suggestedRoles, pageCount, manualMiddleRoles]);

  const pageOrderValid =
    resolvedPageRoles.length === pageCount &&
    resolvedPageRoles[0] === "start" &&
    resolvedPageRoles[resolvedPageRoles.length - 1] === "completion" &&
    new Set(resolvedPageRoles.slice(1, -1)).size === resolvedPageRoles.slice(1, -1).length;

  const moveMiddleRole = (index: number, direction: -1 | 1) => {
    setManualMiddleRoles((prev) => {
      const next = [...prev];
      const target = index + direction;
      if (target < 0 || target >= next.length) return prev;
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
    setAutoSelectSteps(false);
  };

  const removeMiddleRole = (index: number) => {
    setManualMiddleRoles((prev) => prev.filter((_, i) => i !== index));
    setAutoSelectSteps(false);
  };

  const addMiddleRole = (role: string) => {
    setManualMiddleRoles((prev) => {
      if (prev.includes(role) || prev.length >= pageCount - 2) return prev;
      return [...prev, role];
    });
    setAutoSelectSteps(false);
  };

  const onSelectServiceTemplate = (typeId: string, templateId: string) => {
    const key = normalizeSurveyTypeId(typeId);
    setSelectedServiceTemplateIds((prev) => ({ ...prev, [key]: normalizeSurveyTypeId(templateId) }));
    setAutoSelectSteps(true);
    setGenerateErrors([]);
  };

  const buildStep3GeneratePayload = () => {
    const typeOrder = orderedTypeIds;
    const selectedServiceTemplates: Record<string, number> = {};
    const selectedMiddleTemplateIds: number[] = [];
    for (const typeId of typeOrder) {
      const raw = selectedServiceTemplateIds[typeId];
      if (!raw) continue;
      const num = Number(raw);
      if (!Number.isFinite(num) || num <= 0) continue;
      selectedServiceTemplates[typeId] = num;
      selectedMiddleTemplateIds.push(num);
    }
    const effectivePageCount = pageCountFromSelectedTypes(typeOrder.length);
    return { typeOrder, selectedServiceTemplates, selectedMiddleTemplateIds, effectivePageCount };
  };

  const buildTestTemplateIds = (): number[] => {
    const ids: number[] = [];
    const welcome = Number(welcomeTemplateId);
    if (Number.isFinite(welcome) && welcome > 0) ids.push(welcome);
    for (const typeId of orderedServiceTagIds) {
      const raw = selectedServiceTemplateIds[typeId];
      const num = Number(raw);
      if (Number.isFinite(num) && num > 0) ids.push(num);
    }
    const thankYou = Number(thankYouTemplateId);
    if (Number.isFinite(thankYou) && thankYou > 0) ids.push(thankYou);
    return ids;
  };

  const onSendWaTest = async (input: { testPhone: string; welcomeTemplateId: string; firstName: string }) => {
    const phone = input.testPhone.trim();
    if (!phone) {
      toast.error("Enter a test mobile number in E.164 format (e.g. +447700900123).");
      return;
    }
    if (!approved) {
      toast.error("Complete Step 3 (Generate) before sending a test.");
      return;
    }
    const templateIds = buildTestTemplateIds();
    if (templateIds.length < 2) {
      toast.error("Complete Step 3 template selection before sending a test.");
      return;
    }
    const id = await ensureOrder();
    const sendBody = {
      order_id: id,
      test_phone: phone,
      template_ids: templateIds,
      welcome_template_id: Number(input.welcomeTemplateId || welcomeTemplateId),
      thank_you_template_id: Number(thankYouTemplateId),
      middle_template_ids: orderedServiceTagIds
        .map((typeId) => Number(selectedServiceTemplateIds[typeId]))
        .filter((tid) => Number.isFinite(tid) && tid > 0),
      first_name: input.firstName || "Alex",
      client_context: { organisation_name: businessName || goal.slice(0, 80) || undefined },
    };
    console.info("[wa-survey] POST /dashboard/service-scripts/wa-survey/send-test", sendBody);
    try {
      const result = await sendTestWaM.mutateAsync(sendBody);
      console.info("[wa-survey] send-test ok", result);
      toast.success(
        String(
          result.message ||
            "Survey test started — check WhatsApp and reply to continue the survey step by step.",
        ),
      );
    } catch (e) {
      console.error("[wa-survey] send-test failed", e);
      toast.error(e instanceof Error ? e.message : "WhatsApp test send failed");
      throw e;
    }
  };

  const onGenerateWaSurvey = async (): Promise<boolean> => {
    if (step3SelectionErrors.length) {
      setGenerateErrors(step3SelectionErrors);
      toast.error(step3SelectionErrors[0], { duration: 12000 });
      return false;
    }
    setGenerating(true);
    setGenerateErrors([]);
    try {
      const { typeOrder, selectedServiceTemplates, selectedMiddleTemplateIds, effectivePageCount } =
        buildStep3GeneratePayload();
      const generateBody = {
        industry_id: industryId,
        survey_type_id: typeOrder[0] || primarySurveyTypeId,
        selected_survey_type_ids: typeOrder,
        selected_service_template_ids: selectedServiceTemplates,
        selected_middle_template_ids: selectedMiddleTemplateIds,
        welcome_template_id: Number(welcomeTemplateId),
        thank_you_template_id: Number(thankYouTemplateId),
        variant: surveyVariant,
        privacy_mode: privacyMode,
        length: PAGE_COUNT_TO_LENGTH[effectivePageCount],
        page_count: effectivePageCount,
        auto_select_steps: autoSelectSteps,
        selected_step_roles: autoSelectSteps ? undefined : resolvedPageRoles,
        goal,
        allow_final_additional_feedback: allowFinalAdditionalFeedback,
      };
      console.info("[wa-survey] POST /dashboard/service-scripts/wa-survey/generate", generateBody);

      let generated: Record<string, unknown>;
      try {
        generated = await generateWaM.mutateAsync(generateBody);
        console.info("[wa-survey] generate ok", {
          page_count: generated.page_count,
          wa_template_id: generated.wa_template_id,
        });
      } catch (e) {
        const lines = parseWaSurveyGenerateErrors(e);
        setGenerateErrors(lines);
        toast.error(formatWaSurveyGenerateError(e), { duration: 12000 });
        return false;
      }

      setWaPreview(generated);
      setScript(String(generated.approved_script || script));
      setAnonymous(Boolean(generated.anonymous_responses));

      try {
        const id = await ensureOrder();
        const flowExtras = (generated.order_config_flow || {}) as Record<string, unknown>;
        const builderSequence = generated.builder_step_sequence;
        const isBuilderFlow = Array.isArray(builderSequence) && builderSequence.length > 0;
        const patchBody = {
          config: {
            goal,
            delivery: "whatsapp",
            survey_channel: "whatsapp",
            channels: ["whatsapp"],
            anonymous_responses: Boolean(generated.anonymous_responses),
            allow_follow_up: generated.allow_follow_up !== false,
            script: String(generated.approved_script || script),
            industry_id: industryId,
            survey_type_id: primarySurveyTypeId,
            selected_survey_type_ids: orderedServiceTagIds.length ? orderedServiceTagIds : selectedServiceTagIds,
            welcome_template_id: generated.welcome_template_id ?? Number(welcomeTemplateId),
            thank_you_template_id: generated.thank_you_template_id ?? Number(thankYouTemplateId),
            tell_us_more_template_id: generated.tell_us_more_template_id,
            survey_length: PAGE_COUNT_TO_LENGTH[effectivePageCount],
            page_count: effectivePageCount,
            page_roles: generated.page_roles,
            survey_variant: surveyVariant,
            privacy_mode: privacyMode,
            wa_template_id: generated.wa_template_id,
            whatsapp_flow: generated.whatsapp_flow,
            builder_runtime: generated.builder_runtime,
            builder_runtime_hash: generated.builder_runtime_hash,
            builder_step_sequence: generated.builder_step_sequence,
            builder_template_ids: generated.builder_template_ids,
            allow_final_additional_feedback: Boolean(
              generated.allow_final_additional_feedback ?? allowFinalAdditionalFeedback,
            ),
            package_id: packageId || undefined,
            ...(isBuilderFlow
              ? {
                  flow_engine: "linear",
                  flow_definition_id: null,
                  flow_snapshot: null,
                  flow_snapshot_json: null,
                }
              : {
                  flow_engine: generated.flow_engine,
                  flow_definition_id: generated.flow_definition_id,
                  flow_snapshot: generated.flow_snapshot,
                  ...flowExtras,
                }),
          },
        };
        console.info("[wa-survey] PATCH /service-orders/" + id, patchBody);
        await patchM.mutateAsync({ orderId: id, body: patchBody });
      } catch (e) {
        const msg = e instanceof Error ? e.message : "Could not save survey draft";
        setGenerateErrors([`Generated OK but draft save failed: ${msg}`]);
        toast.error(`Survey generated but draft save failed: ${msg}`, { duration: 12000 });
        return false;
      }

      setApproved(true);
      setGenerateErrors([]);
      toast.success("Survey generated from approved WhatsApp template library");
      return true;
    } finally {
      setGenerating(false);
    }
  };

  const onSaveDraft = async () => {
    try {
      const id = await ensureOrder();
      const baseConfig =
        channel === "whatsapp"
          ? {
              goal,
              delivery: "whatsapp" as const,
              anonymous_responses: anonymous,
              script,
              package_id: packageId || undefined,
              industry_id: industryId,
              survey_type_id: primarySurveyTypeId || undefined,
              selected_survey_type_ids: orderedServiceTagIds.length ? orderedServiceTagIds : selectedServiceTagIds,
              welcome_template_id: welcomeTemplateId ? Number(welcomeTemplateId) : undefined,
              thank_you_template_id: thankYouTemplateId ? Number(thankYouTemplateId) : undefined,
              survey_length: PAGE_COUNT_TO_LENGTH[pageCount],
              page_count: pageCount,
              privacy_mode: privacyMode,
              survey_variant: surveyVariant,
            }
          : {
              goal,
              delivery: "ai_call" as const,
              anonymous_responses: anonymous,
              script,
              package_id: packageId || undefined,
            };
      await patchM.mutateAsync({
        orderId: id,
        body: {
          title: surveyTitleFromGoal(goal),
          scheduled_start_at: startAt || null,
          scheduled_end_at: endAt || null,
          config: baseConfig,
        },
      });
      toast.success("Draft saved");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not save draft");
    }
  };

  const onUpload = async (files: FileList | null) => {
    if (!files?.length) return;
    setUploading(true);
    try {
      const id = await ensureOrder();
      if (channel === "whatsapp" && packageId) {
        await patchM.mutateAsync({
          orderId: id,
          body: {
            config: {
              delivery: "whatsapp",
              survey_channel: "whatsapp",
              channels: ["whatsapp"],
              package_id: packageId,
            },
          },
        });
      }
      await apiUploadFiles(`/service-orders/${encodeURIComponent(id)}/recipients/upload`, Array.from(files), "file");
      await qc.invalidateQueries({ queryKey: queryKeys.orderRecipients(id) });
      toast.success("Contacts uploaded");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const onDownloadTemplate = async () => {
    try {
      await downloadAuthenticatedFile("/service-orders/template.csv", "voxbulk-contacts-template.csv");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Download failed");
    }
  };

  const industries = (waIndustriesQ.data?.industries || []) as Array<Record<string, unknown>>;
  const savePending = createM.isPending || patchM.isPending;

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="Surveys"
        title="Create new survey"
        description="Pick a channel — AI phone call or WhatsApp — then run through the guided wizard."
      />

      {!channel && (
        <ChannelPicker anonymous={anonymous} setAnonymous={setAnonymous} onPick={(c) => setChannel(c)} />
      )}

      {channel === "whatsapp" && (
        <SurveyWaWizard
          onBack={() => setChannel(null)}
          anonymous={anonymous}
          industryId={industryId}
          setIndustryId={setIndustryId}
          industries={industries}
          industriesLoading={waIndustriesQ.isLoading}
          selectedServiceTagIds={selectedServiceTagIds}
          orderedServiceTagIds={orderedServiceTagIds}
          setOrderedServiceTagIds={setOrderedServiceTagIds}
          toggleServiceTag={toggleServiceTag}
          serviceTypes={serviceTypes}
          serviceTypesLoading={waTypesQ.isLoading}
          serviceTagErrors={serviceTagErrors}
          step3SelectionErrors={step3SelectionErrors}
          welcomeTemplateId={welcomeTemplateId}
          setWelcomeTemplateId={setWelcomeTemplateId}
          thankYouTemplateId={thankYouTemplateId}
          setThankYouTemplateId={setThankYouTemplateId}
          welcomeTemplates={welcomeTemplates}
          thankYouTemplates={thankYouTemplates}
          selectedServiceTemplateIds={selectedServiceTemplateIds}
          onSelectServiceTemplate={onSelectServiceTemplate}
          libraryTemplatesByTypeId={libraryTemplatesByTypeId}
          libraryTemplatesLoading={libraryTemplatesLoading}
          allowFinalAdditionalFeedback={allowFinalAdditionalFeedback}
          setAllowFinalAdditionalFeedback={setAllowFinalAdditionalFeedback}
          privacyMode={privacyMode}
          setPrivacyMode={setPrivacyMode}
          pageCount={pageCount}
          setPageCount={setPageCount}
          autoSelectSteps={autoSelectSteps}
          setAutoSelectSteps={setAutoSelectSteps}
          manualMiddleRoles={manualMiddleRoles}
          moveMiddleRole={moveMiddleRole}
          removeMiddleRole={removeMiddleRole}
          addMiddleRole={addMiddleRole}
          availableMiddleRoles={availableMiddleRoles}
          resolvedPageRoles={resolvedPageRoles}
          pageOrderValid={pageOrderValid}
          stepBankByRole={stepBankByRole}
          stepBankLoading={stepBankQ.isLoading}
          goal={goal}
          setGoal={setGoal}
          script={script}
          setScript={setScript}
          approved={approved}
          setApproved={setApproved}
          generating={generating}
          generateErrors={generateErrors}
          onGenerateWaSurvey={onGenerateWaSurvey}
          waPreview={waPreview}
          startAt={startAt}
          setStartAt={setStartAt}
          endAt={endAt}
          setEndAt={setEndAt}
          packageId={packageId}
          setPackageId={setPackageId}
          packages={packages}
          packagesLoading={packagesQ.isLoading}
          fileRef={fileRef}
          uploading={uploading}
          onUpload={onUpload}
          onDownloadTemplate={onDownloadTemplate}
          onSaveDraft={onSaveDraft}
          savePending={savePending}
          contactsCount={contactsCount}
          uploadedContacts={uploadedContacts}
          userTestPhone={userTestPhone}
          businessName={businessName}
          onSendWaTest={onSendWaTest}
          sendTestPending={sendTestWaM.isPending}
          onOpenLaunch={onOpenLaunch}
          launchPending={launchM.isPending || payBusy}
          costHint={
            eligibilityQ.data?.payment_required
              ? eligibilityQ.data.amount_due_display || undefined
              : eligibilityQ.data?.can_launch
                ? "Included"
                : undefined
          }
        />
      )}

      {channel === "phone" && (
        <SurveyPhoneWizard
          onBack={() => setChannel(null)}
          anonymous={anonymous}
          goal={goal}
          setGoal={setGoal}
          script={script}
          setScript={setScript}
          approved={approved}
          setApproved={setApproved}
          startAt={startAt}
          setStartAt={setStartAt}
          endAt={endAt}
          setEndAt={setEndAt}
          packageId={packageId}
          setPackageId={setPackageId}
          packages={packages}
          packagesLoading={packagesQ.isLoading}
          fileRef={fileRef}
          uploading={uploading}
          onUpload={onUpload}
          onDownloadTemplate={onDownloadTemplate}
          onSaveDraft={onSaveDraft}
          savePending={savePending}
          contactsCount={contactsCount}
          onOpenLaunch={() => void onOpenLaunch("now")}
          launchPending={launchM.isPending || payBusy}
        />
      )}

      <SurveyLaunchQuoteModal
        open={launchOpen}
        onOpenChange={setLaunchOpen}
        data={{
          campaignName: surveyTitleFromGoal(goal),
          recipientCount: contactsCount,
          channelLabel,
          launchModeLabel,
          packageName: eligibilityQ.data?.billing?.plan_name || eligibilityQ.data?.package_label,
        }}
        eligibility={eligibilityQ.data || null}
        eligibilityLoading={eligibilityQ.isLoading || eligibilityQ.isFetching}
        eligibilityError={
          eligibilityQ.error instanceof Error ? eligibilityQ.error.message : eligibilityQ.isError ? "Could not load billing state" : null
        }
        launchBlockers={
          contactsCount <= 0 ? ["Upload at least one contact before launch."] : channel === "whatsapp" && !approved ? ["Approve your survey before launch."] : []
        }
        onRefreshEligibility={refreshLaunchEligibility}
        onLaunch={onLaunchSurvey}
        onPayLaunch={onPayLaunchSurvey}
        payBusy={payBusy || launchM.isPending}
        gcAvailable={gcReady}
      />
    </div>
  );
}
