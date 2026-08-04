import React, { useCallback, useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { adminOrderViewPath } from '../lib/serviceOrderAdmin'
import { Button } from '@/components/ui/Button'
import { Panel } from '@/components/ui/Card'
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

export default function ServiceOrdersAdmin() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [orders, setOrders] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busyId, setBusyId] = useState('')

  const load = useCallback(async () => {
    setError('')
    const rows = await apiFetch('/admin/platform-services/orders?payment_status=pending_approval')
    setOrders(Array.isArray(rows) ? rows : [])
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      try {
        await load()
      } catch (e) {
        if (!cancelled) setError(e?.message || 'Could not load orders')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [load])

  useEffect(() => {
    const orderId = searchParams.get('order')
    if (!orderId) return
    let cancelled = false
    ;(async () => {
      try {
        const row = await apiFetch(`/admin/platform-services/orders/${encodeURIComponent(orderId)}`)
        if (!cancelled) navigate(adminOrderViewPath(row), { replace: true })
      } catch (e) {
        if (!cancelled) setError(e?.message || 'Could not open order detail')
      }
    })()
    return () => {
      cancelled = true
    }
  }, [searchParams, navigate])

  const approve = async (id) => {
    setBusyId(id)
    setError('')
    try {
      await apiFetch(`/admin/platform-services/orders/${encodeURIComponent(id)}/approve-payment`, {
        method: 'POST',
        body: JSON.stringify({ note: 'Cash payment approved' }),
      })
      await load()
    } catch (e) {
      setError(e?.message || 'Approve failed')
    } finally {
      setBusyId('')
    }
  }

  const reject = async (id) => {
    setBusyId(id)
    setError('')
    try {
      await apiFetch(`/admin/platform-services/orders/${encodeURIComponent(id)}/reject-payment`, {
        method: 'POST',
        body: JSON.stringify({ note: 'Cash payment rejected' }),
      })
      await load()
    } catch (e) {
      setError(e?.message || 'Reject failed')
    } finally {
      setBusyId('')
    }
  }

  return (
    <div className="ds-scope space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="min-w-0">
          <h1 className="text-[15px] font-semibold leading-tight text-foreground">Service orders — cash approval</h1>
          <p className="text-[11px] leading-tight text-muted-foreground">
            Approve survey and interview orders after the customer marks cash payment.
          </p>
        </div>
        <div className="ml-auto">
          <Button type="button" variant="outline" size="sm" className="h-8" onClick={load}>
            Refresh
          </Button>
        </div>
      </div>

      {error ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <Panel title="Pending payment approval" subtitle="Cash orders waiting for admin decision.">
        <StripeTable>
          <TableHeader>
            <TableRow>
              <TableHead>Title</TableHead>
              <TableHead>Service</TableHead>
              <TableHead>Contacts</TableHead>
              <TableHead>Total</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? <TableLoading colSpan={6} /> : null}
            {!loading && !orders.length ? (
              <TableEmpty colSpan={6}>No orders waiting for approval.</TableEmpty>
            ) : null}
            {!loading &&
              orders.map((o) => (
                <TableRow key={o.id}>
                  <TableCell>{o.title}</TableCell>
                  <TableCell>{o.service_code}</TableCell>
                  <TableCell>{o.recipient_count}</TableCell>
                  <TableCell>{o.quote_total_gbp}</TableCell>
                  <TableCell>{o.payment_status}</TableCell>
                  <TableCell className="text-right">
                    <div className="flex flex-wrap justify-end gap-1 whitespace-nowrap">
                      <Button
                        type="button"
                        size="sm"
                        className="h-7"
                        disabled={busyId === o.id}
                        onClick={() => approve(o.id)}
                      >
                        Approve
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="h-7"
                        disabled={busyId === o.id}
                        onClick={() => reject(o.id)}
                      >
                        Reject
                      </Button>
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
