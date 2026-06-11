import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import * as React from "react";
import { Check, Copy, Upload, Download, Wand2, Lock, LockOpen, RotateCcw, Trash2, Save, Eye, FileDown, ArrowUpDown, ArrowUp, ArrowDown, CheckCircle2, Send, Sparkles, Activity, ChevronDown, ChevronLeft, Settings2, FileText, Users, Mail, Rocket, Pencil } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { notifyInterviewLaunch, type InterviewLaunchResult } from "@/lib/interviewLaunchFeedback";
import {
  ATS_ANALYZING_LABEL,
  ATS_CUTOFF_PENDING_COLOR,
  DEFAULT_MIN_ATS_SCORE,
  candidateNeedsAtsScore,
  countScreeningEligibleCandidates,
  interviewCampaignReadOnlyLabel,
  isAtsAnalyzingStatus,
  isInterviewCampaignLaunched,
  isInterviewCampaignReadOnly,
  bookingInvitesWereSent,
  resolveCandidateAtsDisplay,
} from "@/lib/interview-campaign";
import { estimateInterviewDurationMinutes, extractQuestionsBlock, mergeQuestionsIntoScript, resolveScriptFromConfig } from "@/lib/interview-script";

import { Checkbox } from "@/components/ui/checkbox";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { SortHeader, useTableSort } from "@/components/sortable-table";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, DropdownMenuLabel, DropdownMenuSeparator } from "@/components/ui/dropdown-menu";

import { Stepper, WizardNav, type WizardStepDef } from "@/components/create-wizard";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { AtsPreviewGateModal, InterviewPreviewQuoteModal, PackageUpgradeModal, type InterviewPreviewData } from "@/components/modals";
import { AtsScore } from "@/components/ats-score";
import { CandidateActivityDialog, activityStatusLabel, activityStatusTone } from "@/components/candidate-activity-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { apiFetch, apiUploadFiles, downloadAuthenticatedFile, ApiError } from "@/lib/api";
import { gocardlessAvailable, startGoCardlessOrderPayment } from "@/lib/billing/gocardless";
import { formatQuoteDisplay } from "@/lib/billing/market";
import { interviewBillingFromSources } from "@/lib/billing/plan-entitlements";
import { useSession } from "@/lib/session";
import {
  queryKeys,
  useGenerateInterviewScript,
  useInterviewAgents,
  pickDefaultInterviewAgent,
  useInterviewDraft,
  useOrderQuote,
  usePatchServiceOrder,
  useLaunchInterviewCampaign,
  useRunInterviewAts,
  useApplyInterviewAtsThreshold,
  usePatchInterviewRecipient,
  useSaveInterviewDraft,
  useCreateNewInterviewDraft,
  invalidateInterviewOrderQueries,
  useInterviewCvCollectionLimits,
} from "@/lib/queries";

export const Route = createFileRoute("/_app/interviews/new")({
  head: () => ({ meta: [{ title: "Create interview — VoxBulk" }] }),
  validateSearch: (search: Record<string, unknown>) => {
    const orderId = typeof search.order_id === "string" ? search.order_id.trim() : "";
    const rawNew = search.new;
    const explicitNew =
      rawNew === "1" ||
      rawNew === 1 ||
      rawNew === true ||
      rawNew === "true";
    return {
      new: orderId ? false : rawNew === undefined ? true : explicitNew,
      order_id: orderId || undefined,
    };
  },
  component: CreateInterview,
});

type CandidateRow = {
  id: string;
  name: string;
  phone: string;
  email: string;
  source: string;
  cvFilename?: string | null;
  ats: number | null;
  atsStatus?: string | null;
  status?: string;
  activityStatus?: string;
  activityStatusLabel?: string;
  phoneCallAllowed?: boolean;
  phoneCallBlockReason?: string | null;
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

function toIsoFromLocal(value: string) {
  if (!value) return null;
  try {
    return new Date(value).toISOString();
  } catch {
    return null;
  }
}

function scriptFromGenerate(res: Record<string, unknown>) {
  const text = String(res.script_text || res.script || "").trim();
  const system = String(res.system_prompt || text).trim();
  const rawDuration = res.expected_duration_minutes;
  const expected_duration_minutes =
    rawDuration != null && !Number.isNaN(Number(rawDuration)) ? Math.max(3, Math.min(45, Number(rawDuration))) : undefined;
  return { script_text: text || system, system_prompt: system || text, expected_duration_minutes };
}

function isCvCollectionComplete(enabled: boolean, cfg: Record<string, unknown>) {
  if (!enabled) return true;
  if (cfg.cv_collection_closed_early_at || cfg.cv_collection_closed_on_limit_at) return true;
  const endIso = cfg.cv_collection_end_at || cfg.cv_email_end_at;
  if (endIso) {
    try {
      if (new Date(String(endIso)) <= new Date()) return true;
    } catch {
      /* ignore */
    }
  }
  return false;
}

function cvCollectionPhase(
  enabled: boolean,
  cfg: Record<string, unknown>,
): "off" | "before" | "open" | "ready" {
  if (!enabled) return "off";
  if (cfg.cv_collection_closed_early_at || cfg.cv_collection_closed_on_limit_at) return "ready";
  const startIso = cfg.cv_collection_start_at || cfg.cv_email_start_at;
  const endIso = cfg.cv_collection_end_at || cfg.cv_email_end_at;
  const now = Date.now();
  try {
    if (startIso && new Date(String(startIso)).getTime() > now) return "before";
    if (endIso && new Date(String(endIso)).getTime() <= now) return "ready";
  } catch {
    return "open";
  }
  return "open";
}

function formatCvAdvancedSummary(opts: {
  maxCvCount: number | "";
  autoCloseOnLimit: boolean;
  collectionCloseAt: string;
  minAtsScore: number;
}): string | null {
  const parts: string[] = [];
  if (opts.maxCvCount !== "") parts.push(`Max ${opts.maxCvCount} CVs`);
  if (opts.autoCloseOnLimit) parts.push("Auto-close on");
  if (opts.collectionCloseAt) {
    try {
      const d = new Date(opts.collectionCloseAt);
      parts.push(`Closes ${d.toLocaleDateString("en-GB", { day: "numeric", month: "short" })}`);
    } catch {
      parts.push("Close date set");
    }
  }
  parts.push(`Reject below ${opts.minAtsScore}% ATS`);
  return parts.length ? parts.join(" · ") : null;
}

const CAREERS_INBOX = "careers@voxbulk.com";

function formatAtsRunTime(iso: unknown): string | null {
  if (iso == null || iso === "") return null;
  try {
    const raw = String(iso).trim();
    const d = /[zZ]|[+-]\d{2}:\d{2}$/.test(raw) ? new Date(raw) : new Date(`${raw}Z`);
    if (Number.isNaN(d.getTime())) return null;
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return null;
  }
}

function collectInterviewSetupErrors(opts: {
  position: string;
  role: string;
  criteria: string;
  script: string;
  scriptIsApproved: boolean;
  agentId: string;
  agentsCount: number;
}): string[] {
  const errors: string[] = [];
  if (!opts.position.trim() && !opts.role.trim()) errors.push("Add position and role in Step 1");
  if (opts.agentsCount <= 0) {
    errors.push("No voice agents configured — ask your admin to enable interview agents");
  } else if (!opts.agentId.trim()) {
    errors.push("Select an AI voice agent in Step 1");
  }
  if (!opts.criteria.trim()) errors.push("Add screening criteria in Step 1");
  if (!opts.script.trim()) errors.push("Generate or write interview questions in Step 1");
  if (!opts.scriptIsApproved) errors.push("Approve your script in Step 1");
  return errors;
}

function collectInterviewScheduleErrors(callingStart: string, callingEnd: string): string[] {
  const errors: string[] = [];
  if (!callingStart || !callingEnd) errors.push("Set calling start and end in Step 4");
  return errors;
}

function inputErrorClass(invalid: boolean) {
  return invalid ? "border-destructive ring-1 ring-destructive/40 focus-visible:ring-destructive/40" : "";
}

const INTERVIEW_WIZARD_STEPS: WizardStepDef[] = [
  { id: 1, title: "Script", subtitle: "Voice & questions", icon: FileText },
  { id: 2, title: "CVs", subtitle: "Upload candidates", icon: Users },
  { id: 3, title: "Email collect", subtitle: "Inbox options", icon: Mail },
  { id: 4, title: "Review & launch", subtitle: "Confirm and go", icon: Rocket },
];

function collectInterviewLaunchErrors(opts: {
  cvEmailActive: boolean;
  cvReadyForScreening: boolean;
  candidateCount: number;
  screeningEligibleCount: number;
  referenceId: string;
  atsGatePassed: boolean;
  minAtsScore: number;
  atsSkipped?: boolean;
}): string[] {
  const errors: string[] = [];
  if (opts.cvEmailActive) {
    if (!opts.cvReadyForScreening) {
      errors.push("CV collection is still open — wait for applicants or close collection early");
    }
    if (opts.candidateCount <= 0) {
      errors.push(
        `No CVs received yet — applicants should email ${CAREERS_INBOX} with reference ${opts.referenceId || "your job code"}`,
      );
    }
  } else if (opts.candidateCount <= 0) {
    errors.push("Upload at least one candidate in Step 2");
  }
  if (opts.candidateCount > 0 && !opts.atsGatePassed && !opts.cvEmailActive) {
    errors.push("Run ATS scoring or continue without ATS");
  }
  if (opts.candidateCount > 0 && opts.atsGatePassed && opts.screeningEligibleCount <= 0 && !opts.atsSkipped) {
    errors.push(`No candidates meet the ${opts.minAtsScore}% ATS cutoff — lower the cutoff or remove weak profiles`);
  }
  return errors;
}

function CreateInterview() {
  const { new: wantNew, order_id: draftOrderId } = Route.useSearch();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { session } = useSession();
  const gcReady = gocardlessAvailable(session?.subscription as Record<string, unknown> | null);
  const createDraftM = useCreateNewInterviewDraft();
  const draftQ = useInterviewDraft({ orderId: draftOrderId });
  const agentsQ = useInterviewAgents();
  const saveDraftM = useSaveInterviewDraft();
  const patchOrderM = usePatchServiceOrder();
  const generateM = useGenerateInterviewScript();

  const order = draftQ.data?.order ?? createDraftM.data?.order ?? null;
  const orderId = order?.id ?? "";
  const runAtsM = useRunInterviewAts(orderId || null);
  const applyAtsThresholdM = useApplyInterviewAtsThreshold(orderId || null);
  const patchRecipientM = usePatchInterviewRecipient(orderId || null);
  const launchM = useLaunchInterviewCampaign(orderId || null);
  const quoteM = useOrderQuote(orderId || null);
  const [waPreviewBody, setWaPreviewBody] = React.useState<string | undefined>();
  const [waPreviewTemplateName, setWaPreviewTemplateName] = React.useState<string | undefined>();
  const [waPreviewButtons, setWaPreviewButtons] = React.useState<{ label: string; type?: string }[] | undefined>();
  const [waPreviewConfirmationBody, setWaPreviewConfirmationBody] = React.useState<string | undefined>();
  const [waPreviewConfirmationButtons, setWaPreviewConfirmationButtons] = React.useState<{ label: string; type?: string }[] | undefined>();
  const [waPreviewConfirmationTemplateName, setWaPreviewConfirmationTemplateName] = React.useState<string | undefined>();
  const [waPreviewSyncLabel, setWaPreviewSyncLabel] = React.useState<string | undefined>();
  const [waPreviewLoading, setWaPreviewLoading] = React.useState(false);

  const [preview, setPreview] = React.useState(false);
  const [upgradeOpen, setUpgradeOpen] = React.useState(false);
  const [atsPromptOpen, setAtsPromptOpen] = React.useState(false);
  const [atsQuote, setAtsQuote] = React.useState<Record<string, unknown> | null>(null);
  const [atsQuoteLoading, setAtsQuoteLoading] = React.useState(false);
  const [atsQuoteError, setAtsQuoteError] = React.useState<string | null>(null);
  const [atsSkipped, setAtsSkipped] = React.useState(false);
  const [atsForce, setAtsForce] = React.useState(false);
  const [atsRunAt, setAtsRunAt] = React.useState<string | null>(null);
  const [quoteTotalDisplay, setQuoteTotalDisplay] = React.useState<string | undefined>();
  const [quoteError, setQuoteError] = React.useState<string | null>(null);
  const [payBusy, setPayBusy] = React.useState(false);

  const [cvEmailEnabled, setCvEmailEnabled] = React.useState(false);
  const [copiedReference, setCopiedReference] = React.useState(false);
  const [copiedCareersEmail, setCopiedCareersEmail] = React.useState(false);
  const [position, setPosition] = React.useState("");
  const [role, setRole] = React.useState("");
  const [criteria, setCriteria] = React.useState("");
  const [reportNotes, setReportNotes] = React.useState("");
  const [script, setScript] = React.useState("");
  const [questionsText, setQuestionsText] = React.useState("");
  const [expectedDurationMinutes, setExpectedDurationMinutes] = React.useState<number | undefined>();
  const [scriptApproved, setScriptApproved] = React.useState(false);
  const [agentId, setAgentId] = React.useState("");
  const [advancedOpen, setAdvancedOpen] = React.useState(false);
  const [maxCvCount, setMaxCvCount] = React.useState<number | "">("");
  const [autoCloseOnLimit, setAutoCloseOnLimit] = React.useState(true);
  const [minAtsScoreDraft, setMinAtsScoreDraft] = React.useState(DEFAULT_MIN_ATS_SCORE);
  const [collectionStartAt, setCollectionStartAt] = React.useState("");
  const [collectionCloseAt, setCollectionCloseAt] = React.useState("");
  const [overageAcknowledged, setOverageAcknowledged] = React.useState(false);
  const [advancedSaveBusy, setAdvancedSaveBusy] = React.useState(false);
  const [applyAtsBusy, setApplyAtsBusy] = React.useState(false);
  const atsCutoffEditRef = React.useRef(false);
  const [callingStart, setCallingStart] = React.useState("");
  const [callingEnd, setCallingEnd] = React.useState("");
  const fileRef = React.useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = React.useState(false);
  const [activityCandidate, setActivityCandidate] = React.useState<CandidateRow | null>(null);
  const [wizardStep, setWizardStep] = React.useState(1);
  const [step1FieldsTouched, setStep1FieldsTouched] = React.useState(false);
  const goWizardNext = () => setWizardStep((s) => Math.min(INTERVIEW_WIZARD_STEPS.length, s + 1));
  const goWizardPrev = () => setWizardStep((s) => Math.max(1, s - 1));
  const goWizardTo = (n: number) => setWizardStep(n);

  const config = (order?.config || {}) as Record<string, unknown>;
  const configAppliedMinAts = React.useMemo(() => {
    const raw = config.cv_min_ats_score;
    if (raw != null && raw !== "" && !Number.isNaN(Number(raw))) {
      return Math.max(0, Math.min(100, Number(raw)));
    }
    return DEFAULT_MIN_ATS_SCORE;
  }, [config.cv_min_ats_score]);
  const [appliedMinAtsScore, setAppliedMinAtsScore] = React.useState(DEFAULT_MIN_ATS_SCORE);
  const atsCutoffDirty = minAtsScoreDraft !== appliedMinAtsScore;
  const referenceId = order?.reference_id || "";
  const billingContext = (draftQ.data as { billing_context?: Record<string, unknown> })?.billing_context;
  const sessionPlan = (session?.subscription as { plan?: Record<string, unknown> } | null)?.plan;
  const billing = interviewBillingFromSources(billingContext, sessionPlan as { code?: string; name?: string; price_gbp_pence?: number; interval?: string; is_enterprise?: boolean; is_payg?: boolean });
  const cvEmailAllowed = billing.cvEmailAllowed;
  const cvEmailBlockReason = billing.blockReason;
  const billingPlanName = billing.planName;
  const hasPackageSub = billing.hasPackageSub;
  const cvLimitsQ = useInterviewCvCollectionLimits(orderId || null, Boolean(orderId));
  const cvLimits = cvLimitsQ.data;
  const orderHydrationKey = React.useMemo(() => {
    if (!order) return "";
    const cfg = (order.config || {}) as Record<string, unknown>;
    return [
      order.id,
      order.updated_at,
      order.scheduled_start_at,
      order.scheduled_end_at,
      cfg.position,
      cfg.role,
      cfg.criteria,
      cfg.screening_criteria,
      cfg.report_notes,
      cfg.approved_script,
      cfg.generated_script_draft,
      cfg.expected_duration_minutes,
      cfg.script_approved,
      cfg.agent_id,
      cfg.cv_collection_start_at,
      cfg.cv_email_start_at,
      cfg.cv_collection_end_at,
      cfg.cv_email_end_at,
      cfg.cv_email_enabled,
      cfg.cv_collection_closed_early_at,
      cfg.cv_collection_closed_on_limit_at,
      cfg.cv_max_count,
      cfg.cv_auto_close_on_limit,
      cfg.cv_min_ats_score,
      cfg.cv_collection_close_at,
      cfg.ats_last_charge_at,
      cfg.ats_skipped,
    ].join("|");
  }, [order]);
  const lastHydrationKeyRef = React.useRef("");

  React.useEffect(() => {
    lastHydrationKeyRef.current = "";
  }, [draftOrderId]);

  const agents = agentsQ.data || [];
  const defaultAgent = pickDefaultInterviewAgent(agents);
  const resolvedAgentId = agentId || defaultAgent?.id || "";
  const selectedAgent = agents.find((a) => a.id === resolvedAgentId) || defaultAgent;
  const createStartedRef = React.useRef(false);
  const createFailedRef = React.useRef(false);

  React.useEffect(() => {
    createFailedRef.current = false;
  }, [wantNew]);

  // Stale links like ?new=false without order_id (e.g. after billing return stripped params) show a dead page.
  React.useEffect(() => {
    if (draftOrderId) return;
    if (wantNew) return;
    void navigate({ to: "/interviews/new", search: { new: true }, replace: true });
  }, [draftOrderId, navigate, wantNew]);

  React.useEffect(() => {
    if (draftOrderId) return;
    if (!wantNew) return;
    if (createFailedRef.current) return;
    if (createStartedRef.current || createDraftM.isPending || createDraftM.isSuccess) return;
    createStartedRef.current = true;
    console.info("[interview] POST /service-orders/interview/draft/new");
    void createDraftM
      .mutateAsync()
      .then((payload) => {
        const id = payload?.order?.id;
        if (!id) {
          createStartedRef.current = false;
          createFailedRef.current = true;
          toast.error("Could not start interview draft — server returned no order id.");
          return;
        }
        qc.setQueryData([...queryKeys.interviewDraft, id], payload);
        void navigate({
          to: "/interviews/new",
          search: { order_id: id },
          replace: true,
        });
      })
      .catch((err) => {
        createStartedRef.current = false;
        createFailedRef.current = true;
        toast.error(err instanceof Error ? err.message : "Could not start interview draft");
      });
  }, [createDraftM, draftOrderId, navigate, qc, wantNew]);

  const orderStatus = String(order?.status || "").toLowerCase();
  const campaignReadOnly = isInterviewCampaignReadOnly(orderStatus);
  const isEditingExisting = Boolean(draftOrderId && orderId);
  const isLiveCampaign = ["running", "paused", "scheduled"].includes(orderStatus);
  const shouldPollRecipients = ["running", "scheduled", "paused"].includes(orderStatus);
  const lastInviteDispatch = config.last_invite_dispatch as
    | { ok?: boolean; whatsapp_sent?: number; email_sent?: number; errors?: string[] }
    | undefined;
  const campaignLaunched = isInterviewCampaignLaunched(orderStatus);
  const bookingInvitesSent = bookingInvitesWereSent(config);

  React.useEffect(() => {
    if (!orderId || !shouldPollRecipients) return;
    const timer = window.setInterval(() => {
      void qc.refetchQueries({ queryKey: [...queryKeys.interviewDraft, orderId] });
    }, 8000);
    return () => window.clearInterval(timer);
  }, [orderId, qc, shouldPollRecipients]);

  React.useEffect(() => {
    if (!order || !orderHydrationKey) return;
    if (lastHydrationKeyRef.current === orderHydrationKey) return;
    lastHydrationKeyRef.current = orderHydrationKey;
    setPosition(String(config.position || order.title || config.role || ""));
    setRole(String(config.role || ""));
    setCriteria(String(config.criteria || config.screening_criteria || ""));
    setReportNotes(String(config.report_notes || ""));
    const scriptSource = resolveScriptFromConfig(config);
    setScript(scriptSource);
    setQuestionsText(extractQuestionsBlock(scriptSource));
    const savedDuration = config.expected_duration_minutes;
    setExpectedDurationMinutes(
      savedDuration != null && !Number.isNaN(Number(savedDuration))
        ? Math.max(3, Math.min(45, Number(savedDuration)))
        : undefined,
    );
    setScriptApproved(Boolean(config.script_approved));
    const savedAgentId = String(config.agent_id || "").trim();
    setAgentId(savedAgentId || pickDefaultInterviewAgent(agents)?.id || "");
    setCollectionStartAt(toLocalInput(String(config.cv_collection_start_at || config.cv_email_start_at || "")));
    setCollectionCloseAt(toLocalInput(String(config.cv_collection_close_at || config.cv_collection_end_at || config.cv_email_end_at || "")));
    setMaxCvCount(config.cv_max_count != null && config.cv_max_count !== "" ? Number(config.cv_max_count) : "");
    setAutoCloseOnLimit(config.cv_auto_close_on_limit !== false);
    setOverageAcknowledged(config.cv_overage_acknowledged === true);
    setCallingStart(
      toLocalInput(
        order.scheduled_start_at ||
          (config.calling_window_start_at as string | undefined) ||
          (config.scheduled_start_at as string | undefined) ||
          (config.scheduled_start as string | undefined),
      ),
    );
    setCallingEnd(
      toLocalInput(
        order.scheduled_end_at ||
          (config.calling_window_end_at as string | undefined) ||
          (config.scheduled_end_at as string | undefined) ||
          (config.scheduled_end as string | undefined),
      ),
    );
    setCvEmailEnabled(config.cv_email_enabled === true);
    const runLabel = formatAtsRunTime(config.ats_manual_run_at || config.ats_last_charge_at);
    if (runLabel) setAtsRunAt(runLabel);
    if (config.ats_skipped === true) {
      setAtsSkipped(true);
    }
  }, [order, orderHydrationKey, config, agents]);

  React.useEffect(() => {
    setAppliedMinAtsScore(configAppliedMinAts);
    if (!atsCutoffEditRef.current) {
      setMinAtsScoreDraft(configAppliedMinAts);
    }
  }, [configAppliedMinAts]);

  const loadWaPreview = React.useCallback(async () => {
    if (!orderId) return;
    setWaPreviewLoading(true);
    try {
      const res = await apiFetch<{
        template?: {
          rendered_body?: string;
          name?: string;
          buttons?: { label: string; type?: string }[];
          confirmation_body?: string;
          confirmation_buttons?: { label: string; type?: string }[];
          confirmation_template_name?: string;
          is_fallback?: boolean;
          sync?: { synced?: number; approved?: number };
          sync_error?: string | null;
        } | null;
      }>(`/service-orders/${encodeURIComponent(orderId)}/interview-booking/preview-template?sync=false`);
      const tpl = res.template;
      setWaPreviewBody(tpl?.rendered_body);
      setWaPreviewTemplateName(tpl?.name);
      setWaPreviewButtons(tpl?.buttons);
      setWaPreviewConfirmationBody(tpl?.confirmation_body);
      setWaPreviewConfirmationButtons(tpl?.confirmation_buttons);
      setWaPreviewConfirmationTemplateName(tpl?.confirmation_template_name);
      const synced = tpl?.sync?.synced;
      if (tpl?.sync_error) {
        setWaPreviewSyncLabel("Using preview template — sync Telnyx templates in Admin → Integrations");
      } else if (tpl?.is_fallback) {
        setWaPreviewSyncLabel("Preview template — sync Telnyx to load your approved booking template");
      } else {
        setWaPreviewSyncLabel(
          synced != null ? `Templates synced from Telnyx (${synced} total)` : tpl?.name ? "Using cached Telnyx template" : undefined,
        );
      }
    } catch {
      setWaPreviewBody(undefined);
      setWaPreviewTemplateName(undefined);
      setWaPreviewButtons(undefined);
      setWaPreviewConfirmationBody(undefined);
      setWaPreviewSyncLabel(undefined);
    } finally {
      setWaPreviewLoading(false);
    }
  }, [orderId]);

  React.useEffect(() => {
    if (!orderId || !preview) return;
    void loadWaPreview();
  }, [orderId, preview, role, loadWaPreview]);

  React.useEffect(() => {
    if (agentId || !defaultAgent?.id) return;
    setAgentId(defaultAgent.id);
  }, [agentId, defaultAgent?.id]);

  const candidates = React.useMemo<CandidateRow[]>(() => {
    const rows = draftQ.data?.recipients || [];
    return rows
      .filter((r) => Boolean(r.id))
      .map((r) => ({
        id: String(r.id),
        name: String(r.name || "Candidate"),
        phone: String(r.phone || ""),
        email: String(r.outreach_email || r.email || ""),
        source: String(r.intake_source || r.source || "Upload"),
        cvFilename: r.cv_filename ? String(r.cv_filename) : null,
        ats: r.ats_score != null ? Number(r.ats_score) : null,
        atsStatus: String(r.ats_status || ""),
        status: String(r.status || ""),
        activityStatus: String(r.activity_status || ""),
        activityStatusLabel: r.activity_status_label ? String(r.activity_status_label) : undefined,
        phoneCallAllowed: r.phone_call_allowed !== false,
        phoneCallBlockReason: r.phone_call_block_reason ? String(r.phone_call_block_reason) : null,
      }));
  }, [draftQ.data?.recipients]);

  const candidatesLocked =
    campaignReadOnly || ["running", "completed", "cancelled"].includes(orderStatus) || bookingInvitesSent;

  const [deleteDialog, setDeleteDialog] = React.useState<{
    open: boolean;
    mode: "single" | "bulk";
    ids: string[];
    label?: string;
  }>({ open: false, mode: "single", ids: [] });
  const [deleteBusy, setDeleteBusy] = React.useState(false);
  const [closeCvBusy, setCloseCvBusy] = React.useState(false);

  React.useEffect(() => {
    setSelected((prev) => {
      const valid = new Set(candidates.map((c) => c.id));
      const next = new Set([...prev].filter((id) => valid.has(id)));
      return next.size === prev.size ? prev : next;
    });
  }, [candidates]);

  const atsInProgress = React.useMemo(
    () =>
      runAtsM.isPending ||
      candidates.some((c) => isAtsAnalyzingStatus(c.atsStatus)),
    [candidates, runAtsM.isPending],
  );

  React.useEffect(() => {
    if (!orderId || !atsInProgress) return;
    const timer = window.setInterval(() => {
      void qc.invalidateQueries({ queryKey: queryKeys.interviewDraft });
    }, 2500);
    return () => window.clearInterval(timer);
  }, [orderId, atsInProgress, qc]);

  React.useEffect(() => {
    if (atsInProgress) setAtsPromptOpen(false);
  }, [atsInProgress]);

  const screeningEligibleCount = React.useMemo(() => {
    if (atsSkipped || Boolean(config.ats_skipped)) {
      return candidates.filter((c) => c.activityStatus !== "auto_excluded").length;
    }
    return countScreeningEligibleCandidates(candidates, appliedMinAtsScore);
  }, [candidates, appliedMinAtsScore, atsSkipped, config.ats_skipped]);

  const [selected, setSelected] = React.useState<Set<string>>(new Set());
  const allSelected = selected.size > 0 && selected.size === candidates.length;
  const someSelected = selected.size > 0 && !allSelected;
  const toggleAll = () => setSelected(allSelected ? new Set() : new Set(candidates.map((c) => c.id)));
  const toggleOne = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const refreshDraft = () => {
    invalidateInterviewOrderQueries(qc, orderId);
  };

  const completeLaunchSuccess = async (result: InterviewLaunchResult) => {
    const emailN = Number(result?.invites?.email_sent ?? 0);
    const waN = Number(result?.invites?.whatsapp_sent ?? 0);
    const errs = Array.isArray(result?.invites?.errors) ? result!.invites!.errors!.filter(Boolean) : [];
    if (result?.ok === false || emailN < 1) {
      notifyInterviewLaunch(result);
      const smtpHint = errs.find((e) => /smtp/i.test(String(e)));
      const detail = smtpHint || errs[0] || result?.message;
      const suffix =
        emailN < 1 && waN > 0
          ? " WhatsApp was sent but invite email was not — check Admin → Email (SMTP) and candidate email addresses."
          : "";
      throw new Error((detail || "Launch failed — no invite email was sent.") + suffix);
    }
    setPreview(false);
    setPayBusy(false);
    notifyInterviewLaunch(result);
    invalidateInterviewOrderQueries(qc, orderId);
    await navigate({
      to: "/interviews/results/$orderId",
      params: { orderId: orderId! },
      search: { launched: "1" },
    });
  };

  const onEditRecipientPhone = async (recipientId: string, currentPhone: string) => {
    if (!orderId) return;
    const next = window.prompt("Enter phone number (E.164 or local format)", currentPhone || "");
    if (next == null) return;
    try {
      await apiFetch(`/service-orders/${encodeURIComponent(orderId)}/recipients/${encodeURIComponent(recipientId)}`, {
        method: "PATCH",
        body: JSON.stringify({ phone: next.trim() }),
      });
      void qc.invalidateQueries({ queryKey: queryKeys.interviewDraft });
      toast.success("Phone number updated");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not update phone");
    }
  };

  const onDeleteRecipient = (recipientId: string, candidateName?: string) => {
    if (!orderId) return;
    if (candidatesLocked) {
      toast.error(
        bookingInvitesSent
          ? "Candidates cannot be removed after booking invites have been sent."
          : "Candidates cannot be removed once the campaign is running or finished.",
      );
      return;
    }
    setDeleteDialog({ open: true, mode: "single", ids: [recipientId], label: candidateName });
  };

  const onDeleteSelected = () => {
    if (!orderId || selected.size === 0) return;
    if (candidatesLocked) {
      toast.error(
        bookingInvitesSent
          ? "Candidates cannot be removed after booking invites have been sent."
          : "Candidates cannot be removed once the campaign is running or finished.",
      );
      return;
    }
    setDeleteDialog({ open: true, mode: "bulk", ids: [...selected] });
  };

  const executeDeleteCandidates = async () => {
    if (!orderId || deleteDialog.ids.length === 0) return;
    setDeleteBusy(true);
    const ids = deleteDialog.ids;
    try {
      const results = await Promise.allSettled(
        ids.map((id) =>
          apiFetch(`/service-orders/${encodeURIComponent(orderId)}/recipients/${encodeURIComponent(id)}`, {
            method: "DELETE",
          }),
        ),
      );
      const failedResults = results.filter((r) => r.status === "rejected") as PromiseRejectedResult[];
      const failed = failedResults.length;
      const removed = results.length - failed;
      const firstError =
        failedResults[0]?.reason instanceof Error ? failedResults[0].reason.message : undefined;
      setSelected((prev) => {
        const next = new Set(prev);
        ids.forEach((id) => next.delete(id));
        return next;
      });
      refreshDraft();
      setDeleteDialog({ open: false, mode: "single", ids: [] });
      if (removed === 0) {
        toast.error(firstError || "Could not remove candidate(s)");
      } else if (failed > 0) {
        toast.error(firstError ? `${firstError} (${removed} of ${ids.length} removed)` : `Removed ${removed} of ${ids.length} — some could not be deleted`);
      } else {
        toast.success(removed === 1 ? "Candidate removed" : `${removed} candidates removed`);
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not remove candidates");
    } finally {
      setDeleteBusy(false);
    }
  };

  const onDownloadCv = async (recipientId: string, cvFilename?: string | null) => {
    if (!orderId) return;
    try {
      await downloadAuthenticatedFile(
        `/service-orders/${encodeURIComponent(orderId)}/recipients/${encodeURIComponent(recipientId)}/cv`,
        cvFilename || "cv",
      );
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "CV download failed");
    }
  };

  const [recipientContactDraft, setRecipientContactDraft] = React.useState<
    Record<string, { phone: string; email: string }>
  >({});

  const recipientContactValue = (c: CandidateRow, field: "phone" | "email") => {
    const draft = recipientContactDraft[c.id];
    if (draft) return draft[field];
    return field === "phone" ? c.phone : c.email;
  };

  const onRecipientContactChange = (c: CandidateRow, field: "phone" | "email", value: string) => {
    setRecipientContactDraft((prev) => ({
      ...prev,
      [c.id]: {
        phone: recipientContactValue(c, "phone"),
        email: recipientContactValue(c, "email"),
        [field]: value,
      },
    }));
  };

  const onRecipientContactBlur = async (c: CandidateRow, field: "phone" | "email") => {
    if (!orderId || candidatesLocked) return;
    const nextVal = recipientContactValue(c, field);
    const currentVal = field === "phone" ? c.phone : c.email;
    if (nextVal.trim() === currentVal.trim()) return;
    try {
      await patchRecipientM.mutateAsync({ recipientId: c.id, [field]: nextVal.trim() });
      setRecipientContactDraft((prev) => {
        const next = { ...prev };
        delete next[c.id];
        return next;
      });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not update candidate");
      setRecipientContactDraft((prev) => ({
        ...prev,
        [c.id]: {
          phone: field === "phone" ? currentVal : recipientContactValue(c, "phone"),
          email: field === "email" ? currentVal : recipientContactValue(c, "email"),
        },
      }));
    }
  };

  const onCloseCvCollection = async () => {
    if (!orderId) return;
    setCloseCvBusy(true);
    try {
      const res = await apiFetch<{
        closed_early?: boolean;
        collection_complete?: boolean;
        end_at?: string;
        order?: { config?: Record<string, unknown> };
        recipients?: unknown[];
        summary?: unknown;
        mailbox_sync?: { added_cvs?: number; processed?: number; message?: string };
      }>(`/service-orders/${encodeURIComponent(orderId)}/interview/cv-collection/close-early`, {
        method: "POST",
        body: "{}",
      });
      const closedAt = String(
        res?.order?.config?.cv_collection_closed_early_at ||
          res?.end_at ||
          new Date().toISOString(),
      );
      if (res?.order) {
        qc.setQueryData([...queryKeys.interviewDraft, orderId], (prev: Record<string, unknown> | undefined) => ({
          ...(prev || {}),
          order: res.order,
          recipients: res.recipients ?? prev?.recipients,
          summary: res.summary ?? prev?.summary,
        }));
      }
      setCollectionCloseAt(toLocalInput(closedAt));
      lastHydrationKeyRef.current = "";
      const added = Number(res?.mailbox_sync?.added_cvs || 0);
      const processed = Number(res?.mailbox_sync?.processed || 0);
      if (added > 0) {
        toast.success(`CV collection closed — ${added} new CV${added === 1 ? "" : "s"} imported from email`);
      } else if (processed > 0) {
        toast.success("CV collection closed — inbox checked, no new CVs to add");
      } else {
        toast.success("CV collection closed — you can review candidates and launch");
      }
      refreshDraft();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not close CV collection");
    } finally {
      setCloseCvBusy(false);
    }
  };

  const buildSaveBody = (extraConfig?: Record<string, unknown>, options?: { markSaved?: boolean }) => {
    const closedEarlyAt = config.cv_collection_closed_early_at;
    const collectionStartIso = closedEarlyAt
      ? String(config.cv_collection_start_at || config.cv_email_start_at || toIsoFromLocal(collectionStartAt) || "")
      : toIsoFromLocal(collectionStartAt);
    const collectionCloseIso = closedEarlyAt
      ? String(config.cv_collection_close_at || config.cv_collection_end_at || config.cv_email_end_at || closedEarlyAt)
      : toIsoFromLocal(collectionCloseAt);
    const scriptTrim = script.trim();
    const approvedFromConfig = String(config.approved_script || "").trim();
    const configSaysApproved = Boolean(config.script_approved) && approvedFromConfig === scriptTrim;
    const persistScriptApproved =
      extraConfig?.script_approved === true ||
      scriptApproved ||
      configSaysApproved;
    const approvedScriptToSave = persistScriptApproved
      ? String(extraConfig?.approved_script || (scriptApproved ? script : approvedFromConfig || script)).trim()
      : "";
    const draftScript = String(extraConfig?.generated_script_draft ?? script).trim();
    const cvEmailOn = cvEmailAllowed && cvEmailEnabled;
    return {
    order_id: orderId,
    title: position || order?.title || "Interview draft",
    role: role || position,
    criteria,
    config: {
      ...config,
      position,
      role: role || position,
      criteria,
      screening_criteria: criteria,
      report_notes: reportNotes.trim() || undefined,
      agent_id: resolvedAgentId,
      delivery: "ai_call",
      cv_email_enabled: cvEmailOn,
      cv_collection_start_at: cvEmailOn ? collectionStartIso || null : null,
      cv_email_start_at: cvEmailOn ? collectionStartIso || null : null,
      cv_collection_close_at: cvEmailOn ? collectionCloseIso || null : null,
      cv_collection_end_at: cvEmailOn ? collectionCloseIso || null : null,
      cv_email_end_at: cvEmailOn ? collectionCloseIso || null : null,
      cv_max_count: cvEmailOn && maxCvCount !== "" ? Number(maxCvCount) : cvEmailOn ? null : undefined,
      cv_auto_close_on_limit: cvEmailOn ? autoCloseOnLimit : undefined,
      cv_overage_acknowledged: cvEmailOn ? overageAcknowledged : undefined,
      calling_window_start_at: toIsoFromLocal(callingStart),
      calling_window_end_at: toIsoFromLocal(callingEnd),
      generated_script_draft: draftScript,
      expected_duration_minutes: expectedDurationMinutes,
      approved_script: approvedScriptToSave,
      script_approved: persistScriptApproved,
      ...(options?.markSaved ? { draft_saved_by_user: true } : {}),
      ...extraConfig,
    },
    scheduled_start_at: toIsoFromLocal(callingStart),
    scheduled_end_at: toIsoFromLocal(callingEnd),
  };
  };

  const assertCvCollectionSaveAllowed = () => {
    if (!cvEmailAllowed || !cvEmailEnabled || cvLimits?.unlimited) return;
    const available = cvLimits?.available_for_order ?? cvLimits?.remaining ?? 0;
    const maxNum = maxCvCount === "" ? null : Number(maxCvCount);
    if (maxNum != null && maxNum > available && !overageAcknowledged) {
      throw new Error(
        `Max CVs (${maxNum}) is above your remaining allowance (${available}). Open Advanced settings and confirm the additional cost to continue.`,
      );
    }
  };

  const onSaveDraft = async (silent?: boolean, extraConfig?: Record<string, unknown>) => {
    if (!orderId) return;
    if (campaignReadOnly) {
      if (!silent) toast.message(interviewCampaignReadOnlyLabel(orderStatus));
      return;
    }
    try {
      assertCvCollectionSaveAllowed();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not save");
      throw e;
    }
    const body = buildSaveBody(extraConfig, { markSaved: !silent });
    const locked = ["running", "paused", "scheduled"].includes(String(order?.status || ""));
    try {
      if (locked) {
        await patchOrderM.mutateAsync({
          orderId,
          body: {
            title: body.title,
            scheduled_start_at: body.scheduled_start_at,
            scheduled_end_at: body.scheduled_end_at,
            config: body.config,
          },
        });
      } else {
        await saveDraftM.mutateAsync(body);
        await patchOrderM.mutateAsync({ orderId, body });
      }
      if (!silent) toast.success(locked ? "Interview updated" : "Draft saved");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not save");
      throw e;
    }
  };

  const onSaveAdvancedSettings = async () => {
    if (!orderId || campaignReadOnly) return;
    if (cvEmailActive && isOverPlanLimit && !overageAcknowledged) {
      toast.error(
        "Confirm additional screenings beyond your plan will be invoiced at the standard rate before saving.",
      );
      return;
    }
    setAdvancedSaveBusy(true);
    try {
      await onSaveDraft(false);
    } catch {
      /* toast handled in onSaveDraft */
    } finally {
      setAdvancedSaveBusy(false);
    }
  };

  const onGenerateScript = async () => {
    if (!criteria.trim()) {
      setStep1FieldsTouched(true);
      toast.error("Add screening criteria before generating the AI script");
      return;
    }
    if (!position.trim() && !role.trim()) {
      toast.error("Enter the position and role before generating");
      return;
    }
    if (!resolvedAgentId) {
      toast.error("Select an AI voice agent");
      return;
    }
    try {
      const res = await generateM.mutateAsync({
        role: role || position,
        position,
        criteria,
        delivery: "ai_call",
        agent_id: resolvedAgentId,
        client_context: { agent_id: resolvedAgentId },
      });
      const materialised = scriptFromGenerate(res);
      if (!materialised.script_text) {
        toast.error("AI did not return a script — try again");
        return;
      }
      setScript(materialised.script_text);
      setQuestionsText(extractQuestionsBlock(materialised.script_text));
      const draftDuration =
        materialised.expected_duration_minutes ?? estimateInterviewDurationMinutes(materialised.script_text);
      setExpectedDurationMinutes(draftDuration);
      setScriptApproved(false);
      await saveDraftM.mutateAsync(
        buildSaveBody({
          generated_script_draft: materialised.script_text,
          approved_script: "",
          system_prompt: materialised.system_prompt,
          expected_duration_minutes: draftDuration,
          script_approved: false,
        }),
      );
      lastHydrationKeyRef.current = "";
      const mins = draftDuration;
      toast.success(mins ? `AI script ready — est. ~${mins} min per call` : "AI script ready — review and approve when happy");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not generate script");
    }
  };

  const onApproveScript = async () => {
    if (!script.trim()) {
      setStep1FieldsTouched(true);
      toast.error("Generate or paste a script before approving");
      return;
    }
    if (!orderId) return;
    const duration = estimateInterviewDurationMinutes(script);
    try {
      setScriptApproved(true);
      setExpectedDurationMinutes(duration);
      await onSaveDraft(true, {
        approved_script: script,
        generated_script_draft: script,
        script_approved: true,
        expected_duration_minutes: duration,
      });
      toast.success(`Script approved — est. ~${duration} min per call`);
    } catch {
      setScriptApproved(false);
    }
  };

  const approvedScriptFromConfig = String(config.approved_script || "");
  const scriptIsApproved =
    scriptApproved ||
    (Boolean(config.script_approved) && approvedScriptFromConfig.trim() === script.trim());

  const loadAtsQuote = async (force: boolean) => {
    if (!orderId) return;
    if (!criteria.trim() || !(role.trim() || position.trim())) {
      setAtsQuote(null);
      setAtsQuoteError("Complete position, role, and screening criteria before ATS");
      return;
    }
    if (!script.trim()) {
      setAtsQuote(null);
      setAtsQuoteError("Generate the AI script before running ATS — scores need job context");
      return;
    }
    setAtsForce(force);
    setAtsQuoteLoading(true);
    setAtsQuoteError(null);
    try {
      await onSaveDraft(true);
      const quote = await apiFetch<Record<string, unknown>>(
        `/service-orders/${encodeURIComponent(orderId)}/interview/ats/quote${force ? "?force=true" : ""}`,
      );
      setAtsQuote(quote);
    } catch (e) {
      setAtsQuote(null);
      setAtsQuoteError(e instanceof Error ? e.message : "Could not load ATS pricing");
    } finally {
      setAtsQuoteLoading(false);
    }
  };

  const confirmAtsRun = async () => {
    if (!orderId) return;
    setAtsPromptOpen(false);
    toast.message(ATS_ANALYZING_LABEL);
    try {
      await runAtsM.mutateAsync({ confirm_charge: true, force: atsForce });
      setAtsSkipped(false);
      setAtsRunAt(new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }));
      refreshDraft();
      toast.success("ATS run queued");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "ATS run failed");
    }
  };

  const onApplyAtsThreshold = async () => {
    if (!orderId || campaignReadOnly || !atsCutoffDirty) return;
    const score = Math.max(0, Math.min(100, minAtsScoreDraft));
    setApplyAtsBusy(true);
    try {
      const result = await applyAtsThresholdM.mutateAsync({ min_ats_score: score });
      const applied = Math.max(0, Math.min(100, Number(result.min_ats_score ?? score)));
      atsCutoffEditRef.current = false;
      setAppliedMinAtsScore(applied);
      setMinAtsScoreDraft(applied);
      await qc.refetchQueries({ queryKey: [...queryKeys.interviewDraft, orderId] });
      refreshDraft();
      const eligible = Number(result.eligible_count ?? screeningEligibleCount);
      toast.success(`${eligible} candidate${eligible === 1 ? "" : "s"} ready at ${applied}% ATS cutoff`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not apply ATS cutoff");
    } finally {
      setApplyAtsBusy(false);
    }
  };

  const onRunAtsClick = () => {
    if (!script.trim()) {
      toast.error("Complete and approve the interview in Step 1 before running ATS");
      return;
    }
    if (!criteria.trim() || !(role.trim() || position.trim())) {
      toast.error("Complete position, role, and screening criteria before ATS");
      return;
    }
    setAtsQuote(null);
    setAtsQuoteError(null);
    setAtsPromptOpen(true);
    const reRunAll = unscoredCount === 0 && candidates.some((c) => c.ats != null || Boolean(c.atsStatus));
    void loadAtsQuote(reRunAll);
  };

  const onContinueWithoutAts = async () => {
    setAtsPromptOpen(false);
    setAtsSkipped(true);
    try {
      await onSaveDraft(true, { ats_skipped: true });
    } catch {
      /* preview can still proceed locally */
    }
    setPreview(true);
  };

  const onUpload = async (files: FileList | null) => {
    if (!orderId || !files?.length) return;
    setUploading(true);
    try {
      await apiUploadFiles(`/service-orders/${encodeURIComponent(orderId)}/recipients/intake-files`, Array.from(files));
      refreshDraft();
      toast.success(
        cvEmailAllowed && cvEmailEnabled
          ? "Files uploaded — candidates added to the table"
          : "Files uploaded — run ATS after generating your AI script",
      );
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

  const flashCopied = (setter: React.Dispatch<React.SetStateAction<boolean>>) => {
    setter(true);
    window.setTimeout(() => setter(false), 2000);
  };

  const copyReference = async () => {
    if (!referenceId) return;
    try {
      await navigator.clipboard.writeText(referenceId);
      flashCopied(setCopiedReference);
      toast.success("Reference copied");
    } catch {
      toast.error("Could not copy reference");
    }
  };

  const copyCareersInbox = async () => {
    try {
      await navigator.clipboard.writeText(CAREERS_INBOX);
      flashCopied(setCopiedCareersEmail);
      toast.success("Email address copied");
    } catch {
      toast.error("Could not copy email");
    }
  };

  const cvEmailActive = cvEmailAllowed && cvEmailEnabled;
  const cvPhase = cvCollectionPhase(cvEmailActive, config);
  const cvReadyForScreening = isCvCollectionComplete(cvEmailActive, config);
  const cvCollectionClosedEarly = Boolean(config.cv_collection_closed_early_at);
  const cvCollectionClosedOnLimit = Boolean(config.cv_collection_closed_on_limit_at);
  const cvCollectionClosed = cvEmailActive && (cvPhase === "ready" || cvCollectionClosedEarly || cvCollectionClosedOnLimit);
  const availableForOrder = cvLimits?.unlimited
    ? null
    : (cvLimits?.available_for_order ?? cvLimits?.remaining ?? 0);
  const planRemainingDisplay =
    cvLimits?.remaining ?? cvLimits?.plan_balance_remaining ?? availableForOrder;
  const maxCvNum = maxCvCount === "" ? null : Number(maxCvCount);
  const isOverPlanLimit =
    Boolean(cvEmailActive) &&
    !cvLimits?.unlimited &&
    maxCvNum != null &&
    availableForOrder != null &&
    maxCvNum > availableForOrder;
  const savedMaxCv =
    config.cv_max_count != null && config.cv_max_count !== "" ? Number(config.cv_max_count) : ("" as const);
  const savedCollectionStart = toLocalInput(String(config.cv_collection_start_at || config.cv_email_start_at || ""));
  const savedCollectionClose = toLocalInput(
    String(config.cv_collection_close_at || config.cv_collection_end_at || config.cv_email_end_at || ""),
  );
  const savedAutoCloseOnLimit = config.cv_auto_close_on_limit !== false;
  const savedOverageAcknowledged = config.cv_overage_acknowledged === true;
  const advancedSettingsDirty = React.useMemo(() => {
    if (!cvEmailActive) return false;
    if (maxCvCount !== savedMaxCv) return true;
    if (autoCloseOnLimit !== savedAutoCloseOnLimit) return true;
    if (collectionStartAt !== savedCollectionStart) return true;
    if (collectionCloseAt !== savedCollectionClose) return true;
    if (isOverPlanLimit && overageAcknowledged !== savedOverageAcknowledged) return true;
    return false;
  }, [
    cvEmailActive,
    maxCvCount,
    savedMaxCv,
    autoCloseOnLimit,
    savedAutoCloseOnLimit,
    collectionStartAt,
    savedCollectionStart,
    collectionCloseAt,
    savedCollectionClose,
    isOverPlanLimit,
    overageAcknowledged,
    savedOverageAcknowledged,
  ]);
  const advancedSettingsSaved = cvEmailActive && !advancedSettingsDirty;
  const advancedSummary = formatCvAdvancedSummary({
    maxCvCount,
    autoCloseOnLimit,
    collectionCloseAt,
    minAtsScore: appliedMinAtsScore,
  });
  const paymentApproved = String(order?.payment_status || "").toLowerCase() === "approved";
  const inviteDispatchFailed = paymentApproved && lastInviteDispatch?.ok === false;
  const unscoredCount = React.useMemo(
    () => candidates.filter((c) => candidateNeedsAtsScore(c) && !isAtsAnalyzingStatus(c.atsStatus)).length,
    [candidates],
  );
  const analyzingCount = React.useMemo(
    () =>
      candidates.filter(
        (c) => isAtsAnalyzingStatus(c.atsStatus) || (runAtsM.isPending && candidateNeedsAtsScore(c)),
      ).length,
    [candidates, runAtsM.isPending],
  );
  const allCandidatesScored =
    candidates.length > 0 &&
    candidates.every((c) => {
      const st = String(c.atsStatus || "").toLowerCase();
      return (st === "complete" && c.ats != null) || st === "failed";
    });
  const atsRunRecorded =
    Boolean(config.ats_manual_run_at) ||
    Boolean(config.ats_last_charge_at) ||
    Boolean(atsRunAt);
  const atsScoringComplete = React.useMemo(() => {
    if (atsSkipped || config.ats_skipped) return true;
    if (runAtsM.isPending || atsInProgress) return false;
    if (candidates.length === 0) return cvEmailActive;
    return allCandidatesScored;
  }, [
    atsSkipped,
    config.ats_skipped,
    runAtsM.isPending,
    atsInProgress,
    cvEmailActive,
    candidates.length,
    allCandidatesScored,
  ]);
  const atsStatusDetail = React.useMemo(() => {
    if (atsSkipped || config.ats_skipped) return "Skipped";
    if (runAtsM.isPending || atsInProgress) {
      if (analyzingCount > 0) {
        return `${ATS_ANALYZING_LABEL} (${analyzingCount} CV${analyzingCount === 1 ? "" : "s"})`;
      }
      return ATS_ANALYZING_LABEL;
    }
    if (candidates.length > 0 && allCandidatesScored) {
      return cvEmailActive ? "Scored from email" : `${candidates.length} candidate${candidates.length === 1 ? "" : "s"} scored`;
    }
    if (atsRunRecorded) {
      const when =
        atsRunAt || formatAtsRunTime(config.ats_manual_run_at || config.ats_last_charge_at) || null;
      if (unscoredCount > 0) {
        return when ? `Run ${when} · ${unscoredCount} unscored` : `${unscoredCount} unscored`;
      }
      return when ? `Complete · run ${when}` : "Complete";
    }
    if (unscoredCount > 0) return `${unscoredCount} unscored`;
    if (cvEmailActive && candidates.length === 0) return "Waiting for CVs";
    return "Not run";
  }, [
    atsSkipped,
    config.ats_skipped,
    config.ats_manual_run_at,
    config.ats_last_charge_at,
    runAtsM.isPending,
    atsInProgress,
    candidates.length,
    allCandidatesScored,
    cvEmailActive,
    atsRunRecorded,
    atsRunAt,
    unscoredCount,
    analyzingCount,
  ]);
  const atsGatePassed = atsScoringComplete;
  const setupErrors = collectInterviewSetupErrors({
    position,
    role,
    criteria,
    script,
    scriptIsApproved,
    agentId: resolvedAgentId,
    agentsCount: agents.length,
  });
  const scheduleErrors = React.useMemo(
    () => collectInterviewScheduleErrors(callingStart, callingEnd),
    [callingStart, callingEnd],
  );
  const previewBlockers = React.useMemo(
    () => [...setupErrors, ...scheduleErrors],
    [setupErrors, scheduleErrors],
  );
  const launchErrors = collectInterviewLaunchErrors({
    cvEmailActive,
    cvReadyForScreening,
    candidateCount: candidates.length,
    screeningEligibleCount,
    referenceId,
    atsGatePassed,
    minAtsScore: appliedMinAtsScore,
    atsSkipped: atsSkipped || Boolean(config.ats_skipped),
  });
  const missingPosition = !position.trim() && !role.trim();
  const missingCriteria = !criteria.trim();
  const missingScript = !script.trim();
  const missingScriptApproval = !scriptIsApproved && Boolean(script.trim());
  const missingCallingWindow = !callingStart || !callingEnd;
  const showCriteriaError = step1FieldsTouched && missingCriteria;
  const showScriptError = step1FieldsTouched && (missingScript || missingScriptApproval);

  const canWizardNext = React.useMemo(() => {
    if (wizardStep === 1) return setupErrors.length === 0;
    return true;
  }, [wizardStep, setupErrors]);

  const persistStep1Setup = React.useCallback(async () => {
    if (!orderId || campaignReadOnly) return;
    await onSaveDraft(true);
  }, [orderId, campaignReadOnly, onSaveDraft]);

  const onWizardNext = () => {
    if (wizardStep === 1 && setupErrors.length > 0) {
      setStep1FieldsTouched(true);
      toast.error(setupErrors.length === 1 ? setupErrors[0] : `Complete Step 1 first: ${setupErrors[0]}`);
      return;
    }
    if (wizardStep === 1) {
      void persistStep1Setup()
        .then(() => goWizardNext())
        .catch(() => {
          /* toast handled in onSaveDraft */
        });
      return;
    }
    goWizardNext();
  };

  const onWizardStepClick = (step: number) => {
    if (step === wizardStep) return;
    if (step > 1 && wizardStep === 1 && setupErrors.length > 0) {
      setStep1FieldsTouched(true);
      toast.error(setupErrors.length === 1 ? setupErrors[0] : `Complete Step 1 first: ${setupErrors[0]}`);
      return;
    }
    if (step > 1 && wizardStep === 1) {
      void persistStep1Setup()
        .then(() => goWizardTo(step))
        .catch(() => {
          /* toast handled in onSaveDraft */
        });
      return;
    }
    goWizardTo(step);
  };

  React.useEffect(() => {
    if (!cvEmailEnabled || cvLimits?.unlimited) return;
    const available = cvLimits?.available_for_order ?? cvLimits?.remaining;
    if (available == null) return;
    if (maxCvCount !== "" || (config.cv_max_count != null && config.cv_max_count !== "")) return;
    setMaxCvCount(available);
  }, [cvEmailEnabled, cvLimits, maxCvCount, config.cv_max_count]);

  const refreshQuote = async () => {
    if (!orderId) return;
    setQuoteError(null);
    if (candidates.length === 0) {
      if (cvEmailActive) {
        setQuoteError(
          cvReadyForScreening
            ? `No CVs received yet — share reference ${referenceId || "—"} and ${CAREERS_INBOX} with applicants`
            : "Quote unlocks when CV collection ends and at least one CV is received",
        );
      } else {
        setQuoteError("Upload at least one candidate before requesting a quote");
      }
      return;
    }
    if (hasPackageSub) {
      setQuoteTotalDisplay(
        billingPlanName ? `Included in ${billingPlanName}` : "Included in your package",
      );
      return;
    }
    try {
      await onSaveDraft(true);
      const quoted = await apiFetch<{ quote_total_pence?: number; quote_total_display?: string }>(
        `/service-orders/${encodeURIComponent(orderId)}/quote`,
        { method: "POST", body: "{}" },
      );
      const display = quoted.quote_total_display;
      if (display) {
        setQuoteTotalDisplay(display);
        return;
      }
      const pence = Number(quoted.quote_total_pence || order?.quote_total_pence || 0);
      const market = String((quoted as Record<string, unknown>).pricing_market || "gbp");
      setQuoteTotalDisplay(pence ? formatQuoteDisplay(pence, market) : undefined);
      if (!pence && !display) {
        setQuoteError("Quote returned empty — set calling window in Step 4, save draft, then retry");
      }
    } catch (e) {
      setQuoteError(e instanceof Error ? e.message : "Could not load quote");
    }
  };

  const onPayLaunch = async (): Promise<void> => {
    if (!orderId) {
      throw new Error("Save your draft before paying");
    }
    if (launchErrors.length > 0) {
      throw new Error(launchErrors.length === 1 ? launchErrors[0] : launchErrors.join(" · "));
    }
    if (!gcReady) {
      throw new Error("GoCardless checkout is not configured");
    }
    setPayBusy(true);
    try {
      await onSaveDraft(true);
      await startGoCardlessOrderPayment(orderId);
    } catch (e) {
      setPayBusy(false);
      throw e instanceof Error ? e : new Error("Could not start GoCardless checkout");
    }
  };

  const launchStatusRef = React.useRef<HTMLDivElement | null>(null);

  const scrollToLaunchStatus = () => {
    window.setTimeout(() => {
      launchStatusRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 120);
  };

  const onLaunchFromPackage = async (): Promise<boolean> => {
    if (!orderId) {
      throw new Error("Save your draft before launch");
    }
    if (launchErrors.length > 0) {
      const msg = launchErrors.length === 1 ? launchErrors[0] : launchErrors.join(" · ");
      toast.error(msg);
      throw new Error(msg);
    }
    setPayBusy(true);
    try {
      await onSaveDraft(true);
      const result = await launchM.mutateAsync();
      await completeLaunchSuccess(result);
      return true;
    } catch (e) {
      const message = e instanceof Error ? e.message : "Could not launch campaign";
      toast.error(message);
      throw e instanceof Error ? e : new Error(message);
    } finally {
      setPayBusy(false);
    }
  };

  React.useEffect(() => {
    if (!preview) setPayBusy(false);
  }, [preview]);

  const previewData: InterviewPreviewData = {
    position,
    role,
    criteria,
    reportNotes: reportNotes.trim(),
    agentName: selectedAgent?.voice_label || selectedAgent?.name || "—",
    script,
    candidateCount: candidates.length,
    screeningEligibleCount,
    minAtsScore: appliedMinAtsScore,
    atsSkipped: atsSkipped || Boolean(config.ats_skipped),
    referenceId,
    cvEmailEnabled: cvEmailAllowed && cvEmailEnabled,
    cvCollectionComplete: cvReadyForScreening,
    careersInbox: CAREERS_INBOX,
    collectionStart: collectionStartAt || "Now (default)",
    collectionEnd: collectionCloseAt || "None (open until limit or manual close)",
    callingStart: callingStart || "—",
    callingEnd: callingEnd || "—",
    expectedDurationMinutes,
    scriptApproved: scriptIsApproved,
    quoteTotalDisplay,
    waPreviewBody,
    waPreviewTemplateName,
    waPreviewButtons,
    waPreviewConfirmationBody,
    waPreviewConfirmationButtons,
    waPreviewConfirmationTemplateName,
    waPreviewSyncLabel: waPreviewLoading ? "Syncing WhatsApp templates…" : waPreviewSyncLabel,
  };

  const atsQuoteForceRescore =
    unscoredCount === 0 && candidates.some((c) => c.ats != null || Boolean(c.atsStatus));

  const onAttemptPreview = () => {
    if (previewBlockers.length > 0) {
      toast.error(
        previewBlockers.length === 1
          ? previewBlockers[0]
          : `Complete setup first:\n${previewBlockers.map((e) => `• ${e}`).join("\n")}`,
      );
      return;
    }
    if (!cvEmailActive && candidates.length > 0 && !atsGatePassed) {
      setAtsQuote(null);
      setAtsQuoteError(null);
      setAtsPromptOpen(true);
      void loadAtsQuote(atsQuoteForceRescore);
      return;
    }
    setPreview(true);
    if (launchErrors.length > 0) {
      toast.message("Preview opened — finish these before launch", {
        description: launchErrors.join(" · "),
      });
    }
  };

  const onContinueWithoutAtsHandler = () => {
    void onContinueWithoutAts();
  };

  const candSort = useTableSort(candidates, "ats", "desc");

  if (!order && ((wantNew && !draftOrderId && createDraftM.isPending) || (draftOrderId && draftQ.isLoading && !createDraftM.data?.order))) {
    return (
      <div className="flex w-full flex-col gap-6">
        <PageHeader eyebrow="Interviews" title="Create new interview" description="Define your interview, collect CVs, then launch — three steps." />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (draftQ.isError) {
    const isNotFound = draftQ.error instanceof ApiError && draftQ.error.status === 404;
    return (
      <div className="flex w-full flex-col gap-6">
        <PageHeader eyebrow="Interviews" title="Create new interview" description="Could not load interview draft." />
        <Card>
          <CardContent className="py-8 text-center text-sm text-destructive">
            {draftQ.error instanceof Error ? draftQ.error.message : "Failed to load interview draft"}
            {isNotFound ? (
              <p className="mt-3 text-muted-foreground">
                This ID may be a survey (not an interview), deleted, or from another organisation. Open{" "}
                <strong>Interviews → list → Open</strong> for live campaigns, or start fresh below.
              </p>
            ) : null}
            <div className="mt-4 flex flex-wrap justify-center gap-2">
              <Button onClick={() => void draftQ.refetch()}>Try again</Button>
              <Button variant="outline" asChild>
                <Link to="/interviews/new" search={{ new: true }}>
                  Start new interview
                </Link>
              </Button>
              <Button variant="ghost" asChild>
                <Link to="/interviews">Back to interviews</Link>
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (!orderId) {
    if (draftOrderId && draftQ.isSuccess) {
      return (
        <div className="flex w-full flex-col gap-6">
          <PageHeader eyebrow="Interviews" title="Create new interview" description="This draft is no longer available." />
          <Card>
            <CardContent className="p-6 text-sm text-muted-foreground">
              The interview draft was empty or has been removed.
              <div className="mt-4">
                <Button asChild><Link to="/interviews/new" search={{ new: true }}>Start a new interview</Link></Button>
              </div>
            </CardContent>
          </Card>
        </div>
      );
    }
    if (createDraftM.isError || (createDraftM.isSuccess && !createDraftM.data?.order?.id && !draftOrderId)) {
      return (
        <div className="flex w-full flex-col gap-6">
          <PageHeader eyebrow="Interviews" title="Create new interview" description="Could not start a new interview." />
          <Card>
            <CardContent className="p-6 text-sm text-destructive">
              {createDraftM.error instanceof Error ? createDraftM.error.message : "Failed to create interview draft"}
              <div className="mt-4">
                <Button
                  onClick={() => {
                    createStartedRef.current = false;
                    createFailedRef.current = false;
                    void createDraftM.mutateAsync().then((payload) => {
                      const id = payload?.order?.id;
                      if (!id) {
                        createFailedRef.current = true;
                        toast.error("Could not start interview draft — server returned no order id.");
                        return;
                      }
                      void navigate({ to: "/interviews/new", search: { order_id: id }, replace: true });
                    });
                  }}
                >
                  Try again
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      );
    }
    if (!wantNew && !draftOrderId) {
      return (
        <div className="flex w-full flex-col gap-6">
          <PageHeader eyebrow="Interviews" title="Create new interview" description="Start a fresh AI phone screening campaign." />
          <Card>
            <CardContent className="flex flex-col gap-4 p-6">
              <p className="text-sm text-muted-foreground">No draft in progress. Create a new interview when you are ready.</p>
              <Button asChild className="w-fit">
                <Link to="/interviews/new" search={{ new: true }}>Create new interview</Link>
              </Button>
            </CardContent>
          </Card>
        </div>
      );
    }
    return (
      <div className="flex w-full flex-col gap-6">
        <PageHeader eyebrow="Interviews" title="Create new interview" description="Starting a new draft…" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  return (
    <div className="flex w-full flex-col gap-6 pb-24">
      <PageHeader
        eyebrow="Interviews"
        title={isEditingExisting ? "Edit interview" : "Create new interview"}
        description={
          isEditingExisting
            ? "Update script, candidates, and launch settings in the full wizard."
            : "A guided 4-step wizard — script, CVs, email collection, then launch."
        }
        actions={
          isEditingExisting ? (
            <Button variant="outline" size="sm" className="gap-1.5" disabled>
              <Pencil className="size-4" /> Editing
            </Button>
          ) : undefined
        }
      />

      {isLiveCampaign && !campaignReadOnly ? (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 px-4 py-3 text-sm text-amber-950 dark:text-amber-100">
          Live interview — script and calling window changes apply to <strong>candidates not yet called</strong>.
          Completed interviews and in-progress calls are unchanged.
        </div>
      ) : null}

      {campaignReadOnly && orderId ? (
        <Card className="border-muted bg-muted/40">
          <CardContent className="flex flex-wrap items-center justify-between gap-3 p-4 text-sm">
            <p className="text-muted-foreground">{interviewCampaignReadOnlyLabel(orderStatus)}</p>
            <Button asChild variant="outline" size="sm">
              <Link to="/interviews/results/$orderId" params={{ orderId }}>View results</Link>
            </Button>
          </CardContent>
        </Card>
      ) : null}

      {!campaignReadOnly ? (
        <Stepper steps={INTERVIEW_WIZARD_STEPS} current={wizardStep} onStepClick={onWizardStepClick} />
      ) : null}

      {(setupErrors.length > 0 || launchErrors.length > 0) && !campaignReadOnly && wizardStep === 1 && (
        <div className="rounded-lg border border-amber-500/40 bg-amber-500/5 px-4 py-3 text-sm">
          <p className="font-medium text-foreground">Action needed — complete the items below:</p>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-muted-foreground">
            {setupErrors.map((item) => (
              <li key={`setup-${item}`}>{item}</li>
            ))}
            {launchErrors.map((item) => (
              <li key={`launch-${item}`}>{item}</li>
            ))}
          </ul>
        </div>
      )}

      <div key={wizardStep} className="animate-fade-in">
      {(wizardStep === 1 || campaignReadOnly) && (
      <Card>
        <CardHeader>
          <CardTitle>Step 1 · Define interview</CardTitle>
          <CardDescription>
            Approve the job screening script here. Questions 3+ are the same for every candidate; questions 1–2 are CV templates — the AI personalises those on each call.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-5 md:grid-cols-2">
          <Field label="Position" error={missingPosition ? "Enter position or role" : undefined}>
            <Input value={position} onChange={(e) => setPosition(e.target.value)} placeholder="Senior dental hygienist — Manchester" className={inputErrorClass(missingPosition)} />
          </Field>
          <Field label="Role" error={missingPosition ? "Enter role or position" : undefined}>
            <Input value={role} onChange={(e) => setRole(e.target.value)} placeholder="Registered dental hygienist (GDC)" className={inputErrorClass(missingPosition)} />
          </Field>
          <Field label="AI voice agent">
            {agents.length === 0 ? (
              <p className="text-xs text-muted-foreground">No voice agents configured yet. Ask your admin to enable interview agents.</p>
            ) : (
              <Select value={resolvedAgentId} onValueChange={setAgentId}>
                <SelectTrigger><SelectValue placeholder="Select agent" /></SelectTrigger>
                <SelectContent>
                  {agents.map((a) => (
                    <SelectItem key={a.id} value={a.id}>
                      {a.voice_label || a.name}
                      {a.is_default_for_org ? " · default" : a.is_zone_match ? " · GB" : ""}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </Field>
          <div className="md:col-span-2 space-y-1.5">
            <Label className={`text-xs ${showCriteriaError ? "text-destructive" : ""}`}>Screening criteria</Label>
            <Textarea rows={4} value={criteria} onChange={(e) => setCriteria(e.target.value)} placeholder="Must hold GDC registration, 3+ years experience, willing to travel…" className={inputErrorClass(showCriteriaError)} />
            <p className="text-[11px] text-muted-foreground">
              Write anything relevant — must-haves, deal-breakers, or extra context. The AI uses this on the call and in your report.
            </p>
            {showCriteriaError ? <p className="text-[11px] text-destructive">Add screening criteria before generating questions</p> : null}
          </div>
          <div className="md:col-span-2 space-y-1.5">
            <Label className={`text-xs ${showScriptError ? "text-destructive" : ""}`}>Interview questions</Label>
            <Textarea
              rows={8}
              value={questionsText}
              onChange={(e) => {
                const nextQuestions = e.target.value;
                setQuestionsText(nextQuestions);
                const merged = mergeQuestionsIntoScript(script, nextQuestions);
                const approvedText = String(config.approved_script || "").trim();
                setScript(merged);
                if (!approvedText || extractQuestionsBlock(approvedText) !== nextQuestions.trim()) {
                  setScriptApproved(false);
                  setExpectedDurationMinutes(undefined);
                } else {
                  setScriptApproved(Boolean(config.script_approved));
                }
              }}
              placeholder="Write your own numbered questions, or click Generate AI questions for a draft…"
              className={inputErrorClass(showScriptError)}
            />
            <p className="text-[11px] text-muted-foreground">
              Same job questions for every candidate (from your criteria). Questions 1–2 are templates — the AI asks each person different CV questions on the call. Approve when the job script is right.
            </p>
            {step1FieldsTouched && missingScript ? <p className="text-[11px] text-destructive">Generate or paste a script, then approve it</p> : null}
            {step1FieldsTouched && !missingScript && missingScriptApproval ? <p className="text-[11px] text-destructive">Click Approve script when you are happy with it</p> : null}
          </div>
          <div className="md:col-span-2 flex flex-wrap gap-2">
            <Button variant="outline" className="gap-1.5" onClick={() => void onGenerateScript()} disabled={generateM.isPending}>
              <Wand2 className="size-4" /> {generateM.isPending ? "Generating…" : "Generate AI questions"}
            </Button>
            <Button variant="ghost" className="gap-1.5" onClick={() => void onGenerateScript()} disabled={generateM.isPending}><RotateCcw className="size-4" /> Regenerate</Button>
            <Button
              variant="outline"
              className="gap-1.5"
              onClick={() => void onApproveScript()}
              disabled={scriptIsApproved || saveDraftM.isPending || patchOrderM.isPending}
            >
              {scriptIsApproved ? <Lock className="size-4" /> : <LockOpen className="size-4" />}
              {scriptIsApproved ? "Script approved" : "Approve script"}
            </Button>
            <div className="ml-auto flex items-center gap-2">
              {expectedDurationMinutes ? (
                <span className="text-xs text-muted-foreground">Expected call time: ~{expectedDurationMinutes} min</span>
              ) : null}
              <StatusBadge tone={scriptIsApproved ? "approved-script" : "draft-script"} />
            </div>
          </div>
        </CardContent>
      </Card>
      )}

      {(wizardStep === 2 || campaignReadOnly) && (
      <Card>
        <CardHeader>
          <CardTitle>Step 2 · Collect candidates</CardTitle>
          <CardDescription>Upload CVs, then run ATS and apply your cutoff.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-5 md:grid-cols-2">

          <div className="md:col-span-2 group relative overflow-hidden rounded-xl border-2 border-dashed border-border bg-gradient-to-br from-background/60 via-background/40 to-accent/20 px-4 py-8 transition-colors hover:border-primary/40 sm:px-6 sm:py-10">
            <BackdropIllustration />
            <input ref={fileRef} type="file" multiple className="hidden" onChange={(e) => void onUpload(e.target.files)} />
            <div className="relative flex flex-col items-center gap-2 text-center">
              <div className="rounded-full bg-primary/10 p-3 ring-1 ring-primary/20 transition-transform group-hover:scale-110">
                <Upload className="size-6 text-primary" />
              </div>
              <p className="text-sm font-medium">
                {cvEmailActive ? "Optional — upload CVs manually" : "Drop CSV, Excel, PDF, DOCX, or ZIP"}
              </p>
              <p className="text-xs text-muted-foreground">
                {cvEmailActive
                  ? "CVs also arrive by email during your collection window — you do not need to upload files here."
                  : "Or click to upload"}
              </p>
              <div className="mt-2 flex w-full flex-col gap-2 sm:flex-row sm:justify-center">
                <Button size="sm" className="w-full sm:w-auto" onClick={() => fileRef.current?.click()} disabled={uploading || !orderId}>
                  {uploading ? "Uploading…" : "Choose files"}
                </Button>
                <Button size="sm" variant="outline" className="w-full gap-1.5 sm:w-auto" onClick={() => void onDownloadTemplate()}>
                  <Download className="size-3.5" /> Download template
                </Button>
              </div>
            </div>
          </div>

          <div className="md:col-span-2 min-w-0">
            <div className="mb-2 flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
              <div className="flex min-w-0 flex-wrap items-center gap-2">
                <p className="text-xs text-muted-foreground">
                  {cvEmailActive ? `Candidates · ${candidates.length}` : `Candidates uploaded · ${candidates.length}`}
                  {screeningEligibleCount > 0 ? (
                    <span className="text-foreground"> · {screeningEligibleCount} ready for screening</span>
                  ) : null}
                </p>
                {selected.size > 0 && (
                  <span className="animate-fade-in inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary">
                    {selected.size} selected
                  </span>
                )}
              </div>
              <div className="flex flex-wrap items-center gap-2">
                {selected.size > 0 && (
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-7 gap-1.5 text-xs text-destructive hover:text-destructive animate-fade-in"
                    disabled={candidatesLocked || deleteBusy}
                    onClick={onDeleteSelected}
                  >
                    <Trash2 className="size-3.5" /> Delete selected ({selected.size})
                  </Button>
                )}
                {atsRunAt && (
                  <span className="inline-flex items-center gap-1 text-[11px] text-muted-foreground">
                    <CheckCircle2 className="size-3 text-success" /> ATS run {atsRunAt}
                  </span>
                )}
                {unscoredCount > 0 && candidates.length > 0 && (
                  <span className="text-[11px] text-amber-700 dark:text-amber-400">{unscoredCount} unscored</span>
                )}
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 gap-1.5 text-xs"
                  disabled={runAtsM.isPending || candidates.length === 0 || campaignReadOnly}
                  onClick={onRunAtsClick}
                >
                  <Sparkles className="size-3.5" />
                  {runAtsM.isPending ? ATS_ANALYZING_LABEL : atsRunAt ? "Re-run ATS" : "Run ATS"}
                </Button>
              </div>
            </div>
            {atsInProgress ? (
              <div className="mb-2 flex items-center gap-2 rounded-md border border-primary/20 bg-primary/5 px-3 py-2 text-xs text-muted-foreground">
                <Sparkles className="size-3.5 shrink-0 animate-pulse text-primary" />
                {analyzingCount > 0
                  ? `${ATS_ANALYZING_LABEL} ${analyzingCount} CV${analyzingCount === 1 ? "" : "s"} — scores refresh automatically.`
                  : `${ATS_ANALYZING_LABEL} scores refresh automatically.`}
              </div>
            ) : null}
            <div className="table-scroll rounded-lg border border-border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-10 pl-4">
                      <Checkbox
                        checked={allSelected ? true : someSelected ? "indeterminate" : false}
                        onCheckedChange={toggleAll}
                        aria-label="Select all"
                      />
                    </TableHead>
                    <TableHead>Name</TableHead>
                    <TableHead className="min-w-[120px]">Mobile</TableHead>
                    <TableHead className="min-w-[160px]">Email</TableHead>
                    <TableHead className="w-20">ATS</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="w-28 pr-4 text-right" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {candSort.sorted.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={7} className="py-8 text-center text-sm text-muted-foreground">
                        {cvEmailActive
                          ? (
                              <>
                                No CVs yet — applicants email {CAREERS_INBOX} with your{" "}
                                <strong className="font-semibold text-foreground">job reference</strong>. They appear here automatically.
                              </>
                            )
                          : "Upload candidates to get started."}
                      </TableCell>
                    </TableRow>
                  ) : (
                    candSort.sorted.map((r) => (
                      <TableRow key={r.id} data-state={selected.has(r.id) ? "selected" : undefined}>
                        <TableCell className="pl-4">
                          <Checkbox
                            checked={selected.has(r.id)}
                            onCheckedChange={() => toggleOne(r.id)}
                            aria-label={`Select ${r.name}`}
                          />
                        </TableCell>
                        <TableCell>
                          <div className="font-medium">{r.name}</div>
                        </TableCell>
                        <TableCell>
                          <Input
                            value={recipientContactValue(r, "phone")}
                            onChange={(e) => onRecipientContactChange(r, "phone", e.target.value)}
                            onBlur={() => void onRecipientContactBlur(r, "phone")}
                            disabled={candidatesLocked || patchRecipientM.isPending}
                            placeholder="Mobile"
                            className="h-8 min-w-[110px] text-xs"
                          />
                        </TableCell>
                        <TableCell>
                          <Input
                            type="email"
                            value={recipientContactValue(r, "email")}
                            onChange={(e) => onRecipientContactChange(r, "email", e.target.value)}
                            onBlur={() => void onRecipientContactBlur(r, "email")}
                            disabled={candidatesLocked || patchRecipientM.isPending}
                            placeholder="Email"
                            className="h-8 min-w-[140px] text-xs"
                          />
                        </TableCell>
                        <TableCell>
                          {(() => {
                            const atsDisplay = resolveCandidateAtsDisplay(r, {
                              optimisticAnalyzing: runAtsM.isPending && candidateNeedsAtsScore(r),
                            });
                            return (
                              <AtsScore
                                score={atsDisplay.score}
                                status={atsDisplay.status}
                                minThreshold={appliedMinAtsScore}
                              />
                            );
                          })()}
                        </TableCell>
                        <TableCell className="text-xs">
                          <StatusBadge tone={activityStatusTone(r.activityStatus)}>
                            {r.activityStatusLabel || activityStatusLabel(r.activityStatus)}
                          </StatusBadge>
                        </TableCell>
                        <TableCell className="pr-4">
                          <div className="flex justify-end gap-1">
                            <Button
                              size="icon"
                              variant="ghost"
                              className="size-8"
                              aria-label="Download CV"
                              title={r.cvFilename ? `Download ${r.cvFilename}` : "No CV file"}
                              disabled={!r.cvFilename}
                              onClick={() => void onDownloadCv(r.id, r.cvFilename)}
                            >
                              <FileDown className="size-4" />
                            </Button>
                            <Button
                              size="icon"
                              variant="ghost"
                              className="size-8"
                              aria-label="View activity"
                              title="View activity"
                              onClick={() => setActivityCandidate(r)}
                            >
                              <Activity className="size-4" />
                            </Button>
                            <Button
                              size="icon"
                              variant="ghost"
                              className="size-8 text-destructive hover:text-destructive"
                              aria-label="Remove candidate"
                              disabled={candidatesLocked || deleteBusy}
                              title={candidatesLocked ? "Cannot remove after invites are sent or once live" : "Remove candidate"}
                              onClick={() => onDeleteRecipient(r.id, r.name)}
                            >
                              <Trash2 className="size-4" />
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </div>
          </div>

          <div className="md:col-span-2 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end">
            {cvEmailActive && !cvCollectionClosed ? (
              <Button variant="outline" size="sm" className="w-fit gap-1.5" disabled={closeCvBusy} onClick={() => void onCloseCvCollection()}>
                {closeCvBusy ? (
                  <>Checking email & closing…</>
                ) : (
                  <>
                    <LockOpen className="size-3.5" /> Close CV collection early & continue
                  </>
                )}
              </Button>
            ) : null}
            <div className="flex min-w-0 flex-1 flex-col gap-1 sm:max-w-lg">
              <Label
                htmlFor="min-ats-score"
                className="text-xs"
                style={atsCutoffDirty ? { color: ATS_CUTOFF_PENDING_COLOR } : undefined}
              >
                Auto-reject if ATS score below (%)
              </Label>
              <div className="flex flex-wrap items-center gap-2">
                <Input
                  id="min-ats-score"
                  type="number"
                  min={0}
                  max={100}
                  value={minAtsScoreDraft}
                  onChange={(e) => {
                    atsCutoffEditRef.current = true;
                    const raw = e.target.value;
                    if (raw === "") {
                      setMinAtsScoreDraft(0);
                      return;
                    }
                    const next = Number(raw);
                    if (Number.isNaN(next)) return;
                    setMinAtsScoreDraft(Math.max(0, Math.min(100, next)));
                  }}
                  disabled={campaignReadOnly || (cvEmailActive && cvCollectionClosed)}
                  className="h-9 w-20 min-w-0"
                  style={
                    atsCutoffDirty
                      ? {
                          color: ATS_CUTOFF_PENDING_COLOR,
                          borderColor: ATS_CUTOFF_PENDING_COLOR,
                          boxShadow: `0 0 0 1px ${ATS_CUTOFF_PENDING_COLOR}66`,
                        }
                      : undefined
                  }
                />
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  className="h-9 gap-1.5 shadow-sm"
                  disabled={
                    !atsCutoffDirty ||
                    applyAtsBusy ||
                    applyAtsThresholdM.isPending ||
                    campaignReadOnly ||
                    !orderId
                  }
                  onClick={() => void onApplyAtsThreshold()}
                >
                  <Check className="size-3.5" />
                  {applyAtsBusy || applyAtsThresholdM.isPending ? "Applying…" : "Apply cutoff"}
                </Button>
                <p
                  className="text-[11px] text-muted-foreground"
                  style={atsCutoffDirty ? { color: ATS_CUTOFF_PENDING_COLOR } : undefined}
                >
                  {atsCutoffDirty
                    ? `Active cutoff is ${appliedMinAtsScore}% — click Apply cutoff to save ${minAtsScoreDraft}%.`
                    : screeningEligibleCount > 0
                      ? `${screeningEligibleCount} of ${candidates.length} pass the ${appliedMinAtsScore}% cutoff.`
                      : candidates.length > 0
                        ? `Cutoff ${appliedMinAtsScore}% applied — run ATS first if scores are missing.`
                        : "Default cutoff 40%. Run ATS, then adjust and Apply cutoff."}
                </p>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
      )}

      {(wizardStep === 3 || campaignReadOnly) && (
      <Card>
        <CardHeader>
          <CardTitle>Step 3 · CV email collection</CardTitle>
          <CardDescription>Optionally collect CVs by email using your job reference and careers inbox.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-5 md:grid-cols-2">
          {referenceId ? (
            <div className="space-y-1.5 md:col-span-2">
              <Label className="text-xs">Job reference</Label>
              <div className="flex flex-col gap-2 sm:flex-row">
                <Input value={referenceId} readOnly className="min-w-0 font-mono text-xs sm:text-sm" />
                <Button variant="outline" className="w-full shrink-0 gap-1.5 sm:w-auto" onClick={() => void copyReference()}>
                  {copiedReference ? <Check className="size-4 text-success" /> : <Copy className="size-4" />}
                  {copiedReference ? "Copied!" : "Copy reference"}
                </Button>
              </div>
              {cvEmailAllowed && cvEmailEnabled ? (
                <p className="text-[11px] text-muted-foreground">
                  CVs sent to{" "}
                  <span className="inline-flex items-center gap-1 font-medium text-foreground">
                    {CAREERS_INBOX}
                    <button
                      type="button"
                      className="inline-flex rounded p-0.5 text-muted-foreground hover:text-foreground"
                      aria-label={copiedCareersEmail ? "Email copied" : "Copy careers email"}
                      title={copiedCareersEmail ? "Copied!" : "Copy email"}
                      onClick={() => void copyCareersInbox()}
                    >
                      {copiedCareersEmail ? <Check className="size-3.5 text-success" /> : <Copy className="size-3.5" />}
                    </button>
                  </span>{" "}
                  with your <strong className="font-semibold text-foreground">job reference</strong> will be collected here.
                </p>
              ) : (
                <p className="text-[11px] text-muted-foreground">
                  CVs sent to {CAREERS_INBOX} with your <strong className="font-semibold text-foreground">job reference</strong> will be collected here once email collection is enabled.
                </p>
              )}
            </div>
          ) : null}

          <div className="md:col-span-2">
          <ToggleRow
            title="CV email collection"
            desc={
              cvEmailAllowed
                ? "Turn on to collect CVs by email using your job reference."
                : cvEmailBlockReason ||
                  (billingPlanName
                    ? `Not included on ${billingPlanName} — upgrade to Starter, Pro, or Business.`
                    : "Included on Starter, Pro, and Business packages — not Pay as you go or top-up only.")
            }
            checked={cvEmailEnabled}
            onCheckedChange={(v) => {
              if (v && !cvEmailAllowed) {
                setUpgradeOpen(true);
                return;
              }
              setCvEmailEnabled(v);
              if (v) {
                setAutoCloseOnLimit(true);
                setAdvancedOpen(true);
                if (cvLimits?.default_max_cvs != null) setMaxCvCount(cvLimits.default_max_cvs);
              }
              if (orderId) {
                void onSaveDraft(true, { cv_email_enabled: v }).catch(() => {
                  /* toast handled in onSaveDraft */
                });
              }
            }}
          />
          </div>

          <div className="md:col-span-2 space-y-2">
            <Collapsible open={advancedOpen} onOpenChange={setAdvancedOpen}>
              <CollapsibleTrigger className="group flex w-full items-center gap-2.5 rounded-lg border border-border bg-muted/25 px-3 py-2.5 text-left text-sm transition hover:bg-muted/40">
                <Settings2 className="size-4 shrink-0 text-muted-foreground transition group-hover:text-foreground" aria-hidden />
                <span className="flex-1 font-medium text-foreground">Advanced options</span>
                <ChevronDown className="size-4 shrink-0 text-muted-foreground transition group-data-[state=open]:rotate-180" />
              </CollapsibleTrigger>
              <CollapsibleContent className="mt-2 space-y-4 rounded-lg border border-border bg-background/50 p-4">
                <div className="grid gap-4 sm:grid-cols-2">
                  {cvEmailActive ? (
                    <>
                      <div className="grid gap-4 sm:col-span-2 lg:grid-cols-2">
                        <div className="space-y-1.5">
                          <Label className="text-xs">Max CVs to receive</Label>
                          <Input
                            type="number"
                            min={0}
                            value={maxCvCount}
                            onChange={(e) => {
                              const raw = e.target.value;
                              setMaxCvCount(raw === "" ? "" : Math.max(0, Number(raw)));
                              setOverageAcknowledged(false);
                            }}
                            disabled={cvCollectionClosed || cvLimits?.unlimited}
                            className="w-full min-w-0"
                          />
                          {!cvLimits?.unlimited && planRemainingDisplay != null ? (
                            <p className="text-[11px] text-muted-foreground">
                              You have {planRemainingDisplay} screening
                              {planRemainingDisplay === 1 ? "" : "s"} remaining on your plan
                            </p>
                          ) : null}
                          {isOverPlanLimit ? (
                            <div className="space-y-1.5 rounded-md border border-amber-500/30 bg-amber-500/5 p-2.5">
                              <label className="flex items-start gap-2 text-xs text-muted-foreground">
                                <Checkbox
                                  checked={overageAcknowledged}
                                  onCheckedChange={(checked) => setOverageAcknowledged(checked === true)}
                                  className="mt-0.5"
                                />
                                <span>
                                  I understand additional screenings beyond my plan will be invoiced at the standard
                                  rate
                                </span>
                              </label>
                              {!overageAcknowledged || advancedSettingsDirty ? (
                                <p className="text-[11px] text-amber-800 dark:text-amber-300">
                                  {!overageAcknowledged
                                    ? "Tick this box, then click Save advanced settings below."
                                    : "Click Save advanced settings below to keep this change."}
                                </p>
                              ) : null}
                            </div>
                          ) : null}
                        </div>
                        <div className="space-y-1.5">
                          <Label className="text-xs">Auto-close when limit is reached</Label>
                          <div className="flex h-9 items-center justify-between gap-2 rounded-md border border-border bg-background/40 px-3">
                            <p className="text-[11px] leading-tight text-muted-foreground">
                              Stop collection at max
                            </p>
                            <Switch
                              checked={autoCloseOnLimit}
                              onCheckedChange={setAutoCloseOnLimit}
                              disabled={cvCollectionClosed}
                            />
                          </div>
                        </div>
                      </div>
                      <p className="text-[11px] text-muted-foreground sm:col-span-2">
                        Set the ATS cutoff in Step 2. When auto-close is on, new CVs after the max get a polite auto-reply.
                      </p>
                      <Field label="Start collecting">
                        <Input
                          type="datetime-local"
                          value={collectionStartAt}
                          onChange={(e) => setCollectionStartAt(e.target.value)}
                          disabled={cvCollectionClosed}
                          className="w-full min-w-0"
                        />
                        <p className="text-[11px] text-muted-foreground">Leave blank to start immediately.</p>
                      </Field>
                      <Field label="Stop accepting CVs">
                        <Input
                          type="datetime-local"
                          value={collectionCloseAt}
                          onChange={(e) => setCollectionCloseAt(e.target.value)}
                          disabled={cvCollectionClosed}
                          className="w-full min-w-0"
                        />
                        <p className="text-[11px] text-muted-foreground">
                          Leave blank for no end date. Whichever comes first — max or date — closes collection.
                        </p>
                      </Field>
                    </>
                  ) : (
                    <p className="text-[11px] text-muted-foreground sm:col-span-2">
                      Turn on CV email collection above to configure inbox limits and collection windows.
                    </p>
                  )}
                </div>

                <div className="flex flex-col items-stretch gap-2 border-t border-border pt-4 sm:flex-row sm:items-center sm:justify-between">
                  <div className="min-h-5 text-[11px]">
                    {advancedSettingsDirty ? (
                      <p className="text-amber-800 dark:text-amber-300">
                        Unsaved changes — click Save advanced settings to apply.
                      </p>
                    ) : advancedSettingsSaved ? (
                      <p className="inline-flex items-center gap-1.5 text-muted-foreground">
                        <CheckCircle2 className="size-3.5 shrink-0 text-success" aria-hidden />
                        Advanced settings saved
                      </p>
                    ) : null}
                  </div>
                  <Button
                    type="button"
                    size="sm"
                    variant={advancedSettingsDirty ? "default" : "outline"}
                    disabled={advancedSaveBusy || campaignReadOnly || !orderId || !advancedSettingsDirty}
                    onClick={() => void onSaveAdvancedSettings()}
                  >
                    {advancedSaveBusy ? "Saving…" : "Save advanced settings"}
                  </Button>
                </div>
              </CollapsibleContent>
            </Collapsible>

            {!advancedOpen && advancedSummary ? (
              <p className="text-[11px] text-muted-foreground">{advancedSummary}</p>
            ) : null}
          </div>

          {cvEmailActive ? (
            <div className="md:col-span-2 rounded-lg border border-border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
              <div className="flex flex-wrap items-center gap-2">
                {cvCollectionClosed ? (
                  <span className="inline-flex items-center gap-1 font-medium text-success">
                    <Lock className="size-3.5" /> CV collection closed
                    {cvCollectionClosedEarly ? " (closed early)" : cvCollectionClosedOnLimit ? " (limit reached)" : ""}
                  </span>
                ) : cvPhase === "before" ? (
                  <span className="inline-flex items-center gap-1 font-medium text-foreground">
                    <LockOpen className="size-3.5" /> CV collection not started yet
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 font-medium text-primary">
                    <LockOpen className="size-3.5" /> CV collection open
                  </span>
                )}
              </div>
              {cvPhase === "before" ? (
                <>
                  {" — share your "}
                  <strong className="font-semibold text-foreground">job reference</strong>
                  {" and careers email when collection opens."}
                </>
              ) : null}
              {cvPhase === "open" && " — CVs arrive by email and appear in the candidates table in Step 2."}
              {cvCollectionClosed && " — review candidates, remove weak profiles, then launch."}
            </div>
          ) : null}
        </CardContent>
      </Card>
      )}

      {(wizardStep === 4 || campaignReadOnly) ? (
      <Card ref={launchStatusRef}>
        <CardHeader>
          <CardTitle>Step 4 · ATS, preview & launch</CardTitle>
          <CardDescription>
            {cvEmailActive
              ? "When CV collection ends, review email applicants, set your calling window, approve the preview, then launch — booking invites go out by WhatsApp and email."
              : `Run ATS on uploaded CVs, set your calling window, approve the preview, then launch — ${hasPackageSub ? "included in your package" : "pay per campaign"}, then WhatsApp booking invites go to candidates.`}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <LaunchStatus
              label="ATS scoring"
              done={atsScoringComplete}
              pending={runAtsM.isPending || atsInProgress}
              detail={atsStatusDetail}
            />
            <LaunchStatus label="Script approved" done={scriptIsApproved} detail={scriptIsApproved ? "Ready" : "Approve in Step 1"} />
            <LaunchStatus
              label="Calling window"
              done={!missingCallingWindow}
              detail={
                missingCallingWindow
                  ? "Set start and end below"
                  : `${callingStart ? new Date(callingStart).toLocaleString() : "—"} → ${callingEnd ? new Date(callingEnd).toLocaleString() : "—"}`
              }
            />
            <LaunchStatus label="Payment" done={paymentApproved || hasPackageSub} detail={paymentApproved ? "Approved" : hasPackageSub ? `Included in ${billingPlanName || "package"}` : "After preview"} />
            <LaunchStatus
              label="WhatsApp invites"
              done={bookingInvitesSent}
              detail={
                inviteDispatchFailed
                  ? `Failed — ${String(lastInviteDispatch?.errors?.[0] || "check Telnyx template & allowlist")}`
                  : bookingInvitesSent
                    ? `Sent (${lastInviteDispatch?.whatsapp_sent ?? "—"} WA, ${lastInviteDispatch?.email_sent ?? "—"} email)`
                    : paymentApproved
                      ? "Ready to send"
                      : "After payment"
              }
            />
          </div>
          <div className="rounded-lg border border-border bg-muted/20 p-4">
            <p className="text-sm font-medium">Calling schedule</p>
            <p className="mt-1 text-xs text-muted-foreground">
              Choose when the AI can place screening calls to candidates.
            </p>
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              <Field
                label="Calling start"
                error={!campaignReadOnly && missingCallingWindow && !callingStart ? "Set when AI calls can start" : undefined}
              >
                <Input
                  type="datetime-local"
                  value={callingStart}
                  onChange={(e) => setCallingStart(e.target.value)}
                  disabled={campaignReadOnly}
                  className={inputErrorClass(!campaignReadOnly && missingCallingWindow && !callingStart)}
                />
              </Field>
              <Field
                label="Calling end"
                error={!campaignReadOnly && missingCallingWindow && !callingEnd ? "Set when AI calls must end" : undefined}
              >
                <Input
                  type="datetime-local"
                  value={callingEnd}
                  onChange={(e) => setCallingEnd(e.target.value)}
                  disabled={campaignReadOnly}
                  className={inputErrorClass(!campaignReadOnly && missingCallingWindow && !callingEnd)}
                />
              </Field>
            </div>
          </div>
          <ol className="list-decimal space-y-1 pl-5 text-sm text-muted-foreground">
            <li>
              <strong className="text-foreground">Define interview</strong> — complete Step 1 (criteria and questions).
            </li>
            <li>
              <strong className="text-foreground">Set calling window</strong> — choose when AI screening calls can run (above).
            </li>
            <li>
              <strong className="text-foreground">Run ATS</strong> —{" "}
              {cvEmailActive
                ? "email CVs are scored automatically; run ATS only if you uploaded files manually."
                : "score uploaded CVs in Step 2, apply your cutoff, then review the table."}
            </li>
            <li><strong className="text-foreground">Preview &amp; approve</strong> — confirm script and preview, then <strong className="text-foreground">{hasPackageSub ? "Launch" : "Pay & launch"}</strong>.</li>
            <li><strong className="text-foreground">Send booking invites</strong> — {hasPackageSub ? "sent when you launch" : "appears after payment"}; WhatsApp links go to each eligible candidate.</li>
          </ol>
          {(previewBlockers.length > 0 || launchErrors.length > 0) && !campaignReadOnly ? (
            <div className="space-y-2 rounded-lg border border-amber-500/30 bg-amber-500/5 px-3 py-3 text-sm">
              {previewBlockers.length > 0 ? (
                <div>
                  <p className="font-medium text-foreground">Complete before preview:</p>
                  <ul className="mt-1 list-disc space-y-0.5 pl-5 text-xs text-muted-foreground">
                    {previewBlockers.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
              {launchErrors.length > 0 ? (
                <div>
                  <p className="font-medium text-foreground">
                    {previewBlockers.length > 0 ? "Also before launch:" : cvEmailActive ? "You can preview now — finish before launch:" : "Before launch:"}
                  </p>
                  <ul className="mt-1 list-disc space-y-0.5 pl-5 text-xs text-muted-foreground">
                    {launchErrors.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          ) : null}
          {!campaignReadOnly ? (
          <div className="flex flex-col-reverse gap-2 border-t border-border pt-4 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
            <Button variant="outline" className="gap-1.5" onClick={() => void onSaveDraft()} disabled={saveDraftM.isPending || patchOrderM.isPending}>
              <Save className="size-4" /> {saveDraftM.isPending ? "Saving…" : "Save draft"}
            </Button>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" className="gap-1.5" onClick={goWizardPrev}>
                <ChevronLeft className="size-4" /> Back
              </Button>
              <Button variant="outline" className="gap-1.5" disabled={runAtsM.isPending || candidates.length === 0 || campaignReadOnly} onClick={onRunAtsClick}>
                <Sparkles className="size-4" /> {runAtsM.isPending ? ATS_ANALYZING_LABEL : "Run ATS"}
              </Button>
              <Button className="gap-1.5" disabled={campaignReadOnly} onClick={onAttemptPreview}>
                <Eye className="size-4" /> Preview &amp; approve
              </Button>
            </div>
          </div>
          ) : null}
        </CardContent>
      </Card>
      ) : null}
      </div>

      {!campaignReadOnly && wizardStep !== 4 ? (
        <WizardNav
          step={wizardStep}
          total={INTERVIEW_WIZARD_STEPS.length}
          onPrev={goWizardPrev}
          onNext={onWizardNext}
          nextDisabled={!canWizardNext}
          skippable={wizardStep === 2}
          onSkip={goWizardNext}
          leftActions={
            <>
              <Button variant="ghost" className="gap-1.5 text-destructive hover:text-destructive" disabled>
                <Trash2 className="size-4" /> Delete draft
              </Button>
            </>
          }
          saveDraftAction={
            <Button variant="outline" className="gap-1.5" onClick={() => void onSaveDraft()} disabled={saveDraftM.isPending || patchOrderM.isPending}>
              <Save className="size-4" /> {saveDraftM.isPending ? "Saving…" : "Save draft"}
            </Button>
          }
        />
      ) : null}

      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:flex-wrap sm:items-center sm:justify-end">
        {paymentApproved && !campaignLaunched && !campaignReadOnly ? (
          <Button
            variant="secondary"
            className="gap-1.5"
            disabled={launchM.isPending || !callingStart || !callingEnd}
            onClick={() => {
              void (async () => {
                try {
                  const result = await launchM.mutateAsync();
                  await completeLaunchSuccess(result);
                } catch (e) {
                  toast.error(e instanceof Error ? e.message : "Could not launch campaign");
                }
              })();
            }}
          >
            <Send className="size-4" /> {launchM.isPending ? "Launching…" : "Launch — send booking invites"}
          </Button>
        ) : null}
      </div>

      <PackageUpgradeModal
        open={upgradeOpen}
        onOpenChange={setUpgradeOpen}
        blockReason={cvEmailBlockReason || undefined}
        currentPlanName={billingPlanName || undefined}
      />
      <AtsPreviewGateModal
        open={atsPromptOpen}
        onOpenChange={setAtsPromptOpen}
        quote={atsQuote as { candidate_count?: number; total_gbp?: string; unit_price_gbp?: string; wallet_gbp?: string; requires_payment?: boolean } | null}
        quoteLoading={atsQuoteLoading}
        quoteError={atsQuoteError}
        onRetryQuote={() => void loadAtsQuote(atsQuoteForceRescore)}
        onRunAts={() => void confirmAtsRun()}
        onContinueWithoutAts={onContinueWithoutAtsHandler}
        busy={runAtsM.isPending}
        candidateCount={candidates.length}
        unscoredCount={unscoredCount}
      />
      <InterviewPreviewQuoteModal
        open={preview}
        onOpenChange={setPreview}
        data={previewData}
        launchBlockers={launchErrors}
        onApproveScript={onApproveScript}
        onRefreshQuote={() => void refreshQuote()}
        onPayLaunch={() => onPayLaunch()}
        onLaunch={() => onLaunchFromPackage()}
        quoteLoading={quoteM.isPending}
        quoteError={quoteError}
        payBusy={payBusy || launchM.isPending}
        gcAvailable={gcReady}
        hasPackageSubscription={hasPackageSub}
        packagePlanName={billingPlanName || undefined}
      />
      <CandidateActivityDialog
        open={activityCandidate != null}
        onOpenChange={(open) => {
          if (!open) setActivityCandidate(null);
        }}
        orderId={orderId}
        recipientId={activityCandidate?.id ?? null}
        candidateName={activityCandidate?.name}
      />

      <AlertDialog
        open={deleteDialog.open}
        onOpenChange={(open) => {
          if (!deleteBusy) setDeleteDialog((prev) => ({ ...prev, open }));
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {deleteDialog.mode === "bulk"
                ? `Remove ${deleteDialog.ids.length} candidate${deleteDialog.ids.length === 1 ? "" : "s"}?`
                : "Remove this candidate?"}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {deleteDialog.mode === "bulk" ? (
                <>
                  This will permanently remove {deleteDialog.ids.length} selected candidate
                  {deleteDialog.ids.length === 1 ? "" : "s"} from this interview. Their CV will be deleted from the
                  list — this cannot be undone.
                </>
              ) : (
                <>
                  <strong className="text-foreground">{deleteDialog.label || "This candidate"}</strong> will be
                  removed from the interview list. Their CV file will be deleted — this cannot be undone.
                </>
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleteBusy}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              disabled={deleteBusy}
              onClick={(e) => {
                e.preventDefault();
                void executeDeleteCandidates();
              }}
            >
              {deleteBusy ? "Removing…" : deleteDialog.mode === "bulk" ? "Remove selected" : "Remove candidate"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function Field({ label, children, error }: { label: string; children: React.ReactNode; error?: string }) {
  return (
    <div className="space-y-1.5">
      <Label className={error ? "text-xs text-destructive" : "text-xs"}>{label}</Label>
      {children}
      {error ? <p className="text-[11px] text-destructive">{error}</p> : null}
    </div>
  );
}

function LaunchStatus({
  label,
  done,
  pending,
  detail,
}: {
  label: string;
  done?: boolean;
  pending?: boolean;
  detail?: string;
}) {
  return (
    <div className="rounded-lg border border-border bg-muted/20 px-3 py-2.5">
      <div className="flex items-center gap-2">
        {pending ? (
          <span className="size-2 animate-pulse rounded-full bg-primary" />
        ) : (
          <CheckCircle2 className={`size-4 shrink-0 ${done ? "text-success" : "text-muted-foreground/40"}`} />
        )}
        <p className="text-sm font-medium">{label}</p>
      </div>
      <p className="mt-1 pl-6 text-xs text-muted-foreground">{detail || (done ? "Done" : "Pending")}</p>
    </div>
  );
}

function ToggleRow({ title, desc, checked, onCheckedChange }: { title: string; desc: string; checked?: boolean; onCheckedChange?: (v: boolean) => void }) {
  return (
    <div className="flex items-start justify-between gap-3 rounded-lg border border-border bg-background/40 p-3">
      <div>
        <p className="text-sm font-medium">{title}</p>
        <p className="text-xs text-muted-foreground">{desc}</p>
      </div>
      <Switch checked={checked} onCheckedChange={onCheckedChange} />
    </div>
  );
}

function BackdropIllustration() {
  return (
    <svg aria-hidden="true" className="pointer-events-none absolute inset-0 h-full w-full opacity-[0.07] text-primary" viewBox="0 0 600 200" fill="none">
      <defs><pattern id="dots" x="0" y="0" width="22" height="22" patternUnits="userSpaceOnUse"><circle cx="1.5" cy="1.5" r="1.5" fill="currentColor" /></pattern></defs>
      <rect width="600" height="200" fill="url(#dots)" />
    </svg>
  );
}
