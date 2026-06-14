import * as React from "react";
import { Link } from "@tanstack/react-router";
import { AlertCircle, CheckCircle2, Loader2, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useHubSpotStatus, usePushSurveyResultToHubSpot } from "@/lib/queries";

export type HubSpotSyncRespondent = {
  id?: string;
  name?: string;
  email?: string | null;
  phone?: string | null;
  status_label?: string;
  completed_at?: string | null;
  sentiment_label?: string | null;
  short_summary?: string | null;
};

function isCompletedRespondent(row: HubSpotSyncRespondent) {
  return Boolean(row.completed_at) || String(row.status_label || "").toLowerCase() === "completed";
}

export function SurveyRespondentHubSpotPushButton({
  orderId,
  respondent,
  size = "sm",
}: {
  orderId: string | null | undefined;
  respondent: HubSpotSyncRespondent;
  size?: "sm" | "default";
}) {
  const pushM = usePushSurveyResultToHubSpot(orderId);
  const [state, setState] = React.useState<"idle" | "success" | "error">("idle");
  const [message, setMessage] = React.useState<string | null>(null);

  React.useEffect(() => {
    setState("idle");
    setMessage(null);
  }, [respondent.id]);

  const onPush = async () => {
    if (!respondent.id || !orderId) return;
    setState("idle");
    setMessage(null);
    try {
      const res = await pushM.mutateAsync(respondent.id);
      if (res.skipped) {
        setState("error");
        setMessage(
          res.reason === "contact_not_found_in_hubspot"
            ? "No matching HubSpot contact."
            : "Could not push to HubSpot.",
        );
        return;
      }
      setState("success");
      toast.success(`Pushed ${respondent.name || "respondent"} to HubSpot`);
    } catch (e) {
      setState("error");
      const msg = e instanceof Error ? e.message : "Failed to push to HubSpot";
      setMessage(msg);
      toast.error(msg);
    }
  };

  return (
    <div className="space-y-1">
      <Button
        size={size}
        variant={state === "success" ? "secondary" : "outline"}
        className="gap-1.5"
        disabled={pushM.isPending || !respondent.id || !orderId || !isCompletedRespondent(respondent)}
        onClick={() => void onPush()}
      >
        {pushM.isPending ? (
          <Loader2 className="size-3.5 animate-spin" />
        ) : state === "success" ? (
          <CheckCircle2 className="size-3.5 text-success" />
        ) : state === "error" ? (
          <AlertCircle className="size-3.5 text-destructive" />
        ) : (
          <RefreshCw className="size-3.5" />
        )}
        {pushM.isPending ? "Pushing…" : state === "success" ? "Pushed" : "Push to HubSpot"}
      </Button>
      {message ? <p className="text-[11px] text-destructive">{message}</p> : null}
    </div>
  );
}

export function SurveyHubSpotSyncTab({
  orderId,
  respondents,
}: {
  orderId: string | undefined;
  respondents: HubSpotSyncRespondent[];
}) {
  const hubspotQ = useHubSpotStatus();
  const hubspot = (hubspotQ.data || {}) as Record<string, unknown>;
  const hubspotConnected = hubspot.connected === true;
  const completed = respondents.filter(isCompletedRespondent);

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="space-y-3 p-4">
          <div>
            <p className="text-sm font-medium">Push results to HubSpot</p>
            <p className="text-xs text-muted-foreground">
              Manual sync sends contact properties and a timeline note for each completed response. Automatic write-back
              still runs when WhatsApp surveys complete.
            </p>
          </div>
          {!hubspotConnected ? (
            <p className="rounded-md border border-border bg-muted/40 p-3 text-sm text-muted-foreground">
              HubSpot is not connected.{" "}
              <Link to="/settings/integrations" className="text-primary underline-offset-2 hover:underline">
                Connect HubSpot in Settings → Integrations
              </Link>{" "}
              to enable push.
            </p>
          ) : null}
          {hubspotConnected && completed.length === 0 ? (
            <p className="text-sm text-muted-foreground">No completed responses yet for this survey.</p>
          ) : null}
        </CardContent>
      </Card>

      {hubspotConnected && completed.length > 0 ? (
        <Card>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px] text-sm">
                <thead>
                  <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-muted-foreground">
                    <th className="px-4 py-3">Contact</th>
                    <th className="px-4 py-3">Email / phone</th>
                    <th className="px-4 py-3">Sentiment</th>
                    <th className="px-4 py-3 text-right">HubSpot</th>
                  </tr>
                </thead>
                <tbody>
                  {completed.map((row) => (
                    <tr key={row.id || `${row.email}-${row.phone}`} className="border-b border-border/60 last:border-0">
                      <td className="px-4 py-3 font-medium">{row.name || "Respondent"}</td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {[row.email, row.phone].filter(Boolean).join(" · ") || "—"}
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">{row.sentiment_label || "—"}</td>
                      <td className="px-4 py-3">
                        <div className="flex justify-end">
                          <SurveyRespondentHubSpotPushButton orderId={orderId} respondent={row} />
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

export function SurveyRespondentHubSpotPanel({
  orderId,
  respondent,
}: {
  orderId: string | undefined;
  respondent: HubSpotSyncRespondent;
}) {
  const hubspotQ = useHubSpotStatus();
  const hubspot = (hubspotQ.data || {}) as Record<string, unknown>;
  const hubspotConnected = hubspot.connected === true;
  const isCompleted = isCompletedRespondent(respondent);

  return (
    <Card className="border-border">
      <CardContent className="space-y-3 p-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-sm font-medium">HubSpot</p>
            <p className="text-xs text-muted-foreground">
              {hubspotConnected
                ? "Push this survey result to the linked HubSpot contact as contact properties and a timeline note."
                : "Connect HubSpot to push survey results to CRM contacts."}
            </p>
          </div>
          {hubspotConnected && isCompleted ? (
            <SurveyRespondentHubSpotPushButton orderId={orderId} respondent={respondent} />
          ) : null}
        </div>
        {!hubspotConnected ? (
          <p className="rounded-md border border-border bg-muted/40 p-3 text-xs text-muted-foreground">
            HubSpot is not connected.{" "}
            <Link to="/settings/integrations" className="text-primary underline-offset-2 hover:underline">
              Connect HubSpot in Settings → Integrations
            </Link>{" "}
            to sync survey results manually or automatically when responses complete.
          </p>
        ) : null}
        {hubspotConnected && !isCompleted ? (
          <p className="text-xs text-muted-foreground">Only completed survey responses can be pushed to HubSpot.</p>
        ) : null}
        {hubspotConnected && isCompleted ? (
          <p className="text-[11px] text-muted-foreground">
            Automatic write-back runs when responses complete. Use this button to retry or push again.
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}
