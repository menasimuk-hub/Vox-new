import { resolveApiUrl } from './api'
import { readAdminAccessToken, readSharedAccessToken } from './sessionStorage'

async function resolveAdminBearerToken() {
  if (typeof window === 'undefined') return ''
  return readAdminAccessToken() || readSharedAccessToken()
}

export async function downloadAdminCsv(path, filename) {
  const token = await resolveAdminBearerToken()
  const url = resolveApiUrl(path)
  const res = await fetch(url, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!res.ok) {
    let detail = 'Export failed'
    try {
      const data = await res.json()
      detail = data?.detail || detail
    } catch {
      /* ignore */
    }
    throw new Error(detail)
  }
  const blob = await res.blob()
  const objectUrl = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = objectUrl
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(objectUrl)
}
