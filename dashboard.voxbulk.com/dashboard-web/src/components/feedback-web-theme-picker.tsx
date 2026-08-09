import { Check, ChevronRight, Lock, Wand2 } from "lucide-react";

import { Input } from "@/components/ui/input";
import {
  BASE_TEMPLATE,
  CATEGORY_TEMPLATES,
  EVENT_TEMPLATES,
  SEASON_TEMPLATES,
  type SurveyTemplate,
} from "@/lib/feedback-templates";
import { previewThemeUrl, themePreviewQrUrl, type WebThemeWizardState } from "@/lib/feedback-theme-preview";
import { cn } from "@/lib/utils";

function TemplatePreview({ tpl, size = "md" }: { tpl: SurveyTemplate; size?: "sm" | "md" }) {
  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-lg border border-border bg-gradient-to-br",
        tpl.gradient,
        size === "sm" ? "aspect-[4/3]" : "aspect-[4/3]",
      )}
    >
      <div className="absolute inset-2 flex flex-col rounded-md bg-background/85 shadow-sm ring-1 ring-black/5 backdrop-blur-sm">
        <div className="flex items-center gap-1.5 border-b border-border/60 px-2 py-1.5">
          <span className="size-1.5 rounded-full bg-red-400" />
          <span className="size-1.5 rounded-full bg-amber-400" />
          <span className="size-1.5 rounded-full bg-emerald-400" />
          <span className={cn("ml-auto text-[10px] leading-none", tpl.accent)}>{tpl.emoji}</span>
        </div>
        <div className="flex flex-1 flex-col gap-1 p-2">
          <div className={cn("flex items-center gap-1 truncate text-[9px] font-semibold uppercase tracking-wider", tpl.accent)}>
            <span className="truncate">{tpl.label}</span>
          </div>
          <div className="h-1 w-full rounded-full bg-muted-foreground/20" />
          <div className="h-1 w-3/4 rounded-full bg-muted-foreground/20" />
          <div className="mt-auto flex gap-1">
            <div className={cn("h-3 flex-1 rounded-sm bg-gradient-to-r opacity-90", tpl.gradient)} />
            <div className={cn("h-3 flex-1 rounded-sm bg-gradient-to-r opacity-70", tpl.gradient)} />
            <div className={cn("h-3 flex-1 rounded-sm bg-gradient-to-r opacity-50", tpl.gradient)} />
          </div>
        </div>
      </div>
    </div>
  );
}

function TemplateCard({
  tpl,
  active,
  onClick,
  badge,
  compact,
  previewQr,
}: {
  tpl: SurveyTemplate;
  active: boolean;
  onClick: () => void;
  badge?: string;
  compact?: boolean;
  previewQr?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "group relative flex flex-col gap-1.5 rounded-xl border p-2 text-left transition hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md",
        active ? "border-primary bg-primary/5 shadow-sm ring-1 ring-primary/30" : "border-border bg-background/60",
      )}
    >
      {badge ? (
        <span className="absolute right-1.5 top-1.5 z-10 rounded-full bg-primary px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-primary-foreground shadow-sm">
          {badge}
        </span>
      ) : null}
      <TemplatePreview tpl={tpl} size={compact ? "sm" : "md"} />
      <div className="flex items-center gap-1.5 px-0.5">
        <span className="text-sm leading-none">{tpl.emoji}</span>
        <span className="truncate text-[11px] font-semibold leading-tight">{tpl.label}</span>
        {active ? <Check className="ml-auto size-3.5 shrink-0 text-primary" /> : null}
      </div>
      {!compact && tpl.desc ? <p className="px-0.5 text-[10px] leading-snug text-muted-foreground">{tpl.desc}</p> : null}
      {previewQr ? (
        <div className="mt-1 flex items-center gap-2 rounded-lg border border-border bg-white p-1.5">
          <img src={previewQr} alt={`Preview ${tpl.label}`} className="size-14 shrink-0" />
          <p className="text-[10px] leading-snug text-muted-foreground">Scan to preview on your phone</p>
        </div>
      ) : null}
    </button>
  );
}

export type FeedbackWebThemePickerProps = {
  value: WebThemeWizardState;
  onChange: (next: WebThemeWizardState) => void;
  companyName: string;
  industryName?: string;
  industrySlug?: string;
  className?: string;
  /** Prefix for overlay mode radio name (avoid clashes if multiple pickers). */
  radioName?: string;
};

export function FeedbackWebThemePicker({
  value,
  onChange,
  companyName,
  industryName,
  industrySlug,
  className,
  radioName = "feedbackOverlayMode",
}: FeedbackWebThemePickerProps) {
  const { baseTemplateId, overlayIds, overlayMode, customEventLabel } = value;

  const patch = (partial: Partial<WebThemeWizardState>) => onChange({ ...value, ...partial });
  const toggleOverlay = (id: string) =>
    patch({
      overlayIds: overlayIds.includes(id) ? overlayIds.filter((x) => x !== id) : [...overlayIds, id],
    });

  const resolvedCategoryId = industrySlug
    ? CATEGORY_TEMPLATES.find((c) => c.industryId === industrySlug)?.id || "survey-temp"
    : "survey-temp";

  const previewBaseId = baseTemplateId === "auto" ? resolvedCategoryId : baseTemplateId;

  return (
    <div className={cn("space-y-6", className)}>
      <section className="space-y-3">
        <div className="flex items-baseline justify-between gap-3">
          <div>
            <p className="text-sm font-semibold">1. Base template</p>
            <p className="text-xs text-muted-foreground">Auto picks the best match for your industry.</p>
          </div>
          {baseTemplateId !== "auto" ? (
            <button
              type="button"
              onClick={() => patch({ baseTemplateId: "auto" })}
              className="text-[11px] font-medium text-primary hover:underline"
            >
              Reset to Auto
            </button>
          ) : null}
        </div>

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <TemplateCard
            active={baseTemplateId === "auto"}
            onClick={() => patch({ baseTemplateId: "auto" })}
            tpl={{
              id: "auto",
              label: `Auto — ${industryName ?? "smart pick"}`,
              emoji: "🪄",
              kind: "base",
              gradient: "from-primary/30 via-fuchsia-400/20 to-amber-300/20",
              accent: "text-primary",
              desc: "Uses your category template automatically.",
            }}
            badge="Recommended"
            previewQr={themePreviewQrUrl(resolvedCategoryId, companyName)}
          />
          <TemplateCard
            active={baseTemplateId === BASE_TEMPLATE.id}
            onClick={() => patch({ baseTemplateId: BASE_TEMPLATE.id })}
            tpl={BASE_TEMPLATE}
            previewQr={themePreviewQrUrl(BASE_TEMPLATE.id, companyName)}
          />
          {CATEGORY_TEMPLATES.filter((c) => !industrySlug || c.industryId === industrySlug)
            .slice(0, 2)
            .map((c) => (
              <TemplateCard
                key={c.id}
                active={baseTemplateId === c.id}
                onClick={() => patch({ baseTemplateId: c.id })}
                tpl={c}
                badge={industrySlug && c.industryId === industrySlug ? "Your industry" : undefined}
                previewQr={themePreviewQrUrl(c.id, companyName)}
              />
            ))}
        </div>

        <details className="group rounded-xl border border-border bg-background/40">
          <summary className="flex cursor-pointer items-center justify-between gap-2 px-4 py-2.5 text-sm">
            <span className="font-medium">Browse all category templates ({CATEGORY_TEMPLATES.length})</span>
            <ChevronRight className="size-4 transition-transform group-open:rotate-90" />
          </summary>
          <div className="grid gap-3 border-t border-border p-3 sm:grid-cols-3 lg:grid-cols-4">
            {CATEGORY_TEMPLATES.map((c) => (
              <TemplateCard
                key={c.id}
                active={baseTemplateId === c.id}
                onClick={() => patch({ baseTemplateId: c.id })}
                tpl={c}
                compact
                previewQr={themePreviewQrUrl(c.id, companyName)}
              />
            ))}
          </div>
        </details>
      </section>

      <section className="space-y-3 rounded-xl border border-primary/20 bg-primary/5 p-4">
        <div className="flex items-baseline justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-primary">2. Event &amp; seasonal overlays</p>
            <p className="text-xs text-muted-foreground">Multi-select any that apply. Empty = base template all year.</p>
          </div>
          <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-primary">
            {overlayIds.length} selected
          </span>
        </div>

        <div>
          <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Seasons</p>
          <div className="grid gap-2 sm:grid-cols-3">
            {SEASON_TEMPLATES.map((s) => (
              <TemplateCard
                key={s.id}
                active={overlayIds.includes(s.id)}
                onClick={() => toggleOverlay(s.id)}
                tpl={s}
                compact
                previewQr={themePreviewQrUrl(s.id, companyName)}
              />
            ))}
          </div>
        </div>

        <div>
          <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Events &amp; holidays</p>
          <div className="grid gap-2 sm:grid-cols-3 lg:grid-cols-5">
            {EVENT_TEMPLATES.map((e) => (
              <TemplateCard
                key={e.id}
                active={overlayIds.includes(e.id)}
                onClick={() => toggleOverlay(e.id)}
                tpl={e}
                compact
                previewQr={themePreviewQrUrl(e.id, companyName)}
              />
            ))}
          </div>
        </div>

        {overlayIds.length > 0 ? (
          <>
            <div className="grid gap-3 rounded-lg border border-border bg-background/60 p-3 sm:grid-cols-2">
              <label
                className={cn(
                  "flex cursor-pointer items-start gap-2 rounded-lg border p-2.5 transition",
                  overlayMode === "auto" ? "border-primary bg-primary/10" : "border-border hover:border-primary/40",
                )}
              >
                <input
                  type="radio"
                  name={radioName}
                  checked={overlayMode === "auto"}
                  onChange={() => patch({ overlayMode: "auto" })}
                  className="mt-1"
                />
                <div>
                  <p className="flex items-center gap-1.5 text-sm font-semibold">
                    <Wand2 className="size-3.5 text-primary" /> Auto swap by date
                  </p>
                  <p className="text-[11px] text-muted-foreground">
                    Show each overlay during its window, revert to base otherwise.
                  </p>
                </div>
              </label>
              <label
                className={cn(
                  "flex cursor-pointer items-start gap-2 rounded-lg border p-2.5 transition",
                  overlayMode === "fixed" ? "border-primary bg-primary/10" : "border-border hover:border-primary/40",
                )}
              >
                <input
                  type="radio"
                  name={radioName}
                  checked={overlayMode === "fixed"}
                  onChange={() => patch({ overlayMode: "fixed" })}
                  className="mt-1"
                />
                <div>
                  <p className="flex items-center gap-1.5 text-sm font-semibold">
                    <Lock className="size-3.5 text-primary" /> Fixed — always on
                  </p>
                  <p className="text-[11px] text-muted-foreground">
                    Keep the selected overlays permanently until you change them.
                  </p>
                </div>
              </label>
            </div>

            <Input
              value={customEventLabel}
              onChange={(e) => patch({ customEventLabel: e.target.value })}
              placeholder="Optional: custom event label (e.g. Store anniversary, National Day)"
              className="h-9 text-sm"
            />
          </>
        ) : null}
      </section>

      <p className="text-xs text-muted-foreground">
        Live preview:{" "}
        <a
          href={previewThemeUrl(previewBaseId, companyName)}
          target="_blank"
          rel="noreferrer"
          className="text-primary underline-offset-2 hover:underline"
        >
          Open web survey preview
        </a>
      </p>
    </div>
  );
}
