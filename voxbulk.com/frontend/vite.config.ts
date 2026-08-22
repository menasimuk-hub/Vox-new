// @lovable.dev/vite-tanstack-config already includes the following — do NOT add them manually
// or the app will break with duplicate plugins:
//   - tanstackStart, viteReact, tailwindcss, tsConfigPaths, cloudflare (build-only),
//     componentTagger (dev-only), VITE_* env injection, @ path alias, React/TanStack dedupe,
//     error logger plugins, and sandbox detection (port/host/strictPort).
// You can pass additional config via defineConfig({ vite: { ... } }) if needed.
import { copyFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import { defineConfig } from "@lovable.dev/vite-tanstack-config";

function copyCloudflareServerJsForPrerender() {
  return {
    name: "copy-cloudflare-server-js-for-prerender",
    apply: "build" as const,
    writeBundle(options: { dir?: string }) {
      const dir = options.dir || "";
      const normalized = dir.replace(/\\/g, "/");
      if (!normalized.endsWith("/dist/server") && normalized !== "dist/server") return;
      const src = join(dir, "index.js");
      const dest = join(dir, "server.js");
      if (existsSync(src)) copyFileSync(src, dest);
    },
  };
}

/** Paths that must stay CSR-only (tokens, auth, crawler files, previews). */
function shouldPrerenderPath(path: string): boolean {
  const p = (path || "/").split("?")[0] || "/";
  if (
    p === "/signin" ||
    p === "/onboarding" ||
    p === "/reset-password" ||
    p === "/robots.txt" ||
    p === "/sitemap.xml" ||
    p === "/news-sitemap.xml"
  ) {
    return false;
  }
  if (p.endsWith(".txt")) return false;
  if (p.startsWith("/survey/") || p.startsWith("/survey/preview/")) return false;
  if (p.startsWith("/expo/") && p !== "/expo" && p !== "/expo/") return false;
  if (p.startsWith("/smart-card/") && p !== "/smart-card" && p !== "/smart-card/") return false;
  if (p.startsWith("/smartcard/")) return false;
  if (p.startsWith("/demo/session") || p.startsWith("/demo/live-")) return false;
  return true;
}

const MARKETING_PRERENDER_PAGES = [
  "/",
  "/surveys",
  "/feedback",
  "/recruitment",
  "/pricing",
  "/contact",
  "/expo",
  "/smart-card",
  "/blog",
  "/news",
  "/help",
  "/help/zoho-recruit",
  "/faq",
  "/demo",
  "/legal-policies",
  "/privacy",
  "/terms",
  "/cookies",
  "/gdpr",
  "/legal",
  "/dpa",
].map((path) => ({ path, prerender: { enabled: true } }));

export default defineConfig({
  // SPA shell for dynamic routes; static prerender for marketing HTML (SEO).
  tanstackStart: {
    server: { entry: "server" },
    spa: {
      enabled: true,
      maskPath: "/",
      // Fallback shell for non-prerendered routes (tokens, auth). Marketing pages use top-level prerender.
      prerender: { outputPath: "/_shell.html", crawlLinks: false },
    },
    prerender: {
      enabled: true,
      crawlLinks: true,
      autoSubfolderIndex: true,
      filter: ({ path }: { path: string }) => shouldPrerenderPath(path),
    },
    pages: MARKETING_PRERENDER_PAGES,
  },
  vite: {
    plugins: [copyCloudflareServerJsForPrerender()],
    server: {
      port: 5173,
      strictPort: true,
      proxy: {
        "/auth": { target: "http://127.0.0.1:8000", changeOrigin: true },
        "/billing": { target: "http://127.0.0.1:8000", changeOrigin: true },
        "/organisations": { target: "http://127.0.0.1:8000", changeOrigin: true },
        "/frontpage": { target: "http://127.0.0.1:8000", changeOrigin: true },
        "/ai-demo": { target: "http://127.0.0.1:8000", changeOrigin: true },
        "/public": { target: "http://127.0.0.1:8000", changeOrigin: true },
      },
    },
    preview: {
      host: true,
      port: 5173,
      strictPort: true,
      allowedHosts: ["voxbulk.com", "www.voxbulk.com", "localhost", "127.0.0.1"],
      proxy: {
        "/auth": { target: "http://127.0.0.1:8000", changeOrigin: true },
        "/billing": { target: "http://127.0.0.1:8000", changeOrigin: true },
        "/organisations": { target: "http://127.0.0.1:8000", changeOrigin: true },
        "/frontpage": { target: "http://127.0.0.1:8000", changeOrigin: true },
        "/ai-demo": { target: "http://127.0.0.1:8000", changeOrigin: true },
        "/public": { target: "http://127.0.0.1:8000", changeOrigin: true },
      },
    },
  },
});
