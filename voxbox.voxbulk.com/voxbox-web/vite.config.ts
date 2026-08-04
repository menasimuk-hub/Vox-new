import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import tsconfigPaths from "vite-tsconfig-paths";
import { tanstackRouter } from "@tanstack/router-plugin/vite";

export default defineConfig({
  plugins: [
    tanstackRouter({ target: "react", autoCodeSplitting: true }),
    react(),
    tailwindcss(),
    tsconfigPaths(),
  ],
  build: {
    target: "esnext",
    outDir: "dist",
    emptyOutDir: true,
  },
  server: {
    host: true,
    port: 5176,
    strictPort: true,
    proxy: {
      "/voxbox": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  preview: {
    host: true,
    port: 5176,
    strictPort: true,
    allowedHosts: ["voxbox.voxbulk.com", "localhost", "127.0.0.1"],
    proxy: {
      "/voxbox": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
