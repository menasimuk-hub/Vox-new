import { createFileRoute, Link } from "@tanstack/react-router";
import { PageShell } from "@/components/SiteShell";

export const Route = createFileRoute("/terms")({
  head: () => ({
    meta: [
      { title: "Terms & Conditions — VoxBulk" },
      { name: "description", content: "Terms and conditions governing use of the VoxBulk platform for AI interviews, WhatsApp surveys, customer feedback and business messaging." },
      { property: "og:title", content: "Terms & Conditions — VoxBulk" },
      { property: "og:description", content: "Read the terms governing the use of VoxBulk." },
      { property: "og:url", content: "https://voxbulk.com/terms" },
    ],
    links: [{ rel: "canonical", href: "https://voxbulk.com/terms" }],
  }),
  component: () => (
    <PageShell title="Terms & Conditions" eyebrow="Legal">
      <p className="text-sm text-muted-text">Last updated: 25 July 2026</p>

      <h2>1. Acceptance of terms</h2>
      <p>
        These Terms govern your access to and use of the VoxBulk platform, websites and APIs (&quot;Service&quot;)
        provided by VoxBulk Ltd (company number 15466735), registered in England and Wales, London, United Kingdom.
        The Service is offered to <strong>business customers only</strong>. By creating an account you confirm you
        act in a business capacity and agree to these Terms, our <Link to="/privacy">Privacy Policy</Link>, and our
        Data Processing Agreement (accepted at signup; PDF available on request from{" "}
        <a href="mailto:Data.Pro@voxbulk.com">Data.Pro@voxbulk.com</a>).
      </p>

      <h2>2. The service</h2>
      <p>
        VoxBulk provides AI-powered voice and messaging tools for businesses, including recruitment interviews,
        WhatsApp surveys, AI calling surveys, customer feedback, Expo lead capture, broadcast campaigns, and
        booking/CRM integrations. Telephony and messaging are delivered through third-party providers. The Service
        does not provide legal, medical or financial advice.
      </p>

      <h2>3. Customer obligations</h2>
      <p>
        You are responsible for ensuring you have the legal basis (and any required consents under UK GDPR and PECR)
        to contact recipients you upload or sync, for keeping account credentials secure, for the accuracy of data
        you provide, and for complying with messaging platform rules applicable to your use. You must honour opt-outs
        and STOP requests.
      </p>

      <h2>3A. Smart Card QR</h2>
      <p>
        Smart Card QR lets your organisation publish a digital business card via a durable QR link that you choose to
        print or share. Anyone who scans or opens that link can view the contact details you published on the card.
        You control what appears on each card and who you give the QR to. Lead answers (including marketing or contact
        consent) are collected for your organisation; you are responsible for using those leads lawfully, for your own
        marketing, and for honouring withdrawal of consent. VoxBulk provides the platform and security measures; we do
        not control how third parties treat a printed QR once you distribute it. Nothing in this section excludes
        liability that cannot be limited under English law (including fraud, death or personal injury caused by
        negligence, or non-excludable data-protection duties). Aggregate liability remains as set out in section 6.
      </p>

      <h2>4. Data processing</h2>
      <p>
        When we process personal data of your end users, we act as processor under our Data Processing Agreement,
        which forms part of your agreement with us at signup. A PDF copy is available on request from{" "}
        <a href="mailto:Data.Pro@voxbulk.com">Data.Pro@voxbulk.com</a>. Default retention: call recordings and full
        transcripts 30 days; other operational data on our servers 90 days (see the Privacy Policy).
      </p>

      <h2>5. Fees &amp; cancellation</h2>
      <p>
        Paid plans are billed according to your selected package. You may cancel with 30 days&apos; written notice
        unless your order states otherwise. Fees already paid are non-refundable except where required by law or our
        refund processes.
      </p>

      <h2>6. Liability</h2>
      <p>
        To the maximum extent permitted by law, VoxBulk&apos;s aggregate liability under these Terms is limited to
        the fees paid in the 12 months preceding the claim.
      </p>

      <h2>7. Governing law</h2>
      <p>These Terms are governed by the laws of England and Wales.</p>

      <h2>8. Contact</h2>
      <p>
        Data protection: <a href="mailto:Data.Pro@voxbulk.com">Data.Pro@voxbulk.com</a> · Support:{" "}
        <a href="mailto:support@voxbulk.com">support@voxbulk.com</a>
      </p>
    </PageShell>
  ),
});
