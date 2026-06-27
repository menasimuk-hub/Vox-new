import { createFileRoute, useNavigate } from "@tanstack/react-router";
import * as React from "react";
import { Send, Upload, ArrowLeft, ArrowRight, Check, AlertTriangle, Tag, Link2, Calendar, ShieldCheck, FileText } from "lucide-react";
import { toast } from "sonner";
import { z } from "zod";
import { useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { IPhonePreview } from "@/components/iphone-preview";
import { apiFetch } from "@/lib/api";
import { queryKeys, useFeedbackMarketingSubscriberCount, useFeedbackPromoTemplates } from "@/lib/queries";

const searchSchema = z.object({ template: z.string().optional() });

export const Route = createFileRoute("/_app/feedback/campaigns/send")({
  head: () => ({ meta: [{ title: "Send campaign — Customer feedback" }] }),
  validateSearch: searchSchema,
  component: FeedbackCampaignSend,
});

type PromoTemplate = {
  id: string;
  name: string;
  category: string;
  scenario: string;
  body: string;
  footer: string;
  variables: string[];
  buttons?: Array<{ label: string; type?: string }>;
};

function FeedbackCampaignSend() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const { template: presetTpl } = Route.useSearch();
  const tplQ = useFeedbackPromoTemplates();
  const optInQ = useFeedbackMarketingSubscriberCount();
  const templates = (tplQ.data || []) as PromoTemplate[];

  const [step, setStep] = React.useState(1);
  const [templateId, setTemplateId] = React.useState(presetTpl ?? "");
  const [promo, setPromo] = React.useState("20% off");
  const [code, setCode] = React.useState("SPRING20");
  const [link, setLink] = React.useState("https://yourcompany.com/offer");
  const [date, setDate] = React.useState("Sat 28 June, 7pm");
  const [numbersText, setNumbersText] = React.useState("");
  const [uploaded, setUploaded] = React.useState("");
  const [agree, setAgree] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [quote, setQuote] = React.useState<Record<string, unknown> | null>(null);
  const fileRef = React.useRef<HTMLInputElement>(null);

  const [useOptIn, setUseOptIn] = React.useState(true);

  React.useEffect(() => {
    if (presetTpl) setTemplateId(presetTpl);
  }, [presetTpl]);

  const template = templates.find((t) => t.id === templateId);

  const manualNumbers = React.useMemo(() => {
    return numbersText
      .split(/[\s,;\n]+/)
      .map((n) => n.trim())
      .filter((n) => /^\+?\d{6,15}$/.test(n));
  }, [numbersText]);

  const optInCount = useOptIn ? (optInQ.data ?? 0) : 0;
  const totalRecipients = optInCount + manualNumbers.length;

  const variables = React.useMemo(() => ({ promo, code, link, date }), [promo, code, link, date]);

  const previewBody = (template?.body || "")
    .replace(/\{\{1\}\}/g, template?.variables.includes("code") ? code : template?.variables.includes("date") ? date : promo)
    .replace(/\{\{2\}\}/g, link);

  const onFile = (f?: File | null) => {
    if (!f) return;
    const reader = new FileReader();
    reader.onload = () => {
      const text = String(reader.result || "");
      setNumbersText((prev) => (prev ? `${prev}\n` : "") + text);
      setUploaded(f.name);
    };
    reader.readAsText(f);
  };

  const refreshQuote = React.useCallback(async () => {
    if (!templateId) return;
    const data = await apiFetch<{ ok?: boolean; quote?: Record<string, unknown> }>("/customer-feedback/promo-campaigns/quote", {
      method: "POST",
      body: JSON.stringify({
        template_id: templateId,
        variables,
        use_opt_in_audience: useOptIn,
        manual_phones: manualNumbers,
      }),
    });
    setQuote(data?.quote || null);
  }, [templateId, variables, useOptIn, manualNumbers]);

  React.useEffect(() => {
    if (step >= 3 && templateId) void refreshQuote().catch(() => setQuote(null));
  }, [step, templateId, refreshQuote]);

  const costMinor = Number(quote?.cost_minor ?? totalRecipients * Number(quote?.rate_minor ?? 5));
  const currency = String(quote?.currency || "GBP");
  const sym = currency === "GBP" ? "£" : currency === "EUR" ? "€" : "$";

  const launch = async () => {
    if (!templateId || totalRecipients === 0) return;
    setBusy(true);
    try {
      const created = await apiFetch<{ ok?: boolean; item?: { id?: string } }>("/customer-feedback/promo-campaigns", {
        method: "POST",
        body: JSON.stringify({
          template_id: templateId,
          variables,
          use_opt_in_audience: useOptIn,
          manual_phones: manualNumbers,
        }),
      });
      const campaignId = created?.item?.id;
      if (!campaignId) throw new Error("Could not create campaign");
      const checkout = await apiFetch<{ invoice_id?: string; invoice_number?: string }>(
        `/customer-feedback/promo-campaigns/${campaignId}/checkout`,
        { method: "POST" },
      );
      toast.success("Invoice created", {
        description: checkout.invoice_number
          ? `Pay invoice ${checkout.invoice_number}, then launch from Campaign dashboard.`
          : "Pay your invoice in Billing, then launch the campaign.",
      });
      await qc.invalidateQueries({ queryKey: queryKeys.feedbackPromoDashboard });
      nav({ to: "/feedback/campaigns" });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not create campaign");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader eyebrow="Customer feedback" title="Send campaign" description="Pick an approved template, fill variables, add opt-in audience or numbers — pay invoice, then launch." />

      <div className="flex items-center gap-2 rounded-lg border border-success/30 bg-success/5 p-3 text-sm text-success">
        <ShieldCheck className="size-4" />
        <span>Templates are pre-approved for marketing. Recipients must have opted in (survey toggle or uploaded list).</span>
      </div>

      <Stepper step={step} labels={["Choose template", "Fill variables", "Recipients", "Review & pay"]} />

      {step === 1 && (
        <Card><CardContent className="p-4">
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
            {templates.map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => setTemplateId(t.id)}
                className={`rounded-lg border p-3 text-left transition ${templateId === t.id ? "border-primary bg-primary/5" : "border-border hover:border-primary/40"}`}
              >
                <div className="flex items-center justify-between">
                  <p className="font-medium">{t.name}</p>
                  <Badge variant="secondary" className="text-[10px]">{t.category}</Badge>
                </div>
                <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{t.scenario}</p>
              </button>
            ))}
          </div>
        </CardContent></Card>
      )}

      {step === 2 && template && (
        <Card><CardContent className="grid gap-5 p-5 md:grid-cols-[1fr_360px]">
          <div className="space-y-4">
            <div className="rounded-lg border border-border bg-muted/30 p-3">
              <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Template</p>
              <p className="mt-1 font-medium">{template.name}</p>
            </div>
            {template.variables.includes("promo") && (
              <Field label="Promo / offer text ({{1}})" icon={Tag}>
                <Input value={promo} onChange={(e) => setPromo(e.target.value)} />
              </Field>
            )}
            {template.variables.includes("code") && (
              <Field label="Promo code ({{1}})" icon={Tag}>
                <Input value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} />
              </Field>
            )}
            {template.variables.includes("date") && (
              <Field label="Event date ({{1}})" icon={Calendar}>
                <Input value={date} onChange={(e) => setDate(e.target.value)} />
              </Field>
            )}
            {template.variables.includes("link") && (
              <Field label="Link ({{2}})" icon={Link2}>
                <Input value={link} onChange={(e) => setLink(e.target.value)} />
              </Field>
            )}
          </div>
          <IPhonePreview businessName="Your Business" body={previewBody} buttons={template.buttons} footer={template.footer} />
        </CardContent></Card>
      )}

      {step === 3 && (
        <Card><CardContent className="space-y-4 p-5">
          <div className="rounded-lg border border-primary/30 bg-primary/5 p-3">
            <label className="flex cursor-pointer items-start gap-3">
              <Checkbox checked={useOptIn} onCheckedChange={(v) => setUseOptIn(!!v)} className="mt-0.5" />
              <div>
                <p className="text-sm font-medium">Use opt-in audience ({optInCount.toLocaleString()} customers)</p>
                <p className="mt-0.5 text-xs text-muted-foreground">Customers who opted in during your feedback survey.</p>
              </div>
            </label>
          </div>
          <Field label="Extra phone numbers (optional)" icon={FileText}>
            <textarea value={numbersText} onChange={(e) => setNumbersText(e.target.value)} rows={8} className="w-full rounded-md border border-border bg-background p-2 font-mono text-sm" placeholder="+447700900123" />
          </Field>
          <input ref={fileRef} type="file" accept=".txt,.csv" className="hidden" onChange={(e) => onFile(e.target.files?.[0])} />
          <button type="button" onClick={() => fileRef.current?.click()} className="grid w-full place-items-center rounded-lg border-2 border-dashed border-border p-6 hover:border-primary/50">
            <Upload className="mb-1 size-5 text-muted-foreground" />
            <p className="text-sm">{uploaded || "Upload .txt or .csv"}</p>
          </button>
          <div className="grid gap-2 rounded-lg border border-border bg-muted/30 p-3 text-sm sm:grid-cols-3">
            <div><p className="text-xs text-muted-foreground">Opt-in</p><p className="text-lg font-semibold">{optInCount.toLocaleString()}</p></div>
            <div><p className="text-xs text-muted-foreground">Manual</p><p className="text-lg font-semibold">{manualNumbers.length.toLocaleString()}</p></div>
            <div><p className="text-xs text-muted-foreground">Total</p><p className="text-lg font-semibold text-primary">{totalRecipients.toLocaleString()}</p></div>
          </div>
        </CardContent></Card>
      )}

      {step === 4 && template && (
        <Card><CardContent className="grid gap-5 p-5 md:grid-cols-[1fr_360px]">
          <div className="space-y-4 text-sm">
            <Row k="Template" v={template.name} />
            <Row k="Recipients" v={totalRecipients.toLocaleString()} />
            <Row k="Estimated cost" v={`${sym}${(costMinor / 100).toFixed(2)}`} />
            <p className="text-xs text-muted-foreground">An invoice is created at checkout. Launch is enabled after payment (Billing → Invoices).</p>
            {totalRecipients === 0 && (
              <div className="flex items-center gap-2 rounded-md bg-destructive/10 p-2 text-xs text-destructive">
                <AlertTriangle className="size-4" /> Add at least one recipient.
              </div>
            )}
            <label className="flex items-center gap-2">
              <Checkbox checked={agree} onCheckedChange={(v) => setAgree(!!v)} />
              <span>Recipients have opted in to marketing messages from my business.</span>
            </label>
            <Button className="w-full gap-1.5" onClick={launch} disabled={!agree || totalRecipients === 0 || busy}>
              <Send className="size-4" /> {busy ? "Creating invoice…" : "Create invoice & queue"}
            </Button>
          </div>
          <IPhonePreview businessName="Your Business" body={previewBody} buttons={template.buttons} footer={template.footer} />
        </CardContent></Card>
      )}

      <div className="flex items-center justify-between">
        <Button variant="ghost" disabled={step === 1} onClick={() => setStep((s) => s - 1)} className="gap-1.5"><ArrowLeft className="size-4" /> Back</Button>
        {step < 4 && (
          <Button onClick={() => setStep((s) => s + 1)} disabled={(step === 1 && !templateId) || (step === 3 && totalRecipients === 0)} className="gap-1.5">
            Next <ArrowRight className="size-4" />
          </Button>
        )}
      </div>
    </div>
  );
}

function Field({ label, icon: Icon, children }: { label: string; icon?: React.ComponentType<{ className?: string }>; children: React.ReactNode }) {
  return (
    <div>
      <Label className="flex items-center gap-1.5">{Icon && <Icon className="size-3.5" />} {label}</Label>
      <div className="mt-1.5">{children}</div>
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return <div className="flex justify-between gap-3 border-b border-border/60 py-2"><span className="text-muted-foreground">{k}</span><span className="font-medium">{v}</span></div>;
}

function Stepper({ step, labels }: { step: number; labels: string[] }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      {labels.map((l, i) => {
        const n = i + 1;
        const active = step === n;
        const done = step > n;
        return (
          <React.Fragment key={l}>
            <div className={`flex items-center gap-2 rounded-full px-3 py-1.5 text-xs ${active ? "bg-primary text-primary-foreground" : done ? "bg-success/15 text-success" : "bg-muted text-muted-foreground"}`}>
              <span className="grid size-5 place-items-center rounded-full bg-background/30 text-[10px] font-semibold">{done ? <Check className="size-3" /> : n}</span>
              {l}
            </div>
            {i < labels.length - 1 && <div className="h-px w-4 bg-border" />}
          </React.Fragment>
        );
      })}
    </div>
  );
}
