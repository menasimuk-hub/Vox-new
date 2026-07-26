import * as React from "react";
import { createFileRoute } from "@tanstack/react-router";

import { PageHeader } from "@/components/page-header";
import { SalesPayoutWallet } from "@/components/sales-payout-wallet";
import { requirePartnerChannel } from "@/lib/guards/settings-route";

export const Route = createFileRoute("/_app/partner-channel/wallet")({
  head: () => ({ meta: [{ title: "Wallet & commission — VoxBulk" }] }),
  beforeLoad: () => requirePartnerChannel(),
  component: PartnerChannelWallet,
});

function PartnerChannelWallet() {
  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="Partner Channel Sales"
        title="Wallet & commission"
        description="Your partner earnings, payout details, and withdrawal invoices. Amounts are in GBP."
      />
      <SalesPayoutWallet />
    </div>
  );
}
