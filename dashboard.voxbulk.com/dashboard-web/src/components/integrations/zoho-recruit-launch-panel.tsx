import * as React from "react";
import { Link } from "@tanstack/react-router";
import { ExternalLink, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { apiFetch } from "@/lib/api";

type ScreeningRow = {
  id: string;
  partner_reference_id: string;
  candidate_name: string;
  status: string;
  result_status?: string | null;
  candidate_score?: number | null;
  screening_link: string;
};

/**
 * Thin Zoho Recruit integrations panel — hybrid flow runs in the interview wizard.
 * Legacy Partner one-shot launch is not offered here.
 */
export function ZohoRecruitLaunchPanel({ onLaunched }: { onLaunched?: () => void }) {
  const [busy, setBusy] = React.useState(false);
  const [recent, setRecent] = React.useState<ScreeningRow[]>([]);

  const loadRecent = React.useCallback(async () => {
    try {
      const data = await apiFetch<{ items?: ScreeningRow[] }>("/service-orders/zoho-recruit/screenings");
      setRecent(data?.items || []);
    } catch {
      /* ignore */
    }
  }, []);

  React.useEffect(() => {
    void loadRecent();
  }, [loadRecent]);

  const disconnect = async () => {
    setBusy(true);
    try {
      await apiFetch("/service-orders/zoho-recruit/disconnect", { method: "POST" });
      toast.success("Zoho Recruit disconnected");
      onLaunched?.();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Disconnect failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4 rounded-lg border bg-muted/20 p-4">
      <div>
        <p className="text-sm font-medium">Hybrid interview workflow</p>
        <p className="mt-1 text-xs text-muted-foreground">
          Create an interview in VoxBulk, import your Zoho candidate list, run ATS and AI calls, then
          scores write back to Zoho as Notes.
        </p>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" className="gap-1.5" asChild>
          <Link to="/interviews/new">
            Open interview wizard <ExternalLink className="size-3.5" />
          </Link>
        </Button>
        <Button size="sm" variant="outline" disabled={busy} onClick={() => void loadRecent()}>
          {busy ? <Loader2 className="size-3.5 animate-spin" /> : null}
          Refresh history
        </Button>
        <Button size="sm" variant="ghost" disabled={busy} onClick={() => void disconnect()}>
          Disconnect
        </Button>
      </div>
      {recent.length ? (
        <div className="space-y-1.5">
          <p className="text-xs font-medium text-muted-foreground">Recent partner screenings (legacy)</p>
          <ul className="max-h-36 space-y-1 overflow-y-auto text-xs">
            {recent.slice(0, 8).map((row) => (
              <li key={row.id} className="flex justify-between gap-2 border-b border-border/60 py-1">
                <span className="truncate font-medium text-foreground">
                  {row.candidate_name || row.partner_reference_id}
                </span>
                <span className="shrink-0 text-muted-foreground">
                  {row.result_status || row.status}
                  {row.candidate_score != null ? ` · ${row.candidate_score}` : ""}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
