import { createFileRoute, useNavigate } from "@tanstack/react-router";
import * as React from "react";
import { Copy, Upload, Download, Wand2, Lock, LockOpen, RotateCcw, Trash2, Save, Eye, FileDown, ArrowUpDown, ArrowUp, ArrowDown, CheckCircle2 } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { Checkbox } from "@/components/ui/checkbox";
import { SortHeader, useTableSort } from "@/components/sortable-table";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, DropdownMenuLabel, DropdownMenuSeparator } from "@/components/ui/dropdown-menu";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { AtsPreviewGateModal, InterviewPreviewQuoteModal, PackageUpgradeModal, type InterviewPreviewData } from "@/components/modals";
import { AtsScore } from "@/components/ats-score";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiFetch, apiUploadFiles, downloadAuthenticatedFile } from "@/lib/api";
import { gocardlessAvailable, startGoCardlessOrderPayment } from "@/lib/billing/gocardless";
import { formatQuoteDisplay } from "@/lib/billing/market";
import { useSession } from "@/lib/session";
import {
  queryKeys,
  useGenerateInterviewScript,
  useInterviewAgents,
  useInterviewDraft,
  useOrderQuote,
  usePatchServiceOrder,
  useRunInterviewAts,
  useSaveInterviewDraft,
} from "@/lib/queries";

export const Route = createFileRoute("/_app/interviews/new")({
  head: () => ({ meta: [{ title: "Create interview — VoxBulk" }] }),
  validateSearch: (search: Record<string, unknown>) => ({
    new: search.new === "1" || search.new === 1 || search.new === true,
  }),
  component: CreateInterview,
});

type CandidateRow = {
  id: string;
  name: string;
  phone: string;
  email: string;
  source: string;
  ats: number | null;
  atsStatus?: string | null;
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

function CreateInterview() {
  const { new: forceNew } = Route.useSearch();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { session } = useSession();
  const gcReady = gocardlessAvailable(session?.subscription as Record<string, unknown> | null);
  const draftQ = useInterviewDraft({ forceNew });
  const agentsQ = useInterviewAgents();
  const saveDraftM = useSaveInterviewDraft();
  const patchOrderM = usePatchServiceOrder();
  const generateM = useGenerateInterviewScript();

  const order = draftQ.data?.order ?? null;
  const orderId = order?.id ?? "";
  const runAtsM = useRunInterviewAts(orderId || null);
  const quoteM = useOrderQuote(orderId || null);
  const [waPreviewBody, setWaPreviewBody] = React.useState<string | undefined>();
  const [waPreviewTemplateName, setWaPreviewTemplateName] = React.useState<string | undefined>();
  const [waPreviewButtons, setWaPreviewButtons] = React.useState<{ label: string; type?: string }[] | undefined>();
  const [waPreviewConfirmationBody, setWaPreviewConfirmationBody] = React.useState<string | undefined>();
  const [waPreviewConfirmationButtons, setWaPreviewConfirmationButtons] = React.useState<{ label: string; type?: string }[] | undefined>();
  const [waPreviewConfirmationTemplateName, setWaPreviewConfirmationTemplateName] = React.useState<string | undefined>();
  const [waPreviewSyncLabel, setWaPreviewSyncLabel] = React.useState<string | undefined>();
  const [waPreviewLoading, setWaPreviewLoading] = React.useState(false);
  const config = (order?.config || {}) as Record<string, unknown>;
  const referenceId = order?.reference_id || "";
  const billing = (draftQ.data as { billing_context?: Record<string, unknown> })?.billing_context || {};
  const cvEmailAllowed = Boolean(billing.cv_email_allowed);

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
  const [payBusy, setPayBusy] = React.useState(false);

  const [cvEmailEnabled, setCvEmailEnabled] = React.useState(false);
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

  const agents = agentsQ.data || [];
  const selectedAgent = agents.find((a) => a.id === agentId) || agents.find((a) => a.is_default_for_org) || agents[0];

  React.useEffect(() => {
    if (forceNew && draftQ.isSuccess && draftQ.data?.order?.id) {
      void navigate({ to: "/interviews/new", search: { new: false }, replace: true });
    }
  }, [forceNew, draftQ.isSuccess, draftQ.data?.order?.id, navigate]);

  React.useEffect(() => {
    if (!order) return;
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
    setDelivery(String(config.delivery || "ai_call"));
    setCollectionStart(toLocalInput(String(config.cv_collection_start_at || config.cv_email_start_at || "")));
    setCollectionEnd(toLocalInput(String(config.cv_collection_end_at || config.cv_email_end_at || "")));
    setCallingStart(toLocalInput(order.scheduled_start_at));
    setCallingEnd(toLocalInput(order.scheduled_end_at));
    setCvEmailEnabled(config.cv_email_enabled === true);
    if (config.ats_last_charge_at) {
      setAtsRunAt(String(config.ats_last_charge_at).slice(11, 16) || "done");
    }
    if (config.ats_skipped === true) {
      setAtsSkipped(true);
    }
  }, [order, config, order?.scheduled_start_at, order?.scheduled_end_at, cvEmailAllowed]);

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
      }>(`/service-orders/${encodeURIComponent(orderId)}/interview-booking/preview-template?sync=true`);
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
      const def = agents.find((a) => a.is_default_for_org) || agents[0];
      if (def) setAgentId(def.id);
    }
  }, [agents, agentId]);

  const candidates = React.useMemo<CandidateRow[]>(() => {
    const rows = draftQ.data?.recipients || [];
    return rows.map((r) => ({
      id: String(r.id || r.phone || r.name),
      name: String(r.name || "Candidate"),
      phone: String(r.phone || ""),
      email: String(r.email || ""),
      source: String(r.intake_source || r.source || "Upload"),
      ats: r.ats_score != null ? Number(r.ats_score) : null,
      atsStatus: String(r.ats_status || ""),
    }));
  }, [draftQ.data?.recipients]);

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

  const onDeleteRecipient = async (recipientId: string) => {
    if (!orderId) return;
    if (!window.confirm("Remove this candidate from the list?")) return;
    try {
      await apiFetch(`/service-orders/${encodeURIComponent(orderId)}/recipients/${encodeURIComponent(recipientId)}`, {
        method: "DELETE",
      });
      setSelected((prev) => {
        const next = new Set(prev);
        next.delete(recipientId);
        return next;
      });
      refreshDraft();
      toast.success("Candidate removed");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not remove candidate");
    }
  };

  const onDeleteSelected = async () => {
    if (!orderId || selected.size === 0) return;
    if (!window.confirm(`Remove ${selected.size} selected candidate(s)?`)) return;
    try {
      for (const id of selected) {
        await apiFetch(`/service-orders/${encodeURIComponent(orderId)}/recipients/${encodeURIComponent(id)}`, {
          method: "DELETE",
        });
      }
      setSelected(new Set());
      refreshDraft();
      toast.success("Selected candidates removed");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not remove candidates");
    }
  };

  const onDownloadCv = async (recipientId: string, name: string) => {
    if (!orderId) return;
    try {
      const safe = name.replace(/[^\w.-]+/g, "-").replace(/^-+|-+$/g, "") || "candidate";
      await downloadAuthenticatedFile(
        `/service-orders/${encodeURIComponent(orderId)}/recipients/${encodeURIComponent(recipientId)}/cv`,
        `${safe}-cv.pdf`,
      );
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "CV download failed");
    }
  };

  const onCloseCvCollection = async () => {
    if (!orderId) return;
    try {
      await apiFetch(`/service-orders/${encodeURIComponent(orderId)}/interview/cv-collection/close-early`, {
        method: "POST",
        body: "{}",
      });
      toast.success("CV collection closed");
      refreshDraft();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not close CV collection");
    }
  };

  const buildSaveBody = (extraConfig?: Record<string, unknown>) => ({
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
      cv_collection_start_at: toIsoFromLocal(collectionStart),
      cv_collection_end_at: toIsoFromLocal(collectionEnd),
      cv_email_start_at: toIsoFromLocal(collectionStart),
      cv_email_end_at: toIsoFromLocal(collectionEnd),
      generated_script_draft: script,
      expected_duration_minutes: expectedDurationMinutes,
      approved_script: scriptApproved ? script : config.approved_script || "",
      script_approved: scriptApproved,
      ...extraConfig,
    },
    scheduled_start_at: toIsoFromLocal(callingStart),
    scheduled_end_at: toIsoFromLocal(callingEnd),
  });

  const onSaveDraft = async (silent?: boolean, extraConfig?: Record<string, unknown>) => {
    if (!orderId) return;
    try {
      const body = buildSaveBody(extraConfig);
      await saveDraftM.mutateAsync(body);
      await patchOrderM.mutateAsync({ orderId, body });
      if (!silent) toast.success("Draft saved");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not save draft");
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
      setAtsRunAt(new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }));
      refreshDraft();
      toast.success("ATS scoring started");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "ATS run failed");
    }
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
      toast.success("Files uploaded — run ATS after generating your AI script");
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

  const copyReference = async () => {
    if (!referenceId) return;
    try {
      await navigator.clipboard.writeText(referenceId);
      toast.success("Reference copied");
    } catch {
      toast.error("Could not copy reference");
    }
  };

  const refreshQuote = async () => {
    if (!orderId || candidates.length === 0) return;
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
    } catch {
      /* quote optional until ready */
    }
  };

  const onPayLaunch = async () => {
    if (!orderId) {
      toast.error("Save your draft before paying");
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

  const previewData: InterviewPreviewData = {
    position,
    role,
    criteria,
    agentName: selectedAgent?.voice_label || selectedAgent?.name || "—",
    script,
    candidateCount: candidates.length,
    referenceId,
    cvEmailEnabled: cvEmailAllowed && cvEmailEnabled,
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

  const cvEmailActive = cvEmailAllowed && cvEmailEnabled;
  const cvPhase = cvCollectionPhase(cvEmailActive, collectionStart, collectionEnd, config);
  const cvReadyForScreening = isCvCollectionComplete(cvEmailActive, collectionEnd, config);
  const unscoredCount = candidates.filter((c) => c.ats == null && !c.atsStatus).length;
  const atsGatePassed =
    candidates.length > 0 &&
    (atsSkipped ||
      Boolean(config.ats_skipped) ||
      Boolean(atsRunAt) ||
      Boolean(config.ats_last_charge_at) ||
      candidates.some((c) => c.ats != null || Boolean(c.atsStatus)));

  const onAttemptPreview = () => {
    if (!script.trim()) {
      toast.error("Generate the AI script before preview");
      return;
    }
    if (!scriptIsApproved) {
      toast.error("Approve your script before preview & launch");
      return;
    }
    if (candidates.length === 0) {
      toast.error("Upload at least one candidate first");
      return;
    }
    if (cvEmailActive && !cvReadyForScreening) {
      toast.error("CV email collection is still open — wait until the window ends or close collection early, then run AI screening.");
      return;
    }
    if (!atsGatePassed) {
      setAtsQuote(null);
      setAtsQuoteError(null);
      setAtsPromptOpen(true);
      void loadAtsQuote(!!atsRunAt);
      return;
    }
    setPreview(true);
  };

  const onContinueWithoutAtsHandler = () => {
    void onContinueWithoutAts();
  };

  const candSort = useTableSort(candidates, "ats", "desc");

  if (draftQ.isLoading) {
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

      <Card>
        <CardHeader>
          <CardTitle>Step 1 · Collect candidates</CardTitle>
          <CardDescription>Reference, CV email window, and uploads.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-5 md:grid-cols-2">
          {cvEmailEnabled && (
            <div className="space-y-1.5 md:col-span-2">
              <Label className="text-xs">Job reference</Label>
              <div className="flex flex-col gap-2 sm:flex-row">
                <Input value={referenceId || "—"} readOnly className="font-mono" />
                <Button variant="outline" className="gap-1.5 sm:w-auto" onClick={() => void copyReference()} disabled={!referenceId}>
                  <Copy className="size-4" /> Copy reference
                </Button>
              </div>
              <p className="text-[11px] text-muted-foreground">
                Ask candidates to include the job code in the email subject line and send their CVs to{" "}
                <span className="font-medium text-foreground">careers@voxbulk.com</span>. This ensures their applications are automatically matched and updated under the correct listed job.
              </p>
            </div>
          )}

          <ToggleRow
            title="CV email collection"
            desc="Auto-collect candidates from careers@voxbulk.com inbox."
            checked={cvEmailEnabled}
            onCheckedChange={(v) => {
              if (v && !cvEmailAllowed) {
                setUpgradeOpen(true);
                return;
              }
              setCvEmailEnabled(v);
            }}
          />
          {cvEmailActive && (
            <div className="md:col-span-2 rounded-lg border border-border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
              {cvPhase === "before" && "CV collection has not started yet. Candidates can apply once the window opens."}
              {cvPhase === "open" && "Collection is live — CVs arrive automatically. When the window ends (or you close early), approve your script, run ATS, then launch AI screening."}
              {cvPhase === "ready" && "CV collection finished — you can run ATS, remove weak candidates, and open Preview & approve to launch calls."}
            </div>
          )}
          <div className="grid grid-cols-2 gap-2">
            <Field label="Collection start"><Input type="datetime-local" value={collectionStart} onChange={(e) => setCollectionStart(e.target.value)} /></Field>
            <Field label="Collection end"><Input type="datetime-local" value={collectionEnd} onChange={(e) => setCollectionEnd(e.target.value)} /></Field>
          </div>

          <div className="md:col-span-2 group relative overflow-hidden rounded-xl border-2 border-dashed border-border bg-gradient-to-br from-background/60 via-background/40 to-accent/20 px-6 py-10 transition-colors hover:border-primary/40">
            <BackdropIllustration />
            <input ref={fileRef} type="file" multiple className="hidden" onChange={(e) => void onUpload(e.target.files)} />
            <div className="relative flex flex-col items-center gap-2 text-center">
              <div className="rounded-full bg-primary/10 p-3 ring-1 ring-primary/20 transition-transform group-hover:scale-110">
                <Upload className="size-6 text-primary" />
              </div>
              <p className="text-sm font-medium">Drop CSV, Excel, PDF, DOCX, or ZIP</p>
              <p className="text-xs text-muted-foreground">Or click to upload</p>
              <div className="mt-2 flex flex-col gap-2 sm:flex-row">
                <Button size="sm" onClick={() => fileRef.current?.click()} disabled={uploading || !orderId}>
                  {uploading ? "Uploading…" : "Choose files"}
                </Button>
                <Button size="sm" variant="outline" className="gap-1.5" onClick={() => void onDownloadTemplate()}>
                  <Download className="size-3.5" /> Download template
                </Button>
              </div>
            </div>
          </div>

          <div className="md:col-span-2">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <p className="text-xs text-muted-foreground">Candidates uploaded · {candidates.length}</p>
                {selected.size > 0 && (
                  <span className="animate-fade-in inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary">
                    {selected.size} selected
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2">
                {selected.size > 0 && (
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-7 gap-1.5 text-xs text-destructive hover:text-destructive animate-fade-in"
                    onClick={() => void onDeleteSelected()}
                  >
                    <Trash2 className="size-3.5" /> Delete selected
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
            <div className="overflow-x-auto rounded-lg border border-border">
              <Table className="min-w-[820px]">
                <TableHeader><TableRow>
                  <TableHead className="w-10 pl-4">
                    <Checkbox
                      checked={allSelected ? true : someSelected ? "indeterminate" : false}
                      onCheckedChange={toggleAll}
                      aria-label="Select all"
                    />
                  </TableHead>
                  <SortHeader label="Name" sortKey="name" active={candSort.sortKey} dir={candSort.sortDir} onToggle={candSort.toggleSort} />
                  <SortHeader label="Phone" sortKey="phone" active={candSort.sortKey} dir={candSort.sortDir} onToggle={candSort.toggleSort} />
                  <SortHeader label="Email" sortKey="email" active={candSort.sortKey} dir={candSort.sortDir} onToggle={candSort.toggleSort} />
                  <SortHeader label="ATS score" sortKey="ats" active={candSort.sortKey} dir={candSort.sortDir} onToggle={candSort.toggleSort} />
                  <SortHeader label="Source" sortKey="source" active={candSort.sortKey} dir={candSort.sortDir} onToggle={candSort.toggleSort} />
                  <TableHead className="pr-4 text-right">Actions</TableHead>
                </TableRow></TableHeader>
                <TableBody>
                  {candSort.sorted.length === 0 ? (
                    <TableRow><TableCell colSpan={7} className="py-8 text-center text-sm text-muted-foreground">Upload candidates to get started.</TableCell></TableRow>
                  ) : candSort.sorted.map((r) => (
                    <TableRow key={r.id} data-state={selected.has(r.id) ? "selected" : undefined}>
                      <TableCell className="pl-4">
                        <Checkbox
                          checked={selected.has(r.id)}
                          onCheckedChange={() => toggleOne(r.id)}
                          aria-label={`Select ${r.name}`}
                        />
                      </TableCell>
                      <TableCell className="font-medium">{r.name}</TableCell>
                      <TableCell><Input defaultValue={r.phone} className="h-8 w-44 font-mono text-xs" readOnly /></TableCell>
                      <TableCell><Input defaultValue={r.email} className="h-8 w-56 text-xs" readOnly /></TableCell>
                      <TableCell><AtsScore score={r.ats} status={r.atsStatus} /></TableCell>
                      <TableCell className="text-xs text-muted-foreground">{r.source}</TableCell>
                      <TableCell className="pr-4">
                        <div className="flex justify-end gap-1">
                          <Button
                            size="icon"
                            variant="ghost"
                            className="size-8"
                            aria-label="Download CV"
                            onClick={() => void onDownloadCv(r.id, r.name)}
                          >
                            <FileDown className="size-4" />
                          </Button>
                          <Button
                            size="icon"
                            variant="ghost"
                            className="size-8 text-destructive hover:text-destructive"
                            aria-label="Delete"
                            onClick={() => void onDeleteRecipient(r.id)}
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

          {cvEmailActive && cvPhase !== "ready" && (
            <Button variant="outline" size="sm" className="md:col-span-2 w-fit" onClick={() => void onCloseCvCollection()}>
              Close CV collection early & continue
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
          <Field label="Position"><Input value={position} onChange={(e) => setPosition(e.target.value)} placeholder="Senior dental hygienist — Manchester" /></Field>
          <Field label="Role"><Input value={role} onChange={(e) => setRole(e.target.value)} placeholder="Registered dental hygienist (GDC)" /></Field>
          <Field label="AI voice agent">
            {agents.length === 0 ? (
              <p className="text-xs text-muted-foreground">No voice agents configured yet. Ask your admin to enable interview agents.</p>
            ) : (
              <Select value={agentId || agents[0]?.id} onValueChange={setAgentId}>
                <SelectTrigger><SelectValue placeholder="Select agent" /></SelectTrigger>
                <SelectContent>
                  {agents.map((a) => (
                    <SelectItem key={a.id} value={a.id}>{a.voice_label || a.name}{a.is_default_for_org ? " · default" : ""}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </Field>
          <Field label="Interview format">
            <Select value={delivery} onValueChange={setDelivery}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="ai_call">Phone call</SelectItem>
                <SelectItem value="zoom" disabled>Zoom (coming soon)</SelectItem>
              </SelectContent>
            </Select>
          </Field>
          <div className="md:col-span-2 space-y-1.5">
            <Label className="text-xs">Screening criteria</Label>
            <Textarea rows={4} value={criteria} onChange={(e) => setCriteria(e.target.value)} placeholder="Must hold GDC registration…" />
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
            <Label className="text-xs">Generated script</Label>
            <Textarea rows={8} value={script} onChange={(e) => { setScript(e.target.value); setScriptApproved(false); setExpectedDurationMinutes(undefined); }} placeholder="Generate AI questions or paste your own script…" />
          </div>
          <div className="grid gap-2 sm:grid-cols-2 md:col-span-2">
            <Field label="Calling start"><Input type="datetime-local" value={callingStart} onChange={(e) => setCallingStart(e.target.value)} /></Field>
            <Field label="Calling end"><Input type="datetime-local" value={callingEnd} onChange={(e) => setCallingEnd(e.target.value)} /></Field>
          </div>
        </CardContent>
      </Card>

      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:flex-wrap sm:items-center sm:justify-end">
        <Button variant="outline" className="gap-1.5" onClick={() => void onSaveDraft()} disabled={saveDraftM.isPending || patchOrderM.isPending}>
          <Save className="size-4" /> {saveDraftM.isPending ? "Saving…" : "Save draft"}
        </Button>
        <Button className="gap-1.5" onClick={onAttemptPreview}>
          <Eye className="size-4" /> Preview & approve
        </Button>
      </div>

      <PackageUpgradeModal open={upgradeOpen} onOpenChange={setUpgradeOpen} />
      <AtsPreviewGateModal
        open={atsPromptOpen}
        onOpenChange={setAtsPromptOpen}
        quote={atsQuote as { candidate_count?: number; total_gbp?: string; unit_price_gbp?: string; wallet_gbp?: string; requires_payment?: boolean } | null}
        quoteLoading={atsQuoteLoading}
        quoteError={atsQuoteError}
        onRetryQuote={() => void loadAtsQuote(!!atsRunAt)}
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
        quoteLoading={quoteM.isPending}
        payBusy={payBusy}
        gcAvailable={gcReady}
      />
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="space-y-1.5"><Label className="text-xs">{label}</Label>{children}</div>;
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
