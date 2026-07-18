import { createFileRoute } from "@tanstack/react-router";
import type {} from "@tanstack/react-start";
import { frontpageApiFetch } from "@/lib/api";

/** IndexNow ownership verification: /{key}.txt */
export const Route = createFileRoute("/$key.txt")({
  server: {
    handlers: {
      GET: async ({ params }) => {
        const key = params.key || "";
        try {
          const data = await frontpageApiFetch<{ key?: string }>("/frontpage/seo/indexnow-key");
          if (data?.key && data.key === key) {
            return new Response(key, {
              headers: { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store" },
            });
          }
        } catch {
          /* 404 */
        }
        return new Response("Not found", { status: 404, headers: { "Content-Type": "text/plain" } });
      },
    },
  },
});
