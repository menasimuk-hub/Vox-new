import * as React from "react";
import { Coins, Copy, Play, Save, Square, Trash2 } from "lucide-react";
import { useNavigate } from "@tanstack/react-router";
import { toast } from "sonner";

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
import { orderHasPayableQuote, orderPayButton } from "@/lib/billing/order-pay-labels";
import { useBillingUsage, useDeleteOrder, useDuplicateSurveyOrder, useLaunchSurveyCampaign, useStopSurveyOrder } from "@/lib/queries";
import type { ServiceOrder } from "@/lib/types/api";
import { WalletTopupDialog } from "@/components/wallet-topup-dialog";

type SurveyEditActionBarProps = {
  order: ServiceOrder | null | undefined;
  onSave: () => void | Promise<void>;
  savePending?: boolean;
  onOpenLaunch?: () => void | Promise<void>;
  launchPending?: boolean;
};

export function SurveyEditActionBar({
  order,
  onSave,
  savePending,
  onOpenLaunch,
  launchPending,
}: SurveyEditActionBarProps) {
  const navigate = useNavigate();
  const stopM = useStopSurveyOrder();
  const launchM = useLaunchSurveyCampaign();
  const deleteM = useDeleteOrder();
  const duplicateM = useDuplicateSurveyOrder();
  const [deleteOpen, setDeleteOpen] = React.useState(false);
  const [topupOpen, setTopupOpen] = React.useState(false);
  const usageQ = useBillingUsage();

  if (!order?.id) return null;

  const status = String(order.status || "").toLowerCase();
  const paymentStatus = String(order.payment_status || "").toLowerCase();
  const pay = orderPayButton(order);
  const payableQuote = orderHasPayableQuote(order);
  const needsPayAction = pay.action === "launch" && paymentStatus !== "approved" && payableQuote;
  const needsTopUp =
    String(usageQ.data?.next_action || "") === "top_up_wallet" &&
    paymentStatus !== "approved" &&
    !["completed", "cancelled"].includes(status);
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
        {order.workflow_label ? (
          <span className="rounded-md border border-border px-2 py-1 text-xs text-muted-foreground">{order.workflow_label}</span>
        ) : null}
        {runningLike ? (
          <Button size="sm" variant="outline" className="gap-1.5" onClick={() => void onStop()} disabled={stopM.isPending}>
            <Square className="size-4" /> Stop
          </Button>
        ) : null}
        <Button size="sm" variant="default" className="gap-1.5" onClick={() => void onSave()} disabled={savePending}>
          <Save className="size-4" /> Save
        </Button>
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
        ) : pay.action === "launch" && paymentStatus !== "approved" && !payableQuote ? (
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
        {needsTopUp ? (
          <Button size="sm" variant="outline" className="gap-1.5" onClick={() => setTopupOpen(true)}>
            <Coins className="size-4" /> Top up wallet
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

      <WalletTopupDialog open={topupOpen} onOpenChange={setTopupOpen} onToppedUp={() => void usageQ.refetch()} />
    </>
  );
}
