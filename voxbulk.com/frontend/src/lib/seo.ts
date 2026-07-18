import { frontpageApiFetch } from "@/lib/api";

export type SeoContent = {
  slug: string;
  title: string;
  meta_title?: string;
  meta_description?: string;
  canonical_url?: string;
  robots?: string;
  social_title?: string;
  social_description?: string;
  social_image_url?: string | null;
  author?: string;
  published_at?: string | null;
  last_updated?: string | null;
  focus_keyword?: string;
  tags?: string;
  question?: string;
  answer?: string;
  path?: string;
  url?: string;
};

export type PublicSeoSettings = {
  site_name?: string;
  title_template?: string;
  default_meta_description?: string;
  default_social_image_url?: string | null;
  home_title?: string;
  home_description?: string;
  schema_organization?: boolean;
  schema_website?: boolean;
  schema_breadcrumbs?: boolean;
  schema_content?: boolean;
  google_site_verification?: string;
  google_news_enabled?: boolean;
  robots_txt?: string;
  indexnow_key?: string;
};

let settingsCache: PublicSeoSettings | null = null;

export async function fetchSeoSettings(): Promise<PublicSeoSettings> {
  if (settingsCache) return settingsCache;
  try {
    settingsCache = await frontpageApiFetch<PublicSeoSettings>("/frontpage/seo/settings");
  } catch {
    settingsCache = {};
  }
  return settingsCache || {};
}

export function applyTitleTemplate(title: string, settings: PublicSeoSettings): string {
  const site = settings.site_name || "VoxBulk";
  const tpl = settings.title_template || "%title% | %sitename%";
  return tpl.replace(/%title%/g, title).replace(/%sitename%/g, site);
}

export async function fetchContentSeo(kind: "blog" | "news" | "faq", slug: string): Promise<SeoContent | null> {
  try {
    return await frontpageApiFetch<SeoContent>(
      `/frontpage/seo/content/${encodeURIComponent(kind)}/${encodeURIComponent(slug)}`,
    );
  } catch {
    return null;
  }
}

export async function resolveRedirect(pathname: string): Promise<{ to_path: string; status_code: number } | null> {
  try {
    const data = await frontpageApiFetch<{ redirect: { to_path: string; status_code: number } | null }>(
      `/frontpage/seo/resolve-redirect?path=${encodeURIComponent(pathname)}`,
    );
    return data.redirect || null;
  } catch {
    return null;
  }
}

export function buildHeadFromSeo(
  seo: SeoContent,
  settings: PublicSeoSettings,
  opts?: { schemaType?: "Article" | "NewsArticle" | "FAQPage" },
) {
  const title = applyTitleTemplate(seo.meta_title || seo.title || "VoxBulk", settings);
  const description =
    seo.meta_description || settings.default_meta_description || seo.title || "";
  const canonical = seo.canonical_url || seo.url || `https://voxbulk.com${seo.path || ""}`;
  const robots = seo.robots || "index,follow";
  const ogTitle = seo.social_title || seo.meta_title || seo.title || title;
  const ogDesc = seo.social_description || description;
  const ogImage = seo.social_image_url || settings.default_social_image_url || undefined;

  const meta: Array<Record<string, string>> = [
    { title },
    { name: "description", content: description },
    { name: "robots", content: robots },
    { property: "og:title", content: ogTitle },
    { property: "og:description", content: ogDesc },
    { property: "og:type", content: opts?.schemaType === "FAQPage" ? "website" : "article" },
    { property: "og:url", content: canonical },
    { name: "twitter:card", content: ogImage ? "summary_large_image" : "summary" },
    { name: "twitter:title", content: ogTitle },
    { name: "twitter:description", content: ogDesc },
  ];
  if (ogImage) {
    meta.push({ property: "og:image", content: ogImage });
    meta.push({ name: "twitter:image", content: ogImage });
  }
  if (seo.published_at) {
    meta.push({ property: "article:published_time", content: seo.published_at });
  }
  if (seo.author) {
    meta.push({ property: "article:author", content: seo.author });
  }

  const scripts: Array<{ type: string; children: string }> = [];
  if (settings.schema_content !== false && opts?.schemaType) {
    const ld: Record<string, unknown> = {
      "@context": "https://schema.org",
      "@type": opts.schemaType,
      headline: seo.meta_title || seo.title,
      description,
      url: canonical,
      mainEntityOfPage: canonical,
    };
    if (opts.schemaType === "FAQPage" && seo.question && seo.answer) {
      ld.mainEntity = [
        {
          "@type": "Question",
          name: seo.question,
          acceptedAnswer: { "@type": "Answer", text: seo.answer },
        },
      ];
    } else {
      if (seo.author) ld.author = { "@type": "Person", name: seo.author };
      if (seo.published_at) ld.datePublished = seo.published_at;
      if (seo.last_updated) ld.dateModified = seo.last_updated;
      if (ogImage) ld.image = ogImage;
    }
    scripts.push({ type: "application/ld+json", children: JSON.stringify(ld) });
  }

  return {
    meta,
    links: [{ rel: "canonical", href: canonical }],
    scripts,
  };
}
