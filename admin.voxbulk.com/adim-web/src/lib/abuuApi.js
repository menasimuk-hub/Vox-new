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

export function assignAbuuDriver(orderId, driverId) {
  return apiFetch(`/admin/abuu/orders/${orderId}/assignments`, {
    method: 'POST',
    body: JSON.stringify({ driver_id: driverId }),
  })
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
