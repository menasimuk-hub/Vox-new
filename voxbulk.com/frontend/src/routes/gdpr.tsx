import { createFileRoute } from "@tanstack/react-router";
import { PageShell } from "@/components/SiteShell";

export const Route = createFileRoute("/gdpr")({
  head: () => ({
    meta: [
      { title: "GDPR — VoxBulk" },
      { name: "description", content: "How VoxBulk complies with UK GDPR — data processing roles, sub-processors, security measures and how customers can exercise data subject rights." },
      { property: "og:title", content: "GDPR — VoxBulk" },
      { property: "og:description", content: "VoxBulk's UK GDPR compliance overview." },
      { property: "og:url", content: "https://voxbulk.com/gdpr" },
    ],
    links: [{ rel: "canonical", href: "https://voxbulk.com/gdpr" }],
  }),
  component: () => (
    <PageShell title="GDPR" eyebrow="Legal">
      <h2>Roles</h2>
      <p>For website visitors and account holders, VoxBulk LTD is the data controller. For end-user data processed through the platform, VoxBulk acts as the data processor on behalf of the customer (the controller).</p>

      <h2>Data Processing Agreement</h2>
      <p>Every paying customer signs a Data Processing Agreement (DPA) covering Article 28 obligations, sub-processor management, breach notification timelines (within 72 hours) and audit rights.</p>

      <h2>Security</h2>
      <p>All data is encrypted in transit and at rest. Storage and processing take place within UK / EU data centres. Access is role-based, logged and reviewed.</p>

      <h2>Data subject rights</h2>
      <p>End users should contact the customer that initiated the conversation. Customers can use the dashboard or email <a href="mailto:dpo@voxbulk.com">dpo@voxbulk.com</a> to action requests.</p>

      <h2>Regulatory</h2>
      <p>VoxBulk LTD operates in accordance with UK GDPR, the Data Protection Act 2018 and PECR.</p>
    </PageShell>
  ),
});
