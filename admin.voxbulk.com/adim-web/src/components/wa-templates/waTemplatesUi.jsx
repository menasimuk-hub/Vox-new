import React from 'react'
import { Languages } from 'lucide-react'
import { cn } from '@/lib/utils'

export const LANGS = ['EN', 'AR', 'FR', 'ES', 'DE', 'PT', 'IT', 'TR', 'RU', 'HI']

export function StatusDot({ status }) {
  const map = {
    approved: { c: 'bg-success', label: 'Approved' },
    pending: { c: 'bg-warning', label: 'Pending' },
    disabled: { c: 'bg-muted-foreground/50', label: 'Disabled' },
    rejected: { c: 'bg-destructive', label: 'Rejected' },
  }
  const s = map[status] || map.pending
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
      <span className={cn('h-1.5 w-1.5 rounded-full', s.c)} />
      {s.label}
    </span>
  )
}

export function CategoryPill({ category }) {
  const label = category === 'Marketing' ? 'Marketing' : 'Utility'
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset',
        label === 'Utility'
          ? 'bg-info-soft text-info ring-info/20'
          : 'bg-warning-soft text-warning-foreground ring-warning/30',
      )}
    >
      {label}
    </span>
  )
}

export function LangChip({ langs, title }) {
  const list = Array.isArray(langs) ? langs : []
  return (
    <span
      className="inline-flex cursor-default items-center gap-1 rounded-md bg-surface-muted px-1.5 py-0.5 text-xs font-medium text-foreground/80 ring-1 ring-inset ring-border"
      title={title || list.join(' · ')}
    >
      <Languages className="h-3 w-3" /> {list.length}
    </span>
  )
}

export function IconBtn({ icon: Icon, label, onClick, tone = 'default', disabled = false }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        'wa-hub-icon-btn inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-all',
        'hover:bg-accent hover:text-foreground active:scale-95 disabled:pointer-events-none disabled:opacity-40',
        tone === 'danger' && 'hover:bg-destructive/10 hover:text-destructive',
        tone === 'success' && 'hover:bg-success/10 hover:text-success',
      )}
      aria-label={label}
      title={label}
    >
      <Icon className="h-3.5 w-3.5" />
    </button>
  )
}

export function formatRelativeWhen(iso) {
  if (!iso) return '—'
  try {
    const d = new Date(iso)
    const diff = Date.now() - d.getTime()
    const mins = Math.floor(diff / 60000)
    if (mins < 1) return 'just now'
    if (mins < 60) return `${mins}m ago`
    const hrs = Math.floor(mins / 60)
    if (hrs < 48) return `${hrs}h ago`
    const days = Math.floor(hrs / 24)
    if (days < 14) return `${days}d ago`
    return d.toLocaleDateString()
  } catch {
    return String(iso)
  }
}

export function mapApprovalStatus(tpl) {
  if (tpl?.active_for_survey === false || tpl?.active_for_interview === false || tpl?.active_for_appointment === false || tpl?.is_active === false) {
    return 'disabled'
  }
  const raw = String(tpl?.approval_status || tpl?.status || tpl?.sync_status || tpl?.telnyx_sync_status || '').toLowerCase()
  if (raw.includes('reject')) return 'rejected'
  if (raw.includes('disable')) return 'disabled'
  if (raw.includes('pend') || raw.includes('submit')) return 'pending'
  if (raw.includes('approv') || raw.includes('sync') || raw.includes('live')) return 'approved'
  return 'pending'
}

export function mapCategory(tpl) {
  const c = String(tpl?.category || tpl?.meta_category || 'UTILITY').toUpperCase()
  return c.includes('MARKET') ? 'Marketing' : 'Utility'
}

export function langCodeToChip(language) {
  if (!language) return 'EN'
  const s = String(language).toUpperCase()
  if (s.startsWith('EN')) return 'EN'
  if (s.startsWith('AR')) return 'AR'
  if (s.startsWith('FR')) return 'FR'
  if (s.startsWith('ES')) return 'ES'
  if (s.startsWith('DE')) return 'DE'
  if (s.startsWith('PT')) return 'PT'
  if (s.startsWith('IT')) return 'IT'
  if (s.startsWith('TR')) return 'TR'
  if (s.startsWith('RU')) return 'RU'
  if (s.startsWith('HI')) return 'HI'
  return s.slice(0, 2)
}

export function toHubRow(tpl, overrides = {}) {
  const lang = langCodeToChip(tpl.language)
  const langs = tpl.langs || [lang]
  return {
    id: tpl.id,
    name: tpl.name || tpl.display_name || tpl.slug || String(tpl.id),
    langs,
    langsTitle: langs.join(' · '),
    category: mapCategory(tpl),
    status: mapApprovalStatus(tpl),
    used: tpl.usage_count ?? tpl.used_count ?? tpl.sent_count ?? tpl.template_count ?? tpl.templates_count ?? 0,
    updated: formatRelativeWhen(tpl.updated_at || tpl.last_pushed_at || tpl.synced_at),
    body: tpl.body || tpl.body_text || '',
    footer: tpl.footer || '',
    buttons: Array.isArray(tpl.buttons) ? tpl.buttons : [],
    variables: Array.isArray(tpl.variables) ? tpl.variables : Array.isArray(tpl.example_values) ? tpl.example_values : [],
    header: tpl.header,
    raw: tpl,
    ...overrides,
  }
}
