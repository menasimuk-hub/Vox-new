#!/usr/bin/env node
/** Strip TS + TanStack from copied Yallasay portal pages; fix imports for Vite SPA. */
import fs from 'fs'
import path from 'path'

const roots = [
  'abuu.voxbulk.com/abuu-web',
  'driver.voxbulk.com/driver-web',
]

function stripTs(content) {
  return content
    .replace(/^import \{ createFileRoute \} from "@tanstack\/react-router";\n/m, '')
    .replace(/^export const Route = createFileRoute[\s\S]*?component: \w+,\n\}\);\n\n/m, '')
    .replace(/^type [^\n]+\n/gm, '')
    .replace(/: React\.ReactNode/g, '')
    .replace(/: typeof t\.en/g, '')
    .replace(/: boolean/g, '')
    .replace(/: string/g, '')
    .replace(/: number/g, '')
    .replace(/: Status/g, '')
    .replace(/: Vehicle/g, '')
    .replace(/: DStatus/g, '')
    .replace(/: Record<[^>]+>/g, '')
    .replace(/<[^>]+>/g, (m) => {
      if (m.startsWith('</') || m.includes('=') || m.includes('className')) return m
      if (/^<[A-Z]/.test(m) && m.endsWith('>')) return m.replace(/<(\w+)[^>]*>/, '<$1>')
      return m
    })
    .replace(/, type VariantProps/g, '')
    .replace(/React\./g, '')
    .replace(/useLocalState<[^>]+>/g, 'useLocalState')
    .replace(/useState<[^>]+>/g, 'useState')
    .replace(/useMemo<[^>]+>/g, 'useMemo')
    .replace(/ as const/g, '')
    .replace(/ as Status/g, '')
    .replace(/ as DStatus/g, '')
    .replace(/ as Vehicle/g, '')
    .replace(/ satisfies \w+/g, '')
    .replace(/\(dir: 1 \| -1\)/g, '(dir)')
    .replace(/\(id: string\)/g, '(id)')
    .replace(/\(iid: string\)/g, '(iid)')
    .replace(/\(orderId: string, itemId: string\)/g, '(orderId, itemId)')
    .replace(/\(orderId: string\)/g, '(orderId)')
    .replace(/\(offerId: string\)/g, '(offerId)')
    .replace(/\(itemId: string\)/g, '(itemId)')
    .replace(/\(catId: string\)/g, '(catId)')
    .replace(/\(tone: "primary" \| "accent" \| "success"\)/g, '(tone)')
    .replace(/\(lang: "en" \| "ar"\)/g, '(lang)')
    .replace(/\(tab: "orders" \| "history" \| "settings"\)/g, '(tab)')
    .replace(/export default function \w+/g, 'export default function ConsolePage')
}

function fixUiFile(content) {
  return content
    .replace(/import \{ cva, type VariantProps \}/, 'import { cva }')
    .replace(/: VariantProps<typeof \w+>/g, '')
    .replace(/React\./g, '')
    .replace(/"use client"\n\n?/g, '')
}

function fixUtils(content) {
  return content.replace(/: ClassValue/g, '')
}

function fixAppPrefs(content) {
  return content
    .replace(/export function useLang\(scope: string\)/, 'export function useLang(scope)')
    .replace(/export function useTheme\(scope: string\)/, 'export function useTheme(scope)')
    .replace(/export function useLocalState<T>\(/, 'export function useLocalState(')
    .replace(/: T/g, '')
    .replace(/ as "en" \| "ar"/g, '')
    .replace(/ as "light" \| "dark"/g, '')
}

for (const root of roots) {
  const base = path.join(process.cwd(), root, 'src')
  for (const rel of [
    'components/ui/button.jsx',
    'components/ui/card.jsx',
    'components/ui/badge.jsx',
    'components/ui/input.jsx',
    'components/ui/label.jsx',
    'components/ui/textarea.jsx',
    'components/ui/switch.jsx',
    'components/ui/dialog.jsx',
    'components/ui/tabs.jsx',
    'components/OnlineSlider.jsx',
    'lib/utils.js',
    'lib/app-prefs.js',
  ]) {
    const p = path.join(base, rel)
    if (!fs.existsSync(p)) continue
    let c = fs.readFileSync(p, 'utf8')
    if (rel.includes('utils')) c = fixUtils(c)
    else if (rel.includes('app-prefs')) c = fixAppPrefs(c)
    else if (rel.includes('ui/') || rel.includes('OnlineSlider')) c = fixUiFile(c)
    const out = p.replace('.jsx', '.jsx').replace('.js', '.js')
    fs.writeFileSync(out, c)
  }
}

for (const [rel, name] of [
  ['abuu.voxbulk.com/abuu-web/src/pages/RestaurantConsole.jsx', 'RestaurantConsole'],
  ['driver.voxbulk.com/driver-web/src/pages/DriverConsole.jsx', 'DriverConsole'],
]) {
  const p = path.join(process.cwd(), rel)
  if (!fs.existsSync(p)) continue
  let c = stripTs(fs.readFileSync(p, 'utf8'))
  c = c.replace(/function RestaurantPage\(\)/, 'export default function RestaurantConsole()')
  c = c.replace(/function DriverPage\(\)/, 'export default function DriverConsole()')
  c = c.replace(/^export default function ConsolePage/m, 'function ConsolePage')
  fs.writeFileSync(p, c)
}

console.log('port-yallasay-portal: done')
