import * as React from "react";
import { createFileRoute } from "@tanstack/react-router";

import { requireSalesRep } from "@/lib/guards/settings-route";
import { CustomerEditor } from "@/components/sales/CustomerEditor";
import "@/styles/sales-portal.css";

export const Route = createFileRoute("/_app/sales/new")({
  head: () => ({ meta: [{ title: "Add new customer — Sales" }] }),
  beforeLoad: () => requireSalesRep(),
  component: SalesNewCustomer,
});

function SalesNewCustomer() {
  return (
    <div className="salesPortal salesPortal--embedded">
      <div className="sp-app">
        <CustomerEditor customerId={null} />
      </div>
    </div>
  );
}
