import { mkdirSync, rmSync, existsSync, copyFileSync, cpSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawnSync } from 'node:child_process'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const dist = join(root, 'dist')
const zipPath = join(dist, 'VoxBulk-Zoho-Recruit-Widget.zip')
const staging = join(dist, '_pack')

mkdirSync(dist, { recursive: true })
if (existsSync(staging)) rmSync(staging, { recursive: true, force: true })
mkdirSync(staging, { recursive: true })
copyFileSync(join(root, 'plugin-manifest.json'), join(staging, 'plugin-manifest.json'))
cpSync(join(root, 'app'), join(staging, 'app'), { recursive: true })
if (existsSync(zipPath)) rmSync(zipPath, { force: true })

const isWin = process.platform === 'win32'
let ok = false
if (isWin) {
  const r = spawnSync(
    'powershell',
    [
      '-NoProfile',
      '-Command',
      `Compress-Archive -Path '${join(staging, 'plugin-manifest.json')}','${join(staging, 'app')}' -DestinationPath '${zipPath}'`,
    ],
    { encoding: 'utf8' },
  )
  ok = r.status === 0
  if (!ok) console.error(r.stderr || r.stdout)
} else {
  const r = spawnSync('zip', ['-r', zipPath, 'plugin-manifest.json', 'app'], {
    cwd: staging,
    encoding: 'utf8',
  })
  ok = r.status === 0
  if (!ok) console.error(r.stderr || r.stdout)
}

rmSync(staging, { recursive: true, force: true })
if (!ok || !existsSync(zipPath)) {
  console.error('Pack failed')
  process.exit(1)
}
console.log('Wrote', zipPath)
