// @lovable.dev/vite-tanstack-config already includes the following — do NOT add them manually
// or the app will break with duplicate plugins:
//   - tanstackStart, viteReact, tailwindcss, tsConfigPaths, cloudflare (build-only),
//     componentTagger (dev-only), VITE_* env injection, @ path alias, React/TanStack dedupe,
//     error logger plugins, and sandbox detection (port/host/strictPort).
// You can pass additional config via defineConfig({ vite: { ... } }) if needed.
import { defineConfig } from "@lovable.dev/vite-tanstack-config";

export default defineConfig({
  vite: {
    preview: {
      allowedHosts: ["voxbulk.com", "www.voxbulk.com", "452f9ed0.voxbulk.com"],
    },
    build: {
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (id.includes("@vapi-ai/web")) return "vapi";
            if (id.includes("@telnyx/ai-agent-lib")) return "telnyx";
            if (id.includes("node_modules/lucide-react")) return "icons";
          },
        },
      },
    },
  },
});
