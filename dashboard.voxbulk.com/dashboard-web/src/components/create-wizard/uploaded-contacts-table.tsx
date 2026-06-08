import * as React from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export type UploadedContactRow = {
  name: string;
  phone: string;
  language?: string;
};

type UploadedContactsTableProps = {
  contacts: UploadedContactRow[];
  loading?: boolean;
  error?: string | null;
  pageSize?: number;
};

export function UploadedContactsTable({
  contacts,
  loading = false,
  error = null,
  pageSize = 20,
}: UploadedContactsTableProps) {
  const [page, setPage] = React.useState(0);

  const total = contacts.length;
  const pageCount = Math.max(1, Math.ceil(total / pageSize));

  React.useEffect(() => {
    setPage((prev) => Math.min(prev, Math.max(0, pageCount - 1)));
  }, [pageCount, total]);

  const start = page * pageSize;
  const rows = contacts.slice(start, start + pageSize);

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
      <div className="overflow-hidden rounded-lg border border-border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Phone</TableHead>
              <TableHead>Language</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((c, i) => (
              <TableRow key={`${c.phone}-${start + i}`}>
                <TableCell className="font-medium">{c.name || "—"}</TableCell>
                <TableCell className="tabular-nums">{c.phone}</TableCell>
                <TableCell className="text-muted-foreground">{c.language || "—"}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      {pageCount > 1 ? (
        <div className="flex items-center justify-between gap-2">
          <p className="text-xs text-muted-foreground">
            Showing {start + 1}–{Math.min(start + pageSize, total)} of {total}
          </p>
          <div className="flex items-center gap-1">
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-8 gap-1"
              disabled={page <= 0}
              onClick={() => setPage((p) => Math.max(0, p - 1))}
            >
              <ChevronLeft className="size-3.5" /> Previous
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-8 gap-1"
              disabled={page >= pageCount - 1}
              onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
            >
              Next <ChevronRight className="size-3.5" />
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
