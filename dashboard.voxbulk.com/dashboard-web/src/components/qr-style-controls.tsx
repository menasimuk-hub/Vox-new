import * as React from "react";

import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

export type QrStyleValue = {
  fg: string;
  bg: string;
  transparent?: boolean;
  moduleStyle: "square" | "dots";
  cornerStyle: "square" | "rounded";
  showArrow: boolean;
  frameRound: "none" | "top" | "all";
};

type Props = {
  value: QrStyleValue;
  onChange: (next: QrStyleValue) => void;
  disabled?: boolean;
  showTransparent?: boolean;
  className?: string;
};

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

function Seg<T extends string>({
  options,
  value,
  disabled,
  onChange,
}: {
  options: { id: T; label: string }[];
  value: T;
  disabled?: boolean;
  onChange: (id: T) => void;
}) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map((o) => (
        <button
          key={o.id}
          type="button"
          disabled={disabled}
          onClick={() => onChange(o.id)}
          className={cn(
            "rounded-md border px-2.5 py-1 text-xs font-medium transition-colors",
            value === o.id
              ? "border-primary bg-primary/10 text-primary"
              : "border-border bg-background text-muted-foreground hover:bg-muted/60",
            disabled && "opacity-50",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

/** Append draft style overrides onto an API qr.png URL for live preview. */
export function withQrStyleQuery(baseUrl: string, style: QrStyleValue, size = 512): string {
  if (!baseUrl) return "";
  try {
    const u = new URL(baseUrl, typeof window !== "undefined" ? window.location.origin : "https://api.voxbulk.com");
    u.searchParams.set("fg", style.fg.replace("#", ""));
    u.searchParams.set("bg", style.bg.replace("#", ""));
    u.searchParams.set("t", style.transparent ? "1" : "0");
    u.searchParams.set("m", style.moduleStyle);
    u.searchParams.set("c", style.cornerStyle);
    u.searchParams.set("a", style.showArrow ? "1" : "0");
    u.searchParams.set("f", style.frameRound);
    u.searchParams.set("s", String(size));
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
    qr_show_arrow: style.showArrow,
    qr_frame_round: style.frameRound,
  };
  if (includeTransparent) body.qr_transparent = Boolean(style.transparent);
  return body;
}

export function QrStyleControls({ value, onChange, disabled, showTransparent, className }: Props) {
  const patch = (partial: Partial<QrStyleValue>) => onChange({ ...value, ...partial });

  return (
    <div className={cn("grid gap-3", className)}>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-2">
          <Label>Colour</Label>
          <Input
            type="color"
            value={`#${value.fg.replace("#", "")}`}
            disabled={disabled}
            onChange={(e) => patch({ fg: e.target.value.replace("#", "") })}
          />
        </div>
        <div className="space-y-2">
          <Label>Background</Label>
          <Input
            type="color"
            value={`#${value.bg.replace("#", "")}`}
            disabled={disabled || Boolean(value.transparent)}
            onChange={(e) => patch({ bg: e.target.value.replace("#", "") })}
          />
        </div>
      </div>

      {showTransparent ? (
        <label className="flex items-center gap-2 text-sm">
          <Checkbox
            checked={Boolean(value.transparent)}
            disabled={disabled}
            onCheckedChange={(v) => patch({ transparent: Boolean(v) })}
          />
          Transparent background (PNG with no fill — print on any colour)
        </label>
      ) : null}

      <div className="space-y-1.5">
        <Label className="text-xs text-muted-foreground">Modules</Label>
        <Seg
          options={MODULE_OPTS}
          value={value.moduleStyle}
          disabled={disabled}
          onChange={(moduleStyle) => patch({ moduleStyle })}
        />
      </div>

      <div className="space-y-1.5">
        <Label className="text-xs text-muted-foreground">Corners</Label>
        <Seg
          options={CORNER_OPTS}
          value={value.cornerStyle}
          disabled={disabled}
          onChange={(cornerStyle) => patch({ cornerStyle })}
        />
      </div>

      <div className="space-y-1.5">
        <Label className="text-xs text-muted-foreground">Frame</Label>
        <Seg
          options={FRAME_OPTS}
          value={value.frameRound}
          disabled={disabled}
          onChange={(frameRound) => patch({ frameRound })}
        />
      </div>

      <label className="flex items-center gap-2 text-sm">
        <Checkbox
          checked={value.showArrow}
          disabled={disabled}
          onCheckedChange={(v) => patch({ showArrow: Boolean(v) })}
        />
        Show side arrow
      </label>
    </div>
  );
}
