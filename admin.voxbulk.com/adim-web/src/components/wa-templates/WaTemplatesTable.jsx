import React, { useMemo, useState } from 'react'
import { BarChart3, Pencil, Plus, Power, RefreshCw, Search, Trash2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { CategoryPill, IconBtn, LangChip, StatusDot } from './waTemplatesUi'

export default function WaTemplatesTable({
  templates,
  loading = false,
  onEdit,
  onSync,
  onToggle,
  onDelete,
  onNew,
  newLabel = 'New',
  showNew = true,
  emptyLabel = 'No templates match your filters.',
}) {
  const [q, setQ] = useState('')
  const [cat, setCat] = useState('all')

  const filtered = useMemo(
    () =>
      templates.filter(
        (t) =>
          (cat === 'all' || t.category === cat) &&
          (q === '' || String(t.name || '').toLowerCase().includes(q.toLowerCase())),
      ),
    [templates, q, cat],
  )

  return (
    <div className="animate-fade-in">
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
        <select
          value={cat}
          onChange={(e) => setCat(e.target.value)}
          className="h-8 w-[140px] rounded-md border border-input bg-background px-2 text-xs"
        >
          <option value="all">All categories</option>
          <option value="Utility">Utility</option>
          <option value="Marketing">Marketing</option>
        </select>
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
              <th className="w-28 px-2 py-2 text-left font-medium">Status</th>
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
                    t.status === 'disabled' && 'opacity-60',
                  )}
                >
                  <td className="px-3 py-1.5">
                    <button type="button" onClick={() => onEdit?.(t)} className="wa-hub-name-btn">
                      {t.name}
                    </button>
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
                      <IconBtn icon={Pencil} label="Edit" onClick={() => onEdit?.(t)} />
                      <IconBtn icon={RefreshCw} label="Sync" onClick={() => onSync?.(t)} tone="success" />
                      <IconBtn
                        icon={Power}
                        label={t.status === 'disabled' ? 'Enable' : 'Disable'}
                        onClick={() => onToggle?.(t)}
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
