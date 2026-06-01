// @lovable.dev/vite-tanstack-config already includes the following — do NOT add them manually
// or the app will break with duplicate plugins:
//   - tanstackStart, viteReact, tailwindcss, tsConfigPaths, nitro (build-only using cloudflare as a default target),
//     componentTagger (dev-only), VITE_* env injection, @ path alias, React/TanStack dedupe,
//     error logger plugins, and sandbox detection (port/host/strictPort).
// You can pass additional config via defineConfig({ vite: { ... }, etc... }) if needed.
import { defineConfig } from "@lovable.dev/vite-tanstack-config";

const API_PROXY_PATHS = [
  "/auth",
  "/dashboard",
  "/organisations",
  "/calls",
  "/billing",
  "/onboarding",
  "/support",
  "/notifications",
  "/whatsapp",
  "/appointments",
  "/branches",
  "/users",
  "/service-orders",
  "/public",
  "/health",
  "/faq",
  "/promo-offers",
];

function buildApiProxy(target: string) {
  return Object.fromEntries(API_PROXY_PATHS.map((path) => [path, { target, changeOrigin: true }]));
}

export default defineConfig({
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
    build: {
      target: "esnext",
      minify: "esbuild",
    },
    server: {
      host: true,
      port: 5175,
      strictPort: true,
      proxy: buildApiProxy("http://127.0.0.1:8000"),
    },
    preview: {
      host: true,
      port: 5175,
      strictPort: true,
      allowedHosts: ["dashboard.voxbulk.com", "localhost", "127.0.0.1"],
      proxy: buildApiProxy("http://127.0.0.1:8000"),
    },
  },
});
