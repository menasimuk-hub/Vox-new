import { createFileRoute } from "@tanstack/react-router";
import { PageShell } from "@/components/SiteShell";

export const Route = createFileRoute("/privacy")({
  head: () => ({
    meta: [
      { title: "Privacy Policy — VoxBulk" },
      { name: "description", content: "How VoxBulk LTD collects, uses and protects personal data when you use our AI assistant platform for voice, messaging and workflow automation." },
      { property: "og:title", content: "Privacy Policy — VoxBulk" },
      { property: "og:description", content: "How VoxBulk handles personal data and protects user privacy." },
      { property: "og:url", content: "https://voxbulk.com/privacy" },
    ],
    links: [{ rel: "canonical", href: "https://voxbulk.com/privacy" }],
  }),
  component: () => (
    <PageShell title="Privacy Policy" eyebrow="Legal">
      <p className="text-sm text-muted-text">Last updated: 28 May 2026</p>

      <h2>1. Who we are</h2>
      <p>VoxBulk LTD ("VoxBulk", "we", "us") is a company registered in England &amp; Wales. We are the data controller for personal data collected via our website, and the data processor for end-user data processed on behalf of our customers using the Service.</p>

      <h2>2. What we collect</h2>
      <p>We collect (a) account data you provide (name, email, company, phone), (b) usage data (pages viewed, actions taken in the dashboard), and (c) on behalf of our customers, contact details, conversation metadata and AI call / message transcripts.</p>

      <h2>3. Lawful basis</h2>
      <p>We rely on legitimate interests for service operation, contract for paid customers, and consent for marketing communications. End-user conversations are processed under the customer's lawful basis.</p>

      <h2>4. Retention</h2>
      <p>Account data is kept while your account is active and for up to 24 months after closure. Call recordings and transcripts are retained for 90 days by default, configurable per customer.</p>

      <h2>5. Your rights</h2>
      <p>Under UK GDPR you have rights of access, rectification, erasure, restriction, objection and portability. Email <a href="mailto:privacy@voxbulk.com">privacy@voxbulk.com</a> to exercise them.</p>

      <h2>6. Contact</h2>
      <p>VoxBulk LTD · <a href="mailto:privacy@voxbulk.com">privacy@voxbulk.com</a></p>
    </PageShell>
  ),
});
