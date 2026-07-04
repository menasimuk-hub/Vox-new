import React from 'react'
import { cn } from '@/lib/utils'

export const LANGS = ['EN', 'AR', 'FR', 'ES', 'DE', 'PT', 'IT', 'TR', 'RU', 'HI']

export const STATUS_FILTERS = [
  { id: 'all', label: 'All' },
  { id: 'approved', label: 'Approved' },
  { id: 'rejected', label: 'Rejected' },
  { id: 'pending', label: 'Pending' },
  { id: 'local', label: 'Local only' },
  { id: 'disabled', label: 'Disabled' },
]

export function StatusDot({ status }) {
  const map = {
    approved: { c: 'bg-success', label: 'Approved', className: 'text-success' },
    pending: { c: 'bg-warning', label: 'Pending', className: 'text-warning-foreground' },
    disabled: { c: 'bg-muted-foreground/50', label: 'Disabled', className: 'text-muted-foreground' },
    rejected: { c: 'bg-destructive', label: 'Rejected · fix', className: 'text-destructive font-medium' },
    local: { c: 'bg-info', label: 'Local only', className: 'text-info' },
  }
  const s = map[status] || map.pending
  return (
    <span className={cn('inline-flex items-center gap-1.5 text-xs', s.className)}>
      <span className={cn('h-1.5 w-1.5 shrink-0 rounded-full', s.c)} />
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
  const codes = list.length ? list : ['—']
  return (
    <span
      className="inline-flex cursor-default flex-wrap items-center gap-1 text-xs font-medium text-foreground/80"
      title={title || codes.join(' · ')}
    >
      {codes.map((code) => (
        <span
          key={code}
          className="inline-flex items-center rounded-md bg-surface-muted px-1.5 py-0.5 uppercase ring-1 ring-inset ring-border"
        >
          {code}
        </span>
      ))}
    </span>
  )
}

export function IconBtn({ icon: Icon, label, onClick, tone = 'default', disabled = false, className, spinning = false }) {
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
        className,
      )}
      aria-label={label}
      title={label}
    >
      <Icon className={cn('h-3.5 w-3.5', spinning && 'animate-spin')} />
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
  const candidates = [
    tpl?.status,
    tpl?.approval_status,
    tpl?.telnyx_sync_status,
  ]
    .map((v) => String(v || '').toUpperCase().trim())
    .filter(Boolean)

  // Rejection always wins — even when primary language row is APPROVED.
  if (candidates.some((meta) => meta === 'REJECTED' || meta.includes('REJECT'))) return 'rejected'

  const meta = candidates[0] || ''

  if (
    tpl?.active_for_survey === false ||
    tpl?.active_for_interview === false ||
    tpl?.active_for_appointment === false ||
    tpl?.is_active === false
  ) {
    if (meta === 'APPROVED' || meta.includes('APPROV')) {
      // still approved on Meta but hidden locally
      return 'disabled'
    }
    return 'disabled'
  }

  if (meta === 'APPROVED' || meta.includes('APPROV')) return 'approved'
  if (meta === 'DISABLED' || meta === 'PAUSED') return 'disabled'
  if (meta === 'PENDING' || meta === 'PENDING_APPROVAL' || meta === 'IN_APPEAL' || meta === 'SUBMITTED') {
    return 'pending'
  }
  if (meta === 'LOCAL_DRAFT' || meta === 'DRAFT') return 'local'
  if (meta === 'UNKNOWN' && isLocalOnlyRow(tpl)) return 'local'
  if (meta === 'UNKNOWN') return 'pending'

  if (isLocalOnlyRow(tpl)) return 'local'

  const label = String(tpl?.status_label || '').toLowerCase()
  if (label.includes('ready')) return 'approved'
  if (label.includes('reject')) return 'rejected'
  if (label.includes('need')) return 'local'
  if (label.includes('pending')) return 'pending'

  if (Number(tpl?.approved_template_count) > 0) return 'approved'
  if (Number(tpl?.pending_template_count) > 0) return 'pending'

  const sync = String(tpl?.local_sync_status || tpl?.sync_status || '').toLowerCase()
  if (sync === 'in_sync' || sync === 'synced') return 'approved'
  if (sync.includes('draft') || sync.includes('local')) return 'local'
  if (sync.includes('error')) return 'rejected'

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
  const languageList = overrides.languages || tpl.languages || tpl.langs
  const langs = Array.isArray(languageList) && languageList.length
    ? languageList.map((l) => langCodeToChip(l))
    : [lang]
  const languageCount = overrides.languageCount || tpl.language_count || langs.length || 1
  const templateCount =
    tpl.template_count ??
    tpl.templates_count ??
    (Number(tpl.standard_template_count || 0) + Number(tpl.anonymous_template_count || 0) || undefined)
  const status = overrides.status || mapApprovalStatus(tpl)
  return {
    id: tpl.id,
    name: tpl.name || tpl.display_name || tpl.slug || String(tpl.id),
    langs,
    languageCount,
    langsTitle: languageCount > 1 ? `${languageCount} langs · ${langs.join(' · ')}` : langs.join(' · '),
    category: mapCategory(tpl),
    used: tpl.usage_count ?? tpl.used_count ?? tpl.sent_count ?? templateCount ?? 0,
    updated: formatRelativeWhen(tpl.updated_at || tpl.last_pushed_at || tpl.synced_at || tpl.last_synced_at),
    body: tpl.body || tpl.body_text || '',
    footer: tpl.footer || '',
    buttons: Array.isArray(tpl.buttons) ? tpl.buttons : [],
    variables: Array.isArray(tpl.variables) ? tpl.variables : Array.isArray(tpl.example_values) ? tpl.example_values : [],
    header: tpl.header,
    isLocalOnly: isLocalOnlyRow(tpl),
    rejectionReason: tpl.rejection_reason || tpl.last_push_error || '',
    raw: tpl,
    ...overrides,
    status,
  }
}

export function summarizeCatalog(rows) {
  const list = Array.isArray(rows) ? rows : []
  let approved = 0
  let localOnly = 0
  let pending = 0
  let rejected = 0
  let utility = 0
  let marketing = 0
  for (const t of list) {
    const status = mapApprovalStatus(t)
    if (status === 'approved') approved += 1
    else if (status === 'local') localOnly += 1
    else if (status === 'rejected') rejected += 1
    else if (status === 'pending') pending += 1
    if (mapCategory(t) === 'Marketing') marketing += 1
    else utility += 1
  }
  return { total: list.length, approved, localOnly, pending, rejected, utility, marketing }
}
