import React from 'react'
import { Languages } from 'lucide-react'
import { cn } from '@/lib/utils'

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
      className="inline-flex items-center gap-1 rounded-md bg-surface-muted px-1.5 py-0.5 text-xs font-medium text-foreground/80 ring-1 ring-inset ring-border cursor-default"
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
        'inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-all',
        'hover:bg-accent hover:text-foreground active:scale-95 disabled:opacity-40 disabled:pointer-events-none',
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
  const raw = String(tpl?.approval_status || tpl?.status || tpl?.sync_status || '').toLowerCase()
  if (raw.includes('reject')) return 'rejected'
  if (raw.includes('disable') || tpl?.active_for_survey === false || tpl?.active_for_interview === false) return 'disabled'
  if (raw.includes('pend')) return 'pending'
  if (raw.includes('approv') || raw.includes('sync')) return 'approved'
  return 'pending'
}

export function mapCategory(tpl) {
  const c = String(tpl?.category || tpl?.meta_category || 'UTILITY').toUpperCase()
  return c.includes('MARKET') ? 'Marketing' : 'Utility'
}
