import * as React from "react";
import { Coins, Play, Save, Square } from "lucide-react";
import { toast } from "sonner";

import { PaymentModal } from "@/components/modals";
import { Button } from "@/components/ui/button";
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
  gcAvailable?: boolean;
  onPay?: () => void | Promise<void>;
  payBusy?: boolean;
};

export function InterviewEditActionBar({
  order,
  onSave,
  savePending,
  gcAvailable = true,
  onPay,
  payBusy,
}: InterviewEditActionBarProps) {
  const stopM = useStopSurveyOrder();
  const launchM = useLaunchInterviewCampaign(order?.id || null);
  const patchM = usePatchServiceOrder();
  const [payOpen, setPayOpen] = React.useState(false);

  if (!order?.id) return null;

  const status = String(order.status || "").toLowerCase();
  const paymentStatus = String(order.payment_status || "").toLowerCase();
  const needsPay = ["unpaid", "quoted", "pending_approval"].includes(paymentStatus);
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
    <>
      <div className="flex flex-wrap items-center gap-2">
        {runningLike ? (
          <Button size="sm" variant="outline" className="gap-1.5" onClick={() => void onStop()} disabled={stopM.isPending}>
            <Square className="size-4" /> Stop
          </Button>
        ) : null}
        {needsPay ? (
          <Button size="sm" variant="outline" className="gap-1.5" onClick={() => setPayOpen(true)}>
            <Coins className="size-4" /> Pay
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

      <PaymentModal
        open={payOpen}
        onOpenChange={setPayOpen}
        busy={payBusy}
        gcAvailable={gcAvailable}
        onPayGoCardless={onPay}
      />
    </>
  );
}
