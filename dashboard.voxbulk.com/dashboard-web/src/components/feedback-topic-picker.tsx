import * as React from "react";
import { Check, ChevronDown, ChevronUp, GripVertical, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { FeedbackSurveyType } from "@/lib/queries";
import { cn } from "@/lib/utils";

const MAX_TOPICS = 6;

export function FeedbackTopicPicker({
  topics,
  selectedIds,
  onChange,
}: {
  topics: FeedbackSurveyType[];
  selectedIds: string[];
  onChange: (ids: string[]) => void;
}) {
  const [dragIndex, setDragIndex] = React.useState<number | null>(null);
  const [dragOverIndex, setDragOverIndex] = React.useState<number | null>(null);

  const byId = React.useMemo(() => new Map(topics.map((t) => [t.id, t])), [topics]);
  const selected = selectedIds.map((id) => byId.get(id)).filter(Boolean) as FeedbackSurveyType[];
  const available = topics.filter((t) => !selectedIds.includes(t.id));

  const move = (from: number, to: number) => {
    if (to < 0 || to >= selectedIds.length || from === to) return;
    const next = [...selectedIds];
    const [item] = next.splice(from, 1);
    next.splice(to, 0, item);
    onChange(next);
  };

  const toggle = (id: string) => {
    if (selectedIds.includes(id)) {
      onChange(selectedIds.filter((x) => x !== id));
      return;
    }
    if (selectedIds.length >= MAX_TOPICS) return;
    onChange([...selectedIds, id]);
  };

  return (
    <div className="space-y-4">
      <p className="text-xs text-muted-foreground">
        Selected:{" "}
        <span
          className={cn(
            "font-semibold",
            selectedIds.length === 0
              ? "text-muted-foreground"
              : selectedIds.length >= MAX_TOPICS
                ? "text-warning"
                : "text-primary",
          )}
        >
          {selectedIds.length}
        </span>{" "}
        / {MAX_TOPICS}
        {selectedIds.length > 1 ? (
          <span className="ml-1">· Drag or use arrows to set ask order</span>
        ) : null}
      </p>

      {selected.length > 0 ? (
        <div className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Question order
          </p>
          <ul className="space-y-2">
            {selected.map((t, index) => (
              <li
                key={t.id}
                draggable
                onDragStart={() => setDragIndex(index)}
                onDragEnd={() => {
                  setDragIndex(null);
                  setDragOverIndex(null);
                }}
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragOverIndex(index);
                }}
                onDrop={(e) => {
                  e.preventDefault();
                  if (dragIndex !== null) move(dragIndex, index);
                  setDragIndex(null);
                  setDragOverIndex(null);
                }}
                className={cn(
                  "flex items-center gap-2 rounded-xl border border-border bg-background/40 px-3 py-2 transition-all",
                  dragIndex === index && "opacity-40 scale-[0.98] border-dashed border-primary/50",
                  dragOverIndex === index && dragIndex !== index && "border-primary bg-primary/5 shadow-md",
                )}
              >
                <span
                  className="cursor-grab active:cursor-grabbing rounded p-1 text-muted-foreground/60 hover:bg-muted hover:text-foreground"
                  title="Drag to reorder"
                >
                  <GripVertical className="size-4" />
                </span>
                <span className="grid size-6 shrink-0 place-items-center rounded-full bg-primary/10 text-[11px] font-semibold text-primary">
                  {index + 1}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{t.name}</p>
                  {t.description ? (
                    <p className="truncate text-[11px] text-muted-foreground">{t.description}</p>
                  ) : null}
                </div>
                <div className="flex shrink-0 items-center gap-0.5">
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="size-8"
                    title="Move up"
                    disabled={index === 0}
                    onClick={() => move(index, index - 1)}
                  >
                    <ChevronUp className="size-4" />
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="size-8"
                    title="Move down"
                    disabled={index === selected.length - 1}
                    onClick={() => move(index, index + 1)}
                  >
                    <ChevronDown className="size-4" />
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="size-8 text-muted-foreground hover:text-destructive"
                    title="Remove"
                    onClick={() => toggle(t.id)}
                  >
                    <X className="size-4" />
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {available.length > 0 ? (
        <div className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            {selected.length ? "Add topics" : "Topics"}
          </p>
          <div className="flex flex-wrap gap-2">
            {available.map((t) => {
              const disabled = selectedIds.length >= MAX_TOPICS;
              return (
                <button
                  key={t.id}
                  type="button"
                  disabled={disabled}
                  onClick={() => toggle(t.id)}
                  className={cn(
                    "rounded-full border px-3.5 py-1.5 text-sm transition-all",
                    !disabled && "border-border bg-background hover:border-primary/40 hover:bg-primary/5",
                    disabled && "cursor-not-allowed border-border bg-muted/40 text-muted-foreground/50",
                  )}
                >
                  {t.name}
                </button>
              );
            })}
          </div>
        </div>
      ) : null}

      {selected.length > 0 && available.length === 0 ? (
        <p className="text-xs text-muted-foreground">All topics for this industry are selected.</p>
      ) : null}

      {selectedIds.length > 0 ? (
        <p className="text-[11px] text-muted-foreground">
          <Check className="mr-1 inline size-3 text-primary" />
          Customers are asked in the order above (then optional open question / promo opt-in).
        </p>
      ) : null}
    </div>
  );
}
