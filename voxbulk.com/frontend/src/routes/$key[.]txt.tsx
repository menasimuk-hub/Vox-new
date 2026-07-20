import { createFileRoute } from "@tanstack/react-router";
import type {} from "@tanstack/react-start";
import { frontpageApiFetch } from "@/lib/api";

/** IndexNow ownership verification: /{key}.txt */
export const Route = createFileRoute("/$key.txt")({
  server: {
    handlers: {
      GET: async ({ params }) => {
        const key = String(params.key || "").trim();
        if (!key || key.length < 8) {
          return new Response("Not found", { status: 404, headers: { "Content-Type": "text/plain" } });
        }
        try {
          const data = await frontpageApiFetch<{ key?: string }>("/frontpage/seo/indexnow-key");
          if (data?.key && data.key === key) {
            return new Response(key, {
              headers: { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store" },
            });
          }
        } catch {
          /* try direct loopback if proxy/base URL failed */
          try {
            const res = await fetch("http://127.0.0.1:8000/frontpage/seo/indexnow-key");
            if (res.ok) {
              const data = (await res.json()) as { key?: string };
              if (data?.key && data.key === key) {
                return new Response(key, {
                  headers: { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store" },
                });
              }
            }
          } catch {
            /* 404 */
          }
        }
        return new Response("Not found", { status: 404, headers: { "Content-Type": "text/plain" } });
      },
    },
  },
});
