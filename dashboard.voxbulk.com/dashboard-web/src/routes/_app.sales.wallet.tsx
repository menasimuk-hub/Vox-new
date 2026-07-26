import * as React from "react";
import { createFileRoute } from "@tanstack/react-router";

import { SalesPayoutWallet } from "@/components/sales-payout-wallet";
import { requireSalesRep } from "@/lib/guards/settings-route";
import "@/styles/sales-portal.css";

export const Route = createFileRoute("/_app/sales/wallet")({
  head: () => ({ meta: [{ title: "Wallet — Sales" }] }),
  beforeLoad: () => requireSalesRep(),
  component: SalesWallet,
});

function SalesWallet() {
  return (
    <div className="salesPortal salesPortal--embedded">
      <div className="sp-app">
        <div className="sp-simple">
          <h2>Wallet & payouts</h2>
          <p>Your commission balance, bank/PayPal details, and withdrawal invoices.</p>
          <SalesPayoutWallet />
        </div>
      </div>
    </div>
  );
}
