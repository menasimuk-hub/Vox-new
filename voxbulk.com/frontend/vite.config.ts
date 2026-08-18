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

export default defineConfig({
  // Same SPA emit as dashboard — nginx serves dist/client/index.html from wwwroot.
  tanstackStart: {
    server: { entry: "server" },
    spa: {
      enabled: true,
      maskPath: "/",
      prerender: { outputPath: "/index.html", crawlLinks: false },
    },
    prerender: { enabled: false },
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
