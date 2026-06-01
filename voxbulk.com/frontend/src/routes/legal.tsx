import { createFileRoute } from "@tanstack/react-router";
import { PageShell } from "@/components/SiteShell";

export const Route = createFileRoute("/legal")({
  head: () => ({
    meta: [
      { title: "Legal — VoxBulk" },
      { name: "description", content: "Legal notices, company information and regulatory details for VoxBulk LTD, the AI assistant platform for modern businesses." },
      { property: "og:title", content: "Legal — VoxBulk" },
      { property: "og:description", content: "Company information and legal notices for VoxBulk LTD." },
      { property: "og:url", content: "https://voxbulk.com/legal" },
    ],
    links: [{ rel: "canonical", href: "https://voxbulk.com/legal" }],
  }),
  component: () => (
    <PageShell title="Legal" eyebrow="Legal">
      <h2>Company</h2>
      <p>VoxBulk LTD, a company registered in England &amp; Wales. Registered office available on request.</p>

      <h2>Contact</h2>
      <p>Email <a href="mailto:hello@voxbulk.com">hello@voxbulk.com</a> for general enquiries, or <a href="mailto:legal@voxbulk.com">legal@voxbulk.com</a> for legal matters.</p>

      <h2>Trademarks</h2>
      <p>"VoxBulk" and the VoxBulk logo are trademarks of VoxBulk LTD. All other trademarks belong to their respective owners.</p>

      <h2>Compliance</h2>
      <p>VoxBulk operates in accordance with UK GDPR, the Data Protection Act 2018 and PECR.</p>
    </PageShell>
  ),
});
