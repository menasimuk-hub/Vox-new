import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import * as React from "react";
import { Check, Copy, Upload, Download, Wand2, Lock, LockOpen, RotateCcw, Trash2, Save, Eye, FileDown, ArrowUpDown, ArrowUp, ArrowDown, CheckCircle2, Send, Sparkles, Activity } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { notifyInterviewLaunch } from "@/lib/interviewLaunchFeedback";
import { isInterviewCampaignReadOnly, interviewCampaignReadOnlyLabel } from "@/lib/interview-campaign";
import { extractQuestionsBlock, mergeQuestionsIntoScript } from "@/lib/interview-script";

import { Checkbox } from "@/components/ui/checkbox";
import { SortHeader, useTableSort } from "@/components/sortable-table";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, DropdownMenuLabel, DropdownMenuSeparator } from "@/components/ui/dropdown-menu";

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
import { apiFetch, apiUploadFiles, downloadAuthenticatedFile } from "@/lib/api";
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
  useSaveInterviewDraft,
  useSendInterviewBookingInvites,
  useCreateNewInterviewDraft,
} from "@/lib/queries";

export const Route = createFileRoute("/_app/interviews/new")({
  head: () => ({ meta: [{ title: "Create interview — VoxBulk" }] }),
  validateSearch: (search: Record<string, unknown>) => ({
    new: search.new === "1" || search.new === 1 || search.new === true,
    order_id: typeof search.order_id === "string" ? search.order_id : undefined,
  }),
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
  phoneCallAllowed?: boolean;
  phoneCallBlockReason?: string | null;
};

function isBookingResendBlocked(status?: string | null, activityStatus?: string | null) {
  if (String(status || "").toLowerCase() === "completed") return true;
  return ["report_ready", "interview_completed", "scheduling_sent"].includes(String(activityStatus || ""));
}

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

function isCvCollectionComplete(
  enabled: boolean,
  collectionEndLocal: string,
  cfg: Record<string, unknown>,
) {
  if (!enabled) return true;
  if (cfg.cv_collection_closed_early_at) return true;
  const endIso = collectionEndLocal ? toIsoFromLocal(collectionEndLocal) : cfg.cv_collection_end_at || cfg.cv_email_end_at;
  if (!endIso) return false;
  try {
    return new Date(String(endIso)) <= new Date();
  } catch {
    return false;
  }
}

function cvCollectionPhase(
  enabled: boolean,
  collectionStartLocal: string,
  collectionEndLocal: string,
  cfg: Record<string, unknown>,
): "off" | "before" | "open" | "ready" {
  if (!enabled) return "off";
  if (cfg.cv_collection_closed_early_at) return "ready";
  const startIso = collectionStartLocal ? toIsoFromLocal(collectionStartLocal) : cfg.cv_collection_start_at;
  const endIso = collectionEndLocal ? toIsoFromLocal(collectionEndLocal) : cfg.cv_collection_end_at;
  const now = Date.now();
  try {
    if (startIso && new Date(String(startIso)).getTime() > now) return "before";
    if (endIso && new Date(String(endIso)).getTime() <= now) return "ready";
    return "open";
  } catch {
    return "open";
  }
}

const CAREERS_INBOX = "careers@voxbulk.com";

function collectInterviewSetupErrors(opts: {
  position: string;
  role: string;
  criteria: string;
  script: string;
  scriptIsApproved: boolean;
  callingStart: string;
  callingEnd: string;
  cvEmailActive: boolean;
  collectionStart: string;
  collectionEnd: string;
}): string[] {
  const errors: string[] = [];
  if (!opts.position.trim() && !opts.role.trim()) errors.push("Add position and role in Step 2");
  if (!opts.criteria.trim()) errors.push("Add screening criteria in Step 2");
  if (!opts.script.trim()) errors.push("Generate the AI script in Step 2");
  if (!opts.scriptIsApproved) errors.push("Approve your script in Step 2");
  if (!opts.callingStart || !opts.callingEnd) errors.push("Set calling start and end in Step 2");
  if (opts.cvEmailActive && (!opts.collectionStart || !opts.collectionEnd)) {
    errors.push("Set CV collection start and end in Step 1");
  }
  return errors;
}

function inputErrorClass(invalid: boolean) {
  return invalid ? "border-destructive ring-1 ring-destructive/40 focus-visible:ring-destructive/40" : "";
}

function collectInterviewLaunchErrors(opts: {
  cvEmailActive: boolean;
  cvReadyForScreening: boolean;
  candidateCount: number;
  referenceId: string;
  atsGatePassed: boolean;
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
    errors.push("Upload at least one candidate in Step 1");
  }
  if (opts.candidateCount > 0 && !opts.atsGatePassed && !opts.cvEmailActive) {
    errors.push("Run ATS scoring or continue without ATS");
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
  const launchM = useLaunchInterviewCampaign(orderId || null);
  const resendInvitesM = useSendInterviewBookingInvites(orderId || null);
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
  const [script, setScript] = React.useState("");
  const [expectedDurationMinutes, setExpectedDurationMinutes] = React.useState<number | undefined>();
  const [scriptApproved, setScriptApproved] = React.useState(false);
  const [agentId, setAgentId] = React.useState("");
  const [delivery, setDelivery] = React.useState("ai_call");
  const [collectionStart, setCollectionStart] = React.useState("");
  const [collectionEnd, setCollectionEnd] = React.useState("");
  const [callingStart, setCallingStart] = React.useState("");
  const [callingEnd, setCallingEnd] = React.useState("");
  const fileRef = React.useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = React.useState(false);
  const [activityCandidate, setActivityCandidate] = React.useState<CandidateRow | null>(null);

  const config = (order?.config || {}) as Record<string, unknown>;
  const referenceId = order?.reference_id || "";
  const billingContext = (draftQ.data as { billing_context?: Record<string, unknown> })?.billing_context;
  const sessionPlan = (session?.subscription as { plan?: Record<string, unknown> } | null)?.plan;
  const billing = interviewBillingFromSources(billingContext, sessionPlan as { code?: string; name?: string; price_gbp_pence?: number; interval?: string; is_enterprise?: boolean; is_payg?: boolean });
  const cvEmailAllowed = billing.cvEmailAllowed;
  const cvEmailBlockReason = billing.blockReason;
  const billingPlanName = billing.planName;
  const hasPackageSub = billing.hasPackageSub;
  const interviewDeliveryOptions = draftQ.data?.interview_delivery_options?.length
    ? draftQ.data.interview_delivery_options
    : ["ai_call"];
  const zoomInterviewEnabled = interviewDeliveryOptions.includes("zoom");

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
      cfg.approved_script,
      cfg.generated_script_draft,
      cfg.expected_duration_minutes,
      cfg.script_approved,
      cfg.agent_id,
      cfg.delivery,
      cfg.cv_collection_start_at,
      cfg.cv_email_start_at,
      cfg.cv_collection_end_at,
      cfg.cv_email_end_at,
      cfg.cv_email_enabled,
      cfg.cv_collection_closed_early_at,
      cfg.ats_last_charge_at,
      cfg.ats_skipped,
    ].join("|");
  }, [order]);
  const lastHydrationKeyRef = React.useRef("");

  React.useEffect(() => {
    lastHydrationKeyRef.current = "";
  }, [draftOrderId]);

  const agents = agentsQ.data || [];
  const selectedAgent = agents.find((a) => a.id === agentId) || pickDefaultInterviewAgent(agents);
  const createStartedRef = React.useRef(false);

  React.useEffect(() => {
    if (draftOrderId || !wantNew) return;
    if (createStartedRef.current || createDraftM.isPending || createDraftM.isSuccess) return;
    createStartedRef.current = true;
    void createDraftM
      .mutateAsync()
      .then((payload) => {
        const id = payload?.order?.id;
        if (!id) return;
        qc.setQueryData([...queryKeys.interviewDraft, id], payload);
        void navigate({
          to: "/interviews/new",
          search: { order_id: id },
          replace: true,
        });
      })
      .catch(() => {
        createStartedRef.current = false;
      });
  }, [createDraftM, createDraftM.isPending, createDraftM.isSuccess, draftOrderId, navigate, qc, wantNew]);

  const orderStatus = String(order?.status || "").toLowerCase();
  const campaignReadOnly = isInterviewCampaignReadOnly(orderStatus);
  const shouldPollRecipients = ["running", "scheduled", "paused"].includes(orderStatus);
  const lastInviteDispatch = config.last_invite_dispatch as
    | { ok?: boolean; whatsapp_sent?: number; email_sent?: number; errors?: string[] }
    | undefined;
  const bookingInvitesSent =
    Boolean(config.booking_invites_sent_at) && (lastInviteDispatch == null || lastInviteDispatch.ok !== false);

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
    setScript(String(config.approved_script || config.generated_script_draft || ""));
    const savedDuration = config.expected_duration_minutes;
    setExpectedDurationMinutes(
      savedDuration != null && !Number.isNaN(Number(savedDuration))
        ? Math.max(3, Math.min(45, Number(savedDuration)))
        : undefined,
    );
    setScriptApproved(Boolean(config.script_approved));
    setAgentId(String(config.agent_id || ""));
    const savedDelivery = String(config.delivery || "ai_call");
    setDelivery(savedDelivery === "zoom" && !zoomInterviewEnabled ? "ai_call" : savedDelivery);
    setCollectionStart(toLocalInput(String(config.cv_collection_start_at || config.cv_email_start_at || "")));
    setCollectionEnd(toLocalInput(String(config.cv_collection_end_at || config.cv_email_end_at || "")));
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
    if (config.ats_manual_run_at) {
      setAtsRunAt(String(config.ats_manual_run_at).slice(11, 16) || "done");
    } else if (config.ats_last_charge_at && !config.ats_manual_run_at) {
      setAtsRunAt(null);
    }
    if (config.ats_skipped === true) {
      setAtsSkipped(true);
    }
  }, [order, orderHydrationKey, config, zoomInterviewEnabled]);

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
    if (!agentId && agents.length) {
      const def = pickDefaultInterviewAgent(agents);
      if (def) setAgentId(def.id);
    }
  }, [agents, agentId]);

  const candidates = React.useMemo<CandidateRow[]>(() => {
    const rows = draftQ.data?.recipients || [];
    return rows
      .filter((r) => Boolean(r.id))
      .map((r) => ({
        id: String(r.id),
        name: String(r.name || "Candidate"),
        phone: String(r.phone || ""),
        email: String(r.email || ""),
        source: String(r.intake_source || r.source || "Upload"),
        cvFilename: r.cv_filename ? String(r.cv_filename) : null,
        ats: r.ats_score != null ? Number(r.ats_score) : null,
        atsStatus: String(r.ats_status || ""),
        status: String(r.status || ""),
        activityStatus: String(r.activity_status || ""),
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
      candidates.some((c) => {
        const status = String(c.atsStatus || "").toLowerCase();
        return status === "pending" || status === "analyzing";
      }),
    [candidates, runAtsM.isPending],
  );

  React.useEffect(() => {
    if (!orderId || !atsInProgress) return;
    const timer = window.setInterval(() => {
      void qc.invalidateQueries({ queryKey: queryKeys.interviewDraft });
    }, 2500);
    return () => window.clearInterval(timer);
  }, [orderId, atsInProgress, qc]);

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
    void qc.invalidateQueries({ queryKey: queryKeys.interviewDraft });
    if (orderId) void qc.invalidateQueries({ queryKey: queryKeys.orderRecipients(orderId) });
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
      setCollectionEnd(toLocalInput(closedAt));
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
      ? String(config.cv_collection_start_at || config.cv_email_start_at || toIsoFromLocal(collectionStart) || "")
      : toIsoFromLocal(collectionStart);
    const collectionEndIso = closedEarlyAt
      ? String(config.cv_collection_end_at || config.cv_email_end_at || closedEarlyAt)
      : toIsoFromLocal(collectionEnd);
    const scriptTrim = script.trim();
    const approvedFromConfig = String(config.approved_script || "").trim();
    const configSaysApproved = Boolean(config.script_approved) && approvedFromConfig === scriptTrim;
    const persistScriptApproved =
      extraConfig?.script_approved === true ||
      scriptApproved ||
      configSaysApproved;
    const approvedScriptToSave = persistScriptApproved
      ? String(extraConfig?.approved_script || (scriptApproved ? script : approvedFromConfig || script)).trim()
      : String(config.approved_script || "").trim();
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
      agent_id: agentId,
      delivery,
      cv_email_enabled: cvEmailAllowed && cvEmailEnabled,
      cv_collection_start_at: collectionStartIso || null,
      cv_collection_end_at: collectionEndIso || null,
      cv_email_start_at: collectionStartIso || null,
      cv_email_end_at: collectionEndIso || null,
      calling_window_start_at: toIsoFromLocal(callingStart),
      calling_window_end_at: toIsoFromLocal(callingEnd),
      generated_script_draft: script,
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

  const onSaveDraft = async (silent?: boolean, extraConfig?: Record<string, unknown>) => {
    if (!orderId) return;
    if (campaignReadOnly) {
      if (!silent) toast.message(interviewCampaignReadOnlyLabel(orderStatus));
      return;
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

  const onGenerateScript = async () => {
    if (!criteria.trim()) {
      toast.error("Add screening criteria before generating the AI script");
      return;
    }
    if (!position.trim() && !role.trim()) {
      toast.error("Enter the position and role before generating");
      return;
    }
    if (!agentId) {
      toast.error("Select an AI voice agent");
      return;
    }
    try {
      const res = await generateM.mutateAsync({
        role: role || position,
        position,
        criteria,
        delivery,
        agent_id: agentId,
        client_context: { agent_id: agentId },
      });
      const materialised = scriptFromGenerate(res);
      if (!materialised.script_text) {
        toast.error("AI did not return a script — try again");
        return;
      }
      setScript(materialised.script_text);
      setExpectedDurationMinutes(materialised.expected_duration_minutes);
      setScriptApproved(false);
      await saveDraftM.mutateAsync(
        buildSaveBody({
          generated_script_draft: materialised.script_text,
          system_prompt: materialised.system_prompt,
          expected_duration_minutes: materialised.expected_duration_minutes,
          script_approved: false,
        }),
      );
      const mins = materialised.expected_duration_minutes;
      toast.success(mins ? `AI script ready — est. ~${mins} min per call` : "AI script ready — review and approve when happy");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not generate script");
    }
  };

  const onApproveScript = async () => {
    if (!script.trim()) {
      toast.error("Generate or paste a script before approving");
      return;
    }
    if (!orderId) return;
    try {
      setScriptApproved(true);
      await onSaveDraft(true, {
        approved_script: script,
        script_approved: true,
      });
      toast.success("Script approved");
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
    try {
      await runAtsM.mutateAsync({ confirm_charge: true, force: atsForce });
      setAtsPromptOpen(false);
      setAtsSkipped(false);
      setAtsRunAt(new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }));
      refreshDraft();
      toast.success("ATS scoring in progress — scores will update automatically");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "ATS run failed");
    }
  };

  const onRunAtsClick = () => {
    if (!script.trim()) {
      toast.error("Generate the AI script in Step 2 before running ATS");
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
  const cvPhase = cvCollectionPhase(cvEmailActive, collectionStart, collectionEnd, config);
  const cvReadyForScreening = isCvCollectionComplete(cvEmailActive, collectionEnd, config);
  const cvCollectionClosedEarly = Boolean(config.cv_collection_closed_early_at);
  const cvCollectionClosed = cvEmailActive && (cvPhase === "ready" || cvCollectionClosedEarly);
  const paymentApproved = String(order?.payment_status || "").toLowerCase() === "approved";
  const inviteDispatchFailed = paymentApproved && lastInviteDispatch?.ok === false;
  const canResendBookingInvites =
    !campaignReadOnly && candidates.some((c) => !isBookingResendBlocked(c.status, c.activityStatus));
  const unscoredCount = React.useMemo(
    () =>
      candidates.filter((c) => {
        const status = String(c.atsStatus || "").toLowerCase();
        if (status === "complete" && c.ats != null) return false;
        if (status === "pending" || status === "analyzing") return false;
        return true;
      }).length,
    [candidates],
  );
  const allCandidatesScored =
    candidates.length > 0 && candidates.every((c) => c.ats != null || Boolean(c.atsStatus));
  const atsGatePassed =
    cvEmailActive
      ? candidates.length === 0 ||
        allCandidatesScored ||
        atsSkipped ||
        Boolean(config.ats_skipped) ||
        Boolean(atsRunAt) ||
        Boolean(config.ats_manual_run_at) ||
        Boolean(config.ats_last_charge_at)
      : candidates.length > 0 &&
        (atsSkipped ||
          Boolean(config.ats_skipped) ||
          Boolean(atsRunAt) ||
          Boolean(config.ats_manual_run_at) ||
          Boolean(config.ats_last_charge_at) ||
          allCandidatesScored);
  const setupErrors = collectInterviewSetupErrors({
    position,
    role,
    criteria,
    script,
    scriptIsApproved,
    callingStart,
    callingEnd,
    cvEmailActive,
    collectionStart,
    collectionEnd,
  });
  const launchErrors = collectInterviewLaunchErrors({
    cvEmailActive,
    cvReadyForScreening,
    candidateCount: candidates.length,
    referenceId,
    atsGatePassed,
  });
  const missingPosition = !position.trim() && !role.trim();
  const missingCriteria = !criteria.trim();
  const missingScript = !script.trim();
  const missingScriptApproval = !scriptIsApproved && Boolean(script.trim());
  const missingCallingWindow = !callingStart || !callingEnd;
  const missingCollectionWindow = cvEmailActive && (!collectionStart || !collectionEnd);

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
        setQuoteError("Quote returned empty — set calling window and save draft, then retry");
      }
    } catch (e) {
      setQuoteError(e instanceof Error ? e.message : "Could not load quote");
    }
  };

  const onPayLaunch = async () => {
    if (!orderId) {
      toast.error("Save your draft before paying");
      return;
    }
    if (launchErrors.length > 0) {
      toast.error(launchErrors.length === 1 ? launchErrors[0] : launchErrors.join(" · "));
      return;
    }
    if (!gcReady) {
      toast.error("GoCardless checkout is not configured");
      return;
    }
    setPayBusy(true);
    try {
      await onSaveDraft(true);
      await startGoCardlessOrderPayment(orderId);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not start GoCardless checkout");
      setPayBusy(false);
    }
  };

  const launchStatusRef = React.useRef<HTMLDivElement | null>(null);

  const scrollToLaunchStatus = () => {
    window.setTimeout(() => {
      launchStatusRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 120);
  };

  const onLaunchFromPackage = async () => {
    if (!orderId) return;
    if (launchErrors.length > 0) {
      toast.error(launchErrors.length === 1 ? launchErrors[0] : launchErrors.join(" · "));
      return;
    }
    setPayBusy(true);
    try {
      await onSaveDraft(true);
      const result = await launchM.mutateAsync();
      setPreview(false);
      notifyInterviewLaunch(result);
      refreshDraft();
      scrollToLaunchStatus();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not launch campaign");
    } finally {
      setPayBusy(false);
    }
  };

  const previewData: InterviewPreviewData = {
    position,
    role,
    criteria,
    agentName: selectedAgent?.voice_label || selectedAgent?.name || "—",
    script,
    candidateCount: candidates.length,
    referenceId,
    cvEmailEnabled: cvEmailAllowed && cvEmailEnabled,
    cvCollectionComplete: cvReadyForScreening,
    careersInbox: CAREERS_INBOX,
    collectionStart: collectionStart || "—",
    collectionEnd: collectionEnd || "—",
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
    if (setupErrors.length > 0) {
      toast.error(
        setupErrors.length === 1
          ? setupErrors[0]
          : `Complete setup first:\n${setupErrors.map((e) => `• ${e}`).join("\n")}`,
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
        <PageHeader eyebrow="Interviews" title="Create new interview" description="Set up an AI phone screening campaign in three steps." />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (draftQ.isError) {
    return (
      <div className="flex w-full flex-col gap-6">
        <PageHeader eyebrow="Interviews" title="Create new interview" description="Could not load interview draft." />
        <Card>
          <CardContent className="py-8 text-center text-sm text-destructive">
            {draftQ.error instanceof Error ? draftQ.error.message : "Failed to load interview draft"}
            <div className="mt-4">
              <Button onClick={() => void draftQ.refetch()}>Try again</Button>
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
    if (createDraftM.isError) {
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
                    void createDraftM.mutateAsync().then((payload) => {
                      const id = payload?.order?.id;
                      if (!id) return;
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
    if (!wantNew) {
      return (
        <div className="flex w-full flex-col gap-6">
          <PageHeader eyebrow="Interviews" title="Create new interview" description="Start a fresh AI phone screening campaign." />
          <Card>
            <CardContent className="flex flex-col gap-4 p-6">
              <p className="text-sm text-muted-foreground">No draft in progress. Create a new interview when you are ready.</p>
              <Button asChild className="w-fit"><Link to="/interviews/new" search={{ new: true }}>Create new interview</Link></Button>
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
      <PageHeader eyebrow="Interviews" title="Create new interview" description="Set up an AI phone screening campaign in three steps." />

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

      {(setupErrors.length > 0 || launchErrors.length > 0) && !campaignReadOnly && (
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

      <Card>
        <CardHeader>
          <CardTitle>Step 1 · Collect candidates</CardTitle>
          <CardDescription>Reference, CV email window, and uploads.</CardDescription>
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
                  Candidates must put this reference in the email subject or body when sending a CV to{" "}
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
                  </span>
                  . Each CV is added automatically and ATS scored (charged per CV). Re-sending replaces the CV and runs ATS again.
                </p>
              ) : (
                <p className="text-[11px] text-muted-foreground">
                  Use this code to identify this interview task. Enable CV email collection below to receive CVs by email.
                </p>
              )}
            </div>
          ) : null}

          <div className="md:col-span-2">
          <ToggleRow
            title="CV email collection"
            desc={
              cvEmailAllowed
                ? `Receive CVs at ${CAREERS_INBOX} — include the job reference above. ATS runs automatically (charged per CV).`
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
              if (orderId) {
                void onSaveDraft(true, { cv_email_enabled: v }).catch(() => {
                  /* toast handled in onSaveDraft */
                });
              }
            }}
          />
          </div>
          {cvEmailActive && (
            <div className="md:col-span-2 rounded-lg border border-border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
              <div className="flex flex-wrap items-center gap-2">
                {cvCollectionClosed ? (
                  <span className="inline-flex items-center gap-1 font-medium text-success">
                    <Lock className="size-3.5" /> CV collection closed
                    {cvCollectionClosedEarly ? " (closed early)" : ""}
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
              {cvPhase === "before" && " — share the reference and careers email when the window opens."}
              {cvPhase === "open" && " — CVs arrive by email, appear in the table below, and are ATS scored automatically (charged per CV). Manual upload is optional."}
              {cvCollectionClosed && " — review ATS scores, remove weak candidates, then launch. No manual upload required."}
            </div>
          )}
          {cvEmailActive && (
            <div className="grid grid-cols-1 gap-2 md:col-span-2 sm:grid-cols-2">
              <Field label="Collection start" error={missingCollectionWindow && !collectionStart ? "Required when CV email is on" : undefined}>
                <Input type="datetime-local" value={collectionStart} onChange={(e) => setCollectionStart(e.target.value)} disabled={cvCollectionClosed} className={`w-full min-w-0 ${inputErrorClass(missingCollectionWindow && !collectionStart)}`} />
              </Field>
              <Field label="Collection end" error={missingCollectionWindow && !collectionEnd ? "Required when CV email is on" : undefined}>
                <Input type="datetime-local" value={collectionEnd} onChange={(e) => setCollectionEnd(e.target.value)} disabled={cvCollectionClosed} className={`w-full min-w-0 ${inputErrorClass(missingCollectionWindow && !collectionEnd)}`} />
              </Field>
            </div>
          )}

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
                  {runAtsM.isPending ? "Running ATS…" : atsRunAt ? "Re-run ATS" : "Run ATS"}
                </Button>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="outline" size="sm" className="h-7 gap-1.5 text-xs">
                      <ArrowUpDown className="size-3.5" /> Sort
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="w-48">
                    <DropdownMenuLabel className="text-xs">Sort by</DropdownMenuLabel>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem><ArrowDown className="size-3.5" /> ATS score (high → low)</DropdownMenuItem>
                    <DropdownMenuItem><ArrowUp className="size-3.5" /> ATS score (low → high)</DropdownMenuItem>
                    <DropdownMenuItem><ArrowDown className="size-3.5" /> Name (A → Z)</DropdownMenuItem>
                    <DropdownMenuItem><ArrowUp className="size-3.5" /> Name (Z → A)</DropdownMenuItem>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem>Source: CV email first</DropdownMenuItem>
                    <DropdownMenuItem>Source: Upload first</DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
            </div>
            <div className="table-scroll rounded-lg border border-border">
              <Table className="min-w-[720px]">
                <TableHeader><TableRow>
                  <TableHead className="w-10 pl-4">
                    <Checkbox
                      checked={allSelected ? true : someSelected ? "indeterminate" : false}
                      onCheckedChange={toggleAll}
                      aria-label="Select all"
                    />
                  </TableHead>
                  <SortHeader label="Name" sortKey="name" active={candSort.sortKey} dir={candSort.sortDir} onToggle={candSort.toggleSort} />
                  <SortHeader label="Phone" sortKey="phone" active={candSort.sortKey} dir={candSort.sortDir} onToggle={candSort.toggleSort} className="hidden sm:table-cell" />
                  <SortHeader label="Email" sortKey="email" active={candSort.sortKey} dir={candSort.sortDir} onToggle={candSort.toggleSort} className="hidden sm:table-cell" />
                  <TableHead className="sm:hidden">Contact</TableHead>
                  <SortHeader label="ATS score" sortKey="ats" active={candSort.sortKey} dir={candSort.sortDir} onToggle={candSort.toggleSort} />
                  <TableHead>Status</TableHead>
                  <SortHeader label="Source" sortKey="source" active={candSort.sortKey} dir={candSort.sortDir} onToggle={candSort.toggleSort} />
                  <TableHead className="pr-4 text-right">Actions</TableHead>
                </TableRow></TableHeader>
                <TableBody>
                  {candSort.sorted.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={8} className="py-8 text-center text-sm text-muted-foreground">
                        {cvEmailActive
                          ? `No CVs yet — applicants email ${CAREERS_INBOX} with your job reference. They appear here automatically.`
                          : "Upload candidates to get started."}
                      </TableCell>
                    </TableRow>
                  ) : candSort.sorted.map((r) => (
                    <TableRow key={r.id} data-state={selected.has(r.id) ? "selected" : undefined}>
                      <TableCell className="pl-4">
                        <Checkbox
                          checked={selected.has(r.id)}
                          onCheckedChange={() => toggleOne(r.id)}
                          aria-label={`Select ${r.name}`}
                        />
                      </TableCell>
                      <TableCell className="font-medium max-w-[120px] truncate sm:max-w-none">{r.name}</TableCell>
                      <TableCell className="hidden sm:table-cell">
                        <div className="space-y-1">
                          <div className={`text-xs tabular-nums ${r.phone && r.phoneCallAllowed === false ? "font-medium text-destructive" : ""}`}>
                            {r.phone || "—"}
                          </div>
                          {r.phone && r.phoneCallAllowed === false ? (
                            <div className="text-[11px] leading-snug text-destructive">
                              Can&apos;t call this number{r.phoneCallBlockReason ? `: ${r.phoneCallBlockReason}` : ""}.{" "}
                              <button type="button" className="underline" onClick={() => void onEditRecipientPhone(r.id, r.phone)}>
                                Change number
                              </button>
                            </div>
                          ) : null}
                        </div>
                      </TableCell>
                      <TableCell className="hidden text-xs sm:table-cell">{r.email || "—"}</TableCell>
                      <TableCell className="text-xs sm:hidden">
                        <div className="space-y-1 text-muted-foreground">
                          {r.phone ? (
                            <div className={r.phoneCallAllowed === false ? "truncate font-medium text-destructive" : "truncate"}>{r.phone}</div>
                          ) : null}
                          {r.phone && r.phoneCallAllowed === false ? (
                            <div className="text-[11px] leading-snug text-destructive">
                              Can&apos;t call this number.{" "}
                              <button type="button" className="underline" onClick={() => void onEditRecipientPhone(r.id, r.phone)}>
                                Change
                              </button>
                            </div>
                          ) : null}
                          {r.email ? <div className="truncate">{r.email}</div> : null}
                          <StatusBadge tone={activityStatusTone(r.activityStatus)} className="mt-1">
                            {activityStatusLabel(r.activityStatus)}
                          </StatusBadge>
                        </div>
                      </TableCell>
                      <TableCell><AtsScore score={r.ats} status={r.atsStatus} /></TableCell>
                      <TableCell className="text-xs">
                        <StatusBadge tone={activityStatusTone(r.activityStatus)}>
                          {activityStatusLabel(r.activityStatus)}
                        </StatusBadge>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">{r.source}</TableCell>
                      <TableCell className="pr-4">
                        <div className="flex justify-end gap-1">
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
                            className="size-8"
                            aria-label="Download CV"
                            onClick={() => void onDownloadCv(r.id, r.cvFilename)}
                          >
                            <FileDown className="size-4" />
                          </Button>
                          <Button
                            size="icon"
                            variant="ghost"
                            className="size-8 text-destructive hover:text-destructive"
                            aria-label="Delete"
                            disabled={candidatesLocked || deleteBusy}
                            title={candidatesLocked ? "Cannot remove after invites are sent or once live" : "Remove candidate"}
                            onClick={() => onDeleteRecipient(r.id, r.name)}
                          >
                            <Trash2 className="size-4" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </div>

          {cvEmailActive && !cvCollectionClosed && (
            <Button variant="outline" size="sm" className="md:col-span-2 w-fit gap-1.5" disabled={closeCvBusy} onClick={() => void onCloseCvCollection()}>
              {closeCvBusy ? (
                <>Checking email & closing…</>
              ) : (
                <>
                  <LockOpen className="size-3.5" /> Close CV collection early & continue
                </>
              )}
            </Button>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Step 2 · AI script</CardTitle>
          <CardDescription>Position, role, agent, screening criteria, and script approval.</CardDescription>
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
              <Select value={agentId || pickDefaultInterviewAgent(agents)?.id || ""} onValueChange={setAgentId}>
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
          {interviewDeliveryOptions.length > 1 ? (
            <Field label="Interview format">
              <Select value={delivery} onValueChange={setDelivery}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="ai_call">Phone call</SelectItem>
                  {zoomInterviewEnabled ? (
                    <SelectItem value="zoom">Zoom video meeting</SelectItem>
                  ) : null}
                </SelectContent>
              </Select>
            </Field>
          ) : null}
          <div className="md:col-span-2 space-y-1.5">
            <Label className={`text-xs ${missingCriteria ? "text-destructive" : ""}`}>Screening criteria</Label>
            <Textarea rows={4} value={criteria} onChange={(e) => setCriteria(e.target.value)} placeholder="Must hold GDC registration…" className={inputErrorClass(missingCriteria)} />
            {missingCriteria ? <p className="text-[11px] text-destructive">Add screening criteria before generating the script</p> : null}
          </div>
          <div className="md:col-span-2 flex flex-wrap gap-2">
            <Button variant="outline" className="gap-1.5" onClick={() => void onGenerateScript()} disabled={generateM.isPending}>
              <Wand2 className="size-4" /> {generateM.isPending ? "Generating…" : "Generate AI questions"}
            </Button>
            <Button
              variant="outline"
              className="gap-1.5"
              onClick={() => void onApproveScript()}
              disabled={scriptIsApproved || saveDraftM.isPending || patchOrderM.isPending}
            >
              {scriptIsApproved ? <Lock className="size-4" /> : <LockOpen className="size-4" />}
              {scriptIsApproved ? "Script approved" : "Approve script"}
            </Button>
            <Button variant="ghost" className="gap-1.5" onClick={() => void onGenerateScript()} disabled={generateM.isPending}><RotateCcw className="size-4" /> Regenerate</Button>
            <div className="ml-auto flex items-center gap-2">
              {expectedDurationMinutes ? (
                <span className="text-xs text-muted-foreground">Expected call time: ~{expectedDurationMinutes} min</span>
              ) : null}
              <StatusBadge tone={scriptIsApproved ? "approved-script" : "draft-script"} />
            </div>
          </div>
          <div className="md:col-span-2 space-y-1.5">
            <Label className={`text-xs ${missingScript || missingScriptApproval ? "text-destructive" : ""}`}>Interview questions</Label>
            <Textarea
              rows={8}
              value={extractQuestionsBlock(script)}
              onChange={(e) => {
                const nextQuestions = e.target.value;
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
              placeholder="Numbered questions only — opening disclosure and intro are added automatically…"
              className={inputErrorClass(missingScript || missingScriptApproval)}
            />
            <p className="text-[11px] text-muted-foreground">Opening disclosure and intro are not editable here — only interview questions.</p>
            {missingScript ? <p className="text-[11px] text-destructive">Generate or paste a script, then approve it</p> : null}
            {!missingScript && missingScriptApproval ? <p className="text-[11px] text-destructive">Click Approve script when you are happy with it</p> : null}
          </div>
          <div className="grid gap-2 sm:grid-cols-2 md:col-span-2">
            <Field label="Calling start" error={missingCallingWindow && !callingStart ? "Set when AI calls can start" : undefined}>
              <Input type="datetime-local" value={callingStart} onChange={(e) => setCallingStart(e.target.value)} className={inputErrorClass(missingCallingWindow && !callingStart)} />
            </Field>
            <Field label="Calling end" error={missingCallingWindow && !callingEnd ? "Set when AI calls must end" : undefined}>
              <Input type="datetime-local" value={callingEnd} onChange={(e) => setCallingEnd(e.target.value)} className={inputErrorClass(missingCallingWindow && !callingEnd)} />
            </Field>
          </div>
        </CardContent>
      </Card>

      {!campaignReadOnly ? (
      <Card ref={launchStatusRef}>
        <CardHeader>
          <CardTitle>Step 3 · ATS, preview & launch</CardTitle>
          <CardDescription>
            {cvEmailActive
              ? "When CV collection ends, review email applicants, approve the preview, then launch — booking invites go out by WhatsApp and email."
              : `Run ATS on uploaded CVs, approve the preview, then launch — ${hasPackageSub ? "included in your package" : "pay per campaign"}, then WhatsApp booking invites go to candidates.`}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <LaunchStatus
              label="ATS scoring"
              done={atsGatePassed}
              pending={runAtsM.isPending}
              detail={
                atsSkipped || config.ats_skipped
                  ? "Skipped"
                  : allCandidatesScored && cvEmailActive
                    ? "Scored from email"
                    : atsRunAt
                      ? `Run ${atsRunAt}`
                      : unscoredCount > 0
                        ? `${unscoredCount} unscored`
                        : cvEmailActive && candidates.length === 0
                          ? "Waiting for CVs"
                          : "Not run"
              }
            />
            <LaunchStatus label="Script approved" done={scriptIsApproved} detail={scriptIsApproved ? "Ready" : "Approve in Step 2"} />
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
          <ol className="list-decimal space-y-1 pl-5 text-sm text-muted-foreground">
            <li>
              <strong className="text-foreground">Run ATS</strong> —{" "}
              {cvEmailActive
                ? "email CVs are scored automatically; run ATS only if you uploaded files manually."
                : "scores each CV in the table above (or skip when prompted)."}
            </li>
            <li><strong className="text-foreground">Preview &amp; approve</strong> — confirm script and preview, then <strong className="text-foreground">{hasPackageSub ? "Launch" : "Pay & launch"}</strong>.</li>
            <li><strong className="text-foreground">Send booking invites</strong> — {hasPackageSub ? "sent when you launch" : "appears after payment"}; WhatsApp links go to each candidate.</li>
          </ol>
          {(setupErrors.length > 0 || launchErrors.length > 0) && (
            <div className="space-y-2 rounded-lg border border-amber-500/30 bg-amber-500/5 px-3 py-3 text-sm">
              {setupErrors.length > 0 ? (
                <div>
                  <p className="font-medium text-foreground">Complete before preview:</p>
                  <ul className="mt-1 list-disc space-y-0.5 pl-5 text-xs text-muted-foreground">
                    {setupErrors.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
              {launchErrors.length > 0 ? (
                <div>
                  <p className="font-medium text-foreground">
                    {setupErrors.length > 0 ? "Also before launch:" : cvEmailActive ? "You can preview now — finish before launch:" : "Before launch:"}
                  </p>
                  <ul className="mt-1 list-disc space-y-0.5 pl-5 text-xs text-muted-foreground">
                    {launchErrors.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          )}
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" className="gap-1.5" disabled={runAtsM.isPending || candidates.length === 0 || campaignReadOnly} onClick={onRunAtsClick}>
              <Sparkles className="size-4" /> {runAtsM.isPending ? "Running ATS…" : "Run ATS"}
            </Button>
            <Button className="gap-1.5" disabled={campaignReadOnly} onClick={onAttemptPreview}>
              <Eye className="size-4" /> Preview &amp; approve
            </Button>
          </div>
        </CardContent>
      </Card>
      ) : null}

      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:flex-wrap sm:items-center sm:justify-end">
        {paymentApproved && (!bookingInvitesSent || inviteDispatchFailed) && !campaignReadOnly ? (
          <Button
            variant="secondary"
            className="gap-1.5"
            disabled={launchM.isPending || !callingStart || !callingEnd}
            onClick={() => {
              void (async () => {
                try {
                  const result = await launchM.mutateAsync();
                  notifyInterviewLaunch(result);
                  refreshDraft();
                } catch (e) {
                  toast.error(e instanceof Error ? e.message : "Could not launch campaign");
                }
              })();
            }}
          >
            <Send className="size-4" /> {launchM.isPending ? "Launching…" : "Launch — send booking invites"}
          </Button>
        ) : null}
        {paymentApproved && bookingInvitesSent && !campaignReadOnly ? (
          <Button
            variant="outline"
            className="gap-1.5"
            disabled={resendInvitesM.isPending || !canResendBookingInvites}
            title={
              campaignReadOnly
                ? "Campaign stopped or finished — resend disabled"
                : canResendBookingInvites
                  ? "Resend booking WhatsApp to eligible candidates"
                  : "All candidates have completed their interview — booking is locked"
            }
            onClick={() => {
              void (async () => {
                try {
                  const result = await resendInvitesM.mutateAsync(true);
                  const wa = Number(result?.whatsapp_sent || 0);
                  const skipped = Number(result?.skipped_locked || 0);
                  if (wa > 0) {
                    toast.success(`Resent booking WhatsApp to ${wa} candidate(s).`);
                  } else if (skipped > 0) {
                    toast.message("No invites sent — all candidates have already completed their interview.");
                  } else {
                    toast.success("Booking invites queued.");
                  }
                } catch (e) {
                  toast.error(e instanceof Error ? e.message : "Could not resend invites");
                }
              })();
            }}
          >
            <Send className="size-4" /> Resend booking WhatsApp
          </Button>
        ) : null}
        <Button variant="outline" className="gap-1.5" onClick={() => void onSaveDraft()} disabled={saveDraftM.isPending || patchOrderM.isPending || campaignReadOnly}>
          <Save className="size-4" /> {saveDraftM.isPending ? "Saving…" : "Save draft"}
        </Button>
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
        onApproveScript={onApproveScript}
        onRefreshQuote={() => void refreshQuote()}
        onPayLaunch={() => void onPayLaunch()}
        onLaunch={() => void onLaunchFromPackage()}
        quoteLoading={quoteM.isPending}
        quoteError={quoteError}
        payBusy={payBusy}
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
