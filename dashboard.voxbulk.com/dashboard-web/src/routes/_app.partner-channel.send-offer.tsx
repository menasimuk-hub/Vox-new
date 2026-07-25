import * as React from "react";
import { createFileRoute } from "@tanstack/react-router";
import { CheckCircle2, Download, FileSpreadsheet, Loader2, Send, Upload, XCircle } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch, apiUploadFiles, downloadAuthenticatedFile } from "@/lib/api";
import { requirePartnerChannel } from "@/lib/guards/settings-route";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/partner-channel/send-offer")({
  head: () => ({ meta: [{ title: "Send offer — VoxBulk" }] }),
  beforeLoad: () => requirePartnerChannel(),
  component: PartnerSendOffer,
});

type PreviewRow = { email: string; name?: string | null; row?: number };
type SendResult = {
  email: string;
  name?: string | null;
  ok: boolean;
  error?: string | null;
};

type PreviewResponse = {
  ok: boolean;
  count: number;
  recipients: PreviewRow[];
  skipped?: number;
  message?: string;
};

type SendResponse = {
  ok: boolean;
  sent: number;
  failed: number;
  total: number;
  results: SendResult[];
  message?: string;
};

function PartnerSendOffer() {
  const [file, setFile] = React.useState<File | null>(null);
  const [offerDetails, setOfferDetails] = React.useState("Special VoxBulk partner offer");
  const [preview, setPreview] = React.useState<PreviewResponse | null>(null);
  const [result, setResult] = React.useState<SendResponse | null>(null);
  const [busy, setBusy] = React.useState<"preview" | "send" | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [dragOver, setDragOver] = React.useState(false);
  const inputRef = React.useRef<HTMLInputElement>(null);
  const [promo, setPromo] = React.useState("");

  React.useEffect(() => {
    void (async () => {
      try {
        const me = await apiFetch<{ rep: { promo_code?: string } }>("/sales/me");
        setPromo(me.rep?.promo_code || "");
      } catch {
        setPromo("");
      }
    })();
  }, []);

  const onPick = (next: File | null) => {
    setFile(next);
    setPreview(null);
    setResult(null);
    setError(null);
  };

  const runPreview = async () => {
    if (!file) return;
    setBusy("preview");
    setError(null);
    setResult(null);
    try {
      const res = (await apiUploadFiles("/sales/partner/bulk-offers/preview", [file], "file")) as PreviewResponse;
      setPreview(res);
      if (!res.count) setError(res.message || "No valid emails found in this file.");
    } catch (e) {
      setPreview(null);
      setError(e instanceof Error ? e.message : "Could not read spreadsheet");
    } finally {
      setBusy(null);
    }
  };

  const runSend = async () => {
    if (!file) return;
    if (!window.confirm(`Send offer emails to ${preview?.count || "these"} recipients?`)) return;
    setBusy("send");
    setError(null);
    try {
      const res = (await apiUploadFiles("/sales/partner/bulk-offers", [file], "file", {
        offer_details: offerDetails.trim() || "Special VoxBulk partner offer",
      })) as SendResponse;
      setResult(res);
      if (!res.ok && res.failed && !res.sent) {
        setError(res.message || "All sends failed");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not send offers");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="Partner Channel Sales"
        title="Send offer"
        description={
          promo
            ? `Upload an Excel or CSV with emails. Each contact receives your partner signup offer with promo code ${promo}.`
            : "Upload an Excel or CSV with emails. Each contact receives your partner signup offer."
        }
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">1. Upload contacts</CardTitle>
            <CardDescription>
              Columns: <span className="font-medium text-foreground">email</span> (required) and optional{" "}
              <span className="font-medium text-foreground">name</span>. Max 500 rows per send.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") inputRef.current?.click();
              }}
              onClick={() => inputRef.current?.click()}
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragOver(false);
                const f = e.dataTransfer.files?.[0] || null;
                if (f) onPick(f);
              }}
              className={cn(
                "flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-12 text-center transition",
                dragOver
                  ? "border-primary bg-primary/5"
                  : "border-muted-foreground/25 hover:border-primary/40 hover:bg-muted/30",
              )}
            >
              <div className="mb-3 grid size-12 place-items-center rounded-full bg-primary/10 text-primary">
                <FileSpreadsheet className="size-6" />
              </div>
              <p className="text-sm font-medium">{file ? file.name : "Drop Excel / CSV here"}</p>
              <p className="mt-1 text-xs text-muted-foreground">
                {file ? `${(file.size / 1024).toFixed(1)} KB · click to change` : ".xlsx, .xls, .csv"}
              </p>
              <input
                ref={inputRef}
                type="file"
                accept=".xlsx,.xls,.xlsm,.csv,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                className="hidden"
                onChange={(e) => onPick(e.target.files?.[0] || null)}
              />
            </div>

            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={() =>
                  void downloadAuthenticatedFile("/sales/partner/offer-template.xlsx", "partner-offer-contacts.xlsx")
                }
              >
                <Download className="mr-1.5 size-4" />
                Download template
              </Button>
              <Button type="button" disabled={!file || busy !== null} onClick={() => void runPreview()}>
                {busy === "preview" ? (
                  <Loader2 className="mr-1.5 size-4 animate-spin" />
                ) : (
                  <Upload className="mr-1.5 size-4" />
                )}
                Preview contacts
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">2. Offer note</CardTitle>
            <CardDescription>Shown in the email offer summary for this batch.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <Textarea
              rows={8}
              value={offerDetails}
              onChange={(e) => setOfferDetails(e.target.value)}
              placeholder="e.g. Exclusive partner welcome — £20 wallet credit on signup"
              className="min-h-[180px] resize-none"
            />
            <p className="text-xs text-muted-foreground">
              Recipients get the standard VoxBulk offer email with your personal signup link. Duplicate emails in the
              file are ignored.
            </p>
          </CardContent>
        </Card>
      </div>

      {error ? (
        <div className="rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      {preview && preview.count > 0 ? (
        <Card>
          <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3 space-y-0">
            <div>
              <CardTitle className="text-base">3. Review & send</CardTitle>
              <CardDescription>
                {preview.count} recipient{preview.count === 1 ? "" : "s"}
                {preview.skipped ? ` · ${preview.skipped} row(s) skipped` : ""}
              </CardDescription>
            </div>
            <Button type="button" disabled={busy !== null} onClick={() => void runSend()}>
              {busy === "send" ? (
                <Loader2 className="mr-1.5 size-4 animate-spin" />
              ) : (
                <Send className="mr-1.5 size-4" />
              )}
              Send {preview.count} offer{preview.count === 1 ? "" : "s"}
            </Button>
          </CardHeader>
          <CardContent>
            <div className="max-h-[28rem] overflow-auto rounded-xl border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-16">#</TableHead>
                    <TableHead>Name</TableHead>
                    <TableHead>Email</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {preview.recipients.map((r, i) => (
                    <TableRow key={`${r.email}-${i}`}>
                      <TableCell className="text-muted-foreground">{r.row ?? i + 1}</TableCell>
                      <TableCell>{r.name || "—"}</TableCell>
                      <TableCell className="font-medium">{r.email}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {result ? (
        <Card>
          <CardHeader>
            <CardTitle className="flex flex-wrap items-center gap-2 text-base">
              Send results
              <Badge variant="secondary" className="bg-success-soft text-success">
                {result.sent} sent
              </Badge>
              {result.failed > 0 ? (
                <Badge variant="secondary" className="bg-destructive/10 text-destructive">
                  {result.failed} failed
                </Badge>
              ) : null}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="max-h-[28rem] overflow-auto rounded-xl border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Status</TableHead>
                    <TableHead>Email</TableHead>
                    <TableHead>Detail</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {result.results.map((r, i) => (
                    <TableRow key={`${r.email}-${i}`}>
                      <TableCell>
                        {r.ok ? (
                          <span className="inline-flex items-center gap-1 text-success">
                            <CheckCircle2 className="size-3.5" /> Sent
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 text-destructive">
                            <XCircle className="size-3.5" /> Failed
                          </span>
                        )}
                      </TableCell>
                      <TableCell className="font-medium">{r.email}</TableCell>
                      <TableCell className="text-muted-foreground">{r.error || "—"}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
