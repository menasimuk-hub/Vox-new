import React, { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { truncate } from '../lib/billingAdminUtils'
import { Button } from '@/components/ui/Button'
import { Panel } from '@/components/ui/Card'
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

function severityTone(sev) {
  if (sev === 'error') return 'danger'
  if (sev === 'warning') return 'warning'
  return 'info'
}

export default function BillingExceptions() {
  const [items, setItems] = useState([])
  const [summary, setSummary] = useState({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setError('')
    const res = await apiFetch('/admin/billing/exceptions?limit=200')
    setItems(Array.isArray(res?.items) ? res.items : [])
    setSummary(res?.summary || {})
  }, [])

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
          <h1 className="text-[15px] font-semibold leading-tight text-foreground">Billing exceptions</h1>
          <p className="text-[11px] leading-tight text-muted-foreground">
            Failed renewals, missing billing dates, currency mismatches, and pending refund queue.
          </p>
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <Button type="button" variant="outline" size="sm" className="h-8" onClick={load} disabled={loading}>
            Refresh
          </Button>
          <Button asChild variant="outline" size="sm" className="h-8">
            <Link to="/billing/reports">Revenue reports</Link>
          </Button>
        </div>
      </div>

      {error ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <KpiCard label="Total exceptions" value={summary.total ?? items.length} tone="danger" index={0} />
        <KpiCard label="Missing next billing" value={summary.missing_next_billing_date ?? 0} tone="warning" index={1} />
        <KpiCard label="Pending refunds" value={summary.pending_refund_queue ?? 0} tone="primary" index={2} />
        <KpiCard label="Failed renewals" value={summary.failed_renewal ?? 0} tone="danger" index={3} />
        <KpiCard label="Stuck DD" value={summary.stuck_dd_collecting ?? 0} tone="warning" index={4} />
        <KpiCard label="Currency mismatch" value={summary.currency_mismatch ?? 0} tone="info" index={5} />
      </div>

      <Panel title="Exceptions" subtitle="Detected billing anomalies across organisations.">
        <StripeTable>
          <TableHeader>
            <TableRow>
              <TableHead>Severity</TableHead>
              <TableHead>Kind</TableHead>
              <TableHead>Organisation</TableHead>
              <TableHead>Detail</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? <TableLoading colSpan={5} /> : null}
            {!loading && !items.length ? (
              <TableEmpty colSpan={5}>No billing exceptions detected.</TableEmpty>
            ) : null}
            {!loading &&
              items.map((row, idx) => (
                <TableRow key={`${row.kind}-${row.org_id}-${idx}`}>
                  <TableCell>
                    <Pill tone={severityTone(row.severity)}>{row.severity}</Pill>
                  </TableCell>
                  <TableCell>{row.kind}</TableCell>
                  <TableCell>{truncate(row.org_name, 28)}</TableCell>
                  <TableCell className="text-muted-foreground">{truncate(row.detail, 64)}</TableCell>
                  <TableCell className="text-right">
                    <div className="flex flex-wrap justify-end gap-1">
                      {row.invoice_id ? (
                        <Button asChild variant="outline" size="sm" className="h-7">
                          <Link to="/billing/invoices?tab=invoices">Invoice</Link>
                        </Button>
                      ) : null}
                      {row.refund_review_id ? (
                        <Button asChild variant="outline" size="sm" className="h-7">
                          <Link to="/billing/refunds">Refund</Link>
                        </Button>
                      ) : null}
                      {row.org_id ? (
                        <Button asChild variant="outline" size="sm" className="h-7">
                          <Link
                            to="/organisations/all-users"
                            onClick={() => localStorage.setItem('voxbulk_admin_selected_org_id', row.org_id)}
                          >
                            OCC
                          </Link>
                        </Button>
                      ) : null}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
          </TableBody>
        </StripeTable>
      </Panel>
    </div>
  )
}
