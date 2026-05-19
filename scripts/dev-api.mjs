/**
 * Start FastAPI from ./voxbulk-api (repo root = parent of this scripts/ folder).
 * Binds 0.0.0.0:8000 so Vite proxies and browsers can use http://127.0.0.1:8000.
 */
import { spawn } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const repoRoot = path.resolve(__dirname, '..')
const apiRoot = path.join(repoRoot, 'voxbulk-api')

if (!fs.existsSync(path.join(apiRoot, 'main.py'))) {
  console.error(`[dev-api] Expected main.py at ${apiRoot}`)
  process.exit(1)
}

const win = process.platform === 'win32'
const venvPy = win
  ? path.join(apiRoot, '.venv', 'Scripts', 'python.exe')
  : path.join(apiRoot, '.venv', 'bin', 'python')
const python = fs.existsSync(venvPy) ? venvPy : win ? 'python' : 'python3'

const child = spawn(
  python,
  ['-m', 'uvicorn', 'main:app', '--reload', '--host', '0.0.0.0', '--port', '8000'],
  { cwd: apiRoot, stdio: 'inherit', shell: false },
)
child.on('exit', (code, signal) => {
  if (signal) process.exit(1)
  process.exit(code ?? 0)
})
