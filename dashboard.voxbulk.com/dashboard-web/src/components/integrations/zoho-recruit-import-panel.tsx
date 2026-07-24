import * as React from "react";
import { Link } from "@tanstack/react-router";
import { ExternalLink, Loader2, RefreshCw, Users } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { apiFetch } from "@/lib/api";

type JobOpening = { id: string; name: string; status?: string };
type Candidate = {
  id: string;
  name: string;
  email: string;
  phone: string;
  job_title?: string;
  stage?: string;
  phone_missing?: boolean;
};

type Props = {
  orderId: string;
  onImported?: () => void;
  disabled?: boolean;
};

export function ZohoRecruitImportPanel({ orderId, onImported, disabled }: Props) {
  const [connected, setConnected] = React.useState<boolean | null>(null);
  const [jobs, setJobs] = React.useState<JobOpening[]>([]);
  const [candidates, setCandidates] = React.useState<Candidate[]>([]);
  const [jobId, setJobId] = React.useState("");
  const [stage, setStage] = React.useState("");
  const [selected, setSelected] = React.useState<string[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [importing, setImporting] = React.useState(false);

  const loadStatus = React.useCallback(async () => {
    try {
      const data = await apiFetch<{ connected?: boolean }>("/service-orders/zoho-recruit/status");
      setConnected(data?.connected === true);
    } catch {
      setConnected(false);
    }
  }, []);

  const loadJobs = React.useCallback(async () => {
    try {
      const data = await apiFetch<{ items?: JobOpening[] }>("/service-orders/zoho-recruit/job-openings");
      setJobs(data?.items || []);
    } catch {
      setJobs([]);
    }
  }, []);

  const loadCandidates = React.useCallback(async () => {
    setLoading(true);
    try {
      const qs = new URLSearchParams({ per_page: "100" });
      if (jobId) qs.set("job_id", jobId);
      if (stage.trim()) qs.set("stage", stage.trim());
      const data = await apiFetch<{ items?: Candidate[] }>(
        `/service-orders/zoho-recruit/candidates?${qs.toString()}`,
      );
      setCandidates(data?.items || []);
      setSelected([]);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not load Zoho candidates");
      setCandidates([]);
    } finally {
      setLoading(false);
    }
  }, [jobId, stage]);

  React.useEffect(() => {
    void loadStatus();
  }, [loadStatus]);

  React.useEffect(() => {
    if (connected) void loadJobs();
  }, [connected, loadJobs]);

  React.useEffect(() => {
    if (connected) void loadCandidates();
  }, [connected, loadCandidates]);

  const toggle = (id: string, checked: boolean) => {
    setSelected((prev) => (checked ? [...prev, id] : prev.filter((x) => x !== id)));
  };

  const allSelected = candidates.length > 0 && selected.length === candidates.length;

  const runImport = async (importAll: boolean) => {
    if (!orderId || disabled) return;
    const ids = importAll ? candidates.map((c) => c.id) : selected;
    if (!ids.length) {
      toast.error(importAll ? "No candidates to import" : "Select at least one candidate");
      return;
    }
    setImporting(true);
    try {
      const result = await apiFetch<{
        added?: number;
        updated?: number;
        missing_phone?: number;
      }>("/service-orders/zoho-recruit/candidates/import-to-order", {
        method: "POST",
        body: JSON.stringify({
          order_id: orderId,
          candidate_ids: ids,
          job_id: jobId || undefined,
          stage: stage.trim() || undefined,
          import_all_matching: importAll,
        }),
      });
      const added = result?.added ?? 0;
      const updated = result?.updated ?? 0;
      const missingPhone = result?.missing_phone ?? 0;
      toast.success(
        `Imported ${added} new, updated ${updated}` +
          (missingPhone ? ` · ${missingPhone} missing phone` : ""),
      );
      setSelected([]);
      onImported?.();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Import failed");
    } finally {
      setImporting(false);
    }
  };

  if (connected === null) {
    return <Skeleton className="h-28 w-full md:col-span-2" />;
  }

  if (!connected) {
    return (
      <div className="md:col-span-2 rounded-lg border border-dashed bg-muted/30 p-4 text-sm text-muted-foreground">
        Connect Zoho Recruit in{" "}
        <Link to="/settings/integrations" className="font-medium text-primary underline-offset-2 hover:underline">
          Settings → Integrations → Recruiting
        </Link>{" "}
        to import candidates into this campaign.
      </div>
    );
  }

  return (
    <div className="md:col-span-2 space-y-3 rounded-xl border bg-card p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Users className="size-4 text-primary" />
          <p className="text-sm font-medium">Import from Zoho Recruit</p>
        </div>
        <Button
          size="sm"
          variant="outline"
          className="gap-1.5"
          disabled={loading || disabled}
          onClick={() => void loadCandidates()}
        >
          <RefreshCw className={`size-3.5 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label className="text-xs">Job opening (optional)</Label>
          <select
            className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm"
            value={jobId}
            disabled={disabled}
            onChange={(e) => setJobId(e.target.value)}
          >
            <option value="">All recent candidates</option>
            {jobs.map((j) => (
              <option key={j.id} value={j.id}>
                {j.name}
                {j.status ? ` (${j.status})` : ""}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Stage / Candidate Status (optional)</Label>
          <Input
            value={stage}
            disabled={disabled}
            placeholder="e.g. Qualified"
            onChange={(e) => setStage(e.target.value)}
            onBlur={() => void loadCandidates()}
          />
        </div>
      </div>

      {loading ? (
        <Skeleton className="h-32 w-full" />
      ) : candidates.length ? (
        <div className="max-h-56 space-y-2 overflow-y-auto rounded-md border p-2">
          <label className="flex items-center gap-2 border-b pb-2 text-xs font-medium">
            <Checkbox
              checked={allSelected}
              onCheckedChange={(v) => setSelected(v === true ? candidates.map((c) => c.id) : [])}
              disabled={disabled}
            />
            Select all ({candidates.length})
          </label>
          {candidates.map((c) => (
            <label key={c.id} className="flex items-start gap-2 text-sm">
              <Checkbox
                className="mt-0.5"
                checked={selected.includes(c.id)}
                onCheckedChange={(v) => toggle(c.id, v === true)}
                disabled={disabled}
              />
              <span className="min-w-0 flex-1">
                <span className="font-medium">{c.name || "Candidate"}</span>
                <span className="mt-0.5 block truncate text-xs text-muted-foreground">
                  {c.phone || "No phone"}
                  {c.email ? ` · ${c.email}` : ""}
                  {c.stage ? ` · ${c.stage}` : ""}
                  {c.phone_missing ? " · needs phone before launch" : ""}
                </span>
              </span>
            </label>
          ))}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">No candidates matched these filters.</p>
      )}

      <div className="flex flex-wrap gap-2">
        <Button size="sm" disabled={disabled || importing || !selected.length} onClick={() => void runImport(false)}>
          {importing ? <Loader2 className="size-3.5 animate-spin" /> : null}
          Import selected ({selected.length})
        </Button>
        <Button
          size="sm"
          variant="outline"
          disabled={disabled || importing || !candidates.length}
          onClick={() => void runImport(true)}
        >
          Import all shown
        </Button>
        <Button size="sm" variant="ghost" className="gap-1.5" asChild>
          <Link to="/settings/integrations">
            Manage Zoho <ExternalLink className="size-3.5" />
          </Link>
        </Button>
      </div>
    </div>
  );
}
