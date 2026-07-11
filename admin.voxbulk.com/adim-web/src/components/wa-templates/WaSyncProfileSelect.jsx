import React from 'react'
import { cn } from '@/lib/utils'

export default function WaSyncProfileSelect({
  items = [],
  value,
  onChange,
  disabled = false,
  loading = false,
  className,
}) {
  const options = Array.isArray(items) ? items : []
  if (loading && options.length === 0) {
    return (
      <span className={cn('text-[11px] text-muted-foreground', className)}>Loading profiles…</span>
    )
  }
  if (options.length === 0) {
    return (
      <span className={cn('text-[11px] text-warning-foreground', className)} title="Add a WhatsApp connection profile in Integrations">
        No WhatsApp profile
      </span>
    )
  }
  return (
    <label className={cn('inline-flex items-center gap-1.5', className)}>
      <span className="hidden text-[11px] text-muted-foreground sm:inline">Active profile</span>
      <select
        className="h-8 max-w-[220px] truncate rounded-md border border-input bg-background px-2 text-[11px] text-foreground disabled:opacity-60"
        value={value || ''}
        disabled={disabled || loading}
        onChange={(e) => onChange?.(e.target.value || null)}
        title="Select Meta 99 or Telnyx 55 — same as clicking a row in Live template monitor"
      >
        {options.map((item) => (
          <option key={item.id} value={item.id}>
            {item.label || item.name || item.id}
          </option>
        ))}
      </select>
    </label>
  )
}
