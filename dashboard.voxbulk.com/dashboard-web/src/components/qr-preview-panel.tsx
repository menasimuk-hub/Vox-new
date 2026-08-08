import { Download, ExternalLink, Pencil } from "lucide-react";
import * as React from "react";

import { QrStyleControls, withQrStyleQuery, type QrStyleValue } from "@/components/qr-style-controls";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

type Props = {
  style: QrStyleValue;
  onStyleChange: (next: QrStyleValue) => void;
  /** Base API qr.png URL (saved style); draft overrides applied for preview. */
  qrImageUrl: string;
  downloadName: string;
  openUrl?: string | null;
  showTransparent?: boolean;
  canEdit?: boolean;
  saving?: boolean;
  /** Persist the draft style (called with the dialog draft on Save). */
  onSave: (style: QrStyleValue) => void | Promise<void>;
  /** When true, preview uses checkerboard if transparent. */
  className?: string;
};

export function QrPreviewPanel({
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
}: Props) {
  const [open, setOpen] = React.useState(false);
  const [draft, setDraft] = React.useState(style);

  React.useEffect(() => {
    if (open) setDraft(style);
  }, [open, style]);

  const previewUrl = withQrStyleQuery(qrImageUrl, open ? draft : style);
  const dialogPreviewUrl = withQrStyleQuery(qrImageUrl, draft);

  const transparentBg =
    (open ? draft.transparent : style.transparent)
      ? {
          backgroundImage:
            "linear-gradient(45deg,#e5e7eb 25%,transparent 25%),linear-gradient(-45deg,#e5e7eb 25%,transparent 25%),linear-gradient(45deg,transparent 75%,#e5e7eb 75%),linear-gradient(-45deg,transparent 75%,#e5e7eb 75%)",
          backgroundSize: "16px 16px",
          backgroundPosition: "0 0,0 8px,8px -8px,-8px 0",
          backgroundColor: "#fff",
        }
      : { backgroundColor: `#${(open ? draft.bg : style.bg) || "ffffff"}` };

  const handleSave = async () => {
    onStyleChange(draft);
    await onSave(draft);
    setOpen(false);
  };

  return (
    <div className={className}>
      <div className="flex flex-col items-center gap-3">
        {previewUrl ? (
          <img
            key={previewUrl}
            src={previewUrl}
            alt="QR"
            className="max-h-52 w-auto max-w-full rounded-lg border p-2"
            style={transparentBg}
          />
        ) : null}
        <div className="flex w-full flex-wrap justify-center gap-2">
          {canEdit ? (
            <Button type="button" size="sm" variant="default" className="gap-1.5" onClick={() => setOpen(true)}>
              <Pencil className="size-3.5" /> Edit
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
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Edit QR style</DialogTitle>
            <DialogDescription>
              Colours, modules, corners, and frame. Preview updates live — Save to keep.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-6 sm:grid-cols-[minmax(0,1fr)_minmax(180px,220px)] sm:items-start">
            <QrStyleControls value={draft} onChange={setDraft} showTransparent={showTransparent} />
            <div className="flex flex-col items-center gap-2">
              {dialogPreviewUrl ? (
                <img
                  key={dialogPreviewUrl}
                  src={dialogPreviewUrl}
                  alt="QR preview"
                  className="w-full max-w-[200px] rounded-lg border p-2"
                  style={
                    draft.transparent
                      ? {
                          backgroundImage:
                            "linear-gradient(45deg,#e5e7eb 25%,transparent 25%),linear-gradient(-45deg,#e5e7eb 25%,transparent 25%),linear-gradient(45deg,transparent 75%,#e5e7eb 75%),linear-gradient(-45deg,transparent 75%,#e5e7eb 75%)",
                          backgroundSize: "16px 16px",
                          backgroundPosition: "0 0,0 8px,8px -8px,-8px 0",
                          backgroundColor: "#fff",
                        }
                      : { backgroundColor: `#${draft.bg || "ffffff"}` }
                  }
                />
              ) : null}
              <p className="text-center text-xs text-muted-foreground">Live preview</p>
            </div>
          </div>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button type="button" variant="outline" onClick={() => setOpen(false)} disabled={saving}>
              Cancel
            </Button>
            <Button type="button" onClick={() => void handleSave()} disabled={saving}>
              {saving ? "Saving…" : "Save"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
