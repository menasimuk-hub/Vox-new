#!/usr/bin/env node
/**
 * Copy canonical VOXBULK brand files from voxbulk-api/logos/ into frontend public folders.
 * Run automatically via predev/prebuild in admin and dashboard apps.
 */
import { cpSync, existsSync, mkdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const source = join(root, 'voxbulk-api', 'logos')

const targets = [
  join(root, 'admin.voxbulk.com', 'adim-web', 'public', 'brand'),
  join(root, 'dashboard.voxbulk.com', 'dashboard-web', 'public', 'brand'),
]

const files = [
  'logo-black.svg',
  'logo-white.svg',
  'icon-black.svg',
  'icon-white.svg',
  'favicon.ico',
]

if (!existsSync(source)) {
  console.error(`[sync-brand] Missing source folder: ${source}`)
  process.exit(1)
}

let copied = 0
for (const target of targets) {
  mkdirSync(target, { recursive: true })
  for (const file of files) {
    const from = join(source, file)
    if (!existsSync(from)) continue
    cpSync(from, join(target, file), { force: true })
    copied += 1
  }
}

console.info(`[sync-brand] Synced brand assets to ${targets.length} apps (${copied} file copies).`)
