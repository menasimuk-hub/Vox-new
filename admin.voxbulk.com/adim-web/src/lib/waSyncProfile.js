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

export async function fetchProfileTemplateSummary(apiFetch, profileId, { serviceCode = 'survey', timeoutMs = 120000 } = {}) {
  const id = String(profileId || '').trim()
  if (!id) throw new Error('Profile id is required')
  return apiFetch(
    `/admin/connection-profiles/${encodeURIComponent(id)}/whatsapp-template-summary?service_code=${encodeURIComponent(serviceCode)}`,
    { quietNetworkHint: true, timeoutMs },
  )
}

export async function fetchProfileTemplateSummariesBatch(
  apiFetch,
  profileIds,
  { serviceCode = 'survey', timeoutMs = 180000 } = {},
) {
  const ids = (Array.isArray(profileIds) ? profileIds : []).map((x) => String(x).trim()).filter(Boolean)
  if (!ids.length) return { ok: true, items: [] }
  return apiFetch(
    `/admin/connection-profiles/whatsapp-template-summaries?profile_ids=${encodeURIComponent(ids.join(','))}&service_code=${encodeURIComponent(serviceCode)}`,
    { quietNetworkHint: true, timeoutMs },
  )
}

export function resolveBackupSyncProfile(items, primaryProfile) {
  const list = Array.isArray(items) ? items : []
  const primaryId = primaryProfile?.id
  return (
    list.find((item) => String(item.provider || '').toLowerCase() === 'telnyx' && String(item.id) !== String(primaryId)) ||
    list.find((item) => !item.is_default && String(item.id) !== String(primaryId)) ||
    null
  )
}

export function resolvePrimarySyncProfile(items) {
  const list = Array.isArray(items) ? items : []
  return list.find((item) => item.is_default) || list.find((item) => String(item.provider || '').toLowerCase() === 'meta') || list[0] || null
}

export function resolveDualSyncProfileIds(items, { primaryProfile = null, backupProfile = null } = {}) {
  const primary = primaryProfile || resolvePrimarySyncProfile(items)
  const backup = backupProfile || resolveBackupSyncProfile(items, primary)
  const ids = []
  if (primary?.id) ids.push(String(primary.id))
  if (backup?.id && !ids.includes(String(backup.id))) ids.push(String(backup.id))
  return { primary, backup, ids }
}

export const EMPTY_PROFILE_SUMMARY_ROW = {
  loading: false,
  error: null,
  summary: null,
  fetchedAt: null,
}
