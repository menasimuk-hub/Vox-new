import { createFileRoute, useNavigate } from "@tanstack/react-router";
import * as React from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { SurveyEditActionBar } from "@/components/survey-edit-action-bar";
import { ChannelPicker } from "@/components/create-wizard";
import { SurveyPhoneWizard } from "@/components/create-wizard/survey-phone-wizard";
import type { UploadedContactRow } from "@/components/create-wizard/uploaded-contacts-table";
import { SurveyWaWizard } from "@/components/create-wizard/survey-wa-wizard";
import { pageCountFromSelectedTypes } from "@/components/create-wizard/survey-wa-template-step";
import { SurveyLaunchQuoteModal } from "@/components/modals";
import { WalletTopupDialog } from "@/components/wallet-topup-dialog";
import { apiFetch, apiUploadFiles, downloadAuthenticatedFile } from "@/lib/api";
import { GC_ORDER_ID_KEY } from "@/lib/billing/gocardless";
import { surveyTitleFromGoal, normalizeSurveyName } from "@/lib/survey-title";
import {
  buildCampaignRejectTitles,
  surveyTemplateLabel,
  firstStepLabelFromConfig,
  resolveSurveyStepLabel,
  sanitizeStepLabelFromApi,
} from "@/lib/survey-step-labels";
import { toIsoFromLocal } from "@/lib/datetime";
import { buildSurveyDraftCreateBody, buildSurveyDraftPatchBody, resolveSurveyNameForSave } from "@/lib/survey-draft-payload";
import { buildFullSurveyDraftConfig, hydrateSurveyDraftFromOrder, type SurveyDraftWizardSnapshot } from "@/lib/survey-draft-config";
import { scriptModerationBanner } from "@/lib/script-moderation";
import {
  pickDefaultSurveyAgent,
  useCreateServiceOrder,
  fetchSurveyLaunchEligibility,
  type SurveyLaunchEligibility,
  useGenerateSurveyScript,
  useGenerateWaSurvey,
  useLaunchSurveyCampaign,
  useOrderRecipients,
  useOrganisation,
  usePatchServiceOrder,
  usePatchOrderRecipient,
  useSendWaSurveyTest,
  useServiceOrder,
  useSurveyAgents,
  useSurveyPackages,
  useWaSurveyIndustries,
  useWaSurveyLibraryTemplates,
  useWaSurveyStepBank,
  useWaSurveySystemTemplates,
  useWaSurveyTypes,
} from "@/lib/queries";
import { logLaunchFlow } from "@/lib/launch-flow-log";
import {
  billingCheckErrorMessage,
  resolveBillingCheckPhase,
} from "@/lib/survey-launch-billing";
import { formatWaSurveyGenerateError, parseWaSurveyGenerateErrors } from "@/lib/wa-survey-generate-error";
import {
  SURVEY_TYPE_LIBRARY_PRIVACY_MODE,
  filterSystemTemplatesByPrivacy,
} from "@/lib/wa-survey-template-mode";
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

function toLocalInput(iso?: string | null) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    const pad = (n: number) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  } catch {
    return "";
  }
}

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
  const generatePhoneM = useGenerateSurveyScript();
  const sendTestWaM = useSendWaSurveyTest();
  const agentsQ = useSurveyAgents();

  const [channel, setChannel] = React.useState<Channel>(null);
  const [surveyName, setSurveyName] = React.useState("");
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
    SURVEY_TYPE_LIBRARY_PRIVACY_MODE,
    channel === "whatsapp",
  );
  const [approved, setApproved] = React.useState(false);
  const [approveScriptPending, setApproveScriptPending] = React.useState(false);
  const [anonymous, setAnonymous] = React.useState(false);
  const [goal, setGoal] = React.useState(
    "Measure satisfaction with our new hygienist team and identify the top improvement.",
  );
  const [script, setScript] = React.useState(
    "1. On a scale of 0-10, how likely are you to recommend us?\n2. What stood out about your visit?\n3. Anything we could improve?",
  );
  const [agentId, setAgentId] = React.useState("");
  const [systemPrompt, setSystemPrompt] = React.useState("");
  const [expectedDurationMinutes, setExpectedDurationMinutes] = React.useState<number | undefined>(3);
  const [startAt, setStartAt] = React.useState("");
  const [endAt, setEndAt] = React.useState("");
  const [packageId, setPackageId] = React.useState("");
  const [orderId, setOrderId] = React.useState<string | null>(null);
  const [launchOpen, setLaunchOpen] = React.useState(false);
  const [launchOrderId, setLaunchOrderId] = React.useState<string | null>(null);
  const [launchMode, setLaunchMode] = React.useState<"now" | "schedule" | "recurring">("now");
  const [payBusy, setPayBusy] = React.useState(false);
  const [topupOpen, setTopupOpen] = React.useState(false);
  const [eligibilityLoading, setEligibilityLoading] = React.useState(false);
  const [launchEligibility, setLaunchEligibility] = React.useState<SurveyLaunchEligibility | null>(null);
  const [eligibilityError, setEligibilityError] = React.useState<string | null>(null);
  const eligibilityFetchKeyRef = React.useRef("");
  const eligibilityInFlightRef = React.useRef<Promise<SurveyLaunchEligibility | null> | null>(null);
  const fileRef = React.useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = React.useState(false);
  const [uploadTypeAck, setUploadTypeAck] = React.useState(false);
  const [uploadConsent, setUploadConsent] = React.useState(false);
  const [launchConsent, setLaunchConsent] = React.useState(false);
  const qc = useQueryClient();
  const orderQ = useServiceOrder(orderId);
  const recipientsQ = useOrderRecipients(orderId);
  const patchRecipientM = usePatchOrderRecipient(orderId);
  const [recipientContactDraft, setRecipientContactDraft] = React.useState<
    Record<string, { name: string; phone: string; email: string }>
  >({});
  const uploadedContacts = React.useMemo((): UploadedContactRow[] => {
    const rows = recipientsQ.data?.recipients || [];
    return rows.map((row) => ({
      id: String(row.id || "").trim() || undefined,
      name: String(row.name || "").trim(),
      phone: String(row.phone || "").trim(),
      email: String(row.email || "").trim(),
      language: String(row.language || row.locale || "").trim(),
      phoneCallAllowed:
        typeof (row as { phone_call_allowed?: boolean }).phone_call_allowed === "boolean"
          ? (row as { phone_call_allowed?: boolean }).phone_call_allowed
          : undefined,
      phoneCallBlockReason: String((row as { phone_call_block_reason?: string }).phone_call_block_reason || "").trim() || null,
    }));
  }, [recipientsQ.data?.recipients]);

  const recipientContactValue = (c: UploadedContactRow, field: "name" | "phone" | "email") => {
    if (!c.id) return String(c[field] || "");
    const draft = recipientContactDraft[c.id];
    if (draft) return draft[field];
    return String(c[field] || "");
  };

  const onRecipientContactChange = (c: UploadedContactRow, field: "name" | "phone" | "email", value: string) => {
    if (!c.id) return;
    setRecipientContactDraft((prev) => ({
      ...prev,
      [c.id!]: {
        name: recipientContactValue(c, "name"),
        phone: recipientContactValue(c, "phone"),
        email: recipientContactValue(c, "email"),
        [field]: value,
      },
    }));
  };

  const onRecipientContactBlur = async (c: UploadedContactRow, field: "name" | "phone" | "email") => {
    if (!orderId || !c.id) return;
    const nextVal = recipientContactValue(c, field);
    const currentVal = String(c[field] || "");
    if (nextVal.trim() === currentVal.trim()) return;
    try {
      await patchRecipientM.mutateAsync({ recipientId: c.id, [field]: nextVal.trim() });
      setRecipientContactDraft((prev) => {
        const next = { ...prev };
        delete next[c.id!];
        return next;
      });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not update contact");
      setRecipientContactDraft((prev) => ({
        ...prev,
        [c.id!]: {
          name: field === "name" ? currentVal : recipientContactValue(c, "name"),
          phone: field === "phone" ? currentVal : recipientContactValue(c, "phone"),
          email: field === "email" ? currentVal : recipientContactValue(c, "email"),
        },
      }));
    }
  };
  const contactsCount = uploadedContacts.filter((c) => c.phone).length;
  const dialableContactsCount =
    channel === "phone"
      ? uploadedContacts.filter((c) => c.phone && c.phoneCallAllowed !== false).length
      : contactsCount;
  const blockedAllowlistCount =
    channel === "phone" ? uploadedContacts.filter((c) => c.phone && c.phoneCallAllowed === false).length : 0;
  const surveyId = String(orderQ.data?.campaign_id || orderQ.data?.survey_id || "").trim() || null;
  const recipientsLoading = recipientsQ.isFetching || recipientsQ.isLoading;
  const recipientsError =
    recipientsQ.isError && recipientsQ.error instanceof Error ? recipientsQ.error.message : null;
  const launchM = useLaunchSurveyCampaign();
  const activeLaunchOrderId = launchOrderId || orderId;
  const eligibilityCacheKey = React.useMemo(
    () => `${contactsCount}:${packageId || ""}`,
    [contactsCount, packageId],
  );
  const billingCheckPhase = resolveBillingCheckPhase({
    orderId: activeLaunchOrderId,
    launchOpen,
    isLoading: eligibilityLoading,
    isFetching: false,
    isError: Boolean(eligibilityError),
    errorMessage: eligibilityError,
    hasData: Boolean(launchEligibility),
    timedOut: Boolean(eligibilityError?.toLowerCase().includes("timed out")),
  });
  const launchCostHint = React.useMemo(() => {
    const e = launchEligibility;
    if (!e) return undefined;
    if (e.can_launch && !e.payment_required) {
      return e.estimated_send_cost_display ? `${e.estimated_send_cost_display} · included` : "Included in allowance";
    }
    if (e.payment_required) {
      if (
        e.estimated_send_cost_display &&
        e.minimum_charge_display &&
        e.estimated_send_cost_display !== e.minimum_charge_display
      ) {
        return `Send ${e.estimated_send_cost_display} · due ${e.amount_due_display || "—"}`;
      }
      return e.amount_due_display || undefined;
    }
    return undefined;
  }, [launchEligibility]);
  const openingLaunchRef = React.useRef(false);
  const hydratedOrderRef = React.useRef<string | null>(null);
  const navigatedToResultsRef = React.useRef(false);
  const resolvedSurveyTitle = React.useCallback(
    () => resolveSurveyNameForSave(surveyName),
    [surveyName],
  );

  const launchLogCtx = React.useCallback(
    (extra?: Record<string, unknown>) => ({
      component: "CreateSurvey",
      survey_name: resolvedSurveyTitle(),
      title: orderQ.data?.title || "",
      orderId,
      launchOrderId,
      ...extra,
    }),
    [resolvedSurveyTitle, orderQ.data?.title, orderId, launchOrderId],
  );

  React.useEffect(() => {
    const restored = (orderIdSearch || "").trim();
    if (!restored || restored.toLowerCase() === "new") return;
    if (!orderId) setOrderId(restored);
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

  React.useEffect(() => {
    const order = orderQ.data;
    if (!order?.id || hydratedOrderRef.current === order.id) return;
    hydratedOrderRef.current = order.id;
    const hydrated = hydrateSurveyDraftFromOrder({
      survey_name: order.survey_name,
      title: order.title,
      scheduled_start_at: order.scheduled_start_at,
      scheduled_end_at: order.scheduled_end_at,
      config: (order.config || {}) as Record<string, unknown>,
    });

    if (hydrated.surveyName) setSurveyName(hydrated.surveyName);
    if (hydrated.goal) setGoal(hydrated.goal);
    if (hydrated.script) setScript(hydrated.script);
    if (hydrated.agentId) setAgentId(hydrated.agentId);
    if (hydrated.systemPrompt) setSystemPrompt(hydrated.systemPrompt);
    if (hydrated.expectedDurationMinutes != null) setExpectedDurationMinutes(hydrated.expectedDurationMinutes);
    if (hydrated.industryId) setIndustryId(hydrated.industryId);
    if (hydrated.selectedServiceTagIds) setSelectedServiceTagIds(hydrated.selectedServiceTagIds);
    if (hydrated.orderedServiceTagIds) setOrderedServiceTagIds(hydrated.orderedServiceTagIds);
    if (hydrated.welcomeTemplateId) setWelcomeTemplateId(hydrated.welcomeTemplateId);
    if (hydrated.thankYouTemplateId) setThankYouTemplateId(hydrated.thankYouTemplateId);
    if (hydrated.selectedServiceTemplateIds) setSelectedServiceTemplateIds(hydrated.selectedServiceTemplateIds);
    if (hydrated.packageId) setPackageId(hydrated.packageId);
    if (hydrated.privacyMode) setPrivacyMode(hydrated.privacyMode);
    if (typeof hydrated.allowFinalAdditionalFeedback === "boolean") {
      setAllowFinalAdditionalFeedback(hydrated.allowFinalAdditionalFeedback);
    }
    if (typeof hydrated.anonymous === "boolean") setAnonymous(hydrated.anonymous);
    if (typeof hydrated.autoSelectSteps === "boolean") setAutoSelectSteps(hydrated.autoSelectSteps);
    if (hydrated.pageCount) setPageCount(hydrated.pageCount);
    if (hydrated.manualMiddleRoles) setManualMiddleRoles(hydrated.manualMiddleRoles);
    if (hydrated.startAt) setStartAt(hydrated.startAt);
    if (hydrated.endAt) setEndAt(hydrated.endAt);
    if (hydrated.channel) setChannel(hydrated.channel);
    if (hydrated.approved) setApproved(true);
    if (hydrated.waPreview) setWaPreview(hydrated.waPreview);
    const cfg = (order.config || {}) as Record<string, unknown>;
    if (cfg.upload_consent_at) {
      setUploadTypeAck(true);
      setUploadConsent(true);
    }
    if (cfg.launch_consent_at) setLaunchConsent(true);
  }, [orderQ.data]);

  React.useEffect(() => {
    if (channel !== "phone" || agentId) return;
    const defaultAgent = pickDefaultSurveyAgent(agentsQ.data || []);
    if (defaultAgent?.id) setAgentId(defaultAgent.id);
  }, [channel, agentId, agentsQ.data]);

  const surveyOrderConfig = (orderQ.data?.config || {}) as Record<string, unknown>;
  const scriptModerationMessage = React.useMemo(
    () => scriptModerationBanner(surveyOrderConfig),
    [surveyOrderConfig],
  );

  const phoneLaunchBlockers = React.useMemo(() => {
    if (channel !== "phone") return [] as string[];
    const blockers: string[] = [];
    if (dialableContactsCount <= 0) {
      blockers.push(
        blockedAllowlistCount > 0
          ? "No contacts on the AI call allowlist — fix highlighted numbers or upload allowed prefixes."
          : "Upload at least one contact before launch.",
      );
    }
    if (!approved) blockers.push("Approve your survey script before launch.");
    if (scriptModerationMessage) blockers.push(scriptModerationMessage);
    if (!agentId) blockers.push("Select a survey voice agent.");
    if (!startAt || !endAt) blockers.push("Set calling start and end date/time.");
    else if (new Date(startAt) >= new Date(endAt)) blockers.push("Calling end must be after calling start.");
    return blockers;
  }, [channel, dialableContactsCount, blockedAllowlistCount, approved, agentId, startAt, endAt, scriptModerationMessage]);

  const onGeneratePhoneScript = async () => {
    if (!goal.trim()) {
      toast.error("Add a survey goal before generating");
      return;
    }
    if (!agentId) {
      toast.error("Select a survey voice agent");
      return;
    }
    try {
      const res = await generatePhoneM.mutateAsync({
        goal,
        contact_method: "AI phone call",
        max_call_length: "4 minutes",
        agent_id: agentId,
        client_context: { agent_id: agentId },
      });
      const text = String(res.script_text || res.script || "").trim();
      const system = String(res.system_prompt || text).trim();
      if (!text) {
        toast.error("AI did not return a script — try again");
        return;
      }
      const rawDuration = res.expected_duration_minutes;
      const duration =
        rawDuration != null && !Number.isNaN(Number(rawDuration))
          ? Math.max(2, Math.min(10, Number(rawDuration)))
          : undefined;
      setScript(text);
      setSystemPrompt(system);
      setExpectedDurationMinutes(duration);
      setApproved(false);
      toast.success(duration ? `AI script ready — est. ~${duration} min per call` : "AI script ready — review and approve when happy");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not generate script");
    }
  };

  const channelLabel = channel === "whatsapp" ? "WhatsApp" : channel === "phone" ? "AI phone call" : "—";
  const launchModeLabel =
    launchMode === "now"
      ? "Send now"
      : launchMode === "schedule"
        ? `Scheduled · ${startAt || "—"}`
        : `Recurring · starting ${endAt || startAt || "—"}`;

  const creatingRef = React.useRef(false);
  const ensureOrder = React.useCallback(async () => {
    if (orderId) return orderId;
    if (creatingRef.current) {
      await new Promise((r) => setTimeout(r, 200));
      if (orderId) return orderId;
    }
    creatingRef.current = true;
    try {
    const deliveryChannel = channel === "whatsapp" ? "whatsapp" : "ai_call";
    const created = await createM.mutateAsync(
      buildSurveyDraftCreateBody(surveyName, {
        goal,
        delivery: deliveryChannel,
        anonymous_responses: anonymous,
        script,
        package_id: packageId || undefined,
      }),
    );
    setOrderId(created.id);
    return created.id;
    } finally {
      creatingRef.current = false;
    }
  }, [orderId, createM, surveyName, goal, channel, anonymous, script, packageId]);

  const resolvedPageRolesRef = React.useRef<string[]>([]);

  const businessName = React.useMemo(() => {
    const org = orgQ.data;
    return String(org?.display_name || org?.name || "").trim();
  }, [orgQ.data]);

  const buildDraftConfig = React.useCallback(
    (overrides?: Partial<SurveyDraftWizardSnapshot>) => {
    const persisted = (orderQ.data?.config || {}) as Record<string, unknown>;
    return buildFullSurveyDraftConfig(
      {
        channel,
        goal,
        script,
        anonymous,
        packageId,
        industryId,
        primarySurveyTypeId,
        orderedServiceTagIds,
        selectedServiceTagIds,
        selectedServiceTemplateIds,
        welcomeTemplateId,
        thankYouTemplateId,
        pageCount,
        privacyMode,
        surveyVariant,
        allowFinalAdditionalFeedback,
        autoSelectSteps,
        resolvedPageRoles: resolvedPageRolesRef.current,
        waPreview,
        approved,
        agentId,
        systemPrompt,
        expectedDurationMinutes,
        ...overrides,
      },
      persisted,
      { organisationName: businessName || undefined },
    );
  }, [
    channel,
    goal,
    anonymous,
    script,
    packageId,
    businessName,
    industryId,
    primarySurveyTypeId,
    orderedServiceTagIds,
    selectedServiceTagIds,
    selectedServiceTemplateIds,
    welcomeTemplateId,
    thankYouTemplateId,
    pageCount,
    privacyMode,
    surveyVariant,
    allowFinalAdditionalFeedback,
    autoSelectSteps,
    waPreview,
    approved,
    agentId,
    systemPrompt,
    expectedDurationMinutes,
    orderQ.data?.config,
  ]);

  const onApproveSurveyScript = React.useCallback(async () => {
    if (!script.trim()) {
      toast.error("Generate or paste a script before approving");
      return;
    }
    setApproveScriptPending(true);
    try {
      const id = await ensureOrder();
      const draftConfig = buildDraftConfig({ approved: true });
      const patchBody = buildSurveyDraftPatchBody(surveyName, draftConfig, {
        scheduled_start_at: toIsoFromLocal(startAt),
        scheduled_end_at: toIsoFromLocal(endAt),
      });
      const saved = await patchM.mutateAsync({ orderId: id, body: patchBody });
      const cfg = (saved.config || {}) as Record<string, unknown>;
      if (cfg.script_approved === true) {
        setApproved(true);
        toast.success("Script approved — save draft or continue to contacts");
      } else {
        setApproved(false);
        const reason = String(cfg.script_moderation_reason || "").trim();
        toast.error(
          reason
            ? `Script blocked: ${reason} Edit the text and approve again, or wait for VoxBulk admin approval.`
            : "Script could not be approved — please review the content and try again.",
        );
      }
      void orderQ.refetch();
    } catch (e) {
      setApproved(false);
      toast.error(e instanceof Error ? e.message : "Could not approve script");
    } finally {
      setApproveScriptPending(false);
    }
  }, [buildDraftConfig, ensureOrder, endAt, orderQ, patchM, script, startAt, surveyName]);

  const saveSurveyDraft = React.useCallback(
    async (purpose: "save" | "launch") => {
      logLaunchFlow("[save-draft:start]", { ...launchLogCtx(), source: `saveSurveyDraft:${purpose}` });
      const id = await ensureOrder();
      const nowIso = new Date().toISOString();
      const draftConfig = buildDraftConfig();
      if (uploadTypeAck && uploadConsent) {
        draftConfig.upload_consent_at = String(draftConfig.upload_consent_at || nowIso);
      }
      if (purpose === "launch" && launchConsent) {
        draftConfig.launch_consent_at = nowIso;
        draftConfig.upload_consent_at = draftConfig.upload_consent_at || nowIso;
      }
      const patchBody = buildSurveyDraftPatchBody(surveyName, draftConfig, {
        scheduled_start_at: toIsoFromLocal(startAt),
        scheduled_end_at: toIsoFromLocal(endAt),
        ...(purpose === "launch"
          ? { run_mode: launchMode === "now" ? ("manual" as const) : ("scheduled" as const) }
          : {}),
      });
      const saved = await patchM.mutateAsync({ orderId: id, body: patchBody });
      if (!saved?.id) throw new Error("Draft was not persisted");
      setOrderId(saved.id);
      if (purpose === "launch") setLaunchOrderId(saved.id);
      logLaunchFlow("[save-draft:done]", {
        ...launchLogCtx(),
        draftId: saved.id,
        orderId: saved.id,
        title: saved.title,
        survey_name: saved.survey_name,
        source: `saveSurveyDraft:${purpose}`,
      });
      return saved;
    },
    [
      buildDraftConfig,
      ensureOrder,
      launchLogCtx,
      launchMode,
      patchM,
      startAt,
      endAt,
      surveyName,
      uploadTypeAck,
      uploadConsent,
      launchConsent,
    ],
  );

  const runLaunchEligibilityCheck = async (orderId: string, cacheKey: string, force = false) => {
    const dedupeKey = `${orderId}:${cacheKey}`;
    if (!force && eligibilityFetchKeyRef.current === dedupeKey && launchEligibility) {
      return launchEligibility;
    }
    if (eligibilityInFlightRef.current) {
      return eligibilityInFlightRef.current;
    }

    eligibilityFetchKeyRef.current = dedupeKey;
    setEligibilityLoading(true);
    setEligibilityError(null);
    const promise = (async () => {
      try {
        const controller = new AbortController();
        const timeoutId = window.setTimeout(() => controller.abort(), 15_000);
        try {
          const data = await fetchSurveyLaunchEligibility(orderId, controller.signal, { force });
          setLaunchEligibility(data);
          return data;
        } finally {
          window.clearTimeout(timeoutId);
        }
      } catch (e) {
        if (!force) eligibilityFetchKeyRef.current = "";
        const message = e instanceof Error ? e.message : "Could not load billing state";
        setEligibilityError(message);
        throw e;
      } finally {
        setEligibilityLoading(false);
      }
    })();
    eligibilityInFlightRef.current = promise;
    try {
      return await promise;
    } finally {
      eligibilityInFlightRef.current = null;
    }
  };

  const onOpenLaunch = async (mode: "now" | "schedule" | "recurring") => {
    if (!launchConsent) {
      toast.error("Confirm launch consent before continuing");
      return;
    }
    if (openingLaunchRef.current || launchOpen) return;
    openingLaunchRef.current = true;
    navigatedToResultsRef.current = false;
    logLaunchFlow("[launch-click]", { ...launchLogCtx(), source: "onOpenLaunch" });
    try {
      const saved = await saveSurveyDraft("launch");
      const cacheKey = `${contactsCount}:${packageId || ""}`;
      setLaunchOrderId(saved.id);
      setLaunchMode(mode);
      setLaunchOpen(true);
      await runLaunchEligibilityCheck(saved.id, cacheKey, false);
      logLaunchFlow("[launch-modal:open]", {
        ...launchLogCtx(),
        draftId: saved.id,
        orderId: saved.id,
        source: "onOpenLaunch",
      });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not open launch");
    } finally {
      openingLaunchRef.current = false;
    }
  };

  const refreshLaunchEligibility = () => {
    if (!activeLaunchOrderId) return;
    eligibilityFetchKeyRef.current = "";
    void runLaunchEligibilityCheck(activeLaunchOrderId, eligibilityCacheKey, true).catch((e) => {
      toast.error(e instanceof Error ? e.message : "Could not refresh billing state");
    });
  };

  const onLaunchSurvey = async () => {
    setPayBusy(true);
    try {
      const saved = await saveSurveyDraft("launch");
      const id = saved.id;
      if (!id) throw new Error("Save your draft before launch");
      const runMode = launchMode === "now" ? "now" : "schedule";
      logLaunchFlow("[launch-api:start]", { ...launchLogCtx(), orderId: id, draftId: id, source: "onLaunchSurvey" });
      const result = await launchM.mutateAsync({ orderId: id, run_mode: runMode });
      const launchedId = String(result.order_id || result.order?.id || id);
      logLaunchFlow("[launch-api:done]", {
        ...launchLogCtx(),
        orderId: launchedId,
        draftId: id,
        source: "onLaunchSurvey",
      });
      const scheduledLabel =
        runMode === "schedule" && startAt
          ? new Date(toIsoFromLocal(startAt) || startAt).toLocaleString()
          : null;
      toast.success(
        result.message ||
          (runMode === "now" ? "Survey launched" : scheduledLabel ? `Survey scheduled for ${scheduledLabel}` : "Survey scheduled"),
      );
      setLaunchOrderId(null);
      await qc.invalidateQueries({ queryKey: queryKeys.serviceOrders("survey") });
      await qc.invalidateQueries({ queryKey: queryKeys.serviceOrder(launchedId) });
      if (navigatedToResultsRef.current) return;
      navigatedToResultsRef.current = true;
      logLaunchFlow("[navigate]", {
        ...launchLogCtx(),
        orderId: launchedId,
        source: "onLaunchSurvey",
        extra: { to: "/surveys/results", searchOrderId: launchedId },
      });
      void navigate({
        to: "/surveys/results",
        search: { orderId: launchedId },
        replace: true,
      });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Launch failed");
      throw e;
    } finally {
      setPayBusy(false);
    }
  };

  const onOpenWalletTopup = () => {
    setTopupOpen(true);
  };

  const onWalletToppedUp = () => {
    refreshLaunchEligibility();
    toast.success("Wallet updated — you can launch when ready.");
  };

  const userTestPhone = React.useMemo(() => {
    const profile = session?.profile as Record<string, unknown> | undefined;
    const phone = profile?.phone as Record<string, unknown> | undefined;
    const fromUser = String(phone?.phone_e164 || phone?.phone_number || "").trim();
    if (fromUser) return fromUser;
    return String(orgQ.data?.contact_phone || "").trim();
  }, [session?.profile, orgQ.data?.contact_phone]);

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

  const handleIndustryChange = React.useCallback(
    (nextId: string) => {
      if (nextId === industryId) return;
      setIndustryId(nextId);
      setSelectedServiceTagIds([]);
      setOrderedServiceTagIds([]);
      setWelcomeTemplateId("");
      setThankYouTemplateId("");
      setSelectedServiceTemplateIds({});
      setApproved(false);
      setGenerateErrors([]);
      setWaPreview(null);
    },
    [industryId],
  );

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

  const campaignRejectTitles = React.useMemo(
    () =>
      buildCampaignRejectTitles(surveyName, goal, [
        surveyTitleFromGoal(goal),
        orderQ.data?.title || "",
        orderQ.data?.survey_name || "",
      ]),
    [surveyName, goal, orderQ.data?.title, orderQ.data?.survey_name],
  );

  const firstSurveyStepName = React.useMemo(() => {
    const fromApi = sanitizeStepLabelFromApi(String(orderQ.data?.first_step_name || ""), campaignRejectTitles);
    if (fromApi) return fromApi;
    const fromConfig = firstStepLabelFromConfig(orderQ.data?.config, campaignRejectTitles);
    if (fromConfig) return fromConfig;
    const typeId = orderedServiceTagIds[0];
    if (!typeId) {
      const previewSeq = (waPreview?.builder_step_sequence || []) as Array<Record<string, unknown>>;
      if (previewSeq[0]) {
        return resolveSurveyStepLabel(previewSeq[0], { questionNumber: 1, rejectTitles: campaignRejectTitles });
      }
      return "Question 1";
    }
    const typeName = String(serviceTypes.find((t) => String(t.id) === typeId)?.name || "");
    const templateId = selectedServiceTemplateIds[typeId];
    const row = (libraryTemplatesByTypeId[typeId] || []).find((t) => String(t.id) === templateId);
    const fromWizard = surveyTemplateLabel(row, typeName, 1, campaignRejectTitles);
    if (fromWizard && fromWizard !== "Survey question") return fromWizard;
    const previewSeq = (waPreview?.builder_step_sequence || []) as Array<Record<string, unknown>>;
    if (previewSeq[0]) {
      return resolveSurveyStepLabel(previewSeq[0], {
        surveyTypeName: typeName,
        questionNumber: 1,
        rejectTitles: campaignRejectTitles,
      });
    }
    return resolveSurveyStepLabel(null, {
      surveyTypeName: typeName,
      questionNumber: 1,
      rejectTitles: campaignRejectTitles,
    });
  }, [
    orderQ.data?.first_step_name,
    orderQ.data?.config,
    orderQ.data?.title,
    campaignRejectTitles,
    orderedServiceTagIds,
    serviceTypes,
    selectedServiceTemplateIds,
    libraryTemplatesByTypeId,
    waPreview,
  ]);

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

  const filterSystemTemplatesByPrivacyMode = React.useCallback(
    (rows: Array<Record<string, unknown>>) => filterSystemTemplatesByPrivacy(rows, privacyMode),
    [privacyMode],
  );

  const handleAnonymousChange = React.useCallback((value: boolean) => {
    setAnonymous(value);
    setPrivacyMode(value ? "on" : "off");
    setWelcomeTemplateId("");
    setThankYouTemplateId("");
  }, []);

  const welcomeTemplates = React.useMemo(
    () =>
      filterSystemTemplatesByPrivacyMode(
        (systemTemplatesQ.data?.templates?.welcome || []) as Array<Record<string, unknown>>,
      ),
    [systemTemplatesQ.data, filterSystemTemplatesByPrivacyMode],
  );
  const thankYouTemplates = React.useMemo(
    () =>
      filterSystemTemplatesByPrivacyMode(
        (systemTemplatesQ.data?.templates?.thank_you || []) as Array<Record<string, unknown>>,
      ),
    [systemTemplatesQ.data, filterSystemTemplatesByPrivacyMode],
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
    if (!autoSelectSteps) return;
    const suggested = suggestedRoles[String(pageCount)] || [];
    const middle = suggested.filter((r) => r !== "start" && r !== "completion");
    setManualMiddleRoles(middle.slice(0, Math.max(0, pageCount - 2)));
  }, [pageCount, primarySurveyTypeId, surveyVariant, suggestedRoles, autoSelectSteps]);

  const resolvedPageRoles = React.useMemo(() => {
    const auto = suggestedRoles[String(pageCount)];
    if (autoSelectSteps && auto?.length === pageCount) return auto;
    const middle = manualMiddleRoles.slice(0, Math.max(0, pageCount - 2));
    return ["start", ...middle, "completion"];
  }, [autoSelectSteps, suggestedRoles, pageCount, manualMiddleRoles]);

  resolvedPageRolesRef.current = resolvedPageRoles;

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
        const patchBody = buildSurveyDraftPatchBody(surveyName, {
          goal,
          organisation_name: businessName || undefined,
          client_name: businessName || undefined,
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
        });
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
      const saved = await saveSurveyDraft("save");
      if (!saved?.id) throw new Error("Draft was not persisted");
      await qc.invalidateQueries({ queryKey: queryKeys.serviceOrders("survey") });
      await qc.invalidateQueries({ queryKey: queryKeys.serviceOrder(saved.id) });
      if (orderIdSearch !== saved.id) {
        logLaunchFlow("[navigate]", {
          ...launchLogCtx(),
          orderId: saved.id,
          source: "onSaveDraft",
          extra: { to: "/surveys/new", order_id: saved.id },
        });
        void navigate({
          to: "/surveys/new",
          search: {
            channel: channel || undefined,
            order_id: saved.id,
          },
          replace: true,
        });
      }
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
      await qc.refetchQueries({ queryKey: queryKeys.orderRecipients(id) });
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
      const suffix = channel === "whatsapp" ? "?for=survey" : "";
      await downloadAuthenticatedFile(
        `/service-orders/template.csv${suffix}`,
        channel === "whatsapp" ? "voxbulk-survey-contacts-template.csv" : "voxbulk-contacts-template.csv",
      );
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
        title={orderId ? surveyName || orderQ.data?.title || "Edit survey" : "Create new survey"}
        description={
          orderId
            ? "Edit your survey draft — click Save when you are ready to persist changes."
            : "Pick a channel — AI phone call or WhatsApp — then run through the guided wizard."
        }
        actions={
          orderId ? (
            <SurveyEditActionBar
              order={orderQ.data}
              onSave={onSaveDraft}
              savePending={savePending}
              onOpenLaunch={() => void onOpenLaunch("now")}
              launchPending={launchM.isPending || payBusy}
            />
          ) : undefined
        }
      />

      {!channel && (
        <ChannelPicker anonymous={anonymous} setAnonymous={handleAnonymousChange} onPick={(c) => setChannel(c)} />
      )}

      {channel === "whatsapp" && (
        <SurveyWaWizard
          onBack={() => setChannel(null)}
          anonymous={anonymous}
          surveyName={surveyName}
          setSurveyName={setSurveyName}
          campaignRejectTitles={campaignRejectTitles}
          industryId={industryId}
          setIndustryId={handleIndustryChange}
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
          recipientsLoading={recipientsLoading}
          recipientsError={recipientsError}
          contactsEditable={Boolean(orderId)}
          recipientContactValue={recipientContactValue}
          onRecipientContactChange={onRecipientContactChange}
          onRecipientContactBlur={onRecipientContactBlur}
          patchRecipientPending={patchRecipientM.isPending}
          surveyId={surveyId}
          onEnsureDraft={async () => {
            await ensureOrder();
            await saveSurveyDraft("save");
          }}
          uploadTypeAck={uploadTypeAck}
          setUploadTypeAck={setUploadTypeAck}
          uploadConsent={uploadConsent}
          setUploadConsent={setUploadConsent}
          launchConsent={launchConsent}
          setLaunchConsent={setLaunchConsent}
          userTestPhone={userTestPhone}
          businessName={businessName}
          onSendWaTest={onSendWaTest}
          sendTestPending={sendTestWaM.isPending}
          onOpenLaunch={onOpenLaunch}
          launchPending={launchM.isPending || payBusy}
          costHint={launchCostHint || "See launch summary"}
        />
      )}

      {channel === "phone" && (
        <SurveyPhoneWizard
          onBack={() => setChannel(null)}
          surveyName={surveyName}
          setSurveyName={setSurveyName}
          surveyId={surveyId}
          onEnsureDraft={async () => {
            await ensureOrder();
            await saveSurveyDraft("save");
          }}
          anonymous={anonymous}
          goal={goal}
          setGoal={setGoal}
          script={script}
          setScript={setScript}
          approved={approved}
          setApproved={setApproved}
          onApproveScript={onApproveSurveyScript}
          approvePending={approveScriptPending}
          scriptModerationMessage={scriptModerationMessage}
          agentId={agentId}
          setAgentId={setAgentId}
          agents={agentsQ.data || []}
          agentsLoading={agentsQ.isLoading}
          onGenerateScript={onGeneratePhoneScript}
          generatePending={generatePhoneM.isPending}
          expectedDurationMinutes={expectedDurationMinutes}
          startAt={startAt}
          setStartAt={setStartAt}
          endAt={endAt}
          setEndAt={setEndAt}
          fileRef={fileRef}
          uploading={uploading}
          onUpload={onUpload}
          onDownloadTemplate={onDownloadTemplate}
          onSaveDraft={onSaveDraft}
          savePending={savePending}
          contactsCount={contactsCount}
          uploadedContacts={uploadedContacts}
          recipientsLoading={recipientsLoading}
          recipientsError={recipientsError}
          contactsEditable={Boolean(orderId)}
          recipientContactValue={recipientContactValue}
          onRecipientContactChange={onRecipientContactChange}
          onRecipientContactBlur={onRecipientContactBlur}
          patchRecipientPending={patchRecipientM.isPending}
          uploadTypeAck={uploadTypeAck}
          setUploadTypeAck={setUploadTypeAck}
          uploadConsent={uploadConsent}
          setUploadConsent={setUploadConsent}
          launchConsent={launchConsent}
          setLaunchConsent={setLaunchConsent}
          launchBlockers={phoneLaunchBlockers}
          onOpenLaunch={() => void onOpenLaunch("now")}
          launchPending={launchM.isPending || payBusy}
        />
      )}

      <SurveyLaunchQuoteModal
        open={launchOpen}
        onOpenChange={(open) => {
          setLaunchOpen(open);
          if (!open) {
            setLaunchOrderId(null);
            setLaunchEligibility(null);
            eligibilityFetchKeyRef.current = "";
          }
        }}
        data={{
          campaignName: normalizeSurveyName(surveyName),
          surveyId: surveyId || undefined,
          firstStepName: firstSurveyStepName,
          recipientCount: contactsCount,
          channelLabel,
          launchModeLabel,
          packageName: launchEligibility?.billing?.plan_name || launchEligibility?.package_label,
        }}
        eligibility={launchEligibility}
        billingCheckPhase={billingCheckPhase}
        eligibilityLoading={billingCheckPhase === "checking"}
        eligibilityError={billingCheckErrorMessage(
          billingCheckPhase,
          eligibilityError,
          activeLaunchOrderId,
          launchEligibility,
        )}
        launchBlockers={
          channel === "phone"
            ? phoneLaunchBlockers
            : contactsCount <= 0
              ? ["Upload at least one contact before launch."]
              : channel === "whatsapp" && !approved
                ? ["Approve your survey before launch."]
                : []
        }
        onRefreshEligibility={refreshLaunchEligibility}
        onLaunch={onLaunchSurvey}
        onTopUpWallet={onOpenWalletTopup}
        payBusy={payBusy || launchM.isPending}
      />
      <WalletTopupDialog
        open={topupOpen}
        onOpenChange={setTopupOpen}
        initialAmountMinor={
          Math.max(
            Number(launchEligibility?.amount_due_pence || 0),
            Number(launchEligibility?.wallet_shortfall_minor || 0),
            500,
          )
        }
        onToppedUp={onWalletToppedUp}
      />
    </div>
  );
}
