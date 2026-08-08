import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { ArrowLeft, Download, QrCode } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { useQuery } from "@tanstack/react-query";

import {
  categoriesFromApi,
  emptyRepresentative,
  representativesFromApi,
  RepresentativesEditor,
  representativesToPayload,
  type CategoryDraft,
  type RepresentativeDraft,
} from "@/components/expo-booth-sections";
import { ExpoBoothPrintCard } from "@/components/expo-booth-print-card";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch } from "@/lib/api";
import { buildExpoQrImageUrl, formatExpoDay, formatExpoWindow, resolveExpoWebUrl } from "@/lib/expo-qr";
import { canLaunchCampaigns, normalizeOrgRole } from "@/lib/org-roles";
import { useSession } from "@/lib/session";
import { cn } from "@/lib/utils";

type Industry = { id: string; slug: string; name: string; addon_question?: string | null };
type QuestionOpt = {
  key: string;
  prompt: string;
  label: string;
  description?: string;
  matches_products?: boolean;
};
type BoothDetail = {
  id: string;
  name: string;
  company_display_name: string;
  booth_code?: string | null;
  exhibition_name?: string;
  venue?: string | null;
  industry_id?: string | null;
  package_id?: string | null;
  activated_at?: string | null;
  expires_at?: string | null;
  is_paid?: boolean;
  payment_status?: string;
  is_live?: boolean;
  question_config?: {
    steps?: Array<{ key: string; prompt: string }>;
    selected_question_keys?: string[];
  };
  closing?: { thank_you_message?: string; free_gift_enabled?: boolean; free_gift_text?: string };
  contact_capture?: "offer_both" | "manual_only" | "card_only";
  representatives?: Array<Record<string, unknown>>;
  company_website?: string | null;
  notify_mobile?: string | null;
  categories?: Parameters<typeof categoriesFromApi>[0];
  max_categories?: number | null;
  web_url?: string | null;
  qr_image_url?: string | null;
  qr_token?: string | null;
  trigger_text?: string | null;
  booth_asset_count?: number;
  library_asset_count?: number;
  deliverable_asset_count?: number;
};

const SYSTEM_STEP_KEYS = new Set(["contact", "open_feedback"]);

export const Route = createFileRoute("/_app/expo/$boothId/edit")({
  head: () => ({ meta: [{ title: "Edit Expo booth — VoxBulk" }] }),
  component: EditExpoBooth,
});

function EditExpoBooth() {
  const { boothId } = Route.useParams();
  const navigate = useNavigate();
  const { session } = useSession();
  const role = normalizeOrgRole(session?.profile?.role);
  const canEdit = canLaunchCampaigns(role);

  const boothQ = useQuery({
    queryKey: ["expo", "booth", boothId],
    queryFn: () => apiFetch<{ ok: boolean; item: BoothDetail }>(`/expo/booths/${boothId}`),
  });
  const industriesQ = useQuery({
    queryKey: ["expo", "industries"],
    queryFn: () => apiFetch<{ items: Industry[] }>("/expo/catalog/industries"),
  });
  const questionsQ = useQuery({
    queryKey: ["expo", "questions"],
    queryFn: () => apiFetch<{ items: QuestionOpt[] }>("/expo/catalog/questions"),
  });
  const booth = boothQ.data?.item;
  const industries = industriesQ.data?.items || [];
  const industry = industries.find((i) => i.id === booth?.industry_id);

  const [exhibitionName, setExhibitionName] = React.useState("");
  const [venue, setVenue] = React.useState("");
  const [boothCode, setBoothCode] = React.useState("");
  const [company, setCompany] = React.useState("");
  const [representatives, setRepresentatives] = React.useState<RepresentativeDraft[]>([]);
  const [companyWebsite, setCompanyWebsite] = React.useState("");
  const [notifyMobile, setNotifyMobile] = React.useState("");
  const [selectedQKeys, setSelectedQKeys] = React.useState<string[]>([]);
  const [includeAddon, setIncludeAddon] = React.useState(false);
  const [contactCapture, setContactCapture] = React.useState<"offer_both" | "manual_only" | "card_only">(
    "offer_both",
  );
  const [freeGiftEnabled, setFreeGiftEnabled] = React.useState(false);
  const [freeGiftText, setFreeGiftText] = React.useState("");
  const [categories, setCategories] = React.useState<CategoryDraft[]>([]);
  const [packageStartDate, setPackageStartDate] = React.useState("");
  const [saving, setSaving] = React.useState(false);
  const initialized = React.useRef(false);

  React.useEffect(() => {
    if (!booth?.id) return;
    if (typeof window === "undefined") return;
    if (window.location.hash !== "#print") return;
    const t = window.setTimeout(() => {
      document.getElementById("print")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 120);
    return () => window.clearTimeout(t);
  }, [booth?.id]);

  React.useEffect(() => {
    if (!booth || initialized.current) return;
    initialized.current = true;
    setExhibitionName(booth.exhibition_name || "");
    setVenue(booth.venue || "");
    setBoothCode(booth.booth_code || "");
    setCompany(booth.company_display_name || "");
    const reps = representativesFromApi(booth.representatives);
    setRepresentatives(reps.length > 0 ? reps : [emptyRepresentative(booth.company_display_name || "")]);
    setCompanyWebsite(booth.company_website || "");
    setNotifyMobile(booth.notify_mobile || "");
    const storedKeys = booth.question_config?.selected_question_keys;
    const steps = booth.question_config?.steps || [];
    const keys =
      Array.isArray(storedKeys) && storedKeys.length > 0
        ? storedKeys.filter((k) => !SYSTEM_STEP_KEYS.has(k))
        : steps.map((s) => s.key).filter((k) => !SYSTEM_STEP_KEYS.has(k));
    setSelectedQKeys(keys);
    setIncludeAddon(keys.includes("industry_addon"));
    setContactCapture(booth.contact_capture || "offer_both");
    setFreeGiftEnabled(Boolean(booth.closing?.free_gift_enabled));
    setFreeGiftText(booth.closing?.free_gift_text || "");
    setCategories(categoriesFromApi(booth.categories));
    setPackageStartDate(booth.activated_at ? String(booth.activated_at).slice(0, 10) : "");
  }, [booth]);

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

  const onSave = async () => {
    if (!booth) return;
    setSaving(true);
    try {
      const keys = [...selectedQKeys];
      if (includeAddon && industry?.addon_question && !keys.includes("industry_addon")) {
        keys.splice(Math.max(0, keys.indexOf("consent_info")), 0, "industry_addon");
      }
      if (!includeAddon) {
        const idx = keys.indexOf("industry_addon");
        if (idx >= 0) keys.splice(idx, 1);
      }
      const payload = {
        exhibition_name: exhibitionName.trim(),
        venue: venue.trim() || null,
        booth_code: boothCode.trim() || null,
        company_display_name: company.trim(),
        include_industry_addon: includeAddon,
        selected_question_keys: keys,
        contact_capture: contactCapture,
        free_gift_enabled: freeGiftEnabled,
        free_gift_text: freeGiftEnabled ? freeGiftText.trim() : null,
        representatives: representativesToPayload(representatives),
        company_website: companyWebsite.trim() || null,
        notify_mobile: notifyMobile.trim() || null,
        // Do not send categories — catalogues are managed on Add catalogues; sending [] wiped them.
        ...(packageStartDate ? { start_date: packageStartDate } : {}),
      };
      await apiFetch(`/expo/booths/${boothId}`, { method: "PATCH", body: JSON.stringify(payload) });
      toast.success(
        packageStartDate
          ? `Booth updated · package starts ${packageStartDate}. QR stays the same.`
          : "Booth updated — your QR code stays the same.",
      );
      void navigate({ to: "/expo" });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not update booth");
    } finally {
      setSaving(false);
    }
  };

  if (!canEdit) {
    return (
      <Card>
        <CardContent className="p-8 text-center text-sm text-muted-foreground">
          Your role cannot edit Expo booths. Ask an owner or manager.
        </CardContent>
      </Card>
    );
  }

  if (boothQ.isLoading) {
    return (
      <div className="flex w-full flex-col gap-6">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-96 w-full rounded-xl" />
      </div>
    );
  }

  if (boothQ.isError || !booth) {
    return (
      <Card>
        <CardContent className="p-8 text-center text-sm text-destructive">
          Booth not found.
          <div className="mt-4">
            <Button asChild variant="outline">
              <Link to="/expo">Back to saved booths</Link>
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  const webUrl = resolveExpoWebUrl({
    web_url: booth.web_url,
    qr_token: booth.qr_token,
  });
  const displayWebUrl = String(booth.web_url || webUrl || "").trim();
  const qrSrc =
    (booth.qr_image_url && String(booth.qr_image_url).trim()) ||
    (webUrl ? buildExpoQrImageUrl(webUrl, 440) : "");

  return (
    <div className="flex w-full max-w-none flex-col gap-6">
      <PageHeader
        eyebrow="VoxBulk Expo"
        title={`Edit booth — ${booth.name}`}
        description="Update event details and questions. Manage catalogues under Add catalogues. Your printed QR code stays the same."
        actions={
          <Button asChild variant="outline" className="gap-1.5">
            <Link to="/expo">
              <ArrowLeft className="size-4" /> Back
            </Link>
          </Button>
        }
      />

      {(booth.deliverable_asset_count ?? 0) === 0 ? (
        <div className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-950">
          No catalogues or files to offer visitors yet. Add PDFs under{" "}
          <Link to="/expo/catalogues" className="font-medium underline underline-offset-2">
            Add catalogues
          </Link>{" "}
          — they are offered on WhatsApp and web for every booth. Without files, the catalogue step is skipped.
        </div>
      ) : null}

      <div className="grid w-full gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(300px,400px)] lg:items-start">
        <div className="min-w-0 space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Event & booth</CardTitle>
              <CardDescription>QR token is unchanged — editing here does not reprint your QR.</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label>Exhibition name</Label>
                <Input value={exhibitionName} onChange={(e) => setExhibitionName(e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label>Venue</Label>
                <Input value={venue} onChange={(e) => setVenue(e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label>Booth / stand code</Label>
                <Input value={boothCode} onChange={(e) => setBoothCode(e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label>Company name on WhatsApp</Label>
                <Input value={company} onChange={(e) => setCompany(e.target.value)} />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Package live window</CardTitle>
              <CardDescription>
                Change when the paid package starts. End date is calculated from the package length. Current window:{" "}
                {formatExpoWindow(booth.activated_at, booth.expires_at) || "not set"}.
              </CardDescription>
            </CardHeader>
            <CardContent className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2 sm:col-span-2 rounded-lg border border-amber-300/70 bg-amber-50/70 px-3 py-2 text-sm dark:border-amber-700 dark:bg-amber-950/30">
                <p className="font-medium text-amber-950 dark:text-amber-100">
                  {booth.is_paid || booth.payment_status === "paid"
                    ? booth.is_live
                      ? "Paid · live now"
                      : "Paid · waiting for start"
                    : "Unpaid · pay to go live"}
                </p>
                <p className="text-xs text-muted-foreground">
                  Starts {formatExpoDay(booth.activated_at) || "—"} · Ends {formatExpoDay(booth.expires_at) || "—"}
                </p>
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit-expo-start">Package start date</Label>
                <Input
                  id="edit-expo-start"
                  type="date"
                  value={packageStartDate}
                  onChange={(e) => setPackageStartDate(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label>Current end date</Label>
                <Input type="text" value={formatExpoDay(booth.expires_at) || "—"} readOnly disabled />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Representative</CardTitle>
              <CardDescription>
                One stand contact for the digital business card and hot-lead WhatsApp alerts.
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

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Qualifying questions</CardTitle>
              <CardDescription>
                Fixed contact first — visitors see a business-card photo or type name / company option. Choose which
                extra questions are asked below.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="rounded-xl border bg-muted/20 p-4">
                <p className="text-sm font-medium">Fixed · Contact capture</p>
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
                    return (
                      <label
                        key={q.key}
                        className={cn(
                          "flex cursor-pointer gap-3 rounded-xl border p-3 transition hover:border-primary/40",
                          checked && "border-primary bg-primary/5",
                        )}
                      >
                        <Checkbox
                          checked={checked}
                          onCheckedChange={(v) => {
                            const on = Boolean(v);
                            setSelectedQKeys((prev) =>
                              on ? (prev.includes(q.key) ? prev : [...prev, q.key]) : prev.filter((k) => k !== q.key),
                            );
                            if (q.key === "industry_addon") setIncludeAddon(on);
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
                          </span>
                          <span className="mt-0.5 block text-xs text-muted-foreground">{q.prompt}</span>
                        </span>
                      </label>
                    );
                  })}
                </div>
                {industry?.addon_question ? (
                  <label className="mt-3 flex items-center gap-2 text-sm">
                    <Checkbox
                      checked={includeAddon}
                      onCheckedChange={(v) => {
                        const on = Boolean(v);
                        setIncludeAddon(on);
                        setSelectedQKeys((prev) => {
                          if (on) return prev.includes("industry_addon") ? prev : [...prev, "industry_addon"];
                          return prev.filter((k) => k !== "industry_addon");
                        });
                      }}
                    />
                    Include industry question: {industry.addon_question}
                  </label>
                ) : null}
              </div>

              <div className="rounded-xl border p-4">
                <label className="flex items-start gap-3">
                  <Checkbox
                    checked={freeGiftEnabled}
                    onCheckedChange={(v) => setFreeGiftEnabled(Boolean(v))}
                    className="mt-0.5"
                  />
                  <span>
                    <span className="font-medium">Offer a free gift after the questionnaire</span>
                    <span className="mt-0.5 block text-xs text-muted-foreground">
                      After the thank-you message, tell visitors how to collect their gift.
                    </span>
                  </span>
                </label>
                {freeGiftEnabled ? (
                  <Textarea
                    className="mt-3"
                    value={freeGiftText}
                    onChange={(e) => setFreeGiftText(e.target.value)}
                    rows={2}
                  />
                ) : null}
              </div>
            </CardContent>
          </Card>

          <div className="flex flex-wrap gap-2">
            <Button onClick={() => void onSave()} disabled={saving}>
              {saving ? "Saving…" : "Save changes"}
            </Button>
            <Button asChild variant="outline">
              <Link to="/expo">Cancel</Link>
            </Button>
          </div>
        </div>

        <aside className="lg:sticky lg:top-20">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <QrCode className="size-4 text-primary" /> Your QR code
              </CardTitle>
              <CardDescription>
                Print this for your stand. Editing questions does not change the QR.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="flex flex-col items-center gap-3">
                {qrSrc ? (
                  <div className="rounded-xl border-2 border-dashed border-border bg-white p-3">
                    <img
                      src={qrSrc}
                      alt={`QR for ${booth.name}`}
                      className="size-52 sm:size-56"
                      referrerPolicy="no-referrer"
                    />
                  </div>
                ) : (
                  <div className="grid size-52 place-items-center rounded-xl border border-dashed text-muted-foreground sm:size-56">
                    <QrCode className="size-12" />
                  </div>
                )}
                <p className="text-center text-xs text-muted-foreground">Scan to preview on your phone</p>
                {displayWebUrl ? (
                  <a
                    href={displayWebUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="block w-full break-all text-center text-sm font-medium text-sky-700 hover:underline"
                  >
                    {displayWebUrl}
                  </a>
                ) : null}
                {booth.trigger_text ? (
                  <p className="text-center text-xs text-muted-foreground">{booth.trigger_text}</p>
                ) : null}
                <div className="flex w-full flex-wrap justify-center gap-2">
                  {qrSrc ? (
                    <Button size="sm" variant="outline" className="gap-1.5" asChild>
                      <a href={qrSrc} target="_blank" rel="noreferrer" download={`expo-${booth.name || "booth"}-qr.png`}>
                        <Download className="size-3.5" /> Open / download QR
                      </a>
                    </Button>
                  ) : null}
                  {displayWebUrl ? (
                    <Button size="sm" variant="ghost" asChild>
                      <a href={displayWebUrl} target="_blank" rel="noreferrer">
                        Open scan landing
                      </a>
                    </Button>
                  ) : null}
                </div>
              </div>

              {webUrl || qrSrc ? (
                <div id="print" className="border-t pt-5">
                  <h3 className="mb-3 text-sm font-semibold">Print booth card</h3>
                  <ExpoBoothPrintCard
                    boothId={booth.id}
                    qrSrc={qrSrc}
                    webUrl={webUrl}
                    qrToken={booth.qr_token}
                    company={company || booth.company_display_name}
                    boothCode={boothCode || booth.booth_code}
                    eventName={exhibitionName || booth.exhibition_name || booth.name}
                    eventDates={venue || booth.venue || null}
                    companyWebsite={companyWebsite || booth.company_website}
                    contactEmail={representatives.find((r) => r.email?.trim())?.email || null}
                  />
                </div>
              ) : (
                <p className="border-t pt-4 text-sm text-muted-foreground">
                  Scan link missing for this booth — refresh the page or contact support.
                </p>
              )}
            </CardContent>
          </Card>
        </aside>
      </div>
    </div>
  );
}
