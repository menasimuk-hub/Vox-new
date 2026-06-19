#!/usr/bin/env node
/**
 * TanStack Start preview expects dist/server/server.js but Cloudflare build emits index.js.
 * Copy index.js → server.js so `npm run preview` works after build.
 * Also copy public/.well-known into dist/client for Microsoft Entra domain verification.
 */
import { copyFileSync, cpSync, existsSync, mkdirSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const serverDir = join(root, "dist", "server");
const index = join(serverDir, "index.js");
const server = join(serverDir, "server.js");

if (!existsSync(index)) {
  console.warn("[fix-preview] dist/server/index.js not found — skip (run npm run build first)");
  process.exit(0);
}

copyFileSync(index, server);
console.info("[fix-preview] Created dist/server/server.js for vite preview");

const publicWellKnown = join(root, "public", ".well-known");
const distClientWellKnown = join(root, "dist", "client", ".well-known");
if (existsSync(publicWellKnown)) {
  mkdirSync(distClientWellKnown, { recursive: true });
  cpSync(publicWellKnown, distClientWellKnown, { recursive: true });
  console.info("[fix-preview] Copied public/.well-known → dist/client/.well-known");
}
