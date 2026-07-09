import * as React from "react";
import { PhoneCall, Gift, Clock, Sparkles, Info } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { cn } from "@/lib/utils";

export type AiFollowUpConfig = {
  enabled: boolean;
  businessContext: string;
  promoEnabled: boolean;
  promoCode: string;
  promoDescription: string;
  delayHours: "24" | "48";
};

export function defaultAiFollowUp(): AiFollowUpConfig {
  return {
    enabled: false,
    businessContext: "",
    promoEnabled: false,
    promoCode: "",
    promoDescription: "",
    delayHours: "24",
  };
}

export function aiFollowUpToApi(config: AiFollowUpConfig) {
  return {
    enabled: config.enabled,
    business_context: config.businessContext.trim(),
    promo_enabled: config.promoEnabled,
    promo_code: config.promoCode.trim(),
    promo_description: config.promoDescription.trim(),
    delay_hours: Number(config.delayHours),
  };
}

export function aiFollowUpFromApi(raw?: Record<string, unknown> | null): AiFollowUpConfig {
  if (!raw) return defaultAiFollowUp();
  const delay = Number(raw.delay_hours ?? raw.delayHours ?? 24);
  return {
    enabled: Boolean(raw.enabled),
    businessContext: String(raw.business_context ?? raw.businessContext ?? ""),
    promoEnabled: Boolean(raw.promo_enabled ?? raw.promoEnabled),
    promoCode: String(raw.promo_code ?? raw.promoCode ?? ""),
    promoDescription: String(raw.promo_description ?? raw.promoDescription ?? ""),
    delayHours: delay === 48 ? "48" : "24",
  };
}

export function AiFollowUpStep({
  stepLabel,
  config,
  onChange,
}: {
  stepLabel: string;
  config: AiFollowUpConfig;
  onChange: (next: AiFollowUpConfig) => void;
}) {
  const set = <K extends keyof AiFollowUpConfig>(k: K, v: AiFollowUpConfig[K]) =>
    onChange({ ...config, [k]: v });

  return (
    <Card className="animate-scale-in">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <PhoneCall className="size-4 text-primary" /> {stepLabel} · AI call follow-up
          <span className="ml-2 inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-primary">
            <Sparkles className="size-3" /> Optional
          </span>
        </CardTitle>
        <CardDescription>
          When a customer gives a <b>low rating</b> but doesn't explain why, our AI voice agent
          rings them back to understand the problem — and can offer a promo code if you have one.
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-5">
        <label
          className={cn(
            "flex cursor-pointer items-start gap-3 rounded-xl border p-4 transition",
            config.enabled ? "border-primary bg-primary/5 ring-1 ring-primary/30" : "border-border bg-background/40 hover:border-primary/40",
          )}
        >
          <div className="grid size-10 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary ring-1 ring-primary/20">
            <PhoneCall className="size-5" />
          </div>
          <div className="flex-1">
            <div className="flex items-center justify-between gap-3">
              <p className="text-sm font-semibold">Enable AI call follow-up for unhappy customers</p>
              <Switch checked={config.enabled} onCheckedChange={(v) => set("enabled", !!v)} />
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              Runs only when a rating is low and the customer left no written reason. AI calls the phone number on file.
            </p>
          </div>
        </label>

        {config.enabled && (
          <div className="space-y-5 rounded-xl border border-primary/20 bg-primary/5 p-4">
            <div className="space-y-2">
              <Label htmlFor="ai-context" className="text-sm font-semibold">
                What is your business and what is this survey for?
              </Label>
              <p className="text-xs text-muted-foreground">
                The AI agent uses this to sound natural and stay on topic.
              </p>
              <Textarea
                id="ai-context"
                rows={4}
                placeholder="Example: We're Northwell Dental, a family dentist in Marina. This survey is about visits from the last 7 days."
                value={config.businessContext}
                onChange={(e) => set("businessContext", e.target.value)}
              />
            </div>

            <div className="rounded-xl border border-border bg-background/60 p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-start gap-3">
                  <div className="grid size-9 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary ring-1 ring-primary/20">
                    <Gift className="size-4" />
                  </div>
                  <div>
                    <p className="text-sm font-semibold">Offer a promo / recovery code</p>
                    <p className="text-xs text-muted-foreground">
                      If the customer accepts, we send the code on WhatsApp right after the call.
                    </p>
                  </div>
                </div>
                <Switch checked={config.promoEnabled} onCheckedChange={(v) => set("promoEnabled", !!v)} />
              </div>

              {config.promoEnabled && (
                <div className="mt-4 grid gap-3 sm:grid-cols-[180px_1fr]">
                  <div className="space-y-1.5">
                    <Label htmlFor="ai-promo-code" className="text-xs">
                      Promo code
                    </Label>
                    <Input
                      id="ai-promo-code"
                      placeholder="SORRY20"
                      value={config.promoCode}
                      onChange={(e) => set("promoCode", e.target.value.toUpperCase())}
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="ai-promo-desc" className="text-xs">
                      What does it give?
                    </Label>
                    <Input
                      id="ai-promo-desc"
                      placeholder="20% off your next visit — valid 30 days"
                      value={config.promoDescription}
                      onChange={(e) => set("promoDescription", e.target.value)}
                    />
                  </div>
                </div>
              )}
            </div>

            <div className="space-y-2">
              <p className="flex items-center gap-2 text-sm font-semibold">
                <Clock className="size-4 text-primary" /> When should the AI call?
              </p>
              <RadioGroup
                value={config.delayHours}
                onValueChange={(v) => set("delayHours", v as "24" | "48")}
                className="grid gap-3 sm:grid-cols-2"
              >
                {[
                  { v: "24", t: "24 hours later", d: "Fresh in memory — best for service recovery." },
                  { v: "48", t: "48 hours later", d: "Gives the customer space to cool down first." },
                ].map((o) => (
                  <label
                    key={o.v}
                    className={cn(
                      "flex cursor-pointer items-start gap-3 rounded-xl border p-3 transition",
                      config.delayHours === o.v
                        ? "border-primary bg-primary/10 ring-1 ring-primary/30"
                        : "border-border bg-background hover:border-primary/40",
                    )}
                  >
                    <RadioGroupItem value={o.v} className="mt-0.5" />
                    <div>
                      <p className="text-sm font-semibold">{o.t}</p>
                      <p className="text-xs text-muted-foreground">{o.d}</p>
                    </div>
                  </label>
                ))}
              </RadioGroup>
            </div>

            <div className="flex items-start gap-2 rounded-lg border border-primary/20 bg-background/60 p-3 text-xs text-muted-foreground">
              <Info className="size-3.5 shrink-0 text-primary" />
              <p>
                AI follow-up calls only work when a phone number is on file. Anonymous web-only responses are skipped.
              </p>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
