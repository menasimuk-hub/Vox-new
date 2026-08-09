import { createFileRoute } from "@tanstack/react-router";
import { PageShell } from "@/components/SiteShell";

export const Route = createFileRoute("/privacy")({
  head: () => ({
    meta: [
      { title: "Privacy Policy — VoxBulk" },
      { name: "description", content: "How VoxBulk Ltd collects, uses and protects personal data when you use our AI interviews, WhatsApp surveys, customer feedback and messaging platform." },
      { property: "og:title", content: "Privacy Policy — VoxBulk" },
      { property: "og:description", content: "How VoxBulk handles personal data and protects user privacy." },
      { property: "og:url", content: "https://voxbulk.com/privacy" },
    ],
    links: [{ rel: "canonical", href: "https://voxbulk.com/privacy" }],
  }),
  component: () => (
    <PageShell title="Privacy Policy" eyebrow="Legal">
      <p className="text-sm text-muted-text">Last updated: 25 July 2026</p>

      <h2>1. Who we are</h2>
      <p>
        VoxBulk Ltd (&quot;VoxBulk&quot;, &quot;we&quot;, &quot;us&quot;), company number 15466735, is registered in
        England and Wales with its registered office in London, United Kingdom. We are the data controller for
        personal data collected via our website and customer accounts, and the data processor for end-user data
        processed on behalf of our business customers. Data protection contact:{" "}
        <a href="mailto:Data.Pro@voxbulk.com">Data.Pro@voxbulk.com</a>.
      </p>

      <h2>2. What we collect</h2>
      <p>
        We collect (a) account data you provide (name, email, company, phone), (b) usage data (pages viewed, actions
        in the dashboard), and (c) on behalf of our customers: contact details, messaging metadata, survey and
        feedback responses, AI call / message transcripts and related scores or reports.
      </p>

      <h2>3. Lawful basis</h2>
      <p>
        We rely on contract and legitimate interests for service operation, and consent for marketing where required.
        End-user conversations are processed under the customer&apos;s lawful basis. Processor terms are in our Data
        Processing Agreement (accepted at signup; PDF on request from{" "}
        <a href="mailto:Data.Pro@voxbulk.com">Data.Pro@voxbulk.com</a>).
      </p>

      <h2>3A. Smart Card QR</h2>
      <p>
        When a visitor scans a Smart Card QR, we process on behalf of the customer organisation (typically as
        processor) the card profile they published and any lead answers the visitor submits, including optional
        marketing / contact consent and related proof (time, channel, prompt shown, answer). The customer organisation
        usually decides the purpose of that lead data (controller). Contact details on a published card are visible to
        anyone with the QR link. Customers can export consent records from the dashboard for their own compliance
        records. For rights requests relating to lead data collected for a customer, contact that organisation or{" "}
        <a href="mailto:Data.Pro@voxbulk.com">Data.Pro@voxbulk.com</a> and we will assist under our processor role.
      </p>

      <h2>4. Retention</h2>
      <p>
        Account and billing data is kept while your account is active and for up to 24 months after closure (or longer
        where legally required). <strong>Call recordings and full transcripts</strong> are retained for{" "}
        <strong>30 days</strong> by default. <strong>Other operational data</strong> we store on our servers
        (including WhatsApp message bodies, structured survey/interview responses, scores and reports) is retained for{" "}
        <strong>90 days</strong> by default, then anonymised or deleted. Shorter periods may be available in product
        settings where offered.
      </p>

      <h2>5. Your rights</h2>
      <p>
        Under UK GDPR you have rights of access, rectification, erasure, restriction, objection and portability.
        Email <a href="mailto:Data.Pro@voxbulk.com">Data.Pro@voxbulk.com</a> to exercise them. You may also complain
        to the Information Commissioner&apos;s Office (ICO).
      </p>

      <h2>6. Contact</h2>
      <p>
        VoxBulk Ltd · Company No. 15466735 · London, United Kingdom ·{" "}
        <a href="mailto:Data.Pro@voxbulk.com">Data.Pro@voxbulk.com</a>
      </p>
    </PageShell>
  ),
});
