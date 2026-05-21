import { useEffect, useState } from "react";
import { PageShell } from "@/components/SiteShell";
import { getApiBaseUrl } from "@/lib/retoverApi";

type LegalPageData = {
  title: string;
  body: string;
  meta_description?: string | null;
};

type LegalPageViewProps = {
  slug: string;
  fallbackTitle: string;
  fallbackDescription?: string;
};

export function LegalPageView({ slug, fallbackTitle, fallbackDescription }: LegalPageViewProps) {
  const [page, setPage] = useState<LegalPageData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const base = getApiBaseUrl().replace(/\/+$/, "");
        const response = await fetch(`${base}/legal-pages/${encodeURIComponent(slug)}`);
        if (response.ok) {
          const data = (await response.json()) as LegalPageData;
          if (!cancelled) setPage(data);
        }
      } catch {
        /* public fallback copy */
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [slug]);

  const title = page?.title || fallbackTitle;

  return (
    <PageShell eyebrow="Legal" title={title}>
      {loading ? (
        <p className="text-muted-text">Loading…</p>
      ) : page?.body ? (
        <div className="legal-page-content" dangerouslySetInnerHTML={{ __html: page.body }} />
      ) : (
        <p className="text-muted-text italic">
          {fallbackDescription ||
            `Content coming soon. This page is reserved for ${fallbackTitle}. Replace this placeholder with your final copy.`}
        </p>
      )}
    </PageShell>
  );
}
