import React from 'react'
import { cn } from '@/lib/utils'

export const LANGS = ['EN', 'AR', 'FR', 'ES', 'DE', 'PT', 'IT', 'TR', 'RU', 'HI']

/** Customer Feedback seed languages (19) — matches backend DEFAULT_EXPECTED_LANGS. */
export const FEEDBACK_LANG_CHIPS = [
  'EN',
  'ZH',
  'HI',
  'ES',
  'FR',
  'AR',
  'BN',
  'PT',
  'RU',
  'UR',
  'DE',
  'IT',
  'NL',
  'PL',
  'RO',
  'EL',
  'SV',
  'CS',
  'NO',
  'TR',
]

export function feedbackChipToLanguage(chip) {
  const key = String(chip || '').toUpperCase()
  const map = {
    EN: 'en_GB',
    ZH: 'zh_CN',
    PT: 'pt_PT',
    NO: 'nb',
    AR: 'ar',
    BN: 'bn',
    CS: 'cs',
    DE: 'de',
    EL: 'el',
    ES: 'es',
    FR: 'fr',
    HI: 'hi',
    IT: 'it',
    NL: 'nl',
    PL: 'pl',
    RO: 'ro',
    RU: 'ru',
    SV: 'sv',
    UR: 'ur',
    TR: 'tr',
  }
  return map[key] || `${key.toLowerCase()}`
}

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

/** Map a raw Meta/Telnyx approval status to a StatusDot colour key. */
function metaStatusToKey(status, remoteId) {
  const s = String(status || '').trim().toUpperCase()
  const remote = String(remoteId || '').trim()
  const hasRemote = Boolean(remote) && !remote.startsWith('local-')
  if (s === 'APPROVED') return 'approved'
  if (s === 'REJECTED') return 'rejected'
  if ((s.startsWith('PENDING') || s === 'IN_APPEAL' || s === 'PENDING_DELETION') && hasRemote) return 'pending'
  if (s === 'LOCAL_DRAFT' || s === 'DRAFT' || s === '' || s === 'UNKNOWN' || !hasRemote) return 'local'
  if (s === 'DISABLED' || s === 'PAUSED') return 'disabled'
  return hasRemote ? 'pending' : 'local'
}

const PROFILE_STATUS_DOT = {
  approved: 'bg-success',
  pending: 'bg-warning',
  rejected: 'bg-destructive',
  local: 'bg-info',
  disabled: 'bg-muted-foreground/50',
}

/** Per-connection-profile status chips (e.g. "Meta 99 · Approved", "Telnyx 55 · Pending"). */
export function ProfileStatusBadges({ statuses }) {
  const list = Array.isArray(statuses) ? statuses : []
  if (!list.length) return null
  return (
    <div className="mt-1 flex flex-wrap gap-1">
      {list.map((p) => {
        const remoteId = p.remote_template_id || p.remote_record_id
        const key = metaStatusToKey(p.status, remoteId)
        const label = p.profile_label || p.provider || p.profile_key || 'Profile'
        const statusText =
          key === 'local'
            ? 'local draft'
            : String(p.status || 'UNKNOWN').replace(/_/g, ' ').toLowerCase()
        const tip = p.rejection_reason
          ? `${label}: ${statusText} — ${p.rejection_reason}`
          : `${label}: ${statusText}`
        return (
          <span
            key={p.profile_key || label}
            className="inline-flex items-center gap-1 rounded-full border border-border bg-surface-muted px-1.5 py-0.5 text-[10px] font-medium text-foreground/80"
            title={tip}
          >
            <span className={cn('h-1.5 w-1.5 shrink-0 rounded-full', PROFILE_STATUS_DOT[key] || 'bg-warning')} />
            <span className="max-w-[90px] truncate">{label}</span>
          </span>
        )
      })}
    </div>
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

/** Light background colours per language code for quick scanning. */
export function langChipClass(code, { active = false, muted = false } = {}) {
  const key = String(code || '').toUpperCase()
  // Light tint + readable text + matching ring
  const map = {
    EN: 'bg-red-100 text-red-800 ring-red-200',
    AR: 'bg-green-100 text-green-800 ring-green-200',
    FR: 'bg-blue-100 text-blue-800 ring-blue-200',
    DE: 'bg-yellow-100 text-yellow-900 ring-yellow-200',
    ES: 'bg-orange-100 text-orange-800 ring-orange-200',
    PT: 'bg-teal-100 text-teal-800 ring-teal-200',
    IT: 'bg-purple-100 text-purple-800 ring-purple-200',
    TR: 'bg-rose-100 text-rose-800 ring-rose-200',
    RU: 'bg-sky-100 text-sky-800 ring-sky-200',
    HI: 'bg-amber-100 text-amber-900 ring-amber-200',
  }
  const base = map[key] || 'bg-surface-muted text-foreground/80 ring-border'
  if (muted) return cn(base, 'opacity-45')
  if (active) return cn(base, 'ring-2 font-semibold')
  return base
}

export function LangCountBadge({ count, langs, title }) {
  const n = Number(count) || 0
  const label = n > 1 ? `${n} langs` : n === 1 ? '1 lang' : '—'
  const tip = title || (Array.isArray(langs) && langs.length ? langs.join(' · ') : label)
  return (
    <span
      className="inline-flex items-center rounded-md bg-info-soft px-2 py-0.5 text-[11px] font-semibold tabular-nums text-info ring-1 ring-inset ring-info/20"
      title={tip}
    >
      {label}
    </span>
  )
}

export function LangChip({ langs, title, languageCount }) {
  if (languageCount != null && Number(languageCount) > 1) {
    return <LangCountBadge count={languageCount} langs={langs} title={title} />
  }
  const list = Array.isArray(langs) ? langs : []
  const codes = list.length ? list : ['—']
  return (
    <span
      className="inline-flex cursor-default flex-wrap items-center gap-1 text-xs font-medium"
      title={title || codes.join(' · ')}
    >
      {codes.map((code) => (
        <span
          key={code}
          className={cn(
            'inline-flex items-center rounded-md px-1.5 py-0.5 uppercase ring-1 ring-inset',
            langChipClass(code),
          )}
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

export function isHiddenWaTemplate(tpl, product = 'survey') {
  if (product === 'feedback') return tpl?.is_active === false
  return tpl?.active_for_survey === false
}

export function isHubRowHidden(row) {
  if (row?.hiddenFromSurvey != null) return Boolean(row.hiddenFromSurvey)
  return isHiddenWaTemplate(row?.raw, row?.product || 'survey')
}

/** Sort hub rows: hidden topics sink to bottom; rejected bubble up among active. */
export function sortHubTemplateRows(rows) {
  return [...rows].sort((a, b) => {
    const aHidden = isHubRowHidden(a)
    const bHidden = isHubRowHidden(b)
    if (aHidden && !bHidden) return 1
    if (bHidden && !aHidden) return -1
    if (a.status === 'rejected' && b.status !== 'rejected') return -1
    if (b.status === 'rejected' && a.status !== 'rejected') return 1
    const byName = String(a.name).localeCompare(String(b.name))
    if (byName !== 0) return byName
    return String(a.langs?.[0] || '').localeCompare(String(b.langs?.[0] || ''))
  })
}

export function patchHubRowHidden(row, hidden, product = 'survey') {
  const active = !hidden
  const raw =
    product === 'feedback'
      ? {
          ...row.raw,
          is_active: active,
          variants: Array.isArray(row.raw?.variants)
            ? row.raw.variants.map((v) => ({ ...v, is_active: active }))
            : row.raw?.variants,
        }
      : { ...row.raw, active_for_survey: active }
  return toHubRow(raw, {
    rowKind: row.rowKind,
    product: row.product || product,
    surveyTypeId: row.surveyTypeId || row.raw?.survey_type_id,
    surveyTypeName: row.surveyTypeName || row.raw?.survey_type_name,
    name: row.name,
    metaName: row.metaName,
    languageCount: row.languageCount,
    languages: row.raw?.languages || row.langs,
    variants: row.raw?.variants,
    systemKind: row.systemKind,
  })
}

/** Map API row → StatusDot status. Only Meta/Telnyx status counts as rejected — never local push errors. */
export function mapApprovalStatus(tpl) {
  // Prefer live Meta fields when present.
  const candidates = [
    tpl?.live_status,
    tpl?.status,
    tpl?.approval_status,
  ]
    .map((v) => String(v || '').toUpperCase().trim())
    .filter(Boolean)

  // Rejection only from explicit Meta/Telnyx REJECTED status — not local_sync_status / push errors.
  if (candidates.some((meta) => meta === 'REJECTED')) return 'rejected'

  const meta = candidates[0] || ''

  // Hidden-from-flows is shown via the power toggle — keep status for Meta approval only.
  if (tpl?.active_for_survey === false || tpl?.is_active === false) {
    // fall through to Meta status below (do not force status dot to "disabled")
  } else if (
    tpl?.active_for_interview === false ||
    tpl?.active_for_appointment === false
  ) {
    return 'disabled'
  }

  if (meta === 'APPROVED' || meta.includes('APPROV')) return 'approved'
  if (meta === 'DISABLED' || meta === 'PAUSED') return 'disabled'
  if (meta === 'PENDING' || meta === 'PENDING_APPROVAL' || meta === 'IN_APPEAL' || meta === 'SUBMITTED') {
    return isLocalOnlyRow(tpl) ? 'local' : 'pending'
  }
  if (meta === 'LOCAL_DRAFT' || meta === 'DRAFT') return 'local'
  if (meta === 'UNKNOWN' && isLocalOnlyRow(tpl)) return 'local'
  if (meta === 'UNKNOWN') {
    const remote = String(tpl?.telnyx_record_id || tpl?.template_id || '').trim()
    return remote && !remote.startsWith('local-') ? 'pending' : 'local'
  }

  if (isLocalOnlyRow(tpl)) return 'local'

  const label = String(tpl?.status_label || '').toLowerCase()
  if (label.includes('ready')) return 'approved'
  // Do not treat status_label "reject" from local errors as Meta rejection.
  if (label === 'rejected' || label.startsWith('rejected ')) return 'rejected'
  if (label.includes('need')) return 'local'
  if (label.includes('pending')) return 'pending'

  if (Number(tpl?.approved_template_count) > 0) return 'approved'
  if (Number(tpl?.pending_template_count) > 0) return 'pending'

  const sync = String(tpl?.local_sync_status || tpl?.sync_status || '').toLowerCase()
  if (sync === 'in_sync' || sync === 'synced') return 'approved'
  if (sync.includes('draft') || sync.includes('local')) return 'local'
  // Push/sync errors are local problems — show as local, never as Meta rejected.
  if (sync.includes('error') || sync.includes('needs_resubmit')) return 'local'

  return 'pending'
}

export function mapCategory(tpl) {
  const c = String(tpl?.category || tpl?.meta_category || 'UTILITY').toUpperCase()
  return c.includes('MARKET') ? 'Marketing' : 'Utility'
}

export function shortMetaName(name, max = 36) {
  const full = String(name || '').trim()
  if (!full) return '—'
  if (full.length <= max) return full
  return `${full.slice(0, max - 1)}…`
}

export function MetaNamePreview({ name, className, max = 36 }) {
  const full = String(name || '').trim()
  if (!full) {
    return <span className={cn('text-[10px] text-muted-foreground', className)}>Meta name pending</span>
  }
  return (
    <code
      className={cn(
        'block max-w-[320px] truncate rounded bg-surface-muted/60 px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground',
        className,
      )}
      title={full}
    >
      {shortMetaName(full, max)}
    </code>
  )
}

export function MetaSyncNamingNote({ industrySlug, exampleMetaName }) {
  const slug = String(industrySlug || 'industry').trim()
  const example = String(exampleMetaName || `voxbulk_cf_${slug}_topic_slug_topic_slug_xxxxxxxx`).trim()
  return (
    <div className="rounded-md border border-border/70 bg-surface-muted/30 px-3 py-2 text-[11px] leading-relaxed text-muted-foreground">
      <p className="font-medium text-foreground">How names appear in Meta</p>
      <p className="mt-1">
        Meta only supports template categories <span className="font-medium text-foreground">Utility</span>, Marketing,
        and Authentication — not industry folders. Your industry is encoded in the template name prefix{' '}
        <code className="rounded bg-background px-1 font-mono text-[10px]">voxbulk_cf_{slug}_</code>.
      </p>
      <p className="mt-1">
        In WhatsApp Manager, search that prefix to filter this industry. Each topic shares one Meta name across all{' '}
        language versions.
      </p>
      <p className="mt-1">
        Industry sync runs in small batches (default 5 templates, pause between batches) to avoid Meta rate limits.
        ~380 language rows = 20 Meta names × 19 languages — normal, not duplicate spam.
      </p>
      {example ? (
        <p className="mt-1.5">
          Example:{' '}
          <code className="block truncate rounded bg-background px-1.5 py-0.5 font-mono text-[10px] text-foreground" title={example}>
            {example}
          </code>
        </p>
      ) : null}
    </div>
  )
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
  if (s.startsWith('ZH')) return 'ZH'
  if (s.startsWith('BN')) return 'BN'
  if (s.startsWith('UR')) return 'UR'
  if (s.startsWith('RO')) return 'RO'
  if (s.startsWith('EL')) return 'EL'
  if (s.startsWith('SV')) return 'SV'
  if (s.startsWith('CS')) return 'CS'
  if (s.startsWith('NB') || s.startsWith('NO')) return 'NO'
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
  const metaName = String(tpl.meta_name || tpl.telnyx_name || tpl.name || '').trim()
  const displayName = String(tpl.display_name || tpl.name || tpl.slug || tpl.id).trim()
  return {
    id: tpl.id,
    name: overrides.name || displayName,
    metaName,
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
    syncFromMeta: Boolean(tpl.sync_from_meta),
    hiddenFromSurvey: overrides.hiddenFromSurvey ?? isHiddenWaTemplate(tpl, overrides.product),
    rejectionReason: tpl.rejection_reason || tpl.last_push_error || '',
    profileStatuses: Array.isArray(tpl.profile_statuses) ? tpl.profile_statuses : [],
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
