import * as React from "react";
import { Coins, Play, Save, Square } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { orderPayButton } from "@/lib/billing/order-pay-labels";
import {
  useLaunchInterviewCampaign,
  usePatchServiceOrder,
  useStopSurveyOrder,
} from "@/lib/queries";
import type { ServiceOrder } from "@/lib/types/api";

type InterviewEditActionBarProps = {
  order: ServiceOrder | null | undefined;
  onSave: () => void | Promise<void>;
  savePending?: boolean;
  onOpenLaunch?: () => void | Promise<void>;
  launchPending?: boolean;
};

export function InterviewEditActionBar({
  order,
  onSave,
  savePending,
  onOpenLaunch,
  launchPending,
}: InterviewEditActionBarProps) {
  const stopM = useStopSurveyOrder();
  const launchM = useLaunchInterviewCampaign(order?.id || null);
  const patchM = usePatchServiceOrder();
  const pay = orderPayButton(order);

  if (!order?.id) return null;

  const status = String(order.status || "").toLowerCase();
  const paymentStatus = String(order.payment_status || "").toLowerCase();
  const needsPayAction = pay.action === "launch" && paymentStatus !== "approved";
  const runningLike = ["running", "paused", "scheduled"].includes(status);
  const canRun = paymentStatus === "approved" && !runningLike && !["completed", "cancelled"].includes(status);

  const onStop = async () => {
    try {
      await stopM.mutateAsync(order.id);
      toast.success("Interview stopped");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Stop failed");
    }
  };

  const onRun = async () => {
    try {
      await launchM.mutateAsync({});
      toast.success("Interview launched");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Launch failed");
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-2">
      {order.workflow_label ? (
        <span className="rounded-md border border-border px-2 py-1 text-xs text-muted-foreground">{order.workflow_label}</span>
      ) : null}
      {runningLike ? (
        <Button size="sm" variant="outline" className="gap-1.5" onClick={() => void onStop()} disabled={stopM.isPending}>
          <Square className="size-4" /> Stop
        </Button>
      ) : null}
      {pay.action === "wait" ? (
        <Button size="sm" variant="outline" disabled title={pay.hint}>
          {pay.label}
        </Button>
      ) : needsPayAction ? (
        <Button
          size="sm"
          variant="outline"
          className="gap-1.5"
          title={pay.hint}
          disabled={launchPending}
          onClick={() => void onOpenLaunch?.()}
        >
          <Coins className="size-4" /> {pay.label}
        </Button>
      ) : null}
      {canRun ? (
        <Button size="sm" className="gap-1.5" onClick={() => void onRun()} disabled={launchM.isPending || patchM.isPending}>
          <Play className="size-4" /> Run
        </Button>
      ) : null}
      <Button size="sm" variant="default" className="gap-1.5" onClick={() => void onSave()} disabled={savePending}>
        <Save className="size-4" /> Save
      </Button>
    </div>
  );
}
