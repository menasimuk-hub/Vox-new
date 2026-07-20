import { createFileRoute } from "@tanstack/react-router";
import type {} from "@tanstack/react-start";
import { frontpageApiFetch } from "@/lib/api";

async function fetchIndexNowKey(): Promise<string> {
  try {
    const data = await frontpageApiFetch<{ key?: string }>("/frontpage/seo/indexnow-key");
    if (data?.key) return String(data.key).trim();
  } catch {
    /* try fallbacks */
  }
  for (const base of ["http://127.0.0.1:8000", "https://api.voxbulk.com"]) {
    try {
      const res = await fetch(`${base}/frontpage/seo/indexnow-key`);
      if (!res.ok) continue;
      const data = (await res.json()) as { key?: string };
      if (data?.key) return String(data.key).trim();
    } catch {
      /* next */
    }
  }
  return "";
}

/** IndexNow ownership verification: /{key}.txt */
export const Route = createFileRoute("/$key.txt")({
  server: {
    handlers: {
      GET: async ({ params }) => {
        const key = String(params.key || "")
          .trim()
          .replace(/\.txt$/i, "");
        if (!key || key.length < 8) {
          return new Response("Not found", { status: 404, headers: { "Content-Type": "text/plain" } });
        }
        const expected = await fetchIndexNowKey();
        if (expected && expected === key) {
          return new Response(key, {
            headers: { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store" },
          });
        }
        return new Response("Not found", { status: 404, headers: { "Content-Type": "text/plain" } });
      },
    },
  },
});
