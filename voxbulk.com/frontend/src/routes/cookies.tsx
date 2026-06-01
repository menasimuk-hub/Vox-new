import { createFileRoute } from "@tanstack/react-router";
import { PageShell } from "@/components/SiteShell";

export const Route = createFileRoute("/cookies")({
  head: () => ({
    meta: [
      { title: "Cookie Policy — VOXBULK" },
      { name: "description", content: "How VOXBULK uses cookies and similar technologies on its website, the categories we set, and how you can manage your preferences." },
      { property: "og:title", content: "Cookie Policy — VOXBULK" },
      { property: "og:description", content: "Cookies, tracking and how to manage your preferences on the VOXBULK website." },
      { property: "og:url", content: "https://voxbulk.com/cookies" },
    ],
    links: [{ rel: "canonical", href: "https://voxbulk.com/cookies" }],
  }),
  component: () => (
    <PageShell eyebrow="Legal" title="Cookie Policy">
      <p><strong>Last updated:</strong> May 2026</p>
      <h2>1. What cookies are</h2>
      <p>Cookies are small text files stored on your device when you visit a website. We also use similar technologies such as local storage and pixels.</p>
      <h2>2. Categories we use</h2>
      <ul>
        <li><strong>Strictly necessary:</strong> required for sign-in, security and core functionality. Cannot be turned off.</li>
        <li><strong>Analytics:</strong> aggregate usage statistics so we can improve the product. Set only with your consent.</li>
        <li><strong>Functional:</strong> remember preferences such as language and dashboard layout.</li>
      </ul>
      <h2>3. Managing cookies</h2>
      <p>You can manage cookies via your browser settings, and withdraw consent for non-essential cookies at any time using the cookie banner. Disabling strictly necessary cookies may break parts of the site.</p>
      <h2>4. Third parties</h2>
      <p>We use a limited number of third-party providers (hosting, analytics, error monitoring) that may set their own cookies. A current list is available on request.</p>
      <h2>5. Contact</h2>
      <p>Questions: <a href="mailto:privacy@voxbulk.com">privacy@voxbulk.com</a>.</p>
    </PageShell>
  ),
});
