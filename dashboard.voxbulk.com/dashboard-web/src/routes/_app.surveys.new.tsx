import { createFileRoute } from "@tanstack/react-router";
import * as React from "react";
import { Upload, Download, Wand2, Lock, RotateCcw, Eye } from "lucide-react";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { WhatsAppPreviewModal, PreviewQuoteModal } from "@/components/modals";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Skeleton } from "@/components/ui/skeleton";
import { apiUploadFiles, downloadAuthenticatedFile } from "@/lib/api";
import { useCreateServiceOrder, usePatchServiceOrder, useSurveyPackages } from "@/lib/queries";

export const Route = createFileRoute("/_app/surveys/new")({
  head: () => ({ meta: [{ title: "Create survey — VoxBulk" }] }),
  component: CreateSurvey,
});

function CreateSurvey() {
  const packagesQ = useSurveyPackages();
  const createM = useCreateServiceOrder();
  const patchM = usePatchServiceOrder();

  const [method, setMethod] = React.useState<"phone" | "whatsapp">("phone");
  const [waOpen, setWaOpen] = React.useState(false);
  const [quote, setQuote] = React.useState(false);
  const [approved, setApproved] = React.useState(false);
  const [anonymous, setAnonymous] = React.useState(false);
  const [goal, setGoal] = React.useState("Measure satisfaction with our new hygienist team and identify the top 1 improvement.");
  const [script, setScript] = React.useState("1. On a scale of 0-10, how likely are you to recommend us?\n2. What stood out about your visit?\n3. Anything we could improve?");
  const [startAt, setStartAt] = React.useState("");
  const [endAt, setEndAt] = React.useState("");
  const [packageId, setPackageId] = React.useState("");
  const [orderId, setOrderId] = React.useState<string | null>(null);
  const fileRef = React.useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = React.useState(false);

  const packages = React.useMemo(() => {
    const data = packagesQ.data || {};
    const channel = method === "whatsapp" ? "whatsapp" : "ai_call";
    const list = (data.packages as Record<string, unknown[]>)?.[channel] || [];
    return list as Array<Record<string, unknown>>;
  }, [packagesQ.data, method]);

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
        delivery: method === "whatsapp" ? "whatsapp" : "ai_call",
        anonymous_responses: anonymous,
        script,
        package_id: packageId || undefined,
      },
    });
    setOrderId(created.id);
    return created.id;
  };

  const onSaveDraft = async () => {
    try {
      const id = await ensureOrder();
      await patchM.mutateAsync({
        orderId: id,
        body: {
          title: goal.slice(0, 80) || "Survey draft",
          scheduled_start_at: startAt || null,
          scheduled_end_at: endAt || null,
          config: {
            goal,
            delivery: method === "whatsapp" ? "whatsapp" : "ai_call",
            anonymous_responses: anonymous,
            script,
            package_id: packageId || undefined,
          },
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

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader eyebrow="Surveys" title="Create new survey" description="AI phone call or WhatsApp — your choice." />

      <Card>
        <CardHeader><CardTitle>Channel</CardTitle><CardDescription>How patients will be contacted.</CardDescription></CardHeader>
        <CardContent className="space-y-4">
          <Tabs value={method} onValueChange={(v) => setMethod(v as "phone" | "whatsapp")}>
            <TabsList className="w-full sm:w-auto">
              <TabsTrigger value="phone">AI phone call</TabsTrigger>
              <TabsTrigger value="whatsapp">WhatsApp</TabsTrigger>
            </TabsList>
          </Tabs>
          {method === "whatsapp" && (
            <div className="animate-fade-in flex items-start justify-between gap-3 rounded-lg border border-border bg-background/40 p-3">
              <div>
                <p className="text-sm font-medium">Anonymous responses</p>
                <p className="text-xs text-muted-foreground">
                  When on, replies are recorded without name or phone number. Useful for honest feedback.
                </p>
              </div>
              <Switch checked={anonymous} onCheckedChange={setAnonymous} />
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>What do you want to learn?</CardTitle></CardHeader>
        <CardContent className="grid gap-5 md:grid-cols-2">
          <div className="md:col-span-2 space-y-1.5">
            <Label className="text-xs">Survey goal</Label>
            <Textarea rows={3} value={goal} onChange={(e) => setGoal(e.target.value)} />
          </div>
          {method === "phone" && (
            <>
              <Field label="Max call length">
                <Select defaultValue="2">
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {["1", "2", "3", "5"].map((m) => <SelectItem key={m} value={m}>{m} minutes</SelectItem>)}
                  </SelectContent>
                </Select>
              </Field>
              <Field label="AI voice agent">
                <Select defaultValue="amelia">
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="amelia">Amelia (UK · warm)</SelectItem>
                    <SelectItem value="ravi">Ravi (UK · professional)</SelectItem>
                  </SelectContent>
                </Select>
              </Field>
            </>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Contacts</CardTitle><CardDescription>Upload patient list.</CardDescription></CardHeader>
        <CardContent>
          <input ref={fileRef} type="file" accept=".csv,.xlsx,.xls" className="hidden" onChange={(e) => void onUpload(e.target.files)} />
          <div className="flex flex-col items-center gap-2 rounded-xl border-2 border-dashed border-border bg-background/50 px-4 py-8 text-center sm:px-6 sm:py-10">
            <Upload className="size-6 text-muted-foreground" />
            <p className="text-sm font-medium">Upload CSV or Excel</p>
            <div className="mt-2 flex flex-col gap-2 sm:flex-row">
              <Button size="sm" onClick={() => fileRef.current?.click()} disabled={uploading}>
                {uploading ? "Uploading…" : "Choose file"}
              </Button>
              <Button size="sm" variant="outline" className="gap-1.5" onClick={() => void onDownloadTemplate()}>
                <Download className="size-3.5" /> Sample template
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>AI script</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <Textarea rows={6} value={script} onChange={(e) => setScript(e.target.value)} />
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" className="gap-1.5"><Wand2 className="size-4" /> AI write survey script</Button>
            <Button variant="outline" className="gap-1.5" onClick={() => setApproved(true)}><Lock className="size-4" /> Approve script</Button>
            <Button variant="ghost" className="gap-1.5"><RotateCcw className="size-4" /> Regenerate</Button>
            {method === "whatsapp" && (
              <Button variant="outline" className="gap-1.5" onClick={() => setWaOpen(true)}><Eye className="size-4" /> Preview WhatsApp</Button>
            )}
            <div className="ml-auto"><StatusBadge tone={approved ? "approved-script" : "draft-script"} /></div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Schedule & package</CardTitle></CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-3">
          <Field label="Start"><Input type="datetime-local" value={startAt} onChange={(e) => setStartAt(e.target.value)} /></Field>
          <Field label="End"><Input type="datetime-local" value={endAt} onChange={(e) => setEndAt(e.target.value)} /></Field>
          <Field label="Package">
            {packagesQ.isLoading ? (
              <Skeleton className="h-10 w-full" />
            ) : (
              <Select value={packageId} onValueChange={setPackageId}>
                <SelectTrigger><SelectValue placeholder="Select package" /></SelectTrigger>
                <SelectContent>
                  {packages.map((p) => (
                    <SelectItem key={String(p.id || p.rule_id)} value={String(p.id || p.rule_id)}>
                      {String(p.label || p.name || p.bundle_size || "Package")}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </Field>
        </CardContent>
      </Card>

      <div className="flex flex-col gap-2 sm:flex-row sm:justify-end">
        <Button variant="outline" onClick={() => void onSaveDraft()} disabled={createM.isPending || patchM.isPending}>
          {createM.isPending || patchM.isPending ? "Saving…" : "Save draft"}
        </Button>
        <Button className="gap-1.5" onClick={() => setQuote(true)}><Eye className="size-4" /> Preview & approve</Button>
      </div>

      <WhatsAppPreviewModal open={waOpen} onOpenChange={setWaOpen} />
      <PreviewQuoteModal open={quote} onOpenChange={setQuote} kind="survey" />
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="space-y-1.5"><Label className="text-xs">{label}</Label>{children}</div>;
}
