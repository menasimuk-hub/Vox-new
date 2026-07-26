import { createFileRoute, Link } from "@tanstack/react-router";
import {
  Briefcase,
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  Eye,
  FileUp,
  Package,
  Pencil,
  Plus,
  QrCode,
  Rocket,
  Target,
  Trash2,
  Upload,
  Link2,
  X,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Stepper, type WizardStepDef } from "@/components/create-wizard/stepper";
import { ExpoPayDialog } from "@/components/expo-pay-dialog";
import { ExpoScanChoosePreview, ExpoWaPhonePreview, ExpoWebPhonePreview } from "@/components/expo-phone-preview";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch, apiUploadFiles } from "@/lib/api";
import { canLaunchCampaigns, normalizeOrgRole } from "@/lib/org-roles";
import { useSession } from "@/lib/session";
import { cn } from "@/lib/utils";
import { waIndustryIcon } from "@/lib/wa-industry-icon";
import { useQuery, useQueryClient } from "@tanstack/react-query";

type Step = 1 | 2 | 3 | 4 | 5 | 6 | 7;

type Industry = { id: string; slug: string; name: string; addon_question?: string | null };
type Package = {
  id: string;
  name: string;
  tier: string;
  duration_days?: number;
  price_minor: number;
  currency: string;
  features: string[];
  is_featured?: boolean;
  lead_scoring_enabled?: boolean;
};
type QuestionOpt = {
  key: string;
  prompt: string;
  label: string;
  description?: string;
  matches_products?: boolean;
};
type AssetPurpose = "catalogue" | "price_list" | "product";

type AssetDraft = {
  id: string;
  title: string;
  short_description: string;
  source: "link" | "upload";
  external_url: string;
  storage_path: string;
  original_filename: string;
  match_keywords: string;
  kind: string;
  purpose: AssetPurpose;
  is_default: boolean;
};

const PURPOSE_LABELS: Record<AssetPurpose, string> = {
  catalogue: "Catalogue",
  price_list: "Price list",
  product: "Product",
};

const EXPO_STEPS: WizardStepDef[] = [
  { id: 1, title: "Industry", icon: Briefcase },
  { id: 2, title: "Event", icon: CalendarDays },
  { id: 3, title: "Questions", icon: Target },
  { id: 4, title: "Products", icon: FileUp },
  { id: 5, title: "Preview", icon: Eye },
  { id: 6, title: "Package", icon: Package },
  { id: 7, title: "Activate", icon: Rocket },
];

const DEFAULT_Q_KEYS = ["interest", "role", "timeline", "follow_up", "consent_info"];

function defaultFreeGiftText(companyName: string) {
  const name = companyName.trim();
  if (!name) {
    return "Please collect your free gift from our stand team — thanks for completing the short questionnaire!";
  }
  return `Please collect your free gift from ${name}'s stand team — thanks for completing the short questionnaire!`;
}

function newAssetId() {
  return `a-${Math.random().toString(36).slice(2, 10)}`;
}

export const Route = createFileRoute("/_app/expo/new")({
  head: () => ({ meta: [{ title: "Create Expo booth — VoxBulk" }] }),
  component: CreateExpoBooth,
});

function CreateExpoBooth() {
  const { session } = useSession();
  const queryClient = useQueryClient();
  const role = normalizeOrgRole(session?.profile?.role);
  const canCreate = canLaunchCampaigns(role);
  const fileInputRef = React.useRef<HTMLInputElement>(null);

  const industriesQ = useQuery({
    queryKey: ["expo", "industries"],
    queryFn: () => apiFetch<{ items: Industry[] }>("/expo/catalog/industries"),
  });
  const packagesQ = useQuery({
    queryKey: ["expo", "packages"],
    queryFn: () => apiFetch<{ items: Package[] }>("/expo/packages?zone=gb"),
  });
  const questionsQ = useQuery({
    queryKey: ["expo", "questions"],
    queryFn: () => apiFetch<{ items: QuestionOpt[] }>("/expo/catalog/questions"),
  });

  const [step, setStep] = React.useState<Step>(1);
  const [industryId, setIndustryId] = React.useState("");
  const [exhibitionName, setExhibitionName] = React.useState("");
  const [venue, setVenue] = React.useState("");
  const [boothCode, setBoothCode] = React.useState("");
  const [company, setCompany] = React.useState(session?.org?.name || "");
  const [selectedQKeys, setSelectedQKeys] = React.useState<string[]>([...DEFAULT_Q_KEYS]);
  const [includeAddon, setIncludeAddon] = React.useState(true);
  const [contactCapture, setContactCapture] = React.useState<"offer_both" | "manual_only" | "card_only">(
    "offer_both",
  );
  const [freeGiftEnabled, setFreeGiftEnabled] = React.useState(false);
  const [freeGiftCustomized, setFreeGiftCustomized] = React.useState(false);
  const [freeGiftText, setFreeGiftText] = React.useState(() =>
    defaultFreeGiftText(session?.org?.name || ""),
  );

  React.useEffect(() => {
    if (freeGiftCustomized) return;
    setFreeGiftText(defaultFreeGiftText(company));
  }, [company, freeGiftCustomized]);
  const [savedAssets, setSavedAssets] = React.useState<AssetDraft[]>([]);
  const [draft, setDraft] = React.useState<Omit<AssetDraft, "id">>({
    title: "",
    short_description: "",
    source: "upload",
    external_url: "",
    storage_path: "",
    original_filename: "",
    match_keywords: "",
    kind: "pdf",
    purpose: "catalogue",
    is_default: true,
  });
  const [uploading, setUploading] = React.useState(false);
  const [editingId, setEditingId] = React.useState<string | null>(null);
  const [packageId, setPackageId] = React.useState("");
  const [packageStartDate, setPackageStartDate] = React.useState(() => {
    const d = new Date();
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  });
  const [previewChannel, setPreviewChannel] = React.useState<"scan" | "web" | "wa">("scan");
  const [webTemplate] = React.useState("Default template");
  const [saving, setSaving] = React.useState(false);
  const [created, setCreated] = React.useState<{
    id: string;
    qr_image_url?: string;
    trigger_text?: string;
    whatsapp_url?: string;
    is_paid?: boolean;
    is_live?: boolean;
    payment_status?: string;
    activated_at?: string | null;
  } | null>(null);
  const [payOpen, setPayOpen] = React.useState(false);

  const industries = industriesQ.data?.items || [];
  const packages = packagesQ.data?.items || [];
  const industry = industries.find((i) => i.id === industryId);

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

  const selectedPrompts = questionBank.filter((q) => selectedQKeys.includes(q.key)).map((q) => q.prompt);

  const selectedPackage = packages.find((p) => p.id === packageId);
  const packageDays = Math.max(1, selectedPackage?.duration_days || 1);
  const packageEndDate = React.useMemo(() => {
    if (!packageStartDate) return "";
    const start = new Date(`${packageStartDate}T12:00:00`);
    if (Number.isNaN(start.getTime())) return "";
    start.setDate(start.getDate() + packageDays - 1);
    const y = start.getFullYear();
    const m = String(start.getMonth() + 1).padStart(2, "0");
    const day = String(start.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  }, [packageDays, packageStartDate]);

  const draftReady =
    Boolean(draft.title.trim()) &&
    ((draft.source === "link" && Boolean(draft.external_url.trim())) ||
      (draft.source === "upload" && Boolean(draft.storage_path.trim())));

  const canNext: Record<Step, boolean> = {
    1: Boolean(industryId),
    2: Boolean(exhibitionName.trim() && company.trim()),
    3: selectedQKeys.length > 0,
    4: true,
    5: true,
    6: Boolean(packageId),
    7: true,
  };

  const addOrUpdateProduct = () => {
    if (!draftReady) {
      toast.error("Add a title and upload a file or paste a link");
      return;
    }
    const item: AssetDraft = { ...draft, id: editingId || newAssetId() };
    setSavedAssets((rows) => {
      const without = rows.filter((r) => r.id !== item.id);
      const next = [...without, item];
      if (item.is_default) {
        return next.map((r) => ({ ...r, is_default: r.id === item.id }));
      }
      if (!next.some((r) => r.is_default)) {
        next[0] = { ...next[0], is_default: true };
      }
      return next;
    });
    const nextPurpose: AssetPurpose =
      item.purpose === "catalogue"
        ? "price_list"
        : item.purpose === "price_list"
          ? "product"
          : "product";
    setDraft({
      title: "",
      short_description: "",
      source: "upload",
      external_url: "",
      storage_path: "",
      original_filename: "",
      match_keywords: "",
      kind: "pdf",
      // After saving a catalogue, default the next file to price list so both are easy to add.
      purpose: nextPurpose,
      is_default: false,
    });
    setEditingId(null);
    toast.success(editingId ? "Product updated" : "Product added");
  };

  const uploadFile = async (file: File) => {
    setUploading(true);
    try {
      const res = (await apiUploadFiles("/expo/assets/upload", [file], "file")) as {
        item?: { storage_path?: string; original_filename?: string; kind?: string };
      };
      const item = res?.item || {};
      setDraft((d) => ({
        ...d,
        source: "upload",
        storage_path: String(item.storage_path || ""),
        original_filename: String(item.original_filename || file.name),
        kind: String(item.kind || "pdf"),
        title: d.title.trim() || String(item.original_filename || file.name),
        external_url: "",
      }));
      toast.success("File uploaded");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  if (!canCreate) {
    return (
      <Card>
        <CardContent className="p-8 text-center text-sm text-muted-foreground">
          Your role cannot create Expo booths. Ask an owner or manager.
        </CardContent>
      </Card>
    );
  }

  const activate = async () => {
    const assets =
      savedAssets.length > 0
        ? savedAssets
        : draftReady
          ? [{ ...draft, id: newAssetId() }]
          : [];
    setSaving(true);
    try {
      const keys = [...selectedQKeys];
      if (includeAddon && industry?.addon_question && !keys.includes("industry_addon")) {
        keys.splice(Math.max(0, keys.indexOf("consent_info")), 0, "industry_addon");
      }
      const payload = {
        industry_id: industryId,
        exhibition_name: exhibitionName.trim(),
        venue: venue.trim() || null,
        booth_code: boothCode.trim() || exhibitionName.trim(),
        name: boothCode.trim() || exhibitionName.trim(),
        company_display_name: company.trim(),
        include_industry_addon: includeAddon,
        selected_question_keys: keys,
        contact_capture: contactCapture,
        free_gift_enabled: freeGiftEnabled,
        free_gift_text: freeGiftEnabled ? freeGiftText.trim() : null,
        package_id: packageId,
        start_date: packageStartDate,
        assets: assets.map((a, idx) => ({
          title: a.title.trim(),
          short_description: a.short_description.trim() || null,
          external_url: a.source === "link" ? a.external_url.trim() || null : null,
          storage_path: a.source === "upload" ? a.storage_path.trim() || null : null,
          match_keywords: a.match_keywords.trim() || null,
          kind: a.kind || (a.source === "upload" ? "pdf" : "link"),
          purpose: a.purpose || "product",
          is_default: a.is_default || idx === 0,
          sort_order: (idx + 1) * 10,
        })),
      };
      const res = await apiFetch<{ ok: boolean; item: typeof created & { id: string } }>("/expo/booths", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setCreated(res.item);
      setStep(7);
      // Seed Saved booths cache so the new QR appears immediately
      queryClient.setQueryData<{ ok: boolean; items: Array<typeof res.item> }>(["expo", "booths"], (prev) => {
        const items = prev?.items ? [...prev.items] : [];
        if (!items.some((b) => b.id === res.item.id)) {
          items.unshift(res.item);
        }
        return { ok: true, items };
      });
      await queryClient.invalidateQueries({ queryKey: ["expo"] });
      toast.success("Booth saved — pay to go live, or use up to 15 preview tests unpaid");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not create booth");
    } finally {
      setSaving(false);
    }
  };

  const waMessages = [
    {
      from: "user" as const,
      text: `Hi! I visited ${company || "your stand"} at ${boothCode || "Stand"} at ${exhibitionName || "the exhibition"}.`,
    },
    {
      from: "bot" as const,
      text:
        contactCapture === "card_only"
          ? "Please send a photo of your business card to continue."
          : contactCapture === "manual_only"
            ? "Thanks for stopping by — what's your full name?"
            : "Send a photo of your business card, or reply with your full name (photo skips name, company and mobile).",
    },
    ...(selectedPrompts[0]
      ? [
          { from: "user" as const, text: "Alex Carter" },
          { from: "bot" as const, text: selectedPrompts[0] },
        ]
      : []),
  ];

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="VoxBulk Expo"
        title="Create Expo booth"
        description="Set up your exhibition QR, qualifying questions, and product PDF library."
      />

      <Stepper
        steps={EXPO_STEPS}
        current={step}
        onStepClick={(n) => n <= step && setStep(n as Step)}
      />

      <div key={step} className="animate-fade-in">
        {step === 1 && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Choose your industry</CardTitle>
              <CardDescription>We'll tailor a suggested qualifying question for your stand.</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {industries.map((ind) => {
                const Icon = waIndustryIcon(ind.name, ind.slug);
                const selected = industryId === ind.id;
                return (
                  <button
                    key={ind.id}
                    type="button"
                    onClick={() => setIndustryId(ind.id)}
                    className={cn(
                      "group rounded-xl border p-4 text-left transition-all duration-200",
                      "hover:-translate-y-0.5 hover:border-primary/50 hover:shadow-md",
                      selected
                        ? "border-primary bg-primary/5 shadow-md shadow-primary/10 ring-2 ring-primary/20"
                        : "border-border bg-background",
                    )}
                  >
                    <div className="flex items-start gap-3">
                      <span
                        className={cn(
                          "grid size-10 place-items-center rounded-xl border transition",
                          selected
                            ? "border-primary/30 bg-primary text-primary-foreground"
                            : "border-border bg-muted/40 text-muted-foreground group-hover:border-primary/30 group-hover:text-primary",
                        )}
                      >
                        <Icon className="size-5" />
                      </span>
                      <div className="min-w-0">
                        <p className="font-medium">{ind.name}</p>
                        {ind.addon_question ? (
                          <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{ind.addon_question}</p>
                        ) : null}
                      </div>
                    </div>
                  </button>
                );
              })}
            </CardContent>
          </Card>
        )}

        {step === 2 && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Event & booth</CardTitle>
              <CardDescription>Two fields per row — keep stand details clear for the QR message.</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label>Exhibition name</Label>
                <Input
                  value={exhibitionName}
                  onChange={(e) => setExhibitionName(e.target.value)}
                  placeholder="UK Construction Week"
                />
              </div>
              <div className="space-y-2">
                <Label>Venue</Label>
                <Input value={venue} onChange={(e) => setVenue(e.target.value)} placeholder="Excel London" />
              </div>
              <div className="space-y-2">
                <Label>Booth / stand code</Label>
                <Input value={boothCode} onChange={(e) => setBoothCode(e.target.value)} placeholder="H45" />
              </div>
              <div className="space-y-2">
                <Label>Company name on WhatsApp</Label>
                <Input value={company} onChange={(e) => setCompany(e.target.value)} placeholder="Acme Supplies" />
              </div>
            </CardContent>
          </Card>
        )}

        {step === 3 && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Qualifying questions</CardTitle>
              <CardDescription>
                Fixed contact first — visitors see this as the first WhatsApp / web message:
                <span className="font-medium text-foreground"> photo of a business card</span>, or type name /
                company (and mobile on web). Choose which options are allowed below.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="rounded-xl border bg-muted/20 p-4">
                <p className="text-sm font-medium">Fixed · Contact capture</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  WhatsApp & web: visitor can send a business-card photo (skips name, company, mobile) or type
                  details. Web always collects mobile when typing.
                </p>
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
                            setSelectedQKeys((keys) =>
                              v ? [...keys, q.key] : keys.filter((k) => k !== q.key),
                            );
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
                          {q.description ? (
                            <span className="mt-1 block text-[11px] text-muted-foreground/80">{q.description}</span>
                          ) : null}
                        </span>
                      </label>
                    );
                  })}
                </div>
                {industry?.addon_question ? (
                  <label className="mt-3 flex items-center gap-2 text-sm">
                    <Checkbox checked={includeAddon} onCheckedChange={(v) => setIncludeAddon(Boolean(v))} />
                    Include industry question: {industry.addon_question}
                  </label>
                ) : null}
              </div>

              <div className="rounded-xl border p-4">
                <label className="flex items-start gap-3">
                  <Checkbox
                    checked={freeGiftEnabled}
                    onCheckedChange={(v) => {
                      const on = Boolean(v);
                      setFreeGiftEnabled(on);
                      if (on && !freeGiftCustomized) {
                        setFreeGiftText(defaultFreeGiftText(company));
                      }
                    }}
                    className="mt-0.5"
                  />
                  <span>
                    <span className="font-medium">Offer a free gift after the questionnaire</span>
                    <span className="mt-0.5 block text-xs text-muted-foreground">
                      After the thank-you message, tell visitors how to collect their gift. Default text includes your
                      company name so visitors know which stand it is — you can edit it anytime.
                    </span>
                  </span>
                </label>
                {freeGiftEnabled ? (
                  <Textarea
                    className="mt-3"
                    value={freeGiftText}
                    onChange={(e) => {
                      setFreeGiftCustomized(true);
                      setFreeGiftText(e.target.value);
                    }}
                    rows={2}
                  />
                ) : null}
              </div>
            </CardContent>
          </Card>
        )}

        {step === 4 && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Products & files</CardTitle>
              <CardDescription>
                Optional — add catalogue, price list, or product files. Visitors who consent get catalogue/price list
                downloads; product sheets can match interest. Skip to capture leads only.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              {savedAssets.length > 0 ? (
                <ul className="space-y-2">
                  {savedAssets.map((a) => (
                    <li
                      key={a.id}
                      className="flex flex-wrap items-center justify-between gap-2 rounded-xl border px-3 py-2"
                    >
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium">
                          {a.title}
                          {a.is_default ? (
                            <span className="ml-2 text-[10px] font-normal uppercase text-primary">Default</span>
                          ) : null}
                        </p>
                        <p className="truncate text-xs text-muted-foreground">
                          {PURPOSE_LABELS[a.purpose] || "Product"}
                          {" · "}
                          {a.source === "upload"
                            ? a.original_filename || a.kind
                            : a.external_url}
                        </p>
                      </div>
                      <div className="flex gap-1">
                        <Button
                          type="button"
                          size="icon"
                          variant="ghost"
                          aria-label="Edit"
                          onClick={() => {
                            setEditingId(a.id);
                            setDraft({
                              title: a.title,
                              short_description: a.short_description,
                              source: a.source,
                              external_url: a.external_url,
                              storage_path: a.storage_path,
                              original_filename: a.original_filename,
                              match_keywords: a.match_keywords,
                              kind: a.kind,
                              purpose: a.purpose || "product",
                              is_default: a.is_default,
                            });
                          }}
                        >
                          <Pencil className="size-4" />
                        </Button>
                        <Button
                          type="button"
                          size="icon"
                          variant="ghost"
                          aria-label="Delete"
                          onClick={() => setSavedAssets((rows) => rows.filter((r) => r.id !== a.id))}
                        >
                          <Trash2 className="size-4" />
                        </Button>
                      </div>
                    </li>
                  ))}
                </ul>
              ) : null}

              <div className="grid gap-3 rounded-xl border p-4">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-sm font-medium">{editingId ? "Edit product" : "Add a product"}</p>
                  {editingId ? (
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      onClick={() => {
                        setEditingId(null);
                        setDraft({
                          title: "",
                          short_description: "",
                          source: "upload",
                          external_url: "",
                          storage_path: "",
                          original_filename: "",
                          match_keywords: "",
                          kind: "pdf",
                          purpose: "product",
                          is_default: false,
                        });
                      }}
                    >
                      <X className="mr-1 size-3.5" /> Cancel
                    </Button>
                  ) : null}
                </div>
                <div className="space-y-2">
                  <Label>Type</Label>
                  <select
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm"
                    value={draft.purpose}
                    onChange={(e) =>
                      setDraft((d) => ({
                        ...d,
                        purpose: (e.target.value as AssetPurpose) || "product",
                      }))
                    }
                    required
                  >
                    <option value="catalogue">Catalogue</option>
                    <option value="price_list">Price list</option>
                    <option value="product">Product sheet</option>
                  </select>
                  <p className="text-xs text-muted-foreground">
                    Catalogue and price list are offered when visitors consent to receive info.
                  </p>
                </div>
                <div className="space-y-2">
                  <Label>Title</Label>
                  <Input
                    value={draft.title}
                    onChange={(e) => setDraft((d) => ({ ...d, title: e.target.value }))}
                    placeholder="2026 Price List"
                  />
                </div>
                <div className="space-y-2">
                  <Label>Match keywords (optional)</Label>
                  <Input
                    value={draft.match_keywords}
                    onChange={(e) => setDraft((d) => ({ ...d, match_keywords: e.target.value }))}
                    placeholder="price, pricing, catalogue, brochure"
                  />
                  <p className="text-xs text-muted-foreground">
                    Used when visitors ask for a price list or catalogue — match these words to this file.
                  </p>
                </div>
                <div className="space-y-2">
                  <Label>Short description</Label>
                  <Textarea
                    value={draft.short_description}
                    onChange={(e) => setDraft((d) => ({ ...d, short_description: e.target.value }))}
                    placeholder="Bulk & trade pricing for UK distributors"
                    rows={2}
                  />
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button
                    type="button"
                    size="sm"
                    variant={draft.source === "upload" ? "default" : "outline"}
                    disabled={uploading}
                    onClick={() => {
                      setDraft((d) => ({
                        ...d,
                        source: "upload",
                        external_url: "",
                        kind: d.kind || "pdf",
                      }));
                      fileInputRef.current?.click();
                    }}
                  >
                    <Upload className="mr-1.5 size-3.5" />
                    {uploading ? "Uploading…" : draft.storage_path ? "Replace file" : "Upload file"}
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant={draft.source === "link" ? "default" : "outline"}
                    onClick={() =>
                      setDraft((d) => ({
                        ...d,
                        source: "link",
                        storage_path: "",
                        original_filename: "",
                        kind: "link",
                      }))
                    }
                  >
                    <Link2 className="mr-1.5 size-3.5" />
                    Paste link
                  </Button>
                </div>
                <input
                  ref={fileInputRef}
                  type="file"
                  className="hidden"
                  accept=".pdf,.png,.jpg,.jpeg,.webp,.gif,.xls,.xlsx,.csv,application/pdf,image/*,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) void uploadFile(file);
                  }}
                />
                {draft.source === "upload" ? (
                  <p className="text-xs text-muted-foreground">
                    PDF, image or Excel (max 20 MB).
                    {draft.storage_path ? ` Uploaded: ${draft.original_filename || "file"}` : ""}
                  </p>
                ) : (
                  <div className="space-y-2">
                    <Label>PDF / brochure / Excel URL</Label>
                    <Input
                      value={draft.external_url}
                      onChange={(e) => setDraft((d) => ({ ...d, external_url: e.target.value }))}
                      placeholder="https://…"
                    />
                  </div>
                )}
                <label className="flex items-center gap-2 text-sm">
                  <Checkbox
                    checked={draft.is_default}
                    onCheckedChange={(v) => setDraft((d) => ({ ...d, is_default: Boolean(v) }))}
                  />
                  Default when visitor just says “send info”
                </label>
                <Button type="button" onClick={addOrUpdateProduct} disabled={!draftReady || uploading}>
                  <Plus className="mr-1.5 size-4" />
                  {editingId ? "Save changes" : "Add to product list"}
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {step === 5 && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Preview journey</CardTitle>
              <CardDescription>
                Same as the live QR scan: visitors choose WhatsApp or Web (default template). Switch tabs to preview
                each path.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  size="sm"
                  variant={previewChannel === "scan" ? "default" : "outline"}
                  onClick={() => setPreviewChannel("scan")}
                >
                  Scan choice
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant={previewChannel === "web" ? "default" : "outline"}
                  onClick={() => setPreviewChannel("web")}
                >
                  Web form
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant={previewChannel === "wa" ? "default" : "outline"}
                  onClick={() => setPreviewChannel("wa")}
                >
                  WhatsApp
                </Button>
                <span className="self-center text-xs text-muted-foreground">
                  Default template: {webTemplate}
                </span>
              </div>
              <div className="grid gap-6 lg:grid-cols-2 lg:justify-items-center">
                <div className={cn(previewChannel !== "scan" && "opacity-60 lg:opacity-100")}>
                  <ExpoScanChoosePreview
                    companyName={company || "Your stand"}
                    eventName={exhibitionName}
                    templateName={webTemplate}
                  />
                </div>
                <div
                  className={cn(
                    "flex flex-col items-center gap-3",
                    previewChannel === "scan" && "opacity-60 lg:opacity-100",
                  )}
                >
                  {previewChannel === "wa" ? (
                    <ExpoWaPhonePreview businessName={company || "Your stand"} messages={waMessages} />
                  ) : (
                    <ExpoWebPhonePreview
                      companyName={company}
                      eventName={exhibitionName}
                      contactHint={
                        contactCapture === "card_only"
                          ? "Capture a business card photo to continue."
                          : "Capture a business card photo, or enter name, company and mobile."
                      }
                      questions={selectedPrompts}
                      templateName={webTemplate}
                    />
                  )}
                  <div className="rounded-xl border bg-background/80 p-3 text-center shadow-sm">
                    <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                      Preview QR
                    </p>
                    <img
                      src={`https://api.qrserver.com/v1/create-qr-code/?size=120x120&data=${encodeURIComponent(
                        `https://voxbulk.com/expo/preview-${encodeURIComponent((company || "stand").slice(0, 24))}`,
                      )}`}
                      alt="Expo web QR preview"
                      className="mx-auto mt-2 size-16 rounded-md border bg-white p-1"
                    />
                    <p className="mt-1.5 max-w-[160px] text-[10px] leading-snug text-muted-foreground">
                      Live QR opens the scan landing (WhatsApp or Web) — same as Customer Feedback.
                    </p>
                  </div>
                </div>
              </div>
              {freeGiftEnabled ? (
                <p className="text-center text-xs text-muted-foreground">
                  Closing includes thank-you + free gift instructions.
                </p>
              ) : null}
            </CardContent>
          </Card>
        )}

        {step === 6 && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Choose package</CardTitle>
              <CardDescription>How many days should this booth QR stay active?</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-3 sm:grid-cols-3">
              {packages.map((pkg) => {
                const days = pkg.duration_days || 1;
                const featured = Boolean(pkg.is_featured);
                return (
                  <button
                    key={pkg.id}
                    type="button"
                    onClick={() => setPackageId(pkg.id)}
                    className={cn(
                      "relative rounded-xl border p-4 text-left transition hover:-translate-y-0.5 hover:shadow-md",
                      packageId === pkg.id
                        ? "border-primary bg-primary/5 ring-2 ring-primary/20"
                        : "hover:border-primary/40",
                      featured && packageId !== pkg.id && "border-primary/25",
                    )}
                  >
                    {featured ? (
                      <span className="absolute -top-2 left-3 rounded-full bg-primary px-2 py-0.5 text-[10px] font-semibold text-primary-foreground">
                        Most popular
                      </span>
                    ) : null}
                    <p className="font-medium">{pkg.name}</p>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      Active for {days} day{days === 1 ? "" : "s"}
                    </p>
                    <p className="mt-2 text-lg font-semibold">
                      £{(pkg.price_minor / 100).toFixed(0)}
                      <span className="text-sm font-normal text-muted-foreground"> / exhibition</span>
                    </p>
                    <ul className="mt-2 space-y-1 text-xs text-muted-foreground">
                      {(pkg.features || []).slice(0, 4).map((f) => (
                        <li key={f} className="flex gap-1.5">
                          <span className="text-primary">✓</span> {f}
                        </li>
                      ))}
                    </ul>
                  </button>
                );
              })}
            </CardContent>
          </Card>
        )}

        {step === 7 && (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <QrCode className="size-4 text-primary" /> Activate QR
              </CardTitle>
              <CardDescription>
                Set when the package starts. End date is calculated from the package length. Before the start
                date you get 15 mobile preview tests.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {!created ? (
                <>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <div className="space-y-1.5">
                      <Label htmlFor="expo-start-date">Package start date</Label>
                      <Input
                        id="expo-start-date"
                        type="date"
                        value={packageStartDate}
                        onChange={(e) => setPackageStartDate(e.target.value)}
                      />
                    </div>
                    <div className="space-y-1.5">
                      <Label htmlFor="expo-end-date">Auto end date</Label>
                      <Input id="expo-end-date" type="date" value={packageEndDate} readOnly disabled />
                      <p className="text-xs text-muted-foreground">
                        {selectedPackage
                          ? `${selectedPackage.name} · ${packageDays} day${packageDays === 1 ? "" : "s"}`
                          : "Choose a package first"}
                      </p>
                    </div>
                  </div>
                  <div className="rounded-lg border bg-muted/40 px-3 py-2 text-sm text-muted-foreground">
                    <p className="font-medium text-foreground">Save unpaid · pay to go live</p>
                    <p className="mt-0.5 text-xs">
                      Save your design and QR now. You get up to 15 preview tests unpaid. The booth goes live for
                      the package window only after Stripe or Airwallex payment.
                    </p>
                  </div>
                  <p className="text-sm text-muted-foreground">
                    Creates your booth, WhatsApp trigger text, and downloadable QR (status: Unpaid).
                  </p>
                  <Button onClick={() => void activate()} disabled={saving || !packageId || !packageStartDate}>
                    {saving ? "Saving…" : "Save Expo booth"}
                  </Button>
                </>
              ) : (
                <div className="flex flex-col items-start gap-4 sm:flex-row">
                  {created.qr_image_url ? (
                    <img
                      src={created.qr_image_url}
                      alt="Expo QR"
                      className="size-40 rounded-xl border bg-white p-2"
                    />
                  ) : null}
                  <div className="space-y-2 text-sm">
                    <p className="font-medium">
                      {created.is_paid || created.payment_status === "paid"
                        ? created.is_live
                          ? "Booth live"
                          : "Booth paid — waiting for start date"
                        : "Booth saved (unpaid)"}
                    </p>
                    <p className="text-muted-foreground">
                      Window {packageStartDate}
                      {packageEndDate ? ` → ${packageEndDate}` : ""} ·{" "}
                      {created.is_paid || created.payment_status === "paid"
                        ? "Paid — live after start date"
                        : "Pay to go live · 15 preview tests unpaid"}
                    </p>
                    <p className="max-w-md text-muted-foreground">{created.trigger_text}</p>
                    <div className="flex flex-wrap gap-2">
                      {!(created.is_paid || created.payment_status === "paid") ? (
                        <Button size="sm" onClick={() => setPayOpen(true)}>
                          Pay with card
                        </Button>
                      ) : null}
                      <Button asChild variant="outline" size="sm">
                        <Link to="/expo">View saved booths</Link>
                      </Button>
                      <Button asChild size="sm" variant={created.is_paid ? "outline" : "ghost"}>
                        <Link to="/expo/leads" search={{ booth_id: created.id }}>
                          View leads
                        </Link>
                      </Button>
                    </div>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        )}
      </div>

      <ExpoPayDialog
        boothId={created?.id || null}
        boothName={boothCode.trim() || exhibitionName.trim() || company.trim() || "Expo booth"}
        open={payOpen}
        onOpenChange={setPayOpen}
        onPaid={(booth) => {
          if (booth && created) {
            setCreated({
              ...created,
              is_paid: Boolean(booth.is_paid ?? true),
              is_live: Boolean(booth.is_live),
              payment_status: String(booth.payment_status || "paid"),
              activated_at: (booth.activated_at as string | null | undefined) ?? created.activated_at,
            });
          }
          void queryClient.invalidateQueries({ queryKey: ["expo"] });
        }}
      />

      {step < 7 || !created ? (
        <div className="flex items-center justify-between gap-3">
          <Button
            type="button"
            variant="outline"
            disabled={step === 1}
            onClick={() => setStep((s) => (s > 1 ? ((s - 1) as Step) : s))}
          >
            <ChevronLeft className="mr-1 size-4" /> Back
          </Button>
          {step < 7 ? (
            <Button
              type="button"
              disabled={!canNext[step]}
              onClick={() => {
                if (step === 4 && draftReady && savedAssets.length === 0) {
                  addOrUpdateProduct();
                }
                setStep((s) => (s < 7 ? ((s + 1) as Step) : s));
              }}
            >
              Next <ChevronRight className="ml-1 size-4" />
            </Button>
          ) : (
            <Button type="button" disabled={saving || !packageId || Boolean(created)} onClick={() => void activate()}>
              {saving ? "Saving…" : "Save booth"}
            </Button>
          )}
        </div>
      ) : null}
    </div>
  );
}
