import { createFileRoute, Link } from "@tanstack/react-router";
import { PageShell } from "@/components/SiteShell";

export const Route = createFileRoute("/dpa")({
  head: () => ({
    meta: [
      { title: "Data Processing Agreement — VoxBulk" },
      {
        name: "description",
        content:
          "VoxBulk Data Processing Agreement (UK GDPR Article 28) for business customers using our AI interviews, WhatsApp surveys, customer feedback and messaging services.",
      },
      { property: "og:title", content: "Data Processing Agreement — VoxBulk" },
      { property: "og:description", content: "UK GDPR Article 28 DPA for VoxBulk business customers." },
      { property: "og:url", content: "https://voxbulk.com/dpa" },
    ],
    links: [{ rel: "canonical", href: "https://voxbulk.com/dpa" }],
  }),
  component: DpaPage,
});

function DpaPage() {
  return (
    <PageShell title="Data Processing Agreement" eyebrow="Legal">
      <p className="text-sm text-muted-text">
        Last updated: 25 July 2026 · VoxBulk Ltd · Company No. 15466735 · London, United Kingdom
      </p>
      <p>
        <a
          href="/legal/voxbulk-dpa.pdf"
          className="inline-flex items-center font-semibold text-primary underline underline-offset-2 hover:opacity-90"
          download
        >
          Download PDF
        </a>
        {" · "}
        Questions:{" "}
        <a href="mailto:Data.Pro@voxbulk.com" className="underline hover:opacity-90">
          Data.Pro@voxbulk.com
        </a>
      </p>

      <div className="rounded-xl border border-border bg-secondary/40 p-4 text-sm">
        <p>
          This Data Processing Agreement (&quot;DPA&quot;) forms part of the agreement between VoxBulk Ltd
          (&quot;Processor&quot;, &quot;we&quot;, &quot;us&quot;) and the business customer (&quot;Controller&quot;,
          &quot;you&quot;) that creates a VoxBulk account. By ticking the signup checkbox and creating an account,
          you agree to our <Link to="/terms">Terms &amp; Conditions</Link>,{" "}
          <Link to="/privacy">Privacy Policy</Link>, and this DPA.
        </p>
      </div>

      <h2>1. Roles</h2>
      <p>
        For personal data of your end users (candidates, survey respondents, customers, feedback respondents and
        similar contacts), you are the <strong>controller</strong> and VoxBulk is the <strong>processor</strong>.
        For your own account, billing and website visitor data, VoxBulk is the controller as described in our{" "}
        <Link to="/privacy">Privacy Policy</Link>.
      </p>

      <h2>2. Subject matter and duration</h2>
      <p>
        We process personal data only to provide the VoxBulk services you enable (including AI interviews, WhatsApp
        surveys, AI calling surveys, customer feedback, Expo lead capture, broadcast campaigns, booking/CRM
        integrations and related support), for the duration of your subscription and any retention period below,
        unless longer retention is required by law.
      </p>

      <h2>3. Categories of data and data subjects</h2>
      <p>Depending on the services you use, we may process:</p>
      <ul>
        <li>Identity and contact details (name, phone, email)</li>
        <li>WhatsApp and messaging content and delivery metadata</li>
        <li>Call recordings and full transcripts</li>
        <li>Survey answers, interview scores, summaries and reports</li>
        <li>Feedback ratings, voice notes and location codes</li>
        <li>Booking and CRM sync identifiers you choose to connect</li>
      </ul>
      <p>
        Data subjects are typically your candidates, customers, patients/clients, event leads or other contacts you
        instruct us to contact. You must not upload special category data unless you have a valid Article 9 condition
        and have configured your compliance settings accordingly.
      </p>

      <h2>4. Nature and purpose of processing</h2>
      <p>
        Processing includes collection, storage, transmission, transcription, scoring/summarisation where configured,
        display in your dashboard, delivery via messaging and telephony partners, and deletion/anonymisation at the
        end of retention. We process only on your documented instructions (including configuration in the dashboard
        and this DPA).
      </p>

      <h2>5. Retention</h2>
      <ul>
        <li>
          <strong>Call recordings and full transcripts:</strong> 30 days from creation by default, then deleted or
          made inaccessible.
        </li>
        <li>
          <strong>Other operational data on VoxBulk servers</strong> (including WhatsApp message bodies, survey and
          interview structured responses, scores and reports): 90 days by default, then anonymised or deleted.
        </li>
        <li>
          <strong>Account and billing records:</strong> kept while your account is active and for up to 24 months
          after closure (or longer where tax or legal obligations require).
        </li>
      </ul>
      <p>Where the product allows, you may request shorter periods within the ranges we support.</p>

      <h2>6. Your obligations</h2>
      <p>You warrant that you have a lawful basis (and any required consents) under UK GDPR and PECR to instruct us to
        contact data subjects, including for surveys, interviews, feedback and marketing where applicable. You are
        responsible for providing appropriate privacy notices to end users and for honouring opt-outs (including STOP
        replies). You must use the Service only for lawful business purposes.</p>

      <h2>7. Our obligations</h2>
      <p>We will:</p>
      <ul>
        <li>Process personal data only on your instructions, unless required by UK law</li>
        <li>Ensure staff authorised to process personal data are bound by confidentiality</li>
        <li>Implement appropriate technical and organisational security measures</li>
        <li>Assist you, taking into account the nature of processing, with data subject requests</li>
        <li>Notify you without undue delay after becoming aware of a personal data breach affecting your data</li>
        <li>Delete or return personal data at the end of the services, subject to the retention rules above and legal holds</li>
        <li>Make available information reasonably necessary to demonstrate compliance with this DPA</li>
      </ul>

      <h2>8. Sub-processors</h2>
      <p>
        You authorise us to use carefully selected sub-processors in these categories: hosting and infrastructure;
        telephony and messaging delivery partners; AI speech, transcription and language providers; payment
        processors; and email delivery. We remain responsible for their performance. We will ensure appropriate
        contractual protections. A current category list is available on request from{" "}
        <a href="mailto:Data.Pro@voxbulk.com">Data.Pro@voxbulk.com</a>. We do not name individual vendors in this
        public DPA for security and commercial reasons.
      </p>

      <h2>9. International transfers</h2>
      <p>
        We aim to store and process production data in the UK and EU. Where a sub-processor processes data outside
        the UK/EU, we use appropriate transfer mechanisms (such as the UK International Data Transfer Agreement /
        Addendum or equivalent safeguards).
      </p>

      <h2>10. Security</h2>
      <p>
        Measures include encryption in transit and at rest for production systems, role-based access control,
        tenant isolation, credential encryption for integrations, logging, and staff access limited to need-to-know.
      </p>

      <h2>11. AI and recording transparency</h2>
      <p>
        Where voice AI is used, calls include an appropriate disclosure that an AI assistant is speaking and that the
        call may be recorded. We do not use your customer recordings, transcripts or survey replies to train
        foundation models. Structured results may be retained longer than raw audio as set out in section 5.
      </p>

      <h2>12. Audits</h2>
      <p>
        Upon reasonable written notice (and no more than once per year unless a breach or regulator requires
        otherwise), you may request information or questionnaires to verify our compliance. On-site audits are by
        mutual agreement and at your cost unless required following a material breach by us.
      </p>

      <h2>13. Liability and governing law</h2>
      <p>
        Liability under this DPA is subject to the limitations in our Terms &amp; Conditions. This DPA is governed by
        the laws of England and Wales.
      </p>

      <h2>14. Contact</h2>
      <p>
        VoxBulk Ltd · Company No. 15466735 · London, United Kingdom
        <br />
        Data protection:{" "}
        <a href="mailto:Data.Pro@voxbulk.com">Data.Pro@voxbulk.com</a>
      </p>
    </PageShell>
  );
}
