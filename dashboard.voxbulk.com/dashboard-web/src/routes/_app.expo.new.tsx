import { createFileRoute, Link } from "@tanstack/react-router";
import { Briefcase, ChevronLeft, ChevronRight, FileUp, QrCode, Rocket, Target } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch } from "@/lib/api";
import { canLaunchCampaigns, normalizeOrgRole } from "@/lib/org-roles";
import { useSession } from "@/lib/session";
import { cn } from "@/lib/utils";
import { useQuery } from "@tanstack/react-query";

type Step = 1 | 2 | 3 | 4 | 5 | 6 | 7;

type Industry = { id: string; slug: string; name: string; addon_question?: string | null };
type Package = {
  id: string;
  name: string;
  tier: string;
  price_minor: number;
  currency: string;
  features: string[];
  is_featured?: boolean;
  lead_scoring_enabled?: boolean;
};
type AssetDraft = {
  title: string;
  short_description: string;
  external_url: string;
  match_keywords: string;
  kind: string;
  is_default: boolean;
};

export const Route = createFileRoute("/_app/expo/new")({
  head: () => ({ meta: [{ title: "Create Expo booth — VoxBulk" }] }),
  component: CreateExpoBooth,
});

function CreateExpoBooth() {
  const { session } = useSession();
  const role = normalizeOrgRole(session?.profile?.role);
  const canCreate = canLaunchCampaigns(role);

  const industriesQ = useQuery({
    queryKey: ["expo", "industries"],
    queryFn: () => apiFetch<{ items: Industry[] }>("/expo/catalog/industries"),
  });
  const packagesQ = useQuery({
    queryKey: ["expo", "packages"],
    queryFn: () => apiFetch<{ items: Package[] }>("/expo/packages?zone=gb"),
  });

  const [step, setStep] = React.useState<Step>(1);
  const [industryId, setIndustryId] = React.useState("");
  const [exhibitionName, setExhibitionName] = React.useState("");
  const [venue, setVenue] = React.useState("");
  const [boothCode, setBoothCode] = React.useState("");
  const [company, setCompany] = React.useState(session?.org?.name || "");
  const [includeAddon, setIncludeAddon] = React.useState(true);
  const [assets, setAssets] = React.useState<AssetDraft[]>([
    { title: "", short_description: "", external_url: "", match_keywords: "", kind: "pdf", is_default: true },
  ]);
  const [packageId, setPackageId] = React.useState("");
  const [saving, setSaving] = React.useState(false);
  const [created, setCreated] = React.useState<{
    id: string;
    qr_image_url?: string;
    trigger_text?: string;
    whatsapp_url?: string;
  } | null>(null);

  const industries = industriesQ.data?.items || [];
  const packages = packagesQ.data?.items || [];
  const industry = industries.find((i) => i.id === industryId);

  const canNext: Record<Step, boolean> = {
    1: Boolean(industryId),
    2: Boolean(exhibitionName.trim() && company.trim()),
    3: true,
    4: assets.some((a) => a.title.trim() && (a.external_url.trim() || a.short_description.trim())),
    5: true,
    6: Boolean(packageId),
    7: true,
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
    setSaving(true);
    try {
      const payload = {
        industry_id: industryId,
        exhibition_name: exhibitionName.trim(),
        venue: venue.trim() || null,
        booth_code: boothCode.trim() || exhibitionName.trim(),
        name: boothCode.trim() || exhibitionName.trim(),
        company_display_name: company.trim(),
        include_industry_addon: includeAddon,
        package_id: packageId,
        assets: assets
          .filter((a) => a.title.trim())
          .map((a, idx) => ({
            title: a.title.trim(),
            short_description: a.short_description.trim() || null,
            external_url: a.external_url.trim() || null,
            match_keywords: a.match_keywords.trim() || null,
            kind: a.kind || "pdf",
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
      toast.success("Expo booth activated");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not create booth");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="VoxBulk Expo"
        title="Create Expo booth"
        description="Set up your exhibition QR, qualifying questions, and product PDF library."
      />

      <Stepper current={step} onJump={(n) => n < step && setStep(n as Step)} />

      <div key={step} className="animate-fade-in">
        {step === 1 && (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Briefcase className="size-4 text-primary" /> Step 1 · Choose your industry
              </CardTitle>
            </CardHeader>
            <CardContent className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {industries.map((ind) => (
                <button
                  key={ind.id}
                  type="button"
                  onClick={() => setIndustryId(ind.id)}
                  className={cn(
                    "rounded-xl border p-4 text-left transition",
                    industryId === ind.id ? "border-primary bg-primary/5" : "hover:border-primary/40",
                  )}
                >
                  <p className="font-medium">{ind.name}</p>
                  {ind.addon_question ? (
                    <p className="mt-1 text-xs text-muted-foreground line-clamp-2">{ind.addon_question}</p>
                  ) : null}
                </button>
              ))}
            </CardContent>
          </Card>
        )}

        {step === 2 && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Step 2 · Event & booth</CardTitle>
            </CardHeader>
            <CardContent className="grid max-w-xl gap-4">
              <div className="space-y-2">
                <Label>Exhibition name</Label>
                <Input value={exhibitionName} onChange={(e) => setExhibitionName(e.target.value)} placeholder="UK Construction Week 2026" />
              </div>
              <div className="space-y-2">
                <Label>Venue (optional)</Label>
                <Input value={venue} onChange={(e) => setVenue(e.target.value)} placeholder="NEC Birmingham" />
              </div>
              <div className="space-y-2">
                <Label>Stand / booth code</Label>
                <Input value={boothCode} onChange={(e) => setBoothCode(e.target.value)} placeholder="H45" />
              </div>
              <div className="space-y-2">
                <Label>Company display name</Label>
                <Input value={company} onChange={(e) => setCompany(e.target.value)} />
              </div>
            </CardContent>
          </Card>
        )}

        {step === 3 && (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Target className="size-4 text-primary" /> Step 3 · Qualifying questions
              </CardTitle>
              <CardDescription>Universal questions are included. Optionally add your industry question.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
                <li>What’s your name?</li>
                <li>Which company do you represent?</li>
                <li>What are you interested in right now?</li>
                <li>When are you planning to decide?</li>
                <li>Would you like our latest information?</li>
              </ul>
              {industry?.addon_question ? (
                <label className="flex items-start gap-3 rounded-lg border p-3 text-sm">
                  <Checkbox checked={includeAddon} onCheckedChange={(v) => setIncludeAddon(Boolean(v))} />
                  <span>
                    <span className="font-medium">Include industry question</span>
                    <span className="mt-1 block text-muted-foreground">{industry.addon_question}</span>
                  </span>
                </label>
              ) : null}
            </CardContent>
          </Card>
        )}

        {step === 4 && (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <FileUp className="size-4 text-primary" /> Step 4 · Products & files
              </CardTitle>
              <CardDescription>
                Add up to 5 products. When a visitor says what they want, AI matches or sends a numbered list.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {assets.map((asset, idx) => (
                <div key={idx} className="grid gap-3 rounded-xl border p-4">
                  <div className="space-y-2">
                    <Label>Title</Label>
                    <Input
                      value={asset.title}
                      onChange={(e) =>
                        setAssets((rows) => rows.map((r, i) => (i === idx ? { ...r, title: e.target.value } : r)))
                      }
                      placeholder="2026 Price List"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Short description</Label>
                    <Textarea
                      value={asset.short_description}
                      onChange={(e) =>
                        setAssets((rows) =>
                          rows.map((r, i) => (i === idx ? { ...r, short_description: e.target.value } : r)),
                        )
                      }
                      placeholder="Bulk & trade pricing for UK distributors"
                      rows={2}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>PDF / video URL</Label>
                    <Input
                      value={asset.external_url}
                      onChange={(e) =>
                        setAssets((rows) => rows.map((r, i) => (i === idx ? { ...r, external_url: e.target.value } : r)))
                      }
                      placeholder="https://…"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Match keywords (optional)</Label>
                    <Input
                      value={asset.match_keywords}
                      onChange={(e) =>
                        setAssets((rows) =>
                          rows.map((r, i) => (i === idx ? { ...r, match_keywords: e.target.value } : r)),
                        )
                      }
                      placeholder="price, bulk, pricing"
                    />
                  </div>
                  <label className="flex items-center gap-2 text-sm">
                    <Checkbox
                      checked={asset.is_default}
                      onCheckedChange={(v) =>
                        setAssets((rows) =>
                          rows.map((r, i) => ({
                            ...r,
                            is_default: i === idx ? Boolean(v) : Boolean(v) ? false : r.is_default,
                          })),
                        )
                      }
                    />
                    Default when visitor just says “send info”
                  </label>
                </div>
              ))}
              {assets.length < 5 ? (
                <Button
                  type="button"
                  variant="outline"
                  onClick={() =>
                    setAssets((rows) => [
                      ...rows,
                      {
                        title: "",
                        short_description: "",
                        external_url: "",
                        match_keywords: "",
                        kind: "pdf",
                        is_default: false,
                      },
                    ])
                  }
                >
                  Add another product
                </Button>
              ) : null}
            </CardContent>
          </Card>
        )}

        {step === 5 && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Step 5 · Preview journey</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm text-muted-foreground">
              <p>1. Visitor scans QR → opens WhatsApp with welcome trigger</p>
              <p>2. AI asks name → company → interest → timeline → consent</p>
              <p>3. Interest matched to your products → PDF link or numbered list</p>
              <p>4. Lead scored Hot / Warm / Cold and saved to your results</p>
            </CardContent>
          </Card>
        )}

        {step === 6 && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Step 6 · Choose package</CardTitle>
              <CardDescription>Per-exhibition pricing: Starter £49 · Pro £99 · Premium £149</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-3 md:grid-cols-3">
              {packages.map((pkg) => (
                <button
                  key={pkg.id}
                  type="button"
                  onClick={() => setPackageId(pkg.id)}
                  className={cn(
                    "rounded-xl border p-4 text-left",
                    packageId === pkg.id ? "border-primary bg-primary/5" : "hover:border-primary/40",
                    pkg.is_featured && "ring-1 ring-primary/30",
                  )}
                >
                  <p className="font-semibold">{pkg.name}</p>
                  <p className="mt-1 text-2xl font-semibold tabular-nums">
                    {(pkg.price_minor / 100).toLocaleString("en-GB", {
                      style: "currency",
                      currency: pkg.currency || "GBP",
                      maximumFractionDigits: 0,
                    })}
                  </p>
                  <ul className="mt-3 space-y-1 text-xs text-muted-foreground">
                    {(pkg.features || []).slice(0, 5).map((f) => (
                      <li key={f}>• {f}</li>
                    ))}
                  </ul>
                </button>
              ))}
            </CardContent>
          </Card>
        )}

        {step === 7 && (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Rocket className="size-4 text-primary" /> Step 7 · Activate QR
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {!created ? (
                <Button onClick={() => void activate()} disabled={saving || !canNext[6]}>
                  {saving ? "Activating…" : "Activate Expo booth"}
                </Button>
              ) : (
                <div className="space-y-4">
                  {created.qr_image_url ? (
                    <img src={created.qr_image_url} alt="Expo QR" className="size-48 rounded-md border bg-white p-2" />
                  ) : (
                    <QrCode className="size-16" />
                  )}
                  <p className="text-sm text-muted-foreground whitespace-pre-wrap">{created.trigger_text}</p>
                  <div className="flex flex-wrap gap-2">
                    <Button asChild>
                      <Link to="/expo">View saved booths</Link>
                    </Button>
                    <Button variant="outline" asChild>
                      <Link to="/expo/leads" search={{ booth_id: created.id }}>
                        Open leads
                      </Link>
                    </Button>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        )}
      </div>

      {step < 7 || !created ? (
        <div className="flex items-center justify-between">
          <Button
            variant="outline"
            className="gap-1.5"
            onClick={() => setStep((s) => Math.max(1, s - 1) as Step)}
            disabled={step === 1}
          >
            <ChevronLeft className="size-4" /> Back
          </Button>
          {step < 6 ? (
            <Button
              className="gap-1.5"
              onClick={() => setStep((s) => Math.min(6, s + 1) as Step)}
              disabled={!canNext[step]}
            >
              Next <ChevronRight className="size-4" />
            </Button>
          ) : step === 6 ? (
            <Button className="gap-1.5" onClick={() => setStep(7)} disabled={!canNext[6]}>
              Next <ChevronRight className="size-4" />
            </Button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function Stepper({ current, onJump }: { current: Step; onJump: (n: number) => void }) {
  const labels = ["Industry", "Event", "Questions", "Products", "Preview", "Package", "Activate"];
  return (
    <div className="flex flex-wrap gap-2">
      {labels.map((label, idx) => {
        const n = (idx + 1) as Step;
        return (
          <button
            key={label}
            type="button"
            onClick={() => onJump(n)}
            className={cn(
              "rounded-full px-3 py-1 text-xs",
              n === current ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground",
            )}
          >
            {n}. {label}
          </button>
        );
      })}
    </div>
  );
}
