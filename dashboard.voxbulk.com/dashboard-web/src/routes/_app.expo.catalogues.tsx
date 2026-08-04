import { createFileRoute } from "@tanstack/react-router";

import { CatalogueManager } from "@/components/catalogue-manager";

export const Route = createFileRoute("/_app/expo/catalogues")({
  head: () => ({ meta: [{ title: "Add catalogues — Expo — VoxBulk" }] }),
  component: ExpoCataloguesPage,
});

function ExpoCataloguesPage() {
  return <CatalogueManager eyebrow="VoxBulk Expo" apiBase="/expo/catalogue" />;
}
