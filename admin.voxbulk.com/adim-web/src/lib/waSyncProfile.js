const STORAGE_KEY = 'wa_templates_sync_profile_id'

export function getStoredSyncProfileId() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw && String(raw).trim() ? String(raw).trim() : null
  } catch {
    return null
  }
}

export function setStoredSyncProfileId(profileId) {
  try {
    if (!profileId) {
      localStorage.removeItem(STORAGE_KEY)
      return
    }
    localStorage.setItem(STORAGE_KEY, String(profileId))
  } catch {
    /* ignore */
  }
}

export async function fetchWaSyncProfileOptions(apiFetch, { serviceCode = 'survey' } = {}) {
  const data = await apiFetch(
    `/admin/connection-profiles/whatsapp-sync-options?service_code=${encodeURIComponent(serviceCode)}`,
    { quietNetworkHint: true },
  )
  const items = Array.isArray(data?.items) ? data.items : []
  const defaultId = data?.default_profile_id || items.find((i) => i.is_default)?.id || items[0]?.id || null
  return { items, defaultId }
}

export function resolveSelectedSyncProfile(items, selectedId, defaultId) {
  const list = Array.isArray(items) ? items : []
  const wanted = selectedId || defaultId
  const found = list.find((item) => String(item.id) === String(wanted))
  if (found) return found
  return list.find((item) => item.is_default) || list[0] || null
}

export function syncProfilePayload(profile) {
  const id = profile?.id
  return id ? { connection_profile_id: id } : {}
}

export function syncProfileActionLabel(profile, verb = 'Sync') {
  if (!profile) return verb
  const provider = String(profile.provider || '').toLowerCase()
  const phone = profile.whatsapp_from || profile.waba_id || ''
  if (provider === 'meta') {
    return phone ? `${verb} to Meta ${phone}` : `${verb} to Meta`
  }
  if (provider === 'telnyx') {
    return phone ? `${verb} to Telnyx ${phone}` : `${verb} to Telnyx`
  }
  return profile.label ? `${verb} — ${profile.label}` : verb
}
