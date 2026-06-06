import { createFileRoute } from "@tanstack/react-router";
import * as React from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { ChannelPicker } from "@/components/create-wizard";
import { SurveyPhoneWizard } from "@/components/create-wizard/survey-phone-wizard";
import { SurveyWaWizard } from "@/components/create-wizard/survey-wa-wizard";
import { apiUploadFiles, downloadAuthenticatedFile } from "@/lib/api";
import {
  useCreateServiceOrder,
  useGenerateWaSurvey,
  usePatchServiceOrder,
  useSurveyPackages,
  useWaSurveyIndustries,
  useWaSurveyStepBank,
  useWaSurveySystemTemplates,
  useWaSurveyTypes,
} from "@/lib/queries";

export const Route = createFileRoute("/_app/surveys/new")({
  head: () => ({ meta: [{ title: "Create survey — VoxBulk" }] }),
  component: CreateSurvey,
});

const PAGE_COUNT_TO_LENGTH: Record<4 | 5 | 6, "short" | "standard" | "detailed"> = {
  4: "short",
  5: "standard",
  6: "detailed",
};

type Channel = "whatsapp" | "phone" | null;

function CreateSurvey() {
  const packagesQ = useSurveyPackages();
  const createM = useCreateServiceOrder();
  const patchM = usePatchServiceOrder();
  const generateWaM = useGenerateWaSurvey();

  const [channel, setChannel] = React.useState<Channel>(null);
  const [waPreview, setWaPreview] = React.useState<Record<string, unknown> | null>(null);
  const [industryId, setIndustryId] = React.useState("");
  const [selectedServiceTagIds, setSelectedServiceTagIds] = React.useState<string[]>([]);
  const [orderedServiceTagIds, setOrderedServiceTagIds] = React.useState<string[]>([]);
  const [welcomeTemplateId, setWelcomeTemplateId] = React.useState("");
  const [thankYouTemplateId, setThankYouTemplateId] = React.useState("");
  const [privacyMode, setPrivacyMode] = React.useState<"off" | "on">("off");
  const surveyVariant = privacyMode === "on" ? "anonymous" : "standard";
  const [pageCount, setPageCount] = React.useState<4 | 5 | 6>(5);
  const [autoSelectSteps, setAutoSelectSteps] = React.useState(true);
  const [manualMiddleRoles, setManualMiddleRoles] = React.useState<string[]>([]);
  const [generating, setGenerating] = React.useState(false);
  const waIndustriesQ = useWaSurveyIndustries();
  const waTypesQ = useWaSurveyTypes(industryId || null);
  const systemTemplatesQ = useWaSurveySystemTemplates();
  const primarySurveyTypeId = orderedServiceTagIds[0] || selectedServiceTagIds[0] || "";
  const stepBankQ = useWaSurveyStepBank(channel === "whatsapp" ? primarySurveyTypeId : null, privacyMode);
  const [approved, setApproved] = React.useState(false);
  const [anonymous, setAnonymous] = React.useState(false);
  const [goal, setGoal] = React.useState(
    "Measure satisfaction with our new hygienist team and identify the top 1 improvement.",
  );
  const [script, setScript] = React.useState(
    "1. On a scale of 0-10, how likely are you to recommend us?\n2. What stood out about your visit?\n3. Anything we could improve?",
  );
  const [startAt, setStartAt] = React.useState("");
  const [endAt, setEndAt] = React.useState("");
  const [packageId, setPackageId] = React.useState("");
  const [orderId, setOrderId] = React.useState<string | null>(null);
  const fileRef = React.useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = React.useState(false);

  const delivery = channel === "whatsapp" ? "whatsapp" : "ai_call";

  const packages = React.useMemo(() => {
    const data = packagesQ.data || {};
    const channelKey = channel === "whatsapp" ? "whatsapp" : "ai_call";
    const list = (data.packages as Record<string, unknown[]>)?.[channelKey] || [];
    return list as Array<Record<string, unknown>>;
  }, [packagesQ.data, channel]);

  React.useEffect(() => {
    if (packages[0] && !packageId) setPackageId(String(packages[0].id || packages[0].rule_id || ""));
  }, [packages, packageId]);

  const ensureOrder = async () => {
    if (orderId) return orderId;
    const created = await createM.mutateAsync({
      service_code: "survey",
      title: goal.slice(0, 80) || "New survey",
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
    const industries = (waIndustriesQ.data?.industries || []) as Array<Record<string, unknown>>;
    if (industries[0] && !industryId) setIndustryId(String(industries[0].id));
  }, [waIndustriesQ.data, industryId]);

  React.useEffect(() => {
    setSelectedServiceTagIds([]);
    setOrderedServiceTagIds([]);
    setWelcomeTemplateId("");
    setThankYouTemplateId("");
    setApproved(false);
  }, [industryId]);

  React.useEffect(() => {
    setOrderedServiceTagIds((prev) => {
      const next = prev.filter((id) => selectedServiceTagIds.includes(id));
      for (const id of selectedServiceTagIds) {
        if (!next.includes(id)) next.push(id);
      }
      return next;
    });
  }, [selectedServiceTagIds]);

  const serviceTypes = React.useMemo(
    () => (waTypesQ.data?.types || []) as Array<Record<string, unknown>>,
    [waTypesQ.data],
  );

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

  const serviceTagErrors = React.useMemo(() => {
    const errors: string[] = [];
    if (selectedServiceTagIds.length < 1) errors.push("Select at least 1 service (max 4).");
    if (selectedServiceTagIds.length > 4) errors.push("Select at most 4 services.");
    for (const id of selectedServiceTagIds) {
      const row = serviceTypes.find((t) => String(t.id) === id);
      if (!row) continue;
      if (!row.has_wa_template) {
        errors.push(`"${String(row.name)}" has no WhatsApp template yet.`);
      }
    }
    if (!welcomeTemplateId) errors.push("Select a welcome template.");
    if (!thankYouTemplateId) errors.push("Select a thank-you template.");
    return errors;
  }, [selectedServiceTagIds, serviceTypes, welcomeTemplateId, thankYouTemplateId]);

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

  const onGenerateWaSurvey = async () => {
    if (serviceTagErrors.length) {
      toast.error(serviceTagErrors[0]);
      return;
    }
    if (!pageOrderValid) {
      toast.error(`Choose ${pageCount - 2} unique middle steps between start and completion`);
      return;
    }
    setGenerating(true);
    try {
      const generated = await generateWaM.mutateAsync({
        industry_id: industryId,
        survey_type_id: primarySurveyTypeId,
        selected_survey_type_ids: orderedServiceTagIds.length ? orderedServiceTagIds : selectedServiceTagIds,
        welcome_template_id: Number(welcomeTemplateId),
        thank_you_template_id: Number(thankYouTemplateId),
        variant: surveyVariant,
        privacy_mode: privacyMode,
        length: PAGE_COUNT_TO_LENGTH[pageCount],
        page_count: pageCount,
        auto_select_steps: autoSelectSteps,
        selected_step_roles: autoSelectSteps ? undefined : resolvedPageRoles,
        goal,
      });
      setWaPreview(generated);
      setScript(String(generated.approved_script || script));
      setAnonymous(Boolean(generated.anonymous_responses));
      const id = await ensureOrder();
      await patchM.mutateAsync({
        orderId: id,
        body: {
          config: {
            goal,
            delivery: "whatsapp",
            anonymous_responses: Boolean(generated.anonymous_responses),
            allow_follow_up: generated.allow_follow_up !== false,
            script: String(generated.approved_script || script),
            industry_id: industryId,
            survey_type_id: primarySurveyTypeId,
            selected_survey_type_ids: orderedServiceTagIds.length ? orderedServiceTagIds : selectedServiceTagIds,
            welcome_template_id: generated.welcome_template_id ?? Number(welcomeTemplateId),
            thank_you_template_id: generated.thank_you_template_id ?? Number(thankYouTemplateId),
            tell_us_more_template_id: generated.tell_us_more_template_id,
            survey_length: PAGE_COUNT_TO_LENGTH[pageCount],
            page_count: pageCount,
            page_roles: generated.page_roles,
            survey_variant: surveyVariant,
            privacy_mode: privacyMode,
            wa_template_id: generated.wa_template_id,
            whatsapp_flow: generated.whatsapp_flow,
          },
        },
      });
      setApproved(true);
      toast.success("Survey generated from approved WhatsApp template library");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not generate survey");
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
          title: goal.slice(0, 80) || "Survey draft",
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
      await apiUploadFiles(`/service-orders/${encodeURIComponent(id)}/recipients/upload`, Array.from(files), "file");
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
          welcomeTemplateId={welcomeTemplateId}
          setWelcomeTemplateId={setWelcomeTemplateId}
          thankYouTemplateId={thankYouTemplateId}
          setThankYouTemplateId={setThankYouTemplateId}
          welcomeTemplates={welcomeTemplates}
          thankYouTemplates={thankYouTemplates}
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
        />
      )}
    </div>
  );
}
