import { apiFetch } from './api'

export function fetchAbuuHealth() {
  return apiFetch('/admin/abuu/health')
}

export function fetchAbuuRestaurants(params = {}) {
  const q = new URLSearchParams()
  if (params.limit) q.set('limit', String(params.limit))
  if (params.offset) q.set('offset', String(params.offset))
  if (params.is_available != null) q.set('is_available', String(params.is_available))
  const suffix = q.toString() ? `?${q}` : ''
  return apiFetch(`/admin/abuu/restaurants${suffix}`)
}

export function fetchAbuuDrivers(params = {}) {
  const q = new URLSearchParams({ limit: String(params.limit || 100) })
  return apiFetch(`/admin/abuu/drivers?${q}`)
}

export function createAbuuDriver(payload) {
  return apiFetch('/admin/abuu/drivers', { method: 'POST', body: JSON.stringify(payload) })
}

export function patchAbuuDriver(driverId, payload) {
  return apiFetch(`/admin/abuu/drivers/${driverId}`, { method: 'PATCH', body: JSON.stringify(payload) })
}

export function deleteAbuuDriver(driverId) {
  return apiFetch(`/admin/abuu/drivers/${driverId}`, { method: 'DELETE' })
}

export function patchAbuuRestaurant(restaurantId, payload) {
  return apiFetch(`/admin/abuu/restaurants/${restaurantId}`, { method: 'PATCH', body: JSON.stringify(payload) })
}

export function fetchAbuuCustomers(params = {}) {
  const q = new URLSearchParams({ limit: String(params.limit || 100) })
  return apiFetch(`/admin/abuu/customers?${q}`)
}

export function fetchAbuuCustomerHistory(customerId) {
  return apiFetch(`/admin/abuu/customers/${customerId}/history`)
}

export function fetchAbuuOrders(params = {}) {
  const q = new URLSearchParams({ limit: String(params.limit || 100) })
  if (params.status) q.set('status', params.status)
  if (params.restaurant_id) q.set('restaurant_id', params.restaurant_id)
  return apiFetch(`/admin/abuu/orders?${q}`)
}

export function fetchAbuuOrder(orderId) {
  return apiFetch(`/admin/abuu/orders/${orderId}`)
}

export function markAbuuOrderPaid(orderId) {
  return apiFetch(`/admin/abuu/orders/${orderId}/mark-paid`, { method: 'POST', body: '{}' })
}

export function cancelAbuuPaidOrder(orderId, reason = '') {
  return apiFetch(`/admin/abuu/orders/${orderId}/cancel-paid`, {
    method: 'POST',
    body: JSON.stringify({ reason }),
  })
}

export function markAbuuRefundProcessed(orderId) {
  return apiFetch(`/admin/abuu/orders/${orderId}/refund-processed`, { method: 'POST', body: '{}' })
}

export function recoverAbuuOrder(orderId, payload) {
  return apiFetch(`/admin/abuu/orders/${orderId}/recover`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function fetchAbuuOrderEvents(orderId) {
  return apiFetch(`/admin/abuu/orders/${orderId}/events`)
}

export function fetchAbuuExternalEvents(params = {}) {
  const q = new URLSearchParams({ limit: String(params.limit || 100) })
  if (params.status) q.set('status', params.status)
  if (params.event_type) q.set('event_type', params.event_type)
  if (params.order_id) q.set('order_id', params.order_id)
  return apiFetch(`/admin/abuu/events?${q}`)
}

export function assignAbuuDriver(orderId, driverId) {
  return apiFetch(`/admin/abuu/orders/${orderId}/assignments`, {
    method: 'POST',
    body: JSON.stringify({ driver_id: driverId }),
  })
}

export function timeoutAbuuAssignment(assignmentId) {
  return apiFetch(`/admin/abuu/assignments/${assignmentId}/timeout`, { method: 'POST', body: '{}' })
}

export function fetchAbuuMenuCategories(restaurantId) {
  return apiFetch(`/admin/abuu/restaurants/${restaurantId}/menu-categories`)
}

export function createAbuuMenuCategory(restaurantId, payload) {
  return apiFetch(`/admin/abuu/restaurants/${restaurantId}/menu-categories`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function createAbuuMenuItem(categoryId, payload) {
  return apiFetch(`/admin/abuu/menu-categories/${categoryId}/items`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function patchAbuuMenuItem(itemId, payload) {
  return apiFetch(`/admin/abuu/menu-items/${itemId}`, { method: 'PATCH', body: JSON.stringify(payload) })
}

export function deleteAbuuMenuItem(itemId) {
  return apiFetch(`/admin/abuu/menu-items/${itemId}`, { method: 'DELETE' })
}

export async function uploadAbuuMenuItemPhoto(itemId, file) {
  const form = new FormData()
  form.append('file', file)
  const token = localStorage.getItem('access_token')
  const resp = await fetch(`/api/admin/abuu/menu-items/${itemId}/photo`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  })
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}))
    throw new Error(err.detail || 'Upload failed')
  }
  return resp.json()
}
