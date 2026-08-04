import { createFileRoute } from "@tanstack/react-router";

import { CatalogueManager } from "@/components/catalogue-manager";

export const Route = createFileRoute("/_app/smart-card/catalogue")({
  head: () => ({ meta: [{ title: "Manage products — Smart Card QR" }] }),
  component: SmartCardCataloguePage,
});

function SmartCardCataloguePage() {
  return <CatalogueManager eyebrow="Smart Card QR" apiBase="/smart-card/catalogue" />;
}
