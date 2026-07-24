import * as React from "react";
import { Link } from "@tanstack/react-router";
import { Loader2, RefreshCw, Users } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { apiFetch } from "@/lib/api";

type Position = { id: string; name: string; status?: string | null };
type Candidate = {
  id: string;
  name: string;
  email: string;
  phone: string;
  job_title?: string;
  stage?: string | null;
  phone_missing?: boolean;
};

type Props = {
  orderId: string;
  onImported?: () => void;
  disabled?: boolean;
  /** Prefill from deep-link */
  initialPositionId?: string;
  initialCandidateId?: string;
};

export function BreezyHrImportPanel({
  orderId,
  onImported,
  disabled,
  initialPositionId,
  initialCandidateId,
}: Props) {
  const [connected, setConnected] = React.useState<boolean | null>(null);
  const [positions, setPositions] = React.useState<Position[]>([]);
  const [candidates, setCandidates] = React.useState<Candidate[]>([]);
  const [positionId, setPositionId] = React.useState(initialPositionId || "");
  const [selected, setSelected] = React.useState<string[]>(
    initialCandidateId ? [initialCandidateId] : [],
  );
  const [loading, setLoading] = React.useState(false);
  const [importing, setImporting] = React.useState(false);

  const loadStatus = React.useCallback(async () => {
    try {
      const data = await apiFetch<{ connected?: boolean }>("/service-orders/breezy-hr/status");
      setConnected(data?.connected === true);
    } catch {
      setConnected(false);
    }
  }, []);

  const loadPositions = React.useCallback(async () => {
    try {
      const data = await apiFetch<{ items?: Position[] }>("/service-orders/breezy-hr/positions");
      setPositions(data?.items || []);
    } catch {
      setPositions([]);
    }
  }, []);

  const loadCandidates = React.useCallback(async () => {
    if (!positionId) {
      setCandidates([]);
      setSelected([]);
      return;
    }
    setLoading(true);
    try {
      const qs = new URLSearchParams({ position_id: positionId, per_page: "100" });
      const data = await apiFetch<{ items?: Candidate[] }>(
        `/service-orders/breezy-hr/candidates?${qs.toString()}`,
      );
      setCandidates(data?.items || []);
      setSelected((prev) => prev.filter((id) => (data?.items || []).some((c) => c.id === id)));
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not load Breezy candidates");
      setCandidates([]);
    } finally {
      setLoading(false);
    }
  }, [positionId]);

  React.useEffect(() => {
    void loadStatus();
  }, [loadStatus]);

  React.useEffect(() => {
    if (connected) void loadPositions();
  }, [connected, loadPositions]);

  React.useEffect(() => {
    if (connected && positionId) void loadCandidates();
  }, [connected, positionId, loadCandidates]);

  const toggle = (id: string, checked: boolean) => {
    setSelected((prev) => (checked ? [...prev, id] : prev.filter((x) => x !== id)));
  };

  const allSelected = candidates.length > 0 && selected.length === candidates.length;

  const runImport = async (importAll: boolean) => {
    if (!orderId || disabled || !positionId) return;
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
      }>("/service-orders/breezy-hr/candidates/import-to-order", {
        method: "POST",
        body: JSON.stringify({
          order_id: orderId,
          position_id: positionId,
          candidate_ids: ids,
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
        Connect Breezy HR in{" "}
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
          <p className="text-sm font-medium">Import from Breezy HR</p>
        </div>
        <Button
          size="sm"
          variant="outline"
          className="gap-1.5"
          disabled={loading || disabled || !positionId}
          onClick={() => void loadCandidates()}
        >
          <RefreshCw className={`size-3.5 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>

      <div className="space-y-1.5">
        <Label className="text-xs">Position</Label>
        <select
          className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm"
          value={positionId}
          disabled={disabled}
          onChange={(e) => setPositionId(e.target.value)}
        >
          <option value="">Select a position…</option>
          {positions.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
              {p.status ? ` (${p.status})` : ""}
            </option>
          ))}
        </select>
      </div>

      {!positionId ? (
        <p className="text-xs text-muted-foreground">Choose a Breezy position to load candidates.</p>
      ) : loading ? (
        <Skeleton className="h-32 w-full" />
      ) : candidates.length === 0 ? (
        <p className="text-xs text-muted-foreground">No candidates on this position.</p>
      ) : (
        <>
          <div className="flex items-center gap-2 border-b pb-2">
            <Checkbox
              checked={allSelected}
              onCheckedChange={(v) =>
                setSelected(v === true ? candidates.map((c) => c.id) : [])
              }
              disabled={disabled}
            />
            <span className="text-xs text-muted-foreground">
              {selected.length} of {candidates.length} selected
            </span>
          </div>
          <ul className="max-h-48 space-y-2 overflow-y-auto">
            {candidates.map((c) => (
              <li key={c.id} className="flex items-start gap-2 text-sm">
                <Checkbox
                  checked={selected.includes(c.id)}
                  onCheckedChange={(v) => toggle(c.id, v === true)}
                  disabled={disabled}
                  className="mt-0.5"
                />
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium">{c.name}</p>
                  <p className="truncate text-xs text-muted-foreground">
                    {[c.email, c.phone, c.stage].filter(Boolean).join(" · ") || c.id}
                    {c.phone_missing ? " · missing phone" : ""}
                  </p>
                </div>
              </li>
            ))}
          </ul>
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              disabled={disabled || importing || selected.length === 0}
              onClick={() => void runImport(false)}
            >
              {importing ? <Loader2 className="size-3.5 animate-spin" /> : null}
              Import selected
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={disabled || importing || candidates.length === 0}
              onClick={() => void runImport(true)}
            >
              Import all on position
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
