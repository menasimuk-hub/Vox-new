import * as React from "react";
import { Check, Package } from "lucide-react";
import { Link } from "@tanstack/react-router";

import { catalogueColors, colorOf } from "@/components/catalogue-manager";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { cn } from "@/lib/utils";

export type AssignProduct = {
  id: string;
  name: string;
  short_description?: string | null;
  description?: string | null;
};

export type AssignCategory = {
  id: string;
  name: string;
  accent_color?: string | null;
  color?: string | null;
  products?: AssignProduct[];
};

type Props = {
  categories: AssignCategory[];
  selectedIds: string[];
  onChange: (ids: string[]) => void;
  disabled?: boolean;
  emptyHint?: React.ReactNode;
  className?: string;
};

function catColour(cat: AssignCategory) {
  const raw = (cat.accent_color || cat.color || "sky").toLowerCase();
  return colorOf(catalogueColors.some((c) => c.id === raw) ? raw : "sky");
}

export function AssignProductsPicker({
  categories,
  selectedIds,
  onChange,
  disabled,
  emptyHint,
  className,
}: Props) {
  const withProducts = categories.filter((c) => (c.products || []).length > 0);
  const total = withProducts.reduce((n, c) => n + (c.products || []).length, 0);

  const toggle = (id: string, on: boolean) => {
    if (disabled) return;
    onChange(on ? [...selectedIds, id] : selectedIds.filter((x) => x !== id));
  };

  if (total === 0) {
    return (
      <div className={cn("rounded-xl border border-dashed p-6 text-center", className)}>
        <Package className="mx-auto mb-2 size-7 text-muted-foreground/50" />
        <p className="text-sm text-muted-foreground">
          {emptyHint ?? (
            <>
              No catalogue products yet.{" "}
              <Link to="/smart-card/catalogue" className="text-primary underline underline-offset-2">
                Add catalogues
              </Link>
            </>
          )}
        </p>
      </div>
    );
  }

  return (
    <div className={cn("space-y-4", className)}>
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline" className="text-[11px]">
          {selectedIds.length} of {total} selected
        </Badge>
        {withProducts.map((cat) => {
          const col = catColour(cat);
          const count = (cat.products || []).filter((p) => selectedIds.includes(p.id)).length;
          return (
            <span
              key={cat.id}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium",
                col.chip,
                col.text,
              )}
            >
              <span className={cn("size-1.5 rounded-full", col.dot)} />
              {cat.name}
              {count > 0 ? <span className="opacity-70">· {count}</span> : null}
            </span>
          );
        })}
      </div>

      <div className="space-y-5">
        {withProducts.map((cat) => {
          const col = catColour(cat);
          return (
            <div key={cat.id} className="space-y-2">
              <div className="flex items-center gap-2">
                <span className={cn("size-2.5 rounded-full", col.dot)} />
                <p className={cn("text-xs font-semibold uppercase tracking-wide", col.text)}>{cat.name}</p>
              </div>
              <div className="grid grid-cols-2 gap-2">
                {(cat.products || []).map((p) => {
                  const checked = selectedIds.includes(p.id);
                  const desc = p.short_description || p.description || "";
                  return (
                    <button
                      key={p.id}
                      type="button"
                      disabled={disabled}
                      onClick={() => toggle(p.id, !checked)}
                      className={cn(
                        "group relative flex w-full gap-3 overflow-hidden rounded-xl border bg-card p-3 text-left transition-all duration-200",
                        checked
                          ? cn("border-transparent shadow-sm ring-2", col.ring)
                          : "border-border hover:-translate-y-0.5 hover:shadow-sm",
                        disabled && "pointer-events-none opacity-60",
                      )}
                    >
                      <span className={cn("absolute inset-x-0 top-0 h-1", col.dot)} />
                      <div
                        className={cn(
                          "mt-1 grid size-9 shrink-0 place-items-center rounded-lg transition-transform duration-200 group-hover:scale-105",
                          col.chip,
                        )}
                      >
                        {checked ? (
                          <Check className={cn("size-4", col.text)} />
                        ) : (
                          <Package className={cn("size-4", col.text)} />
                        )}
                      </div>
                      <div className="min-w-0 flex-1 space-y-1 pt-0.5">
                        <div className="flex items-start justify-between gap-2">
                          <p className="text-sm font-semibold leading-snug">{p.name}</p>
                          <Checkbox
                            checked={checked}
                            disabled={disabled}
                            tabIndex={-1}
                            className="mt-0.5 shrink-0 pointer-events-none"
                            aria-hidden
                          />
                        </div>
                        {desc ? (
                          <p className="line-clamp-2 text-[11px] text-muted-foreground">{desc}</p>
                        ) : (
                          <p className="text-[11px] text-muted-foreground/70">Catalogue product</p>
                        )}
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
