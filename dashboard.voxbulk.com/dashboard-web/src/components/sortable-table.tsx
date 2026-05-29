import * as React from "react";
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import { TableHead } from "@/components/ui/table";
import { cn } from "@/lib/utils";

export type SortDir = "asc" | "desc" | null;

export function useTableSort<T extends Record<string, unknown>>(
  rows: T[],
  defaultKey: keyof T | null = null,
  defaultDir: SortDir = null,
) {
  const [sortKey, setSortKey] = React.useState<string | null>(
    defaultKey ? String(defaultKey) : null,
  );
  const [sortDir, setSortDir] = React.useState<SortDir>(defaultDir);

  const toggleSort = React.useCallback(
    (key: string) => {
      if (sortKey !== key) {
        setSortKey(key);
        setSortDir("asc");
        return;
      }
      if (sortDir === "asc") {
        setSortDir("desc");
      } else if (sortDir === "desc") {
        setSortDir(null);
        setSortKey(null);
      } else {
        setSortDir("asc");
      }
    },
    [sortKey, sortDir],
  );

  const sorted = React.useMemo(() => {
    if (!sortKey || !sortDir) return rows;
    const copy = [...rows];
    copy.sort((a, b) => {
      const av = (a as Record<string, unknown>)[sortKey];
      const bv = (b as Record<string, unknown>)[sortKey];
      const cmp = compare(av, bv);
      return sortDir === "asc" ? cmp : -cmp;
    });
    return copy;
  }, [rows, sortKey, sortDir]);

  return { sorted, sortKey, sortDir, toggleSort };
}

function compare(a: unknown, b: unknown): number {
  if (a == null && b == null) return 0;
  if (a == null) return -1;
  if (b == null) return 1;

  if (typeof a === "number" && typeof b === "number") return a - b;
  if (a instanceof Date && b instanceof Date) return a.getTime() - b.getTime();

  const an = typeof a === "string" ? parseFloat(a) : NaN;
  const bn = typeof b === "string" ? parseFloat(b) : NaN;
  if (
    !isNaN(an) &&
    !isNaN(bn) &&
    /^[\d\s.,%-]+$/.test(String(a)) &&
    /^[\d\s.,%-]+$/.test(String(b))
  ) {
    return an - bn;
  }

  return String(a).toLowerCase().localeCompare(String(b).toLowerCase());
}

export function SortHeader({
  label,
  sortKey,
  active,
  dir,
  onToggle,
  className,
  align = "left",
}: {
  label: React.ReactNode;
  sortKey: string;
  active: string | null;
  dir: SortDir;
  onToggle: (k: string) => void;
  className?: string;
  align?: "left" | "right" | "center";
}) {
  const isActive = active === sortKey && dir !== null;
  const Icon = !isActive ? ArrowUpDown : dir === "asc" ? ArrowUp : ArrowDown;
  return (
    <TableHead className={className}>
      <button
        type="button"
        onClick={() => onToggle(sortKey)}
        className={cn(
          "group inline-flex items-center gap-1.5 text-left text-xs font-medium transition-colors hover:text-foreground",
          isActive ? "text-foreground" : "text-muted-foreground",
          align === "right" && "ml-auto flex-row-reverse",
          align === "center" && "mx-auto",
        )}
      >
        <span>{label}</span>
        <Icon
          className={cn(
            "size-3.5 shrink-0 transition-opacity",
            isActive ? "opacity-100" : "opacity-40 group-hover:opacity-80",
          )}
        />
      </button>
    </TableHead>
  );
}
