import { createFileRoute } from "@tanstack/react-router";
import { PageShell } from "@/components/SiteShell";

export const Route = createFileRoute("/terms")({
  head: () => ({
    meta: [
      { title: "Terms & Conditions — VoxBulk" },
      { name: "description", content: "The terms and conditions that govern your use of the VoxBulk AI assistant platform, including voice, messaging and workflow automation services." },
      { property: "og:title", content: "Terms & Conditions — VoxBulk" },
      { property: "og:description", content: "Read the terms governing the use of VoxBulk's AI assistant platform." },
      { property: "og:url", content: "https://voxbulk.com/terms" },
    ],
    links: [{ rel: "canonical", href: "https://voxbulk.com/terms" }],
  }),
  component: () => (
    <PageShell title="Terms & Conditions" eyebrow="Legal">
      <p className="text-sm text-muted-text">Last updated: 28 May 2026</p>

      <h2>1. Acceptance of terms</h2>
      <p>These Terms govern your access to and use of the VoxBulk platform, websites and APIs ("Service") provided by VoxBulk LTD. By using the Service you agree to be bound by these Terms.</p>

      <h2>2. The service</h2>
      <p>VoxBulk provides AI-powered voice and messaging tools that automate conversations, workflows and data collection for businesses, including recruitment automation and survey delivery. The Service does not provide legal, medical or financial advice.</p>

      <h2>3. Customer obligations</h2>
      <p>You are responsible for ensuring you have the legal basis to contact the recipients you upload, for keeping account credentials secure, and for the accuracy of data you provide to the Service.</p>

      <h2>4. Fees & cancellation</h2>
      <p>Paid plans are billed monthly in advance. You may cancel at any time with 30 days' written notice. Fees already paid are non-refundable.</p>

      <h2>5. Liability</h2>
      <p>To the maximum extent permitted by law, VoxBulk's aggregate liability under these Terms is limited to the fees paid in the 12 months preceding the claim.</p>

      <h2>6. Governing law</h2>
      <p>These Terms are governed by the laws of England &amp; Wales.</p>
    </PageShell>
  ),
});
