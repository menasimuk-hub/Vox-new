import { createFileRoute } from "@tanstack/react-router";
import type {} from "@tanstack/react-start";
import { frontpageApiFetch } from "@/lib/api";

export const Route = createFileRoute("/news-sitemap.xml")({
  server: {
    handlers: {
      GET: async () => {
        let enabled = false;
        let pubName = "VoxBulk";
        let lang = "en";
        let items: Array<{ path: string; lastmod?: string; title?: string }> = [];
        try {
          const settings = await frontpageApiFetch<{
            google_news_enabled?: boolean;
            google_news_publication?: string;
            google_news_language?: string;
          }>("/frontpage/seo/settings");
          enabled = !!settings.google_news_enabled;
          pubName = settings.google_news_publication || pubName;
          lang = settings.google_news_language || lang;
          if (enabled) {
            const news = await frontpageApiFetch<{
              items: Array<{ slug: string; title: string; published_at?: string }>;
            }>("/frontpage/news");
            const cutoff = Date.now() - 2 * 24 * 60 * 60 * 1000;
            items = (news.items || [])
              .filter((n) => n.published_at && new Date(n.published_at).getTime() >= cutoff)
              .map((n) => ({
                path: `/news/${n.slug}`,
                lastmod: n.published_at,
                title: n.title,
              }));
          }
        } catch {
          enabled = false;
        }

        if (!enabled) {
          return new Response("<?xml version=\"1.0\" encoding=\"UTF-8\"?><urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\"></urlset>", {
            headers: { "Content-Type": "application/xml", "Cache-Control": "public, max-age=300" },
          });
        }

        const urls = items.map((it) => {
          const pubDate = it.lastmod ? new Date(it.lastmod).toISOString() : new Date().toISOString();
          return [
            "  <url>",
            `    <loc>https://voxbulk.com${it.path}</loc>`,
            "    <news:news>",
            "      <news:publication>",
            `        <news:name>${escapeXml(pubName)}</news:name>`,
            `        <news:language>${escapeXml(lang)}</news:language>`,
            "      </news:publication>",
            `      <news:publication_date>${pubDate}</news:publication_date>`,
            `      <news:title>${escapeXml(it.title || "")}</news:title>`,
            "    </news:news>",
            "  </url>",
          ].join("\n");
        });

        const xml = [
          `<?xml version="1.0" encoding="UTF-8"?>`,
          `<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">`,
          ...urls,
          `</urlset>`,
        ].join("\n");

        return new Response(xml, {
          headers: { "Content-Type": "application/xml", "Cache-Control": "public, max-age=300" },
        });
      },
    },
  },
});

function escapeXml(s: string) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
