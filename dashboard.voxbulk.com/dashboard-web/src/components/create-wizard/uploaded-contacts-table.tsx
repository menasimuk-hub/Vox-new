import * as React from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export type UploadedContactRow = {
  id?: string;
  name: string;
  phone: string;
  email?: string;
  language?: string;
  phoneCallAllowed?: boolean;
  phoneCallBlockReason?: string | null;
};

type UploadedContactsTableProps = {
  contacts: UploadedContactRow[];
  loading?: boolean;
  error?: string | null;
  pageSize?: number;
  highlightAllowlist?: boolean;
  editable?: boolean;
  locked?: boolean;
  contactValue?: (row: UploadedContactRow, field: "name" | "phone" | "email") => string;
  onContactChange?: (row: UploadedContactRow, field: "name" | "phone" | "email", value: string) => void;
  onContactBlur?: (row: UploadedContactRow, field: "name" | "phone" | "email") => void;
  patchPending?: boolean;
};

export function UploadedContactsTable({
  contacts,
  loading = false,
  error = null,
  pageSize = 20,
  highlightAllowlist = false,
  editable = false,
  locked = false,
  contactValue,
  onContactChange,
  onContactBlur,
  patchPending = false,
}: UploadedContactsTableProps) {
  const [page, setPage] = React.useState(0);

  const total = contacts.length;
  const pageCount = Math.max(1, Math.ceil(total / pageSize));

  React.useEffect(() => {
    setPage((prev) => Math.min(prev, Math.max(0, pageCount - 1)));
  }, [pageCount, total]);

  const start = page * pageSize;
  const rows = contacts.slice(start, start + pageSize);

  const cellValue = (row: UploadedContactRow, field: "name" | "phone" | "email") =>
    contactValue ? contactValue(row, field) : String(row[field] || "");

  if (loading) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-4 w-40" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  if (error) {
    return <p className="text-sm text-destructive">Could not load contacts: {error}</p>;
  }

  if (total === 0) {
    return null;
  }

  const blockedCount = highlightAllowlist
    ? contacts.filter((c) => c.phoneCallAllowed === false).length
    : 0;

  const canEdit = editable && !locked;

  return (
    <div className="space-y-2 animate-fade-in">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-semibold">{total} uploaded contact{total === 1 ? "" : "s"}</p>
        {pageCount > 1 ? (
          <p className="text-xs text-muted-foreground">
            Page {page + 1} of {pageCount}
          </p>
        ) : null}
      </div>
      {blockedCount > 0 ? (
        <p className="text-xs text-destructive rounded-md border border-destructive/30 bg-destructive/5 p-2">
          {blockedCount} number{blockedCount === 1 ? "" : "s"} cannot be called — not in an approved calling region. Fix or
          remove them; only allowed numbers will be dialled.
        </p>
      ) : null}
      {canEdit ? (
        <p className="text-xs text-muted-foreground">Click a field to edit name, phone, or email — changes save when you leave the field.</p>
      ) : null}
      <div className="overflow-x-auto rounded-lg border border-border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Phone</TableHead>
              <TableHead>Email</TableHead>
              <TableHead>Language</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((c, i) => {
              const blocked = highlightAllowlist && c.phoneCallAllowed === false;
              const rowKey = c.id || `${c.phone}-${start + i}`;
              return (
                <TableRow key={rowKey} className={blocked ? "bg-destructive/5" : undefined}>
                  <TableCell>
                    {canEdit && c.id ? (
                      <Input
                        value={cellValue(c, "name")}
                        onChange={(e) => onContactChange?.(c, "name", e.target.value)}
                        onBlur={() => onContactBlur?.(c, "name")}
                        disabled={patchPending}
                        className="h-8 min-w-[120px] text-xs"
                      />
                    ) : (
                      <span className="font-medium">{c.name || "—"}</span>
                    )}
                  </TableCell>
                  <TableCell className="tabular-nums">
                    {canEdit && c.id ? (
                      <Input
                        value={cellValue(c, "phone")}
                        onChange={(e) => onContactChange?.(c, "phone", e.target.value)}
                        onBlur={() => onContactBlur?.(c, "phone")}
                        disabled={patchPending}
                        className="h-8 min-w-[120px] text-xs"
                      />
                    ) : (
                      <>
                        <span className={blocked ? "text-destructive font-medium" : undefined}>{c.phone}</span>
                        {blocked && c.phoneCallBlockReason ? (
                          <p className="text-[10px] text-destructive/90 mt-0.5 max-w-[220px]">{c.phoneCallBlockReason}</p>
                        ) : null}
                      </>
                    )}
                  </TableCell>
                  <TableCell>
                    {canEdit && c.id ? (
                      <Input
                        type="email"
                        value={cellValue(c, "email")}
                        onChange={(e) => onContactChange?.(c, "email", e.target.value)}
                        onBlur={() => onContactBlur?.(c, "email")}
                        disabled={patchPending}
                        className="h-8 min-w-[140px] text-xs"
                      />
                    ) : (
                      <span className="text-muted-foreground">{c.email || "—"}</span>
                    )}
                  </TableCell>
                  <TableCell className="text-muted-foreground">{c.language || "—"}</TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>
      {pageCount > 1 ? (
        <div className="flex items-center justify-end gap-2">
          <Button type="button" size="sm" variant="outline" disabled={page <= 0} onClick={() => setPage((p) => p - 1)}>
            <ChevronLeft className="size-4" />
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={page >= pageCount - 1}
            onClick={() => setPage((p) => p + 1)}
          >
            <ChevronRight className="size-4" />
          </Button>
        </div>
      ) : null}
    </div>
  );
}
