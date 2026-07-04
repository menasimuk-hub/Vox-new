import React, { useMemo, useState } from 'react'
import { AlertTriangle, CheckCircle2, Circle, Loader2, X } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { cn } from '@/lib/utils'

function StepIcon({ status }) {
  if (status === 'running') return <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
  if (status === 'done') return <CheckCircle2 className="h-3.5 w-3.5 text-success" />
  if (status === 'error') return <AlertTriangle className="h-3.5 w-3.5 text-destructive" />
  return <Circle className="h-3.5 w-3.5 text-muted-foreground/50" />
}

function MiniTable({ columns, rows, emptyLabel = 'None' }) {
  const list = Array.isArray(rows) ? rows : []
  if (!list.length) {
    return <p className="px-1 py-2 text-[11px] text-muted-foreground">{emptyLabel}</p>
  }
  return (
    <div className="max-h-40 overflow-auto rounded-md border">
      <table className="w-full text-left text-[11px]">
        <thead className="sticky top-0 bg-surface-muted">
          <tr>
            {columns.map((c) => (
              <th key={c.key} className="px-2 py-1.5 font-semibold text-muted-foreground">
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {list.slice(0, 200).map((row, i) => (
            <tr key={row.id || row.name || row.message || i} className="border-t">
              {columns.map((c) => (
                <td key={c.key} className="max-w-[220px] truncate px-2 py-1 font-mono" title={String(row[c.key] ?? '')}>
                  {String(row[c.key] ?? '—')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {list.length > 200 ? (
        <p className="border-t px-2 py-1 text-[10px] text-muted-foreground">Showing first 200 of {list.length}</p>
      ) : null}
    </div>
  )
}

const DETAIL_TABS = [
  { id: 'summary', label: 'Summary' },
  { id: 'deleted_local', label: 'Deleted local' },
  { id: 'deleted_meta', label: 'Deleted Meta' },
  { id: 'pushed', label: 'Pushed' },
  { id: 'skipped_buttonless', label: 'Buttonless' },
  { id: 'meta_orphans_remaining', label: 'Meta orphans' },
  { id: 'push_failed', label: 'Failures' },
]

export default function WaJobProgressDialog({
  open,
  title,
  dryRun = false,
  steps = [],
  phase = 'running',
  summaryRows = [],
  tables = {},
  message = '',
  error = '',
  reportPath = '',
  onClose,
}) {
  const [tab, setTab] = useState('summary')
  const running = phase === 'running'
  const done = phase === 'done'
  const failed = phase === 'error'

  const doneCount = useMemo(() => steps.filter((s) => s.status === 'done').length, [steps])
  const totalSteps = steps.length || 1

  if (!open) return null

  const activeTab = DETAIL_TABS.some((t) => t.id === tab) ? tab : 'summary'

  return (
    <div
      className="fixed inset-0 z-[130] flex items-center justify-center bg-black/50 p-4"
      role="presentation"
      onClick={running ? undefined : onClose}
    >
      <div
        className="flex max-h-[90vh] w-full max-w-2xl flex-col rounded-xl border bg-surface shadow-lg"
        role="dialog"
        aria-modal="true"
        aria-labelledby="wa-job-progress-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start gap-3 border-b px-4 py-3">
          <div
            className={cn(
              'flex h-8 w-8 shrink-0 items-center justify-center rounded-md',
              failed && 'bg-destructive/10 text-destructive',
              done && 'bg-success/10 text-success',
              running && 'bg-primary/10 text-primary',
            )}
          >
            {running ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            {done ? <CheckCircle2 className="h-4 w-4" /> : null}
            {failed ? <AlertTriangle className="h-4 w-4" /> : null}
          </div>
          <div className="min-w-0 flex-1">
            <div id="wa-job-progress-title" className="flex flex-wrap items-center gap-2 text-sm font-semibold">
              {title}
              {dryRun ? (
                <span className="rounded bg-warning/15 px-1.5 py-0.5 text-[10px] font-medium text-warning-foreground">
                  Dry-run
                </span>
              ) : null}
            </div>
            <div className="mt-0.5 text-[11px] text-muted-foreground">
              {running
                ? `Step ${Math.min(doneCount + 1, totalSteps)} of ${totalSteps} — local DB is source of truth`
                : done
                  ? 'Finished — review the tables below'
                  : 'Stopped with an error'}
            </div>
          </div>
          {!running ? (
            <Button type="button" size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={onClose}>
              <X className="h-3.5 w-3.5" />
            </Button>
          ) : null}
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
          <div className="mb-3">
            <div className="mb-1.5 flex justify-between text-[10px] text-muted-foreground">
              <span>Progress</span>
              <span>
                {doneCount}/{totalSteps}
              </span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-surface-muted">
              <div
                className={cn('h-full rounded-full transition-all', failed ? 'bg-destructive' : 'bg-primary')}
                style={{ width: `${Math.round((doneCount / totalSteps) * 100)}%` }}
              />
            </div>
          </div>

          <ul className="mb-4 space-y-1.5">
            {steps.map((s) => (
              <li key={s.id} className="flex items-start gap-2 text-xs">
                <span className="mt-0.5">
                  <StepIcon status={s.status} />
                </span>
                <div className="min-w-0 flex-1">
                  <div className={cn('font-medium', s.status === 'error' && 'text-destructive')}>{s.label}</div>
                  {s.detail ? <div className="truncate text-[11px] text-muted-foreground">{s.detail}</div> : null}
                </div>
              </li>
            ))}
          </ul>

          {error ? (
            <div className="mb-3 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
              {error}
            </div>
          ) : null}

          {message && (done || failed) ? (
            <p className="mb-3 text-xs text-muted-foreground">{message}</p>
          ) : null}

          {(done || failed) && (summaryRows.length > 0 || Object.keys(tables || {}).length > 0) ? (
            <>
              <div className="mb-2 flex flex-wrap gap-1">
                {DETAIL_TABS.map((t) => {
                  const count =
                    t.id === 'summary'
                      ? summaryRows.length
                      : Array.isArray(tables?.[t.id])
                        ? tables[t.id].length
                        : 0
                  if (t.id !== 'summary' && count === 0 && t.id !== 'meta_orphans_remaining') return null
                  return (
                    <button
                      key={t.id}
                      type="button"
                      className={cn(
                        'rounded-md border px-2 py-1 text-[10px] font-medium',
                        activeTab === t.id ? 'border-primary bg-primary/10 text-primary' : 'text-muted-foreground',
                      )}
                      onClick={() => setTab(t.id)}
                    >
                      {t.label}
                      {t.id !== 'summary' ? ` (${count})` : ''}
                    </button>
                  )
                })}
              </div>

              {activeTab === 'summary' ? (
                <div className="overflow-hidden rounded-md border">
                  <table className="w-full text-left text-[11px]">
                    <thead className="bg-surface-muted">
                      <tr>
                        <th className="px-2 py-1.5 font-semibold text-muted-foreground">Metric</th>
                        <th className="px-2 py-1.5 text-right font-semibold text-muted-foreground">Count</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(summaryRows || []).map((row) => (
                        <tr key={row.metric} className="border-t">
                          <td className="px-2 py-1.5">{row.metric}</td>
                          <td className="px-2 py-1.5 text-right font-mono tabular-nums">{row.count ?? 0}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : null}

              {activeTab === 'deleted_local' ? (
                <MiniTable
                  columns={[
                    { key: 'name', label: 'Name' },
                    { key: 'language', label: 'Lang' },
                    { key: 'reason', label: 'Reason' },
                  ]}
                  rows={tables?.deleted_local}
                />
              ) : null}
              {activeTab === 'deleted_meta' ? (
                <MiniTable
                  columns={[
                    { key: 'name', label: 'Name' },
                    { key: 'status', label: 'Status' },
                    { key: 'reason', label: 'Reason' },
                  ]}
                  rows={tables?.deleted_meta}
                />
              ) : null}
              {activeTab === 'pushed' ? (
                <MiniTable
                  columns={[
                    { key: 'name', label: 'Name' },
                    { key: 'language', label: 'Lang' },
                    { key: 'product', label: 'Product' },
                  ]}
                  rows={tables?.pushed}
                />
              ) : null}
              {activeTab === 'skipped_buttonless' ? (
                <MiniTable
                  columns={[
                    { key: 'name', label: 'Name' },
                    { key: 'language', label: 'Lang' },
                    { key: 'product', label: 'Product' },
                  ]}
                  rows={tables?.skipped_buttonless}
                  emptyLabel="No buttonless templates"
                />
              ) : null}
              {activeTab === 'meta_orphans_remaining' ? (
                <MiniTable
                  columns={[
                    { key: 'name', label: 'Name' },
                    { key: 'status', label: 'Status' },
                    { key: 'reason', label: 'Reason' },
                  ]}
                  rows={tables?.meta_orphans_remaining}
                  emptyLabel="No Meta orphans — survey/CF on Meta matches local keepers"
                />
              ) : null}
              {activeTab === 'push_failed' ? (
                <MiniTable
                  columns={[
                    { key: 'name', label: 'Name' },
                    { key: 'product', label: 'Product' },
                    { key: 'error', label: 'Error' },
                  ]}
                  rows={tables?.push_failed}
                  emptyLabel="No push failures"
                />
              ) : null}

              {reportPath ? (
                <p className="mt-2 truncate font-mono text-[10px] text-muted-foreground" title={reportPath}>
                  Report: {reportPath}
                </p>
              ) : null}
            </>
          ) : null}
        </div>

        <div className="flex justify-end gap-2 border-t px-4 py-3">
          <Button type="button" size="sm" className="h-8 text-xs" onClick={onClose} disabled={running}>
            {running ? 'Working…' : 'Close'}
          </Button>
        </div>
      </div>
    </div>
  )
}
