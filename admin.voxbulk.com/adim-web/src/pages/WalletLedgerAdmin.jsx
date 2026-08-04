import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../lib/api'
import { dateText, money, truncate } from '../lib/billingAdminUtils'
import { Button } from '@/components/ui/Button'
import { Panel } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
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

const selectClass =
  'flex h-8 min-w-[140px] rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring'

export default function WalletLedgerAdmin() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [filters, setFilters] = useState({ search: '', kind: '', direction: '' })

  const load = useCallback(async () => {
    setError('')
    const params = new URLSearchParams({ limit: '250' })
    if (filters.search.trim()) params.set('search', filters.search.trim())
    if (filters.kind) params.set('kind', filters.kind)
    if (filters.direction) params.set('direction', filters.direction)
    const res = await apiFetch(`/admin/billing/wallet-ledger?${params.toString()}`)
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

  useEffect(() => {
    const timer = window.setTimeout(() => load().catch(() => {}), 250)
    return () => window.clearTimeout(timer)
  }, [filters, load])

  const liability = useMemo(() => rows.reduce((sum, r) => sum + Number(r.signed_amount_minor || 0), 0), [rows])

  return (
    <div className="ds-scope space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="min-w-0">
          <h1 className="text-[15px] font-semibold leading-tight text-foreground">Wallet ledger</h1>
          <p className="text-[11px] leading-tight text-muted-foreground">
            All signed wallet balance changes with running balance after each entry.
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

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        <KpiCard label="Entries shown" value={rows.length} tone="success" index={0} />
      </div>

      <Panel title="Ledger" subtitle="Search by organisation, reference, or note." bodyClassName="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <Input
            className="h-8 max-w-xs"
            placeholder="Search org, ref, note…"
            value={filters.search}
            onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value }))}
          />
          <select
            className={selectClass}
            value={filters.direction}
            onChange={(e) => setFilters((f) => ({ ...f, direction: e.target.value }))}
          >
            <option value="">All directions</option>
            <option value="credit">Credit</option>
            <option value="debit">Debit</option>
          </select>
          <Input
            className="h-8 max-w-[140px]"
            placeholder="Kind"
            value={filters.kind}
            onChange={(e) => setFilters((f) => ({ ...f, kind: e.target.value }))}
          />
        </div>

        <StripeTable>
          <TableHeader>
            <TableRow>
              <TableHead>When</TableHead>
              <TableHead>Organisation</TableHead>
              <TableHead>Kind</TableHead>
              <TableHead>Direction</TableHead>
              <TableHead>Amount</TableHead>
              <TableHead>Balance after</TableHead>
              <TableHead>Reference</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? <TableLoading colSpan={7} /> : null}
            {!loading && !rows.length ? <TableEmpty colSpan={7}>No ledger entries.</TableEmpty> : null}
            {!loading &&
              rows.map((row) => (
                <TableRow key={row.id}>
                  <TableCell className="text-muted-foreground">{dateText(row.created_at)}</TableCell>
                  <TableCell>
                    <div className="flex flex-wrap items-center gap-2">
                      <strong className="font-medium">{truncate(row.org_name, 22)}</strong>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="h-7"
                        onClick={() => {
                          localStorage.setItem('voxbulk_admin_selected_org_id', row.org_id)
                          window.location.assign('/organisations/all-users')
                        }}
                      >
                        OCC
                      </Button>
                    </div>
                  </TableCell>
                  <TableCell>{row.kind}</TableCell>
                  <TableCell>{row.direction}</TableCell>
                  <TableCell>
                    <strong className="font-medium">
                      {row.amount_display || money(row.amount_minor, row.currency)}
                    </strong>
                  </TableCell>
                  <TableCell>{row.balance_after_display || money(row.balance_after_minor, row.currency)}</TableCell>
                  <TableCell className="text-muted-foreground">
                    {truncate(row.provider_reference || row.description, 28)}
                  </TableCell>
                </TableRow>
              ))}
          </TableBody>
        </StripeTable>
      </Panel>
    </div>
  )
}
