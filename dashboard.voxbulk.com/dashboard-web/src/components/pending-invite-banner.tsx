import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { useAcceptInviteSession, usePendingInvites } from "@/lib/queries";

export function PendingInviteBanner() {
  const invitesQ = usePendingInvites();
  const acceptM = useAcceptInviteSession();
  const invites = invitesQ.data?.invites ?? [];

  if (invitesQ.isLoading || invites.length === 0) return null;

  const inv = invites[0];

  return (
    <div className="rounded-lg border border-primary/30 bg-primary/5 px-4 py-3 text-sm flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <p>
        You were invited to join <strong>{inv.organisation_name}</strong> as{" "}
        <strong className="capitalize">{inv.role}</strong>.
      </p>
      <Button
        size="sm"
        disabled={acceptM.isPending}
        onClick={() => {
          void acceptM.mutateAsync(inv.token).catch((e: unknown) => {
            toast.error(e instanceof Error ? e.message : "Could not accept invitation");
          });
        }}
      >
        {acceptM.isPending ? "Joining…" : "Accept invitation"}
      </Button>
    </div>
  );
}
