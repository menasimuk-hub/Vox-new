import React, { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { dateText, statusPillClass, truncate } from '../lib/billingAdminUtils'
import { Button } from '@/components/ui/Button'
import { Panel } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { Pill } from '@/components/ui/Badge'
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

const STATUS_PILL_TONE = {
  'p-green': 'success',
  'p-amber': 'warning',
  'p-red': 'danger',
  'p-cyan': 'info',
}

export default function PaymentEventsAdmin() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [filters, setFilters] = useState({ provider: '', status: '', duplicates_only: false })

  const load = useCallback(async () => {
    setError('')
    const params = new URLSearchParams({ limit: '200' })
    if (filters.provider) params.set('provider', filters.provider)
    if (filters.status) params.set('status', filters.status)
    if (filters.duplicates_only) params.set('duplicates_only', 'true')
    const res = await apiFetch(`/admin/billing/payment-events?${params.toString()}`)
    setRows(Array.isArray(res?.items) ? res.items : [])
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

  return (
    <div className="ds-scope space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="min-w-0">
          <h1 className="text-[15px] font-semibold leading-tight text-foreground">Payment events</h1>
          <p className="text-[11px] leading-tight text-muted-foreground">
            Provider webhooks and internal admin billing events.
          </p>
          <p className="mt-1 text-[11px] text-muted-foreground">
            For failed-only view see{' '}
            <Link to="/billing/failed-payments" className="font-medium text-foreground underline-offset-2 hover:underline">
              Failed payments
            </Link>
            .
          </p>
        </div>
        <div className="ml-auto">
          <Button type="button" variant="outline" size="sm" className="h-8" onClick={load} disabled={loading}>
            Refresh
          </Button>
        </div>
      </div>

      {error ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <Panel title="Events" subtitle="Filter by provider, status, or duplicates." bodyClassName="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <Input
            className="h-8 max-w-[160px]"
            placeholder="Provider"
            value={filters.provider}
            onChange={(e) => setFilters((f) => ({ ...f, provider: e.target.value }))}
          />
          <Input
            className="h-8 max-w-[160px]"
            placeholder="Status"
            value={filters.status}
            onChange={(e) => setFilters((f) => ({ ...f, status: e.target.value }))}
          />
          <label className="flex items-center gap-2 text-[12.5px] text-foreground">
            <input
              type="checkbox"
              className="size-3.5 accent-primary"
              checked={filters.duplicates_only}
              onChange={(e) => setFilters((f) => ({ ...f, duplicates_only: e.target.checked }))}
            />
            Duplicates only
          </label>
        </div>

        <StripeTable>
          <TableHeader>
            <TableRow>
              <TableHead>When</TableHead>
              <TableHead>Provider</TableHead>
              <TableHead>Kind</TableHead>
              <TableHead>Organisation</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Reason</TableHead>
              <TableHead>Event ID</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? <TableLoading colSpan={7} /> : null}
            {!loading && !rows.length ? <TableEmpty colSpan={7}>No payment events.</TableEmpty> : null}
            {!loading &&
              rows.map((row) => (
                <TableRow key={row.id}>
                  <TableCell className="text-muted-foreground">{dateText(row.created_at)}</TableCell>
                  <TableCell>{row.provider}</TableCell>
                  <TableCell>{row.event_kind || '—'}</TableCell>
                  <TableCell>{truncate(row.organisation_name, 24)}</TableCell>
                  <TableCell>
                    <div className="flex flex-wrap items-center gap-1">
                      <Pill tone={STATUS_PILL_TONE[statusPillClass(row.status)] || 'info'}>{row.status}</Pill>
                      {row.is_duplicate ? <Pill tone="warning">dup</Pill> : null}
                    </div>
                  </TableCell>
                  <TableCell className="text-muted-foreground">{truncate(row.failure_reason, 36)}</TableCell>
                  <TableCell>
                    <code className="rounded bg-muted px-1.5 py-0.5 text-[11px]">
                      {truncate(row.external_event_id, 22)}
                    </code>
                  </TableCell>
                </TableRow>
              ))}
          </TableBody>
        </StripeTable>
      </Panel>
    </div>
  )
}
