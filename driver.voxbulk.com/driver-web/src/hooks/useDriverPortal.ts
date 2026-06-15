import { useCallback, useEffect, useState } from 'react'
import { toast } from 'sonner'
import { apiFetch } from '@/lib/api'
import { useLocalState } from '@/lib/app-prefs'

export type DStatus = 'incoming' | 'collected' | 'onway' | 'arrived' | 'delivered' | 'cancelled'

export type DOrder = {
  id: string
  assignmentId: string
  number: string
  status: DStatus
  apiStatus: string
  restaurantName: string
  restaurantAddr: string
  customerName: string
  customerAddr: string
  total: number
  createdAt: number
  deliveredAt?: number
}

export type DriverSettings = { name: string; mobile: string; vehicle: 'bike' | 'ebike' | 'cycle' | 'car' }

function shekel(agorot: number) {
  return Number(agorot || 0) / 100
}

function mapAssignment(row: any, lang: 'en' | 'ar'): DOrder {
  const st = String(row.status || '')
  let status: DStatus = 'collected'
  if (['assigned', 'unassigned'].includes(st)) status = 'incoming'
  else if (st === 'accepted') status = 'collected'
  else if (st === 'on_route') status = 'onway'
  else if (st === 'delivered') status = 'delivered'
  else if (['rejected', 'failed', 'timed_out'].includes(st)) status = 'cancelled'

  const pickup = row.pickup || {}
  const dropoff = row.dropoff || {}
  const order = row.order || {}
  const total = shekel(order.total_agorot || order.subtotal_agorot || 0)

  return {
    id: row.order_id || row.id,
    assignmentId: row.id,
    number: `#${String(row.order_id || row.id).slice(0, 8).toUpperCase()}`,
    status,
    apiStatus: st,
    restaurantName: lang === 'ar' ? pickup.restaurant_name_ar || pickup.restaurant_name_en || '—' : pickup.restaurant_name_en || pickup.restaurant_name_ar || '—',
    restaurantAddr: pickup.address_text || '—',
    customerName: dropoff.customer_name || '—',
    customerAddr: dropoff.address_text || '—',
    total,
    createdAt: row.assigned_at ? new Date(row.assigned_at).getTime() : Date.now(),
    deliveredAt: row.delivered_at ? new Date(row.delivered_at).getTime() : undefined,
  }
}

export function useDriverPortal(lang: 'en' | 'ar') {
  const [orders, setOrders] = useState<DOrder[]>([])
  const [settings, setSettings] = useLocalState<DriverSettings>('driver:settings', {
    name: 'Driver',
    mobile: '',
    vehicle: 'bike',
  })
  const [loading, setLoading] = useState(true)
  const [incoming, setIncoming] = useState<DOrder | null>(null)

  const refresh = useCallback(async () => {
    const [me, rows, notifications] = await Promise.all([
      apiFetch('/abuu/driver/me'),
      apiFetch('/abuu/driver/assignments'),
      apiFetch('/abuu/driver/notifications?unread_only=true').catch(() => []),
    ])
    setSettings((prev) => ({
      ...prev,
      name: me.name || prev.name,
      mobile: me.phone || prev.mobile,
    }))
    const mapped = (rows || []).map((r: any) => mapAssignment(r, lang))
    setOrders(mapped)
    const inc = mapped.find((o) => o.status === 'incoming')
    setIncoming((prev) => {
      if (inc) return inc
      if (prev && mapped.some((o) => o.assignmentId === prev.assignmentId && o.status === 'incoming')) return prev
      return null
    })
    for (const n of notifications || []) {
      if (n.kind === 'order_ready') {
        toast.info(n.title || (lang === 'ar' ? 'طلب جديد' : 'New delivery'), { description: n.body })
        if (n.id) {
          apiFetch(`/abuu/driver/notifications/${n.id}/read`, { method: 'PATCH', body: '{}' }).catch(() => {})
        }
      }
    }
  }, [lang, setSettings])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        await refresh()
      } catch (e: any) {
        if (!cancelled) toast.error(e?.message || 'Load failed')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    const timer = setInterval(() => refresh().catch(() => {}), 10000)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [refresh])

  const acceptIncoming = useCallback(async () => {
    if (!incoming) return
    try {
      await apiFetch(`/abuu/driver/assignments/${incoming.assignmentId}`, {
        method: 'PATCH',
        body: JSON.stringify({ status: 'accepted' }),
      })
      setIncoming(null)
      await refresh()
      toast.success(lang === 'ar' ? 'تم الاستلام' : 'Collected')
    } catch (e: any) {
      toast.error(e?.message || 'Update failed')
    }
  }, [incoming, refresh, lang])

  const rejectIncoming = useCallback(async () => {
    if (!incoming) return
    try {
      await apiFetch(`/abuu/driver/assignments/${incoming.assignmentId}`, {
        method: 'PATCH',
        body: JSON.stringify({ status: 'rejected' }),
      })
      setIncoming(null)
      await refresh()
    } catch (e: any) {
      toast.error(e?.message || 'Update failed')
    }
  }, [incoming, refresh])

  const notifyCustomer = useCallback(
    async (assignmentId: string) => {
      try {
        await apiFetch(`/abuu/driver/assignments/${assignmentId}/notify-customer`, {
          method: 'POST',
          body: '{}',
        })
        toast.success(lang === 'ar' ? 'تم إعلام العميل على واتساب' : 'Customer notified on WhatsApp')
      } catch (e: any) {
        toast.error(e?.message || 'Notify failed')
      }
    },
    [lang],
  )

  const advance = useCallback(
    async (id: string) => {
      const order = orders.find((o) => o.id === id)
      if (!order) return
      try {
        if (order.status === 'collected') {
          await apiFetch(`/abuu/driver/assignments/${order.assignmentId}`, {
            method: 'PATCH',
            body: JSON.stringify({ status: 'picked_up' }),
          })
        } else if (order.status === 'onway') {
          setOrders((os) => os.map((o) => (o.id === id ? { ...o, status: 'arrived' as DStatus } : o)))
          return
        } else if (order.status === 'arrived') {
          await apiFetch(`/abuu/driver/assignments/${order.assignmentId}`, {
            method: 'PATCH',
            body: JSON.stringify({ status: 'delivered' }),
          })
        } else {
          return
        }
        await refresh()
      } catch (e: any) {
        toast.error(e?.message || 'Update failed')
      }
    },
    [orders, refresh],
  )

  return { orders, settings, setSettings, loading, incoming, refresh, acceptIncoming, rejectIncoming, advance, notifyCustomer }
}
