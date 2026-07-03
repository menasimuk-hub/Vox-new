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
    local: { c: 'bg-info', label: 'Local only' },
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

function isLocalOnlyRow(tpl) {
  if (tpl?.is_local_only === true) return true
  const rid = String(tpl?.telnyx_record_id || '')
  if (rid.startsWith('local-')) return true
  const status = String(tpl?.status || tpl?.approval_status || '').toUpperCase()
  return status === 'LOCAL_DRAFT' || status === 'DRAFT'
}

/** Map API row → StatusDot status. Prefer Meta approval_status / status. */
export function mapApprovalStatus(tpl) {
  if (
    tpl?.active_for_survey === false ||
    tpl?.active_for_interview === false ||
    tpl?.active_for_appointment === false ||
    tpl?.is_active === false
  ) {
    return 'disabled'
  }

  const meta = String(tpl?.approval_status || tpl?.status || '').toUpperCase().trim()
  if (meta === 'APPROVED') return 'approved'
  if (meta === 'REJECTED') return 'rejected'
  if (meta === 'DISABLED' || meta === 'PAUSED') return 'disabled'
  if (meta === 'PENDING' || meta === 'PENDING_APPROVAL' || meta === 'IN_APPEAL' || meta === 'SUBMITTED') {
    return 'pending'
  }
  if (meta === 'LOCAL_DRAFT' || meta === 'DRAFT' || meta === 'UNKNOWN') {
    return isLocalOnlyRow(tpl) ? 'local' : 'pending'
  }

  if (isLocalOnlyRow(tpl)) return 'local'

  const label = String(tpl?.status_label || '').toLowerCase()
  if (label.includes('ready')) return 'approved'
  if (label.includes('need')) return 'local'
  if (label.includes('pending')) return 'pending'

  if (Number(tpl?.approved_template_count) > 0) return 'approved'
  if (Number(tpl?.pending_template_count) > 0) return 'pending'
  if (Number(tpl?.template_count) > 0 && Number(tpl?.approved_template_count) === 0) return 'pending'

  const sync = String(tpl?.local_sync_status || tpl?.sync_status || tpl?.telnyx_sync_status || '').toLowerCase()
  if (sync === 'in_sync' || sync === 'synced') return 'approved'
  if (sync.includes('draft') || sync.includes('local') || sync.includes('error')) return 'local'

  if (!meta && !label && !sync) return 'pending'
  if (meta.includes('APPROV')) return 'approved'
  if (meta.includes('REJECT')) return 'rejected'
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
  const templateCount =
    tpl.template_count ??
    tpl.templates_count ??
    (Number(tpl.standard_template_count || 0) + Number(tpl.anonymous_template_count || 0) || undefined)
  return {
    id: tpl.id,
    name: tpl.name || tpl.display_name || tpl.slug || String(tpl.id),
    langs,
    langsTitle: langs.join(' · '),
    category: mapCategory(tpl),
    status: mapApprovalStatus(tpl),
    used: tpl.usage_count ?? tpl.used_count ?? tpl.sent_count ?? templateCount ?? 0,
    updated: formatRelativeWhen(tpl.updated_at || tpl.last_pushed_at || tpl.synced_at || tpl.last_synced_at),
    body: tpl.body || tpl.body_text || '',
    footer: tpl.footer || '',
    buttons: Array.isArray(tpl.buttons) ? tpl.buttons : [],
    variables: Array.isArray(tpl.variables) ? tpl.variables : Array.isArray(tpl.example_values) ? tpl.example_values : [],
    header: tpl.header,
    isLocalOnly: isLocalOnlyRow(tpl),
    raw: tpl,
    ...overrides,
  }
}

export function summarizeCatalog(rows) {
  const list = Array.isArray(rows) ? rows : []
  let approved = 0
  let localOnly = 0
  let pending = 0
  for (const t of list) {
    const status = String(t.status || '').toUpperCase()
    const rid = String(t.telnyx_record_id || '')
    if (rid.startsWith('local-') || status === 'LOCAL_DRAFT' || status === 'DRAFT') {
      localOnly += 1
    } else if (status === 'APPROVED') {
      approved += 1
    } else if (status === 'PENDING' || status === 'SUBMITTED' || status === 'UNKNOWN') {
      pending += 1
    }
  }
  return { total: list.length, approved, localOnly, pending }
}
