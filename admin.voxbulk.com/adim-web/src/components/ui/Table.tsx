import * as React from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/Button";

const Table = React.forwardRef<HTMLTableElement, React.HTMLAttributes<HTMLTableElement>>(
  ({ className, ...props }, ref) => (
    <div className="relative w-full overflow-auto">
      <table ref={ref} className={cn("w-full caption-bottom text-sm", className)} {...props} />
    </div>
  ),
);
Table.displayName = "Table";

const TableHeader = React.forwardRef<
  HTMLTableSectionElement,
  React.HTMLAttributes<HTMLTableSectionElement>
>(({ className, ...props }, ref) => (
  <thead ref={ref} className={cn("[&_tr]:border-b", className)} {...props} />
));
TableHeader.displayName = "TableHeader";

const TableBody = React.forwardRef<
  HTMLTableSectionElement,
  React.HTMLAttributes<HTMLTableSectionElement>
>(({ className, ...props }, ref) => (
  <tbody ref={ref} className={cn("[&_tr:last-child]:border-0", className)} {...props} />
));
TableBody.displayName = "TableBody";

const TableFooter = React.forwardRef<
  HTMLTableSectionElement,
  React.HTMLAttributes<HTMLTableSectionElement>
>(({ className, ...props }, ref) => (
  <tfoot
    ref={ref}
    className={cn("border-t bg-muted/50 font-medium [&>tr]:last:border-b-0", className)}
    {...props}
  />
));
TableFooter.displayName = "TableFooter";

const TableRow = React.forwardRef<HTMLTableRowElement, React.HTMLAttributes<HTMLTableRowElement>>(
  ({ className, ...props }, ref) => (
    <tr
      ref={ref}
      className={cn(
        "border-b transition-colors hover:bg-muted/50 data-[state=selected]:bg-muted",
        className,
      )}
      {...props}
    />
  ),
);
TableRow.displayName = "TableRow";

const TableHead = React.forwardRef<
  HTMLTableCellElement,
  React.ThHTMLAttributes<HTMLTableCellElement>
>(({ className, ...props }, ref) => (
  <th
    ref={ref}
    className={cn(
      "h-10 px-2 text-left align-middle font-medium text-muted-foreground [&:has([role=checkbox])]:pr-0 [&>[role=checkbox]]:translate-y-[2px]",
      className,
    )}
    {...props}
  />
));
TableHead.displayName = "TableHead";

const TableCell = React.forwardRef<
  HTMLTableCellElement,
  React.TdHTMLAttributes<HTMLTableCellElement>
>(({ className, ...props }, ref) => (
  <td
    ref={ref}
    className={cn(
      "p-2 align-middle [&:has([role=checkbox])]:pr-0 [&>[role=checkbox]]:translate-y-[2px]",
      className,
    )}
    {...props}
  />
));
TableCell.displayName = "TableCell";

const TableCaption = React.forwardRef<
  HTMLTableCaptionElement,
  React.HTMLAttributes<HTMLTableCaptionElement>
>(({ className, ...props }, ref) => (
  <caption ref={ref} className={cn("mt-4 text-sm text-muted-foreground", className)} {...props} />
));
TableCaption.displayName = "TableCaption";

/**
 * StripeTable — the compact, bordered, zebra-striped table container from
 * telynx-settings-hub-main. Wrap a normal `<TableHeader>/<TableBody>` in it:
 * headers become slim uppercase, cells get tight padding, and even rows are
 * softly highlighted (one on / one off).
 */
const StripeTable = React.forwardRef<
  HTMLTableElement,
  React.HTMLAttributes<HTMLTableElement>
>(({ className, children, ...props }, ref) => (
  <div className="overflow-hidden rounded-md border border-border">
    <Table
      ref={ref}
      className={cn(
        "[&_tbody_tr:nth-child(even)]:bg-surface-muted/60",
        "[&_thead_th]:h-8 [&_thead_th]:px-3 [&_thead_th]:text-[10.5px] [&_thead_th]:font-semibold [&_thead_th]:uppercase [&_thead_th]:tracking-wider",
        "[&_tbody_td]:px-3 [&_tbody_td]:py-1.5 [&_tbody_td]:text-[12.5px]",
        className,
      )}
      {...props}
    >
      {children}
    </Table>
  </div>
));
StripeTable.displayName = "StripeTable";

/* ---- Composition helpers: empty / loading / pagination ---- */

interface TableStateRowProps {
  colSpan: number;
  children?: React.ReactNode;
  className?: string;
}

function TableEmpty({ colSpan, children = "No results found.", className }: TableStateRowProps) {
  return (
    <TableRow className="hover:bg-transparent">
      <TableCell colSpan={colSpan} className={cn("py-10 text-center text-muted-foreground", className)}>
        {children}
      </TableCell>
    </TableRow>
  );
}

function TableLoading({ colSpan, children = "Loading…", className }: TableStateRowProps) {
  return (
    <TableRow className="hover:bg-transparent">
      <TableCell colSpan={colSpan} className={cn("py-10 text-center text-muted-foreground", className)}>
        {children}
      </TableCell>
    </TableRow>
  );
}

interface TablePaginationProps {
  page: number;
  pageCount: number;
  total?: number;
  onPrev?: () => void;
  onNext?: () => void;
  className?: string;
}

function TablePagination({
  page,
  pageCount,
  total,
  onPrev,
  onNext,
  className,
}: TablePaginationProps) {
  return (
    <div className={cn("flex items-center justify-between gap-3 pt-3", className)}>
      <span className="text-xs text-muted-foreground">
        {typeof total === "number"
          ? `${total} total · Page ${page} of ${Math.max(pageCount, 1)}`
          : `Page ${page} of ${Math.max(pageCount, 1)}`}
      </span>
      <div className="flex items-center gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={onPrev}
          disabled={page <= 1}
        >
          <ChevronLeft /> Prev
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={onNext}
          disabled={page >= pageCount}
        >
          Next <ChevronRight />
        </Button>
      </div>
    </div>
  );
}

export {
  Table,
  StripeTable,
  TableHeader,
  TableBody,
  TableFooter,
  TableHead,
  TableRow,
  TableCell,
  TableCaption,
  TableEmpty,
  TableLoading,
  TablePagination,
};
