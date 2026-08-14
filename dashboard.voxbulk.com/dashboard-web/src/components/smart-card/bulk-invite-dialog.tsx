import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Loader2, Upload } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { apiFetch, downloadAuthenticatedFile } from "@/lib/api";

type Entitlement = {
  seat_quantity: number;
  active_reps: number;
};

type BulkResult = {
  ok?: boolean;
  created_count: number;
  invited_count: number;
  linked_count: number;
  skipped_count: number;
  remaining_seats: number;
  created: Array<{ email: string; name?: string; action: string }>;
  skipped: Array<{ email?: string | null; reason: string }>;
};

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

function reasonLabel(reason: string) {
  switch (reason) {
    case "invalid_email":
      return "Invalid email";
    case "duplicate_in_file":
      return "Duplicate in file";
    case "already_has_qr":
      return "Already has a QR";
    case "seat_limit":
      return "No seats left";
    default:
      return reason;
  }
}

export function SmartCardBulkInviteDialog({ open, onOpenChange }: Props) {
  const qc = useQueryClient();
  const fileRef = React.useRef<HTMLInputElement>(null);
  const [file, setFile] = React.useState<File | null>(null);
  const [result, setResult] = React.useState<BulkResult | null>(null);
  const [downloading, setDownloading] = React.useState(false);

  const entQ = useQuery({
    queryKey: ["smart-card", "entitlement"],
    queryFn: () => apiFetch<{ ok: boolean } & Entitlement>("/smart-card/entitlement"),
    enabled: open,
  });

  React.useEffect(() => {
    if (!open) {
      setFile(null);
      setResult(null);
      if (fileRef.current) fileRef.current.value = "";
    }
  }, [open]);

  const seats = Number(entQ.data?.seat_quantity || 0);
  const active = Number(entQ.data?.active_reps || 0);
  const remaining = Math.max(0, seats - active);

  const uploadMut = useMutation({
    mutationFn: async (upload: File) => {
      const fd = new FormData();
      fd.append("file", upload);
      return apiFetch<BulkResult>("/smart-card/representatives/bulk-invite", {
        method: "POST",
        body: fd,
      });
    },
    onSuccess: async (data) => {
      setResult(data);
      const n = Number(data.created_count || 0);
      if (n > 0) {
        toast.success(
          `Created ${n} seat${n === 1 ? "" : "s"} · ${data.invited_count} invite${data.invited_count === 1 ? "" : "s"} sent`,
        );
      } else {
        toast.message("No new invites created — see the report below");
      }
      await qc.invalidateQueries({ queryKey: ["smart-card"] });
    },
    onError: (e: Error) => toast.error(e.message || "Could not invite team"),
  });

  async function downloadTemplate() {
    setDownloading(true);
    try {
      await downloadAuthenticatedFile(
        "/smart-card/representatives/bulk-invite-template.xlsx",
        "smart-card-team-invite-template.xlsx",
      );
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not download template");
    } finally {
      setDownloading(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Invite team (Excel)</DialogTitle>
          <DialogDescription>
            Upload emails only — each person gets a seat stub and an invite to set a password and complete their own
            Smart Card QR. Does not exceed remaining seats.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-1 text-sm">
          <p className="rounded-md border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
            Remaining seats: <strong className="text-foreground">{remaining}</strong>
            {seats > 0 ? (
              <>
                {" "}
                ({active} / {seats} used)
              </>
            ) : (
              <> — buy seats before inviting</>
            )}
          </p>

          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="gap-1.5"
              disabled={downloading}
              onClick={() => void downloadTemplate()}
            >
              {downloading ? <Loader2 className="size-3.5 animate-spin" /> : <Download className="size-3.5" />}
              Download template
            </Button>
          </div>

          <div className="space-y-2">
            <input
              ref={fileRef}
              type="file"
              accept=".xlsx,.csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv"
              className="block w-full text-xs file:mr-3 file:rounded-md file:border-0 file:bg-primary file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-primary-foreground"
              onChange={(e) => {
                setResult(null);
                setFile(e.target.files?.[0] || null);
              }}
            />
            <p className="text-xs text-muted-foreground">Columns: <code>email</code> (required), <code>name</code> (optional).</p>
          </div>

          {result ? (
            <div className="max-h-48 space-y-2 overflow-y-auto rounded-md border px-3 py-2 text-xs">
              <p>
                Created {result.created_count} · invited {result.invited_count} · linked {result.linked_count} · skipped{" "}
                {result.skipped_count}
              </p>
              {result.skipped.length > 0 ? (
                <ul className="space-y-0.5 text-muted-foreground">
                  {result.skipped.slice(0, 40).map((s, i) => (
                    <li key={`${s.email || "row"}-${i}`}>
                      {s.email || "(blank)"} — {reasonLabel(s.reason)}
                    </li>
                  ))}
                  {result.skipped.length > 40 ? <li>…and {result.skipped.length - 40} more</li> : null}
                </ul>
              ) : null}
            </div>
          ) : null}
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={uploadMut.isPending}>
            {result ? "Close" : "Never mind"}
          </Button>
          <Button
            type="button"
            disabled={!file || remaining <= 0 || uploadMut.isPending}
            onClick={() => file && uploadMut.mutate(file)}
          >
            {uploadMut.isPending ? (
              <>
                <Loader2 className="mr-2 size-4 animate-spin" /> Sending…
              </>
            ) : (
              <>
                <Upload className="mr-2 size-4" /> Create stubs &amp; send invites
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
