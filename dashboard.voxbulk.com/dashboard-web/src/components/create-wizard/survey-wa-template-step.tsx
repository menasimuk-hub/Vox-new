import * as React from "react";
import { Check, ChevronDown, ChevronUp, Eye, GripVertical } from "lucide-react";

import { WaSurveyPhonePreview } from "@/components/wa-survey-phone-preview";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import { wizardTemplateDisplayName } from "@/lib/survey-step-labels";

export type WaBuilderTemplateRow = {
  id: string;
  title: string;
  description: string;
  bodyPreview?: string;
  footer?: string;
  buttons?: Array<{ label: string; type?: string }>;
  isApproved?: boolean;
};

function buttonsFromApiRow(row: Record<string, unknown>): Array<{ label: string; type?: string }> {
  if (String(row.send_mode || "").toLowerCase() === "session_text") return [];
  const raw = row.buttons;
  if (!Array.isArray(raw)) return [];
  return raw
    .map((btn) => {
      if (!btn || typeof btn !== "object") return null;
      const label = String((btn as Record<string, unknown>).text || (btn as Record<string, unknown>).label || "").trim();
      if (!label) return null;
      return { label, type: String((btn as Record<string, unknown>).type || "QUICK_REPLY") };
    })
    .filter(Boolean) as Array<{ label: string; type?: string }>;
}

function templateFromApiRow(
  row: Record<string, unknown>,
  questionNumber?: number,
  fallback = "",
): WaBuilderTemplateRow {
  const name = String(row.name || "").trim();
  let body = "";
  for (const key of ["draft_components", "remote_components", "components"] as const) {
    const comps = row[key];
    if (!Array.isArray(comps)) continue;
    for (const comp of comps) {
      if (!comp || typeof comp !== "object") continue;
      if (String((comp as Record<string, unknown>).type || "").toUpperCase() === "BODY") {
        body = String((comp as Record<string, unknown>).text || "").trim();
        if (body) break;
      }
    }
    if (body) break;
  }
  if (!body) {
    body = String(row.body_preview || row.body || row.body_text || "").trim();
  }
  if (!body || body === name || body.startsWith("voxbulk_")) {
    body = "";
  }
  const title = wizardTemplateDisplayName(row, fallback, questionNumber);
  const approved =
    row.is_approved === true ||
    String(row.approval_status || row.telnyx_status || row.status || "").toUpperCase() === "APPROVED";
  return {
    id: String(row.id),
    title,
    description: String(row.customer_description || "").trim(),
    bodyPreview: body || undefined,
    footer: String(row.footer || "Reply STOP to opt out").trim() || undefined,
    buttons: buttonsFromApiRow(row),
    isApproved: approved,
  };
}

export function mapSystemTemplates(
  rows: Array<Record<string, unknown>>,
  options?: { fallback?: string },
): WaBuilderTemplateRow[] {
  const fallback = String(options?.fallback || "").trim();
  return rows.map((row, index) => templateFromApiRow(row, index + 1, fallback));
}

export function pageCountFromServiceType(row: Record<string, unknown> | undefined): 4 | 5 | 6 {
  const length = String(row?.default_length || "standard").toLowerCase();
  if (length === "short") return 4;
  if (length === "detailed") return 6;
  return 5;
}

/** One middle page per selected survey type → start + N middles + completion (3–6 pages). */
export function pageCountFromSelectedTypes(typeCount: number): 3 | 4 | 5 | 6 {
  return Math.min(6, Math.max(3, typeCount + 2)) as 3 | 4 | 5 | 6;
}

type WaTemplatePickerSectionProps = {
  label: string;
  templates: WaBuilderTemplateRow[];
  selectedId: string;
  onSelect: (id: string) => void;
};

export function WaTemplatePickerSection({ label, templates, selectedId, onSelect }: WaTemplatePickerSectionProps) {
  const [preview, setPreview] = React.useState<WaBuilderTemplateRow | null>(null);

  return (
    <>
      <div className="space-y-2.5">
        <p className="text-sm font-semibold">{label}</p>
        {templates.length === 0 ? (
          <p className="rounded-xl border border-dashed border-border bg-muted/20 px-4 py-6 text-center text-sm text-muted-foreground">
            No templates yet.
          </p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {templates.map((tpl) => (
              <TemplateCard
                key={tpl.id}
                tpl={tpl}
                active={selectedId === tpl.id}
                dimOthers={Boolean(selectedId && selectedId !== tpl.id)}
                onPreview={() => setPreview(tpl)}
                onSelect={() => onSelect(tpl.id)}
              />
            ))}
          </div>
        )}
      </div>

      <TemplatePreviewDialog preview={preview} onClose={() => setPreview(null)} />
    </>
  );
}

type WaDraggableTypeGroupProps = {
  serviceName: string;
  index: number;
  total: number;
  templates: WaBuilderTemplateRow[];
  selectedId: string;
  onSelect: (id: string) => void;
  onMoveUp?: () => void;
  onMoveDown?: () => void;
  onDragStart: () => void;
  onDragEnd: () => void;
  isDragging?: boolean;
  isDragOver?: boolean;
};

export function WaDraggableTypeGroup({
  serviceName,
  index,
  total,
  templates,
  selectedId,
  onSelect,
  onMoveUp,
  onMoveDown,
  onDragStart,
  onDragEnd,
  isDragging,
  isDragOver,
}: WaDraggableTypeGroupProps) {
  const [preview, setPreview] = React.useState<WaBuilderTemplateRow | null>(null);

  return (
    <>
      <div
        className={cn(
          "rounded-xl border border-border bg-background/40 transition-all",
          isDragging && "opacity-40 scale-[0.98] border-dashed border-primary/50 shadow-inner",
          isDragOver && "border-primary bg-primary/5 shadow-md translate-y-0.5",
        )}
        draggable
        onDragStart={onDragStart}
        onDragEnd={onDragEnd}
      >
        <div className="flex items-center gap-3 border-b border-border bg-muted/20 px-4 py-3">
          <div
            className="cursor-grab active:cursor-grabbing -ml-1 rounded p-1 text-muted-foreground/60 transition-colors hover:bg-muted hover:text-foreground"
            title="Drag to reorder"
          >
            <GripVertical className="size-4" />
          </div>
          <span
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold",
              selectedId ? "bg-primary text-primary-foreground shadow-sm" : "bg-primary/10 text-primary ring-1 ring-primary/20",
            )}
          >
            {selectedId ? <Check className="size-3" /> : null} {serviceName}
          </span>
          <div className="ml-auto flex items-center gap-1">
            <Button
              type="button"
              variant="ghost"
              size="icon"
              onClick={(e) => {
                e.stopPropagation();
                onMoveUp?.();
              }}
              disabled={!onMoveUp}
              className="size-8 rounded-lg text-muted-foreground hover:bg-background hover:text-foreground disabled:opacity-30"
              title="Move Up"
            >
              <ChevronUp className="size-4" />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              onClick={(e) => {
                e.stopPropagation();
                onMoveDown?.();
              }}
              disabled={!onMoveDown}
              className="size-8 rounded-lg text-muted-foreground hover:bg-background hover:text-foreground disabled:opacity-30"
              title="Move Down"
            >
              <ChevronDown className="size-4" />
            </Button>
          </div>
        </div>
        {templates.length === 0 ? (
          <p className="px-4 py-6 text-center text-sm text-muted-foreground">No templates yet.</p>
        ) : (
          <div className={cn("grid gap-3 p-4", templates.length === 1 ? "grid-cols-1" : "sm:grid-cols-2 lg:grid-cols-3")}>
            {templates.map((tpl) => (
              <TemplateCard
                key={tpl.id}
                tpl={tpl}
                active={selectedId === tpl.id}
                dimOthers={Boolean(selectedId && selectedId !== tpl.id)}
                onPreview={() => setPreview(tpl)}
                onSelect={() => onSelect(tpl.id)}
              />
            ))}
          </div>
        )}
      </div>

      <TemplatePreviewDialog preview={preview} onClose={() => setPreview(null)} />
    </>
  );
}

function TemplateCard({
  tpl,
  active,
  dimOthers,
  onPreview,
  onSelect,
}: {
  tpl: WaBuilderTemplateRow;
  active: boolean;
  dimOthers: boolean;
  onPreview: () => void;
  onSelect: () => void;
}) {
  const pending = tpl.isApproved === false;
  return (
    <div
      className={cn(
        "flex flex-col gap-3 rounded-xl border p-4 transition-all",
        active ? "border-primary bg-primary/5 ring-1 ring-primary/30" : "border-border bg-background/40",
        !dimOthers && "hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md",
        dimOthers && "opacity-50",
      )}
    >
      <div>
        <p className="text-sm font-semibold">{tpl.title}</p>
        {pending ? (
          <p className="mt-1 text-xs font-medium text-amber-700 dark:text-amber-400">Pending Meta approval</p>
        ) : null}
        {tpl.description ? <p className="mt-1 text-xs text-muted-foreground">{tpl.description}</p> : null}
      </div>
      <div className="mt-auto flex items-center gap-2">
        <Button size="sm" variant="outline" className="gap-1.5" type="button" onClick={onPreview}>
          <Eye className="size-3.5" /> Preview
        </Button>
        <Button
          size="sm"
          className="gap-1.5"
          type="button"
          variant={active ? "default" : "secondary"}
          disabled={pending}
          onClick={onSelect}
        >
          {active ? (
            <>
              <Check className="size-3.5" /> Selected
            </>
          ) : (
            "Use this template"
          )}
        </Button>
      </div>
    </div>
  );
}

function TemplatePreviewDialog({
  preview,
  onClose,
}: {
  preview: WaBuilderTemplateRow | null;
  onClose: () => void;
}) {
  const body = preview?.bodyPreview || preview?.description || "";
  return (
    <Dialog open={!!preview} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-sm gap-0 p-0">
        <DialogHeader className="px-5 pb-2 pt-5">
          <DialogTitle>WhatsApp preview</DialogTitle>
        </DialogHeader>
        <div className="px-5 pb-5">
          <WaSurveyPhonePreview
            businessName="Your business"
            renderedBody={body.replace(/\{\{1\}\}/g, "Alex").replace(/\{\{2\}\}/g, "Your business")}
            footer={preview?.footer || "Reply STOP to opt out"}
            buttons={preview?.buttons || []}
          />
        </div>
      </DialogContent>
    </Dialog>
  );
}
