import React, { useMemo, useState } from 'react'
import { BarChart3, Pencil, Plus, Power, RefreshCw, Search, Trash2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { CategoryPill, IconBtn, LangChip, STATUS_FILTERS, StatusDot } from './waTemplatesUi'

export default function WaTemplatesTable({
  templates,
  loading = false,
  onEdit,
  onSync,
  onToggle,
  onDelete,
  onReject,
  syncingId = null,
  onNew,
  newLabel = 'New',
  showNew = true,
  emptyLabel = 'No templates match your filters.',
  defaultStatusFilter = 'all',
  plainNames = false,
}) {
  const [q, setQ] = useState('')
  const [cat, setCat] = useState('all')
  const [statusFilter, setStatusFilter] = useState(defaultStatusFilter)

  const statusCounts = useMemo(() => {
    const counts = { all: templates.length, approved: 0, rejected: 0, pending: 0, local: 0, disabled: 0 }
    for (const t of templates) {
      if (counts[t.status] != null) counts[t.status] += 1
    }
    return counts
  }, [templates])

  const categoryCounts = useMemo(() => {
    const counts = { all: templates.length, Utility: 0, Marketing: 0 }
    for (const t of templates) {
      if (t.category === 'Marketing') counts.Marketing += 1
      else counts.Utility += 1
    }
    return counts
  }, [templates])

  const filtered = useMemo(() => {
    const list = templates.filter((t) => {
      if (statusFilter !== 'all' && t.status !== statusFilter) return false
      if (cat !== 'all' && t.category !== cat) return false
      if (q && !String(t.name || '').toLowerCase().includes(q.toLowerCase())) return false
      return true
    })
    // Disabled always sink to the bottom.
    return list.sort((a, b) => {
      if (a.status === 'disabled' && b.status !== 'disabled') return 1
      if (b.status === 'disabled' && a.status !== 'disabled') return -1
      if (a.status === 'rejected' && b.status !== 'rejected') return -1
      if (b.status === 'rejected' && a.status !== 'rejected') return 1
      return String(a.name).localeCompare(String(b.name))
    })
  }, [templates, q, cat, statusFilter])

  const chipClass = (active, tone) =>
    cn(
      'inline-flex h-7 items-center gap-1.5 rounded-md px-2.5 text-[11px] font-medium transition',
      active
        ? tone === 'rejected'
          ? 'bg-destructive text-destructive-foreground shadow-sm'
          : tone === 'approved'
            ? 'bg-success text-success-foreground shadow-sm'
            : tone === 'marketing'
              ? 'bg-warning text-warning-foreground shadow-sm'
              : 'bg-background text-foreground shadow-sm ring-1 ring-border'
        : 'text-muted-foreground hover:bg-background/80 hover:text-foreground',
    )

  return (
    <div className="animate-fade-in">
      <div className="flex flex-wrap items-center gap-1.5 border-b bg-surface-muted/30 px-3 py-2">
        {STATUS_FILTERS.map((f) => {
          const count = statusCounts[f.id] ?? 0
          const active = statusFilter === f.id
          return (
            <button
              key={f.id}
              type="button"
              onClick={() => setStatusFilter(f.id)}
              className={chipClass(active, f.id)}
            >
              {f.label}
              <span
                className={cn(
                  'tabular-nums',
                  active ? 'opacity-90' : 'text-muted-foreground',
                  f.id === 'rejected' && count > 0 && !active && 'font-semibold text-destructive',
                )}
              >
                {count}
              </span>
            </button>
          )
        })}
        <span className="mx-1 h-4 w-px bg-border" />
        {[
          { id: 'all', label: 'All cats' },
          { id: 'Utility', label: 'Utility' },
          { id: 'Marketing', label: 'Marketing' },
        ].map((f) => {
          const count = categoryCounts[f.id] ?? 0
          const active = cat === f.id
          return (
            <button
              key={f.id}
              type="button"
              onClick={() => setCat(f.id)}
              className={chipClass(active, f.id === 'Marketing' ? 'marketing' : 'default')}
            >
              {f.label}
              <span className={cn('tabular-nums', active ? 'opacity-90' : 'text-muted-foreground')}>{count}</span>
            </button>
          )
        })}
      </div>

      <div className="flex flex-wrap items-center gap-2 border-b bg-surface-muted/40 px-3 py-2">
        <div className="relative min-w-[220px] flex-1">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search templates…"
            className="h-8 bg-background pl-8 text-xs"
          />
        </div>
        <div className="text-xs tabular-nums text-muted-foreground">
          {filtered.length} / {templates.length}
        </div>
        {showNew && onNew ? (
          <Button size="sm" variant="outline" className="ml-auto h-8 gap-1.5 text-xs" onClick={onNew}>
            <Plus className="h-3.5 w-3.5" /> {newLabel}
          </Button>
        ) : (
          <div className="ml-auto" />
        )}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-surface-muted/30 text-[11px] uppercase tracking-wider text-muted-foreground">
              <th className="px-3 py-2 text-left font-medium">Name</th>
              <th className="w-24 px-2 py-2 text-left font-medium">Langs</th>
              <th className="w-28 px-2 py-2 text-left font-medium">Category</th>
              <th className="w-32 px-2 py-2 text-left font-medium">Status</th>
              <th className="w-20 px-2 py-2 text-right font-medium">Used</th>
              <th className="w-20 px-2 py-2 text-left font-medium">Updated</th>
              <th className="w-40 px-3 py-2 text-right font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={7} className="py-10 text-center text-xs text-muted-foreground">
                  Loading templates…
                </td>
              </tr>
            ) : (
              filtered.map((t, i) => (
                <tr
                  key={t.id}
                  className={cn(
                    'border-t border-border/60 transition-colors hover:bg-accent/40',
                    i % 2 === 1 && 'bg-surface-muted/20',
                    t.status === 'disabled' && 'bg-muted/40 opacity-50',
                    t.status === 'rejected' && 'bg-destructive/5 hover:bg-destructive/10',
                    t.status === 'approved' && 'bg-success/5',
                  )}
                >
                  <td className="px-3 py-1.5">
                    <button
                      type="button"
                      onClick={() => (t.status === 'rejected' && onReject ? onReject(t) : onEdit?.(t))}
                      className={cn(plainNames ? 'wa-hub-name-plain' : 'wa-hub-name-btn')}
                      title={t.name}
                    >
                      {t.name}
                    </button>
                    {t.status === 'rejected' ? (
                      <button
                        type="button"
                        className="mt-0.5 block max-w-[280px] truncate text-left text-[10px] font-medium text-destructive hover:underline"
                        title={t.rejectionReason || 'View rejection details'}
                        onClick={() => onReject?.(t)}
                      >
                        {t.rejectionReason || 'Rejected — click for details'}
                      </button>
                    ) : null}
                  </td>
                  <td className="px-2 py-1.5">
                    <LangChip langs={t.langs} title={t.langsTitle} />
                  </td>
                  <td className="px-2 py-1.5">
                    <CategoryPill category={t.category} />
                  </td>
                  <td className="px-2 py-1.5">
                    <StatusDot status={t.status} />
                  </td>
                  <td className="px-2 py-1.5 text-right text-xs tabular-nums text-muted-foreground">
                    <span className="inline-flex items-center gap-1">
                      <BarChart3 className="h-3 w-3" />
                      {Number(t.used || 0).toLocaleString()}
                    </span>
                  </td>
                  <td className="px-2 py-1.5 text-xs text-muted-foreground">{t.updated}</td>
                  <td className="px-3 py-1.5">
                    <div className="flex items-center justify-end gap-0.5">
                      <IconBtn
                        icon={Pencil}
                        label={t.status === 'rejected' ? 'Fix / edit' : 'Edit'}
                        onClick={() => onEdit?.(t)}
                        disabled={syncingId != null}
                      />
                      <IconBtn
                        icon={RefreshCw}
                        label={syncingId === t.id ? 'Syncing…' : 'Sync'}
                        onClick={() => onSync?.(t)}
                        tone="success"
                        disabled={syncingId != null}
                        spinning={syncingId === t.id}
                        className={syncingId === t.id ? 'text-success' : undefined}
                      />
                      <IconBtn
                        icon={Power}
                        label={t.status === 'disabled' ? 'Enable template' : 'Disable template'}
                        onClick={() => onToggle?.(t)}
                        disabled={syncingId != null}
                        className={
                          t.status === 'disabled'
                            ? 'bg-destructive/15 text-destructive hover:bg-destructive/25 hover:text-destructive'
                            : undefined
                        }
                        tone={t.status === 'disabled' ? 'danger' : 'default'}
                      />
                      <IconBtn icon={Trash2} label="Delete" onClick={() => onDelete?.(t)} tone="danger" />
                    </div>
                  </td>
                </tr>
              ))
            )}
            {!loading && filtered.length === 0 ? (
              <tr>
                <td colSpan={7} className="py-10 text-center text-xs text-muted-foreground">
                  {emptyLabel}
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </div>
  )
}
