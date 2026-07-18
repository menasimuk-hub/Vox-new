import { createFileRoute } from "@tanstack/react-router";
import type {} from "@tanstack/react-start";
import { frontpageApiFetch } from "@/lib/api";

const FALLBACK = `User-agent: *
Allow: /
Disallow: /onboarding
Disallow: /signin

Sitemap: https://voxbulk.com/sitemap.xml
`;

export const Route = createFileRoute("/robots.txt")({
  server: {
    handlers: {
      GET: async () => {
        let body = FALLBACK;
        try {
          const data = await frontpageApiFetch<{ robots_txt?: string }>("/frontpage/seo/robots.txt");
          if (data?.robots_txt?.trim()) body = data.robots_txt;
        } catch {
          /* fallback */
        }
        return new Response(body, {
          headers: {
            "Content-Type": "text/plain; charset=utf-8",
            "Cache-Control": "public, max-age=300",
          },
        });
      },
    },
  },
});
