import { createFileRoute, Link } from "@tanstack/react-router";
import { PageShell } from "@/components/SiteShell";

export const Route = createFileRoute("/legal")({
  head: () => ({
    meta: [
      { title: "Legal — VoxBulk" },
      { name: "description", content: "Legal notices and company information for VoxBulk Ltd." },
      { property: "og:title", content: "Legal — VoxBulk" },
      { property: "og:description", content: "Company information and legal notices for VoxBulk Ltd." },
      { property: "og:url", content: "https://voxbulk.com/legal" },
    ],
    links: [{ rel: "canonical", href: "https://voxbulk.com/legal" }],
  }),
  component: () => (
    <PageShell title="Legal" eyebrow="Legal">
      <h2>Company</h2>
      <p>
        VoxBulk Ltd, company number 15466735, registered in England and Wales. Registered office: London, United
        Kingdom.
      </p>

      <h2>Documents</h2>
      <ul>
        <li>
          <Link to="/terms">Terms &amp; Conditions</Link>
        </li>
        <li>
          <Link to="/privacy">Privacy Policy</Link>
        </li>
        <li>
          <Link to="/dpa">Data Processing Agreement</Link> (
          <a href="/legal/voxbulk-dpa.pdf" download>
            PDF
          </a>
          )
        </li>
        <li>
          <Link to="/cookies">Cookie Policy</Link>
        </li>
        <li>
          <Link to="/gdpr">GDPR overview</Link>
        </li>
        <li>
          <Link to="/legal-policies">Full legal pack</Link>
        </li>
      </ul>

      <h2>Contact</h2>
      <p>
        Data protection: <a href="mailto:Data.Pro@voxbulk.com">Data.Pro@voxbulk.com</a>
        <br />
        Support: <a href="mailto:support@voxbulk.com">support@voxbulk.com</a>
      </p>

      <h2>Trademarks</h2>
      <p>
        &quot;VoxBulk&quot; and the VoxBulk logo are trademarks of VoxBulk Ltd. All other trademarks belong to their
        respective owners.
      </p>

      <h2>Compliance</h2>
      <p>VoxBulk operates in accordance with UK GDPR, the Data Protection Act 2018 and PECR.</p>
    </PageShell>
  ),
});
