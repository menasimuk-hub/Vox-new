#!/usr/bin/env node
/**
 * Copy canonical VOXBULK brand files from voxbulk-api/logos/ into every frontend public folder.
 * Run automatically via predev/prebuild in admin, dashboard, and marketing apps, and on deploy.
 */
import { cpSync, existsSync, mkdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const source = join(root, 'voxbulk-api', 'logos')

const brandTargets = [
  join(root, 'admin.voxbulk.com', 'adim-web', 'public', 'brand'),
  join(root, 'dashboard.voxbulk.com', 'dashboard-web', 'public', 'brand'),
  join(root, 'voxbulk.com', 'frontend', 'public', 'brand'),
  join(root, 'voxbulk.com', 'voxbulk.com', 'frontend', 'public', 'brand'),
]

const files = [
  'logo-black.svg',
  'logo-black.png',
  'logo-white.svg',
  'logo-white.png',
  'logo-dark.png',
  'logo-light.png',
  'icon-black.svg',
  'icon-black.png',
  'icon-white.svg',
  'icon-white.png',
  'icon-dark.png',
  'icon-light.png',
  'favicon.ico',
  'favicon.png',
]

/** Legacy paths still referenced by PDF/report embeds and older assets. */
const legacyCopies = [
  { from: 'logo-black.svg', to: join(root, 'admin.voxbulk.com', 'adim-web', 'public', 'logo-light.svg') },
  { from: 'logo-white.svg', to: join(root, 'admin.voxbulk.com', 'adim-web', 'public', 'logo-dark.svg') },
  { from: 'logo-white.svg', to: join(root, 'dashboard.voxbulk.com', 'dashboard-web', 'public', 'logo-dark.svg') },
  { from: 'icon-black.svg', to: join(root, 'admin.voxbulk.com', 'adim-web', 'public', 'favicon-mark.svg') },
]

if (!existsSync(source)) {
  console.error(`[sync-brand] Missing source folder: ${source}`)
  process.exit(1)
}

let copied = 0
const activeTargets = brandTargets.filter((t) => {
  const parent = dirname(dirname(t))
  if (!existsSync(parent)) return false
  return true
})

for (const target of activeTargets) {
  mkdirSync(target, { recursive: true })
  for (const file of files) {
    const from = join(source, file)
    if (!existsSync(from)) continue
    cpSync(from, join(target, file), { force: true })
    copied += 1
  }
}

for (const { from, to } of legacyCopies) {
  const src = join(source, from)
  if (!existsSync(src)) continue
  mkdirSync(dirname(to), { recursive: true })
  cpSync(src, to, { force: true })
  copied += 1
}

console.info(`[sync-brand] Synced brand assets to ${activeTargets.length} apps + legacy paths (${copied} file copies).`)
