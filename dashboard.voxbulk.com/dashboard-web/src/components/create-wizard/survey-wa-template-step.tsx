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
            {templates.map((tpl) => {
              const active = selectedId === tpl.id;
              const dimOthers = Boolean(selectedId && selectedId !== tpl.id);
              return (
                <div
                  key={tpl.id}
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
                    <Button size="sm" variant="outline" className="gap-1.5" type="button" onClick={() => setPreview(tpl)}>
                      <Eye className="size-3.5" /> Preview
                    </Button>
                    <Button
                      size="sm"
                      className="gap-1.5"
                      type="button"
                      variant={active ? "default" : "secondary"}
                      onClick={() => onSelect(tpl.id)}
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
            })}
          </div>
        )}
      </div>

      <Dialog open={!!preview} onOpenChange={(open) => !open && setPreview(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{preview?.title}</DialogTitle>
            <DialogDescription>WhatsApp message preview</DialogDescription>
          </DialogHeader>
          <div className="rounded-xl border border-border bg-muted/30 p-4 text-sm leading-relaxed whitespace-pre-wrap">
            {preview?.bodyPreview || preview?.description}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

type WaServiceFlowGroupProps = {
  serviceName: string;
  index: number;
  total: number;
  templateTitle?: string;
  templateBody?: string;
  ready: boolean;
  onMoveUp?: () => void;
  onMoveDown?: () => void;
  onDragStart: () => void;
  onDragEnd: () => void;
  onDragOver: (e: React.DragEvent) => void;
  onDrop: () => void;
  isDragging?: boolean;
  isDragOver?: boolean;
};

export function WaServiceFlowGroup({
  serviceName,
  index,
  total,
  templateTitle,
  templateBody,
  ready,
  onMoveUp,
  onMoveDown,
  onDragStart,
  onDragEnd,
  onDragOver,
  onDrop,
  isDragging,
  isDragOver,
}: WaServiceFlowGroupProps) {
  return (
    <div
      className={cn(
        "transition-all duration-200 rounded-xl overflow-hidden border",
        isDragging && "opacity-40 scale-[0.98] border-dashed border-primary/50 shadow-inner",
        isDragOver ? "border-primary bg-primary/5 shadow-md translate-y-0.5" : "border-transparent",
      )}
      onDragOver={onDragOver}
      onDrop={(e) => {
        e.preventDefault();
        onDrop();
      }}
    >
      <div
        className="rounded-xl border border-border bg-background/40"
        draggable
        onDragStart={onDragStart}
        onDragEnd={onDragEnd}
      >
        <div className="flex items-center gap-3 border-b border-border bg-muted/20 px-4 py-3">
          <div
            className="cursor-grab active:cursor-grabbing rounded p-1 -ml-1 text-muted-foreground/60 hover:bg-muted hover:text-foreground"
            title="Drag to reorder"
          >
            <GripVertical className="size-4" />
          </div>
          <span
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold",
              ready ? "bg-primary text-primary-foreground shadow-sm" : "bg-destructive/10 text-destructive ring-1 ring-destructive/20",
            )}
          >
            {ready ? <Check className="size-3" /> : null} {serviceName}
          </span>
          <span className="text-xs font-medium text-muted-foreground">
            ({index + 1} of {total})
          </span>
          <div className="ml-auto flex items-center gap-1">
            <Button type="button" variant="ghost" size="icon" className="size-8" onClick={onMoveUp} disabled={!onMoveUp}>
              <ChevronUp className="size-4" />
            </Button>
            <Button type="button" variant="ghost" size="icon" className="size-8" onClick={onMoveDown} disabled={!onMoveDown}>
              <ChevronDown className="size-4" />
            </Button>
          </div>
        </div>
        <div className="p-4">
          <div
            className={cn(
              "rounded-xl border p-4",
              ready ? "border-primary/30 bg-primary/5 ring-1 ring-primary/20" : "border-destructive/30 bg-destructive/5",
            )}
          >
            <p className="text-sm font-semibold">{templateTitle || "Library template"}</p>
            <p className="mt-1 text-xs text-muted-foreground">
              {ready
                ? templateBody || "Industry-specific WhatsApp question from your template library."
                : "No WhatsApp template linked for this service yet."}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
