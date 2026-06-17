import { useCallback, useEffect, useState } from 'react'
import { toast } from 'sonner'
import { apiFetch } from '@/lib/api'
import { useLocalState } from '@/lib/app-prefs'

export type UiStatus = 'new' | 'preparing' | 'ready' | 'collected' | 'with_driver'

export type UiOrderItem = {
  id: string
  nameEn: string
  nameAr: string
  qty: number
  price: number
  outOfStock?: boolean
  substitutionStatus?: string | null
}

export type UiOrder = {
  id: string
  number: string
  status: UiStatus
  items: UiOrderItem[]
  createdAt: number
  collectedAt?: number
  outOfStockCount: number
  substitutionPending: boolean
  customerPhone?: string
  customerName?: string
  deliveryAddress?: string
  notes?: string
  allergyNote?: string
}

export type UiMenuItem = {
  id: string
  nameEn: string
  nameAr: string
  price: number
  icon: string
  descEn: string
  descAr: string
  recipeEn: string
  recipeAr: string
  allergy: string
  diet: string
  itemType: string
  hidden: boolean
  categoryId: string
}

export type UiCategory = { id: string; nameEn: string; nameAr: string; items: UiMenuItem[] }

export type UiOffer = {
  id: string
  titleEn: string
  titleAr: string
  items: { itemId: string; qty: number }[]
  originalPrice: number
  offerPrice: number
  discountPercentage: number
  createdAt: number
}

const ITEM_ICONS: Record<string, string> = {
  chicken: '🍗',
  fish: '🐟',
  meat: '🥩',
  salad: '🥗',
  drinks: '🥤',
  drink: '🥤',
  dessert: '🍰',
  food: '🍽️',
  addon: '➕',
  sides: '🍟',
}

export function shekel(agorot: number) {
  return Number(agorot || 0) / 100
}

export function formatMoney(amount: number) {
  return `₪${amount.toFixed(2)}`
}

function mapApiStatus(status: string): UiStatus {
  if (status === 'sent_to_restaurant' || status === 'confirmed' || status === 'paid') return 'new'
  if (status === 'preparing') return 'preparing'
  if (status === 'ready') return 'ready'
  if (['assigned_to_driver', 'picked_up'].includes(status)) return 'with_driver'
  if (status === 'delivered') return 'collected'
  return 'new'
}

function parseTagJson(raw: unknown, opts?: { hideHalal?: boolean }): string {
  const hideHalal = opts?.hideHalal !== false
  const format = (tags: string[]) => {
    const cleaned = hideHalal ? tags.filter((t) => t !== 'halal') : tags
    return cleaned.length ? cleaned.join(', ') : '—'
  }
  if (!raw) return '—'
  if (Array.isArray(raw)) return format(raw.map(String))
  if (typeof raw === 'string') {
    try {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed)) return format(parsed.map(String))
    } catch {
      return raw || '—'
    }
  }
  return '—'
}

function parseRecipeJson(raw: unknown, lang: 'en' | 'ar'): string {
  if (!raw || typeof raw !== 'string') return ''
  try {
    const parsed = JSON.parse(raw)
    if (parsed && typeof parsed === 'object') {
      const key = lang === 'ar' ? 'ingredients_ar' : 'ingredients_en'
      const legacy = parsed.ingredients
      const value = parsed[key] || legacy
      return typeof value === 'string' ? value : ''
    }
  } catch {
    return raw
  }
  return ''
}

function mapMenuItem(item: any, categoryId: string): UiMenuItem {
  return {
    id: item.id,
    nameEn: item.name_en,
    nameAr: item.name_ar,
    price: shekel(item.price_agorot),
    icon: ITEM_ICONS[item.item_type] || '🍽️',
    descEn: item.description_en || '',
    descAr: item.description_ar || '',
    recipeEn: parseRecipeJson(item.ingredients_json, 'en'),
    recipeAr: parseRecipeJson(item.ingredients_json, 'ar'),
    allergy: parseTagJson(item.allergen_tags_json),
    diet: parseTagJson(item.dietary_tags_json),
    itemType: item.item_type || 'meal',
    hidden: !item.is_available,
    categoryId,
  }
}

function flattenMenu(categories: any[]): UiCategory[] {
  const rows: UiCategory[] = []
  for (const cat of categories || []) {
    const items: UiMenuItem[] = []
    for (const item of cat.items || []) {
      items.push(mapMenuItem(item, cat.id))
    }
    for (const sub of cat.subcategories || []) {
      for (const item of sub.items || []) {
        items.push(mapMenuItem(item, sub.id))
      }
    }
    rows.push({ id: cat.id, nameEn: cat.name_en, nameAr: cat.name_ar, items })
  }
  return rows
}

function mapOrderDetail(row: any): UiOrder {
  const items: UiOrderItem[] = (row.items || []).map((it: any) => ({
    id: it.id || it.menu_item_id,
    nameEn: it.name_en || '',
    nameAr: it.name_ar || '',
    qty: it.quantity || 1,
    price: shekel(it.unit_price_agorot || it.line_total_agorot),
    outOfStock: Boolean(it.unavailable),
    substitutionStatus: it.substitution_status || null,
  }))
  const status = mapApiStatus(row.status)
  return {
    id: row.id,
    number: `#${String(row.id).slice(0, 8).toUpperCase()}`,
    status,
    items,
    createdAt: row.created_at ? new Date(row.created_at).getTime() : Date.now(),
    collectedAt: status === 'collected' && row.updated_at ? new Date(row.updated_at).getTime() : undefined,
    outOfStockCount: items.filter((i) => i.outOfStock && i.substitutionStatus === 'pending_customer').length,
    substitutionPending: Boolean(row.substitution_pending),
    customerPhone: row.customer?.phone || '',
    customerName: row.customer?.name || '',
    deliveryAddress: row.delivery_address?.address_text || '',
    notes: row.notes || '',
    allergyNote: row.allergy_note || '',
  }
}

export function useRestaurantPortal(lang: 'en' | 'ar') {
  const [orders, setOrders] = useState<UiOrder[]>([])
  const [cats, setCats] = useState<UiCategory[]>([])
  const [offers, setOffers] = useState<UiOffer[]>([])
  const [settings, setSettings] = useLocalState('restaurant:settings', {
    name: 'My Restaurant',
    mobile: '',
    address: '',
    hours: {},
  })
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    const [me, orderRows, menuRows, offerRows, notifications] = await Promise.all([
      apiFetch('/abuu/restaurant/me'),
      apiFetch('/abuu/restaurant/orders'),
      apiFetch('/abuu/restaurant/menu'),
      apiFetch('/abuu/restaurant/offers'),
      apiFetch('/abuu/restaurant/notifications?unread_only=true').catch(() => []),
    ])
    setSettings((prev) => ({
      ...prev,
      name: lang === 'ar' ? me.name_ar || me.name_en : me.name_en || me.name_ar,
      mobile: me.phone || prev.mobile,
      address: me.address_text || prev.address,
    }))
    setCats(flattenMenu(menuRows))
    setOffers(
      (offerRows || []).map((o: any) => ({
        id: o.id,
        titleEn: o.title_en,
        titleAr: o.title_ar,
        items: (o.items || []).map((it: any) => ({ itemId: it.menu_item_id, qty: it.quantity || 1 })),
        originalPrice: shekel(o.original_price_agorot),
        offerPrice: shekel(o.offer_price_agorot),
        discountPercentage:
          o.original_price_agorot > o.offer_price_agorot
            ? Math.round(((o.original_price_agorot - o.offer_price_agorot) / o.original_price_agorot) * 100)
            : 0,
        createdAt: o.created_at ? new Date(o.created_at).getTime() : Date.now(),
      })),
    )
    const activeIds = (orderRows || [])
      .filter((r: any) => !['delivered', 'cancelled', 'draft'].includes(r.status))
      .map((r: any) => r.id)
    const details = await Promise.all(
      activeIds.map((id: string) => apiFetch(`/abuu/restaurant/orders/${id}`).catch(() => null)),
    )
    const mapped = details.filter(Boolean).map(mapOrderDetail)
    const history = (orderRows || [])
      .filter((r: any) => r.status === 'delivered')
      .map((r: any) => ({
        id: r.id,
        number: `#${String(r.id).slice(0, 8).toUpperCase()}`,
        status: 'collected' as UiStatus,
        items: [],
        createdAt: r.created_at ? new Date(r.created_at).getTime() : Date.now(),
        collectedAt: r.updated_at ? new Date(r.updated_at).getTime() : undefined,
        outOfStockCount: 0,
        substitutionPending: false,
      }))
    setOrders([...mapped, ...history])

    for (const n of notifications || []) {
      if (n.kind === 'order_paid' || n.kind === 'substitution_resolved') {
        toast.info(n.title || (lang === 'ar' ? 'تحديث طلب' : 'Order update'), { description: n.body })
        if (n.id) {
          apiFetch(`/abuu/restaurant/notifications/${n.id}/read`, { method: 'PATCH', body: '{}' }).catch(() => {})
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
    const timer = setInterval(() => {
      refresh().catch(() => {})
    }, 12000)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [refresh])

  const changeStatus = useCallback(
    async (id: string, dir: 1 | -1) => {
      const order = orders.find((o) => o.id === id)
      if (!order) return
      if (order.substitutionPending && dir === 1) {
        toast.error(lang === 'ar' ? 'انتظر رد العميل على البديل' : 'Wait for customer substitution reply')
        return
      }
      const flow: UiStatus[] = ['new', 'preparing', 'ready', 'collected']
      const idx = flow.indexOf(order.status === 'with_driver' ? 'ready' : order.status)
      const next = flow[Math.max(0, Math.min(flow.length - 1, idx + dir))]
      if (next === order.status || order.status === 'with_driver') return
      try {
        if (order.status === 'new' && next === 'preparing') {
          await apiFetch(`/abuu/restaurant/orders/${id}/preparing`, { method: 'POST', body: '{}' })
        } else if (order.status === 'preparing' && next === 'ready') {
          await apiFetch(`/abuu/restaurant/orders/${id}/ready`, { method: 'POST', body: '{}' })
        } else {
          return
        }
        await refresh()
        toast.success(lang === 'ar' ? 'تم تحديث الطلب' : 'Order updated')
      } catch (e: any) {
        toast.error(e?.message || 'Update failed')
      }
    },
    [orders, refresh, lang],
  )

  const markOOS = useCallback(
    async (orderId: string, itemId: string) => {
      try {
        await apiFetch(`/abuu/restaurant/orders/${orderId}/items/${itemId}/unavailable`, {
          method: 'POST',
          body: '{}',
        })
        await refresh()
        toast.success(lang === 'ar' ? 'تم إعلام العميل' : 'Customer notified on WhatsApp')
      } catch (e: any) {
        toast.error(e?.message || 'Update failed')
      }
    },
    [refresh, lang],
  )

  return {
    orders,
    setOrders,
    cats,
    setCats,
    offers,
    setOffers,
    settings,
    setSettings,
    loading,
    refresh,
    changeStatus,
    markOOS,
    formatMoney,
  }
}
