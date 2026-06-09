#!/usr/bin/env node
/**
 * Write admin build metadata into public/build-info.json (copied to dist on build).
 */
import { execSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const outDir = join(root, "admin.voxbulk.com", "adim-web", "public");

function git(cmd) {
  try {
    return execSync(cmd, { cwd: root, encoding: "utf8" }).trim();
  } catch {
    return "";
  }
}

const payload = {
  git_sha: git("git rev-parse --short HEAD"),
  git_branch: git("git rev-parse --abbrev-ref HEAD"),
  built_at: new Date().toISOString(),
  admin_templates_marker: "admin-system-templates-privacy-v1",
};

mkdirSync(outDir, { recursive: true });
writeFileSync(join(outDir, "build-info.json"), `${JSON.stringify(payload, null, 2)}\n`, "utf8");
console.log(`[admin-build-info] ${payload.git_branch}@${payload.git_sha}`);
