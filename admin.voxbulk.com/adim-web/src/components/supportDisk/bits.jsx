import React from 'react'
import { cn } from './utils'

export const STATUS_META = {
  open: { label: 'Open', bg: 'bg-status-open-bg', text: 'text-status-open', dot: 'bg-status-open' },
  pending: { label: 'Pending', bg: 'bg-status-pending-bg', text: 'text-status-pending', dot: 'bg-status-pending' },
  waiting: { label: 'Waiting', bg: 'bg-status-waiting-bg', text: 'text-status-waiting', dot: 'bg-status-waiting' },
  resolved: { label: 'Resolved', bg: 'bg-status-resolved-bg', text: 'text-status-resolved', dot: 'bg-status-resolved' },
  closed: { label: 'Closed', bg: 'bg-status-closed-bg', text: 'text-status-closed', dot: 'bg-status-closed' },
}

export const PRIORITY_META = {
  urgent: { label: 'Urgent', bars: 4, text: 'text-priority-urgent' },
  high: { label: 'High', bars: 3, text: 'text-priority-high' },
  normal: { label: 'Normal', bars: 2, text: 'text-priority-normal' },
  low: { label: 'Low', bars: 1, text: 'text-priority-low' },
}

export function StatusPill({ status, className }) {
  const meta = STATUS_META[status] || STATUS_META.open
  return <span className={cn('inline-flex shrink-0 items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-semibold whitespace-nowrap', meta.bg, meta.text, className)}>
    <span className={cn('size-1.5 rounded-full', meta.dot)} />{meta.label}
  </span>
}

export function PriorityMark({ priority = 'normal' }) {
  const meta = PRIORITY_META[priority] || PRIORITY_META.normal
  return <span className={cn('inline-flex items-end gap-[2px]', meta.text)} title={`${meta.label} priority`}>
    {[1, 2, 3, 4].map((i) => <span key={i} className={cn('w-[3px] rounded-full bg-current', i <= meta.bars ? 'opacity-100' : 'opacity-20')} style={{ height: `${3 + i * 2}px` }} />)}
  </span>
}

const tones = ['bg-status-open-bg text-status-open', 'bg-status-resolved-bg text-status-resolved', 'bg-status-pending-bg text-status-pending', 'bg-status-waiting-bg text-status-waiting']
export function InitialsAvatar({ name = 'Unknown', className }) {
  const initials = String(name).split(/[\s@]+/).filter(Boolean).map((p) => p[0]).slice(0, 2).join('').toUpperCase()
  return <span className={cn('grid size-8 shrink-0 place-items-center rounded-full text-[11px] font-bold', tones[String(name).length % tones.length], className)}>{initials || '?'}</span>
}

export function TagChip({ label }) {
  return <span className="inline-flex items-center rounded-md border border-border bg-secondary px-1.5 py-0.5 text-[11px] font-medium text-muted-foreground">{label}</span>
}
