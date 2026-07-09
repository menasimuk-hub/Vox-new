import React from 'react'
import { RefreshCw } from 'lucide-react'
import { cn } from '@/lib/utils'

const ACCOUNT_KEY = {
  utility: 'profileUtility',
  marketing: 'profileMarketing',
  approved: 'profileApproved',
  pending: 'profilePending',
  rejected: 'profileRejected',
  total: 'profileTotal',
}

const BASE_COLS = [
  {
    key: 'utility',
    label: 'utility',
    title: 'Utility templates: scoped count / whole WABA or account (live Meta/Telnyx)',
  },
  {
    key: 'marketing',
    label: 'marketing',
    title: 'Marketing templates: scoped count / whole WABA or account (live Meta/Telnyx)',
  },
  {
    key: 'approved',
    label: 'approved',
    title: 'Approved: scoped / whole account',
  },
  {
    key: 'pending',
    label: 'pending',
    title: 'Pending: scoped / whole account',
  },
  {
    key: 'rejected',
    label: 'rejected',
    title: 'Rejected: scoped / whole account',
  },
  {
    key: 'total',
    label: 'total',
    title: 'Live template rows: scoped to active tab / all on profile WABA',
  },
]

function fmtCell(value, loading) {
  if (loading) return '…'
  if (value == null || value === '') return '—'
  return Number(value).toLocaleString()
}

function scopedMetric(summary, key) {
  if (!summary) return null
  const scoped = summary.scoped
  if (scoped && scoped[key] != null) return scoped[key]
  return summary[key]
}

function accountMetric(summary, key) {
  if (!summary) return null
  const alias = ACCOUNT_KEY[key]
  if (alias && summary[alias] != null) return summary[alias]
  const account = summary.account
  if (account && account[key] != null) return account[key]
  if (key === 'total') return summary.profileTotal
  return null
}

function showAccountSuffix(summary, key) {
  const scoped = scopedMetric(summary, key)
  const account = accountMetric(summary, key)
  if (account == null || scoped == null) return false
  return Number(account) !== Number(scoped)
}

function providerChip(provider) {
  const p = String(provider || '').toLowerCase()
  if (p === 'meta') {
    return (
      <span className="rounded bg-[#1877F2]/15 px-1 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-[#1877F2]">
        Meta
      </span>
    )
  }
  if (p === 'telnyx') {
    return (
      <span className="rounded bg-violet-500/15 px-1 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-violet-700 dark:text-violet-300">
        Telnyx
      </span>
    )
  }
  return null
}

export default function WaSyncProfileMatrix({
  profiles = [],
  selectedProfileId,
  rowState = {},
  onSelectProfile,
  onRefreshProfile,
  onRefreshAll,
  refreshingAll = false,
  scopeLabel = 'this tab',
}) {
  const items = Array.isArray(profiles) ? profiles : []
  const cols = BASE_COLS
  if (items.length === 0) {
    return (
      <p className="text-[11px] text-muted-foreground">No WhatsApp connection profiles — add one in Integrations.</p>
    )
  }

  return (
    <div className="w-full overflow-x-auto">
      <div className="mb-1 flex flex-col gap-0.5 sm:flex-row sm:items-center sm:justify-between">
        <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
          Live template monitor · scoped to {scopeLabel} · <span className="normal-case">counts show scoped / whole WABA</span>
        </span>
        <button
          type="button"
          className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] text-muted-foreground hover:bg-accent hover:text-foreground disabled:opacity-50"
          onClick={() => onRefreshAll?.()}
          disabled={refreshingAll}
          title="Refresh all profile rows"
        >
          <RefreshCw className={cn('h-3 w-3', refreshingAll && 'animate-spin')} />
          Refresh all
        </button>
      </div>
      <table className="w-full min-w-[640px] border-collapse text-[11px]">
        <thead>
          <tr className="border-b text-muted-foreground">
            <th className="py-1 pr-3 text-left font-medium">Profile</th>
            {cols.map((col) => (
              <th key={col.key} className="px-2 py-1 text-right font-medium" title={col.title}>
                {col.label}
              </th>
            ))}
            <th className="w-8 py-1" />
          </tr>
        </thead>
        <tbody>
          {items.map((profile) => {
            const id = String(profile.id)
            const state = rowState[id] || {}
            const selected = String(selectedProfileId) === id
            const summary = state.summary
            const loading = Boolean(state.loading)
            const err = state.error
            const label = profile.label || profile.name || id
            const scopedTotal = scopedMetric(summary, 'total')
            const accountTotal = accountMetric(summary, 'total')
            const accountMarketing = accountMetric(summary, 'marketing')
            const rowTitle = err
              ? err
              : selected
                ? 'Sync target'
                : `Scoped = ${scopeLabel}. After slash = all templates on this WABA/account.`

            return (
              <tr
                key={id}
                className={cn(
                  'cursor-pointer border-b border-border/60 transition-colors last:border-0',
                  selected ? 'bg-primary/8' : 'hover:bg-accent/40',
                  err && !loading && 'bg-destructive/5',
                )}
                onClick={() => onSelectProfile?.(id)}
                title={rowTitle}
              >
                <td className="max-w-[200px] truncate py-1.5 pr-3 align-middle">
                  <div className="flex items-center gap-1.5">
                    <span
                      className={cn(
                        'h-1.5 w-1.5 shrink-0 rounded-full',
                        selected ? 'bg-primary' : 'bg-muted-foreground/30',
                      )}
                    />
                    {providerChip(profile.provider)}
                    <span className={cn('truncate font-medium', selected && 'text-foreground')}>{label}</span>
                  </div>
                </td>
                {cols.map((col) => {
                  const scoped = scopedMetric(summary, col.key)
                  const account = accountMetric(summary, col.key)
                  const dual = showAccountSuffix(summary, col.key)
                  const warn =
                    col.key === 'marketing' && (Number(scoped) > 0 || Number(accountMarketing) > 0)
                  const bad = col.key === 'rejected' && Number(scoped) > 0
                  return (
                    <td
                      key={col.key}
                      className={cn(
                        'px-2 py-1.5 text-right tabular-nums',
                        col.key === 'approved' && 'text-success',
                        warn && 'font-medium text-warning-foreground',
                        bad && 'font-medium text-destructive',
                      )}
                      title={
                        dual
                          ? `${scoped ?? '—'} scoped (${scopeLabel}) · ${account ?? '—'} on whole WABA`
                          : col.title
                      }
                    >
                      {fmtCell(scoped, loading && summary == null)}
                      {dual && !loading ? (
                        <span className="ml-0.5 text-[9px] text-muted-foreground">/{fmtCell(account, false)}</span>
                      ) : null}
                    </td>
                  )
                })}
                <td className="py-1.5 pl-1 text-right align-middle">
                  <button
                    type="button"
                    className="rounded p-0.5 text-muted-foreground hover:bg-accent hover:text-foreground disabled:opacity-40"
                    title="Refresh this row"
                    disabled={loading}
                    onClick={(e) => {
                      e.stopPropagation()
                      onRefreshProfile?.(id)
                    }}
                  >
                    <RefreshCw className={cn('h-3 w-3', loading && 'animate-spin')} />
                  </button>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
