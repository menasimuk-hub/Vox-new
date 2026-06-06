import * as React from "react";
import { Check, ChevronDown, ChevronUp, Eye, GripVertical } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

export type WaBuilderTemplateRow = {
  id: string;
  title: string;
  description: string;
  bodyPreview?: string;
};

function templateFromApiRow(row: Record<string, unknown>): WaBuilderTemplateRow {
  const body = String(row.body_preview || row.body || "").trim();
  return {
    id: String(row.id),
    title: String(row.display_name || row.title || row.name || row.id),
    description: body ? body.slice(0, 120) + (body.length > 120 ? "…" : "") : "WhatsApp template",
    bodyPreview: body || undefined,
  };
}

export function mapSystemTemplates(rows: Array<Record<string, unknown>>): WaBuilderTemplateRow[] {
  return rows.map(templateFromApiRow);
}

/** Lovable-style 3 template variants per survey type (maps to survey length on generate). */
export function buildSurveyTypeTemplateOptions(serviceName: string, typeId: string): WaBuilderTemplateRow[] {
  const label = serviceName.trim() || "Survey";
  return [
    {
      id: `${typeId}-short`,
      title: `${label} — Quick 3 questions`,
      description: "Fast pulse check. ~30 seconds. Best response rates.",
    },
    {
      id: `${typeId}-standard`,
      title: `${label} — Standard 5 questions`,
      description: "Balanced survey with rating + open feedback.",
    },
    {
      id: `${typeId}-detailed`,
      title: `${label} — In-depth 8 questions`,
      description: "Detailed survey for deeper insight. ~2 minutes.",
    },
  ];
}

export function pageCountFromServiceTemplateId(templateId: string): 4 | 5 | 6 | null {
  if (templateId.endsWith("-short")) return 4;
  if (templateId.endsWith("-standard")) return 5;
  if (templateId.endsWith("-detailed")) return 6;
  return null;
}

type WaTemplatePickerSectionProps = {
  label: string;
  badge: "Opening" | "Closing";
  templates: WaBuilderTemplateRow[];
  selectedId: string;
  onSelect: (id: string) => void;
};

export function WaTemplatePickerSection({ label, badge, templates, selectedId, onSelect }: WaTemplatePickerSectionProps) {
  const [preview, setPreview] = React.useState<WaBuilderTemplateRow | null>(null);

  return (
    <>
      <div className="space-y-2.5">
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-muted px-3 py-1 text-xs font-semibold text-muted-foreground">
            {badge} · {label}
          </span>
        </div>
        {templates.length === 0 ? (
          <p className="rounded-xl border border-dashed border-border bg-muted/20 px-4 py-6 text-center text-sm text-muted-foreground">
            No templates available yet. Ask your admin to add global system templates.
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
          <span className="text-xs font-medium text-muted-foreground">({index + 1} of survey order)</span>
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
        <div className="grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-3">
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
        <p className="mt-0.5 text-xs text-muted-foreground">{tpl.description}</p>
      </div>
      <div className="mt-auto flex items-center gap-2">
        <Button size="sm" variant="outline" className="gap-1.5" type="button" onClick={onPreview}>
          <Eye className="size-3.5" /> Preview
        </Button>
        <Button size="sm" className="gap-1.5" type="button" variant={active ? "default" : "secondary"} onClick={onSelect}>
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
  return (
    <Dialog open={!!preview} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{preview?.title}</DialogTitle>
          <DialogDescription>{preview?.description}</DialogDescription>
        </DialogHeader>
        <div className="rounded-xl border border-border bg-muted/30 p-4 text-sm leading-relaxed whitespace-pre-wrap">
          {preview?.bodyPreview || preview?.description}
        </div>
      </DialogContent>
    </Dialog>
  );
}
