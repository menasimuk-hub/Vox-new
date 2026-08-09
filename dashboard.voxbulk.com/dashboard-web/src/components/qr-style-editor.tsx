import { Download, ExternalLink } from "lucide-react";
import * as React from "react";

import { QrStyleControls, withQrStyleQuery, type QrStyleValue } from "@/components/qr-style-controls";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type Props = {
  style: QrStyleValue;
  onStyleChange: (next: QrStyleValue) => void;
  qrImageUrl: string;
  downloadName: string;
  openUrl?: string | null;
  showTransparent?: boolean;
  canEdit?: boolean;
  saving?: boolean;
  onSave: (style: QrStyleValue) => void | Promise<void>;
  className?: string;
  /** Extra content under the style controls (e.g. print card). */
  footer?: React.ReactNode;
};

/**
 * Partner-sales-hub QR style editor layout (no Content card):
 * sticky live preview on top, then FG/BG/Modules/Corners/Frame controls.
 */
export function QrStyleEditor({
  style,
  onStyleChange,
  qrImageUrl,
  downloadName,
  openUrl,
  showTransparent,
  canEdit = true,
  saving,
  onSave,
  className,
  footer,
}: Props) {
  const previewUrl = withQrStyleQuery(qrImageUrl, style);
  const frameLabel =
    style.frameRound === "none" ? "None" : style.frameRound === "top" ? "Round top" : "Round all";

  return (
    <div className={cn("space-y-4", className)}>
      <aside className="rounded-xl border border-border bg-card p-4 lg:sticky lg:top-4 lg:self-start">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-[13px] font-semibold uppercase tracking-wider text-foreground/80">Live preview</h2>
          <span className="rounded-full bg-secondary px-2 py-0.5 text-[11px] text-muted-foreground">
            {style.transparent ? "transparent" : "filled"}
          </span>
        </div>

        <div
          className="flex items-center justify-center rounded-lg border border-border p-5"
          style={{
            backgroundImage:
              "linear-gradient(45deg,var(--muted) 25%,transparent 25%,transparent 75%,var(--muted) 75%),linear-gradient(45deg,var(--muted) 25%,transparent 25%,transparent 75%,var(--muted) 75%)",
            backgroundSize: "16px 16px",
            backgroundPosition: "0 0, 8px 8px",
          }}
        >
          {previewUrl ? (
            <img key={previewUrl} src={previewUrl} alt="QR code style preview" className="size-56 max-w-full" />
          ) : (
            <p className="text-sm text-muted-foreground">Save once to generate a QR preview</p>
          )}
        </div>

        <dl className="mt-4 grid grid-cols-2 gap-2 text-[11px]">
          {[
            ["Modules", style.moduleStyle === "dots" ? "Dots" : "Square"],
            ["Corners", style.cornerStyle === "rounded" ? "Rounded" : "Square"],
            ["Frame", frameLabel],
            [
              "Colours",
              `#${style.fg.replace("#", "").toUpperCase()} / ${
                style.transparent ? "—" : `#${style.bg.replace("#", "").toUpperCase()}`
              }`,
            ],
          ].map(([k, v]) => (
            <div key={k} className="rounded-md bg-secondary/60 px-2 py-1.5">
              <dt className="text-muted-foreground">{k}</dt>
              <dd className="font-medium text-foreground">{v}</dd>
            </div>
          ))}
        </dl>

        <p className="mt-3 text-[11px] leading-relaxed text-muted-foreground">
          Tip: keep strong contrast between foreground and background so scanners lock on instantly.
        </p>

        <div className="mt-4 flex flex-wrap gap-2">
          {canEdit ? (
            <Button
              type="button"
              size="sm"
              disabled={saving}
              onClick={() => void onSave(style)}
            >
              {saving ? "Saving…" : "Save style"}
            </Button>
          ) : null}
          {previewUrl ? (
            <Button asChild size="sm" variant="outline" className="gap-1.5">
              <a href={previewUrl} download={downloadName} target="_blank" rel="noreferrer">
                <Download className="size-3.5" /> Download
              </a>
            </Button>
          ) : null}
          {openUrl ? (
            <Button asChild size="sm" variant="outline" className="gap-1.5">
              <a href={openUrl} target="_blank" rel="noreferrer">
                <ExternalLink className="size-3.5" /> Open link
              </a>
            </Button>
          ) : null}
        </div>
      </aside>

      {canEdit ? (
        <QrStyleControls
          value={style}
          onChange={onStyleChange}
          showTransparent={showTransparent}
          disabled={saving}
        />
      ) : null}

      {footer}
    </div>
  );
}
