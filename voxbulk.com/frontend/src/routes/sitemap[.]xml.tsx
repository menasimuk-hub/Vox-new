import { createFileRoute } from "@tanstack/react-router";
import type {} from "@tanstack/react-start";

import { SITE_ORIGIN } from "@/lib/brand";
import { newsItems, posts } from "@/lib/blog-data";
import { fetchBlogList, fetchNewsList } from "@/lib/site-content";

const BASE_URL = SITE_ORIGIN;

interface SitemapEntry {
  path: string;
  changefreq?: "always" | "hourly" | "daily" | "weekly" | "monthly" | "yearly" | "never";
  priority?: string;
}

export const Route = createFileRoute("/sitemap.xml")({
  server: {
    handlers: {
      GET: async () => {
        let blogSlugs = posts.map((p) => p.slug);
        let newsSlugs = newsItems.map((n) => n.slug);
        try {
          const [blog, news] = await Promise.all([fetchBlogList(), fetchNewsList()]);
          if (blog.length) blogSlugs = blog.map((p) => p.slug);
          if (news.length) newsSlugs = news.map((n) => n.slug);
        } catch {
          /* keep static fallback */
        }

        const entries: SitemapEntry[] = [
          { path: "/", changefreq: "weekly", priority: "1.0" },
          { path: "/recruitment", changefreq: "weekly", priority: "0.9" },
          { path: "/surveys", changefreq: "weekly", priority: "0.9" },
          { path: "/feedback", changefreq: "weekly", priority: "0.9" },
          { path: "/pricing", changefreq: "weekly", priority: "0.9" },
          { path: "/contact", changefreq: "monthly", priority: "0.7" },
          { path: "/blog", changefreq: "weekly", priority: "0.7" },
          ...blogSlugs.map((slug) => ({ path: `/blog/${slug}`, changefreq: "monthly" as const, priority: "0.6" })),
          { path: "/news", changefreq: "weekly", priority: "0.7" },
          ...newsSlugs.map((slug) => ({ path: `/news/${slug}`, changefreq: "monthly" as const, priority: "0.55" })),
          { path: "/legal-policies", changefreq: "yearly", priority: "0.3" },
          { path: "/privacy", changefreq: "yearly", priority: "0.3" },
          { path: "/terms", changefreq: "yearly", priority: "0.3" },
          { path: "/cookies", changefreq: "yearly", priority: "0.3" },
          { path: "/gdpr", changefreq: "yearly", priority: "0.3" },
          { path: "/legal", changefreq: "yearly", priority: "0.3" },
        ];

        const urls = entries.map((e) =>
          [
            `  <url>`,
            `    <loc>${BASE_URL}${e.path}</loc>`,
            e.changefreq ? `    <changefreq>${e.changefreq}</changefreq>` : null,
            e.priority ? `    <priority>${e.priority}</priority>` : null,
            `  </url>`,
          ]
            .filter(Boolean)
            .join("\n"),
        );

        const xml = [
          `<?xml version="1.0" encoding="UTF-8"?>`,
          `<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">`,
          ...urls,
          `</urlset>`,
        ].join("\n");

        return new Response(xml, {
          headers: {
            "Content-Type": "application/xml",
            "Cache-Control": "public, max-age=3600",
          },
        });
      },
    },
  },
});
