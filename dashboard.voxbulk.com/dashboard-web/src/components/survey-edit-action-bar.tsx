import * as React from "react";
import { Coins, Copy, Play, Save, Square, Trash2 } from "lucide-react";
import { useNavigate } from "@tanstack/react-router";
import { toast } from "sonner";

import { PaymentModal } from "@/components/modals";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { useDeleteOrder, useDuplicateSurveyOrder, useLaunchSurveyCampaign, useStopSurveyOrder } from "@/lib/queries";
import type { ServiceOrder } from "@/lib/types/api";

type SurveyEditActionBarProps = {
  order: ServiceOrder | null | undefined;
  onSave: () => void | Promise<void>;
  savePending?: boolean;
  onPay?: () => void | Promise<void>;
  payBusy?: boolean;
  gcAvailable?: boolean;
};

export function SurveyEditActionBar({
  order,
  onSave,
  savePending,
  onPay,
  payBusy,
  gcAvailable = true,
}: SurveyEditActionBarProps) {
  const navigate = useNavigate();
  const stopM = useStopSurveyOrder();
  const launchM = useLaunchSurveyCampaign();
  const deleteM = useDeleteOrder();
  const duplicateM = useDuplicateSurveyOrder();
  const [deleteOpen, setDeleteOpen] = React.useState(false);
  const [payOpen, setPayOpen] = React.useState(false);

  if (!order?.id) return null;

  const status = String(order.status || "").toLowerCase();
  const paymentStatus = String(order.payment_status || "").toLowerCase();
  const needsPay = ["unpaid", "quoted", "pending_approval"].includes(paymentStatus);
  const runningLike = ["running", "paused", "scheduled"].includes(status);
  const canRun = paymentStatus === "approved" && !runningLike && !["completed", "cancelled"].includes(status);

  const onRun = async () => {
    try {
      await launchM.mutateAsync({ orderId: order.id, run_mode: "now" });
      toast.success("Survey launched");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Launch failed");
    }
  };

  const onStop = async () => {
    try {
      await stopM.mutateAsync(order.id);
      toast.success("Survey stopped");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Stop failed");
    }
  };

  const onDuplicate = async () => {
    try {
      const res = await duplicateM.mutateAsync(order.id);
      const copyId = res.order?.id;
      if (copyId) {
        toast.success("Survey duplicated");
        void navigate({ to: "/surveys/new", search: { order_id: copyId } });
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Duplicate failed");
    }
  };

  const onDelete = async () => {
    try {
      if (runningLike) await stopM.mutateAsync(order.id);
      await deleteM.mutateAsync({ orderId: order.id, confirmRunningDelete: runningLike });
      toast.success("Survey deleted");
      setDeleteOpen(false);
      void navigate({ to: "/surveys" });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Delete failed");
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
        <Button size="sm" variant="default" className="gap-1.5" onClick={() => void onSave()} disabled={savePending}>
          <Save className="size-4" /> Save
        </Button>
        {needsPay ? (
          <Button size="sm" variant="outline" className="gap-1.5" onClick={() => setPayOpen(true)}>
            <Coins className="size-4" /> Pay
          </Button>
        ) : null}
        {canRun ? (
          <Button size="sm" className="gap-1.5" onClick={() => void onRun()} disabled={launchM.isPending}>
            <Play className="size-4" /> Run
          </Button>
        ) : null}
        <Button size="sm" variant="outline" className="gap-1.5" onClick={() => void onDuplicate()} disabled={duplicateM.isPending}>
          <Copy className="size-4" /> Duplicate
        </Button>
        <Button
          size="sm"
          variant="outline"
          className="gap-1.5 text-destructive hover:text-destructive"
          onClick={() => setDeleteOpen(true)}
        >
          <Trash2 className="size-4" /> Delete
        </Button>
      </div>

      <PaymentModal
        open={payOpen}
        onOpenChange={setPayOpen}
        busy={payBusy}
        gcAvailable={gcAvailable}
        onPayGoCardless={onPay}
      />

      <AlertDialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete survey?</AlertDialogTitle>
            <AlertDialogDescription>
              {runningLike
                ? "This survey is still active. It will be stopped, then permanently deleted."
                : "Permanently delete this survey? This cannot be undone."}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => void onDelete()}
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
