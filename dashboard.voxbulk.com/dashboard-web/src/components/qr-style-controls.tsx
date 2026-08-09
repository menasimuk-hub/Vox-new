import { Check } from "lucide-react";
import * as React from "react";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";

export type QrStyleValue = {
  fg: string;
  bg: string;
  transparent?: boolean;
  moduleStyle: "square" | "dots";
  cornerStyle: "square" | "rounded";
  frameRound: "none" | "top" | "all";
};

type Props = {
  value: QrStyleValue;
  onChange: (next: QrStyleValue) => void;
  disabled?: boolean;
  showTransparent?: boolean;
  className?: string;
};

const FG_SWATCHES = ["#1b2a4a", "#0f172a", "#2f5d50", "#7c2d12", "#111111", "#4338ca"];
const BG_SWATCHES = ["#f7f1e6", "#fdfaf3", "#ffffff", "#e8dfcd", "#eef2ff", "#1b2a4a"];

const MODULE_OPTS = [
  { id: "square" as const, label: "Square" },
  { id: "dots" as const, label: "Dots" },
];

const CORNER_OPTS = [
  { id: "square" as const, label: "Square" },
  { id: "rounded" as const, label: "Rounded" },
];

const FRAME_OPTS = [
  { id: "none" as const, label: "None" },
  { id: "top" as const, label: "Round top" },
  { id: "all" as const, label: "Round all" },
];

function Section({
  title,
  hint,
  children,
  className,
}: {
  title: string;
  hint?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("rounded-xl border border-border bg-card p-4", className)}>
      <div className="mb-3 flex items-baseline justify-between gap-2">
        <h2 className="text-[13px] font-semibold uppercase tracking-wider text-foreground/80">{title}</h2>
        {hint ? <span className="text-[11px] text-muted-foreground">{hint}</span> : null}
      </div>
      {children}
    </section>
  );
}

function SegGroup<T extends string>({
  value,
  onChange,
  options,
  disabled,
}: {
  value: T;
  onChange: (v: T) => void;
  options: { id: T; label: string }[];
  disabled?: boolean;
}) {
  return (
    <div className="flex w-full gap-1 rounded-lg bg-muted p-1">
      {options.map((o) => (
        <button
          key={o.id}
          type="button"
          disabled={disabled}
          onClick={() => onChange(o.id)}
          className={cn(
            "flex-1 rounded-md px-2 py-1.5 text-xs font-medium transition-all",
            value === o.id
              ? "bg-primary text-primary-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground",
            disabled && "opacity-50",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

function ColorField({
  label,
  value,
  onChange,
  swatches,
  disabled,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  swatches: string[];
  disabled?: boolean;
}) {
  const hex = `#${value.replace("#", "").slice(0, 6)}`;
  return (
    <div className={cn("space-y-2", disabled && "pointer-events-none opacity-40")}>
      <Label className="text-xs text-muted-foreground">{label}</Label>
      <div className="flex items-center gap-2">
        <label className="relative size-9 shrink-0 overflow-hidden rounded-md border border-border">
          <span className="block size-full" style={{ background: hex }} />
          <input
            type="color"
            value={hex}
            disabled={disabled}
            onChange={(e) => onChange(e.target.value.replace("#", ""))}
            className="absolute inset-0 cursor-pointer opacity-0"
          />
        </label>
        <Input
          value={hex.toUpperCase()}
          disabled={disabled}
          onChange={(e) => {
            const raw = e.target.value.replace("#", "").replace(/[^0-9a-fA-F]/g, "").slice(0, 6);
            if (raw.length === 6) onChange(raw.toLowerCase());
          }}
          className="h-9 font-mono text-xs uppercase"
        />
      </div>
      <div className="flex gap-1.5">
        {swatches.map((s) => {
          const bare = s.replace("#", "").toLowerCase();
          const selected = value.replace("#", "").toLowerCase() === bare;
          return (
            <button
              key={s}
              type="button"
              disabled={disabled}
              onClick={() => onChange(bare)}
              aria-label={s}
              className={cn(
                "flex size-6 items-center justify-center rounded-full border border-border transition-transform hover:scale-110",
                selected && "ring-2 ring-ring ring-offset-2 ring-offset-card",
              )}
              style={{ background: s }}
            >
              {selected ? <Check className="size-3 text-white mix-blend-difference" /> : null}
            </button>
          );
        })}
      </div>
    </div>
  );
}

/** Append draft style overrides onto an API qr.png URL for live preview. */
export function withQrStyleQuery(baseUrl: string, style: QrStyleValue, size = 512): string {
  if (!baseUrl) return "";
  // External generators ignore our style params — do not pretend they work.
  if (/qrserver\.com/i.test(baseUrl)) return baseUrl;
  try {
    const apiOrigin =
      typeof window !== "undefined" && window.location.hostname === "dashboard.voxbulk.com"
        ? "https://api.voxbulk.com"
        : typeof window !== "undefined"
          ? window.location.origin
          : "https://api.voxbulk.com";
    const u = new URL(baseUrl, apiOrigin);
    if (u.pathname.startsWith("/public/") && !/api\.voxbulk\.com$/i.test(u.hostname)) {
      u.protocol = "https:";
      u.host = "api.voxbulk.com";
    }
    u.searchParams.set("fg", style.fg.replace("#", ""));
    u.searchParams.set("bg", style.bg.replace("#", ""));
    u.searchParams.set("t", style.transparent ? "1" : "0");
    u.searchParams.set("m", style.moduleStyle);
    u.searchParams.set("c", style.cornerStyle);
    u.searchParams.set("a", "0");
    u.searchParams.set("f", style.frameRound);
    u.searchParams.set("s", String(size));
    u.searchParams.set("_", String(Date.now()));
    return u.toString();
  } catch {
    return baseUrl;
  }
}

export function qrStylePayload(style: QrStyleValue, { includeTransparent = false } = {}) {
  const body: Record<string, unknown> = {
    qr_fg_color: style.fg.replace("#", ""),
    qr_bg_color: style.bg.replace("#", ""),
    qr_module_style: style.moduleStyle,
    qr_corner_style: style.cornerStyle,
    qr_show_arrow: false,
    qr_frame_round: style.frameRound,
  };
  if (includeTransparent) body.qr_transparent = Boolean(style.transparent);
  return body;
}

export function QrStyleControls({ value, onChange, disabled, showTransparent, className }: Props) {
  const patch = (partial: Partial<QrStyleValue>) => onChange({ ...value, ...partial });
  const cornersDisabled = disabled || value.moduleStyle === "dots";

  return (
    <div className={cn("grid gap-4 md:grid-cols-2", className)}>
      <Section title="Foreground">
        <ColorField
          label="Module colour"
          value={value.fg}
          onChange={(fg) => patch({ fg })}
          swatches={FG_SWATCHES}
          disabled={disabled}
        />
      </Section>

      <Section title="Background">
        <div className="space-y-3">
          <ColorField
            label="Fill colour"
            value={value.bg}
            onChange={(bg) => patch({ bg })}
            swatches={BG_SWATCHES}
            disabled={disabled || Boolean(value.transparent)}
          />
          {showTransparent ? (
            <div className="flex items-start justify-between gap-3 rounded-lg border border-border bg-secondary/60 p-3">
              <div>
                <p className="text-xs font-medium text-foreground">Transparent background</p>
                <p className="text-[11px] text-muted-foreground">PNG with no fill — print on any colour</p>
              </div>
              <Switch
                checked={Boolean(value.transparent)}
                disabled={disabled}
                onCheckedChange={(v) => patch({ transparent: Boolean(v) })}
              />
            </div>
          ) : null}
        </div>
      </Section>

      <Section title="Modules" hint="dot shape">
        <SegGroup
          options={MODULE_OPTS}
          value={value.moduleStyle}
          disabled={disabled}
          onChange={(moduleStyle) => patch({ moduleStyle })}
        />
        {value.moduleStyle === "dots" ? (
          <p className="mt-2 text-[11px] text-muted-foreground">Dots also use circular corner markers.</p>
        ) : null}
      </Section>

      <Section title="Corners" hint="finder eyes">
        <SegGroup
          options={CORNER_OPTS}
          value={value.moduleStyle === "dots" ? "square" : value.cornerStyle}
          disabled={cornersDisabled}
          onChange={(cornerStyle) => patch({ cornerStyle })}
        />
      </Section>

      <Section title="Frame" className="md:col-span-2">
        <SegGroup
          options={FRAME_OPTS}
          value={value.frameRound}
          disabled={disabled}
          onChange={(frameRound) => patch({ frameRound })}
        />
      </Section>
    </div>
  );
}
