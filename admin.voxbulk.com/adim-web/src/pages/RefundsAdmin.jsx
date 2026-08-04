import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import RefundResolveModal from '../components/RefundResolveModal'
import { dateText, money, statusPillClass, truncate } from '../lib/billingAdminUtils'
import { Button } from '@/components/ui/Button'
import { Panel } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { Pill } from '@/components/ui/Badge'
import { KpiCard } from '@/components/ui/KpiCard'
import {
  StripeTable,
  TableBody,
  TableCell,
  TableEmpty,
  TableHead,
  TableHeader,
  TableLoading,
  TableRow,
} from '@/components/ui/Table'

const STATUS_OPTIONS = ['', 'pending', 'under_review', 'approved', 'processed', 'rejected', 'failed']

const STATUS_PILL_TONE = {
  'p-green': 'success',
  'p-amber': 'warning',
  'p-red': 'danger',
  'p-cyan': 'info',
}

const selectClass =
  'flex h-8 min-w-[160px] rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring'

export default function RefundsAdmin() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const [filters, setFilters] = useState({ status: '', provider: '', search: '' })
  const [modalRow, setModalRow] = useState(null)

  const load = useCallback(async () => {
    setError('')
    const params = new URLSearchParams({ limit: '200' })
    if (filters.status) params.set('status', filters.status)
    if (filters.provider.trim()) params.set('provider', filters.provider.trim())
    const res = await apiFetch(`/admin/billing/refunds?${params.toString()}`)
    let items = Array.isArray(res?.items) ? res.items : []
    if (filters.search.trim()) {
      const q = filters.search.trim().toLowerCase()
      items = items.filter(
        (r) =>
          String(r.organisation_name || '').toLowerCase().includes(q) ||
          String(r.org_email || '').toLowerCase().includes(q) ||
          String(r.id || '').toLowerCase().includes(q),
      )
    }
    setRows(items)
  }, [filters])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      try {
        await load()
      } catch (e) {
        if (!cancelled) setError(e?.message || 'Load failed')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [load])

  const stats = useMemo(() => {
    const pending = rows.filter((r) =>
      ['pending', 'under_review', 'approved'].includes(
        String(r.review_status_normalized || r.review_status || '').toLowerCase(),
      ),
    )
    return { total: rows.length, pending: pending.length }
  }, [rows])

  const resolveReview = async (row, status, extra = {}) => {
    if (!row?.org_id || !row?.id) return
    setBusy(row.id)
    setError('')
    try {
      const result = await apiFetch(
        `/admin/organisations/${encodeURIComponent(row.org_id)}/control-center/refund-reviews/${encodeURIComponent(row.id)}/resolve`,
        {
          method: 'POST',
          body: JSON.stringify({
            review_status: status,
            admin_notes: extra.admin_notes || '',
            issue_wallet_credit: Boolean(extra.issue_wallet_credit),
            approved_external_refund_pence: extra.approved_external_refund_pence,
          }),
        },
      )
      if (result?.stripe_refund_error) {
        setError(`Stripe refund failed: ${result.stripe_refund_error}`)
      }
      setModalRow(null)
      await load()
    } catch (e) {
      setError(e?.message || 'Action failed')
    } finally {
      setBusy('')
    }
  }

  return (
    <div className="ds-scope space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="min-w-0">
          <h1 className="text-[15px] font-semibold leading-tight text-foreground">Refunds</h1>
          <p className="text-[11px] leading-tight text-muted-foreground">
            Admin refund review queue — approve wallet credit, mark external refund, or reject.
          </p>
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <Button type="button" variant="outline" size="sm" className="h-8" onClick={load} disabled={loading}>
            Refresh
          </Button>
          <Button asChild variant="outline" size="sm" className="h-8">
            <Link to="/billing/exceptions">Exceptions</Link>
          </Button>
        </div>
      </div>

      {error ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        <KpiCard
          label="Pending queue"
          value={stats.pending}
          hint="Awaiting admin action"
          tone="warning"
          index={0}
        />
        <KpiCard label="Total reviews" value={stats.total} tone="info" index={1} />
      </div>

      <Panel title="Refund reviews" subtitle="Filter by status or search organisation." bodyClassName="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <select
            className={selectClass}
            value={filters.status}
            onChange={(e) => setFilters((f) => ({ ...f, status: e.target.value }))}
          >
            {STATUS_OPTIONS.map((opt) => (
              <option key={opt || 'all'} value={opt}>
                {opt ? opt.replace('_', ' ') : 'All statuses'}
              </option>
            ))}
          </select>
          <Input
            className="h-8 max-w-xs"
            placeholder="Search org or email…"
            value={filters.search}
            onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value }))}
          />
        </div>

        <StripeTable>
          <TableHeader>
            <TableRow>
              <TableHead>Requested</TableHead>
              <TableHead>Organisation</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Unused value</TableHead>
              <TableHead>Provider ref</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? <TableLoading colSpan={7} /> : null}
            {!loading && !rows.length ? (
              <TableEmpty colSpan={7}>No refund reviews match filters.</TableEmpty>
            ) : null}
            {!loading &&
              rows.map((row) => {
                const st = row.review_status_normalized || row.review_status
                const isBusy = busy === row.id
                return (
                  <TableRow key={row.id}>
                    <TableCell className="text-muted-foreground">{dateText(row.requested_at)}</TableCell>
                    <TableCell>
                      <div className="flex flex-col leading-tight">
                        <strong className="font-medium">{truncate(row.organisation_name, 24)}</strong>
                        <span className="text-[11px] text-muted-foreground">{truncate(row.org_email, 28)}</span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <Pill tone={STATUS_PILL_TONE[statusPillClass(st)] || 'info'}>{st}</Pill>
                    </TableCell>
                    <TableCell>{row.requested_refund_type || '—'}</TableCell>
                    <TableCell>{money(row.calculated_unused_value_pence, row.billing_currency)}</TableCell>
                    <TableCell className="text-muted-foreground" title={row.source_payment_reference || ''}>
                      {truncate(row.source_payment_reference, 28)}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex flex-wrap justify-end gap-1">
                        {['pending', 'under_review', 'approved'].includes(String(st).toLowerCase()) ? (
                          <Button
                            type="button"
                            size="sm"
                            className="h-7"
                            disabled={isBusy}
                            onClick={() => setModalRow(row)}
                          >
                            Resolve
                          </Button>
                        ) : null}
                        {String(st).toLowerCase() === 'processed' && row.wallet_transaction_id ? (
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            className="h-7"
                            disabled={isBusy}
                            onClick={async () => {
                              const note = window.prompt('Reason for reversing wallet credit:', 'Admin reversal')
                              if (note === null) return
                              setBusy(row.id)
                              setError('')
                              try {
                                await apiFetch(
                                  `/admin/organisations/${encodeURIComponent(row.org_id)}/control-center/refund-reviews/${encodeURIComponent(row.id)}/reverse-wallet`,
                                  { method: 'POST', body: JSON.stringify({ reason: note }) },
                                )
                                await load()
                              } catch (e) {
                                setError(e?.message || 'Reverse failed')
                              } finally {
                                setBusy('')
                              }
                            }}
                          >
                            Reverse wallet
                          </Button>
                        ) : null}
                        <Button asChild variant="outline" size="sm" className="h-7">
                          <Link
                            to="/organisations/all-users"
                            onClick={() => localStorage.setItem('voxbulk_admin_selected_org_id', row.org_id)}
                          >
                            OCC
                          </Link>
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                )
              })}
          </TableBody>
        </StripeTable>
      </Panel>

      <RefundResolveModal
        row={modalRow}
        open={Boolean(modalRow)}
        onClose={() => setModalRow(null)}
        onSubmit={resolveReview}
        busy={Boolean(busy)}
      />
    </div>
  )
}
