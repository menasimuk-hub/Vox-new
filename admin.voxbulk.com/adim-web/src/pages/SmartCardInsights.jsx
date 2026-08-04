import React, { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { BarChart3, Flame, QrCode, RefreshCw, Users } from 'lucide-react'
import { apiFetch } from '../lib/api'
import { Button } from '@/components/ui/Button'
import { Panel } from '@/components/ui/Card'
import { KpiCard } from '@/components/ui/KpiCard'
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

function fmtWhen(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString()
}

export default function SmartCardInsights() {
  const [overview, setOverview] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setError('')
    const ov = await apiFetch('/admin/smart-card/overview')
    setOverview(ov || null)
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      try {
        await load()
      } catch (e) {
        if (!cancelled) setError(e?.message || 'Could not load Smart Card insights')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [load])

  const subs = overview?.subscriptions || []

  return (
    <div className="ds-scope space-y-4">
      <div className="pageTop">
        <div>
          <h1>Smart Card QR insights</h1>
          <p>Platform scans, sessions, leads, and seat subscription expiry.</p>
        </div>
        <div className="actions">
          <Button asChild variant="outline" size="sm" className="h-8">
            <Link to="/billing/products?filter=smart_card">Products</Link>
          </Button>
          <Button asChild variant="outline" size="sm" className="h-8">
            <Link to="/pricing/packages?service=smart_card">Pricing</Link>
          </Button>
          <Button type="button" size="sm" className="h-8" onClick={() => load()} disabled={loading}>
            <RefreshCw className={loading ? 'h-3.5 w-3.5 animate-spin' : 'h-3.5 w-3.5'} />
            Refresh
          </Button>
        </div>
      </div>

      {error ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      {loading && !overview ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            <KpiCard label="Scans" value={overview?.scans ?? '—'} icon={QrCode} tone="info" />
            <KpiCard label="Sessions" value={overview?.sessions ?? '—'} icon={BarChart3} tone="info" />
            <KpiCard
              label="Completed"
              value={overview?.sessions_completed ?? 0}
              hint={`${overview?.sessions ?? 0} total sessions`}
              icon={BarChart3}
              tone="success"
            />
            <KpiCard label="Leads" value={overview?.leads ?? '—'} icon={Users} tone="info" />
            <KpiCard label="Hot leads" value={overview?.hot_leads ?? 0} icon={Flame} tone="warning" />
            <KpiCard
              label="Companies / reps"
              value={`${overview?.companies ?? 0} / ${overview?.representatives ?? 0}`}
              icon={Users}
              tone="primary"
            />
          </div>

          <Panel
            title="Seat subscriptions"
            subtitle="Shows when seats expire after purchase (`period_end`)."
            action={<Pill tone="info">{subs.length}</Pill>}
            bodyClassName="p-0"
          >
            <StripeTable>
              <TableHeader>
                <TableRow>
                  <TableHead>Org</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Seats</TableHead>
                  <TableHead>Expires</TableHead>
                  <TableHead>Created</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading ? (
                  <TableLoading colSpan={5} />
                ) : subs.length === 0 ? (
                  <TableEmpty colSpan={5}>No Smart Card seat subscriptions yet.</TableEmpty>
                ) : (
                  subs.map((s) => (
                    <TableRow key={s.id}>
                      <TableCell>
                        <Link to={`/organisations/${s.org_id}`} className="text-primary underline-offset-4 hover:underline">
                          {s.org_id}
                        </Link>
                      </TableCell>
                      <TableCell>
                        <Pill tone={s.expired ? 'danger' : 'neutral'}>{s.status}</Pill>
                        {s.expired ? <span className="ml-1 text-[11px] text-muted-foreground">expired</span> : null}
                      </TableCell>
                      <TableCell>{s.seat_quantity}</TableCell>
                      <TableCell>{fmtWhen(s.period_end)}</TableCell>
                      <TableCell>{fmtWhen(s.created_at)}</TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </StripeTable>
          </Panel>
        </>
      )}
    </div>
  )
}
