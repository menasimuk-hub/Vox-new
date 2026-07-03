/** WhatsApp template category + Meta sync labels (must match backend). */

export const WA_TEMPLATE_CATEGORY_OPTIONS = [
  { value: 'MARKETING', label: 'Marketing' },
  { value: 'UTILITY', label: 'Utility' },
  { value: 'AUTHENTICATION', label: 'Authentication' },
]

export const LOCAL_STATUS_LABELS = {
  DRAFT: 'Draft',
  SAVED: 'Template saved',
}

export const TELNYX_SYNC_LABELS = {
  NOT_SYNCED: 'Not synced',
  SYNCING: 'Syncing',
  SYNCED: 'Synced to Meta',
  PENDING: 'Pending approval',
  APPROVED: 'Approved',
  REJECTED: 'Rejected',
  FAILED: 'Sync failed',
  OUT_OF_SYNC: 'Out of sync',
}

export function isValidWaTemplateCategory(value) {
  return WA_TEMPLATE_CATEGORY_OPTIONS.some((opt) => opt.value === String(value || '').trim().toUpperCase())
}

export function validateCategoryBeforeSync(category) {
  const cat = String(category || '').trim().toUpperCase()
  if (!cat) {
    return 'Template Category is required before pushing to Meta.'
  }
  if (!isValidWaTemplateCategory(cat)) {
    return 'Template Category must be MARKETING, UTILITY, or AUTHENTICATION.'
  }
  return null
}

export function resolveLocalStatus(template, { isDirty = false } = {}) {
  if (isDirty) return LOCAL_STATUS_LABELS.DRAFT
  return template?.local_status || LOCAL_STATUS_LABELS.SAVED
}

export function resolveSyncStatus(template, { syncing = false } = {}) {
  if (syncing) return TELNYX_SYNC_LABELS.SYNCING
  return template?.sync_status || template?.telnyx_sync_label || TELNYX_SYNC_LABELS.NOT_SYNCED
}

export function resolveTelnyxSyncLabel(template) {
  return resolveSyncStatus(template)
}

export function templateNeedsResync(template) {
  if (template?.needs_resync) return true
  const label = resolveSyncStatus(template)
  return [
    TELNYX_SYNC_LABELS.NOT_SYNCED,
    TELNYX_SYNC_LABELS.OUT_OF_SYNC,
    TELNYX_SYNC_LABELS.FAILED,
    TELNYX_SYNC_LABELS.REJECTED,
  ].includes(label)
}

/** True when Sync should only refresh Telnyx/Meta approval status (no content upload). */
export function templateSyncIsStatusRefreshOnly(template) {
  const status = String(template?.approval_status || template?.status || '').toUpperCase()
  const remoteId = String(template?.telnyx_template_id || template?.telnyx_record_id || '').trim()
  const hasRemote = remoteId && !remoteId.startsWith('local-')
  if (!hasRemote) return false
  if (status === 'PENDING') return true
  if (status === 'APPROVED' && !templateNeedsResync(template)) return true
  if (status === 'REJECTED' && !templateNeedsResync(template)) return true
  return false
}

export function templateSyncButtonLabel(template, { isDirty = false, syncing = false } = {}) {
  if (syncing) return 'Syncing…'
  if (templateSyncIsStatusRefreshOnly(template)) return 'Refresh status'
  if (isDirty) return 'Save & push to Meta'
  return 'Push to Meta'
}

export function telnyxSyncPillClass(label) {
  switch (label) {
    case TELNYX_SYNC_LABELS.APPROVED:
    case TELNYX_SYNC_LABELS.SYNCED:
      return 'p-green'
    case TELNYX_SYNC_LABELS.PENDING:
      return 'p-amber'
    case TELNYX_SYNC_LABELS.REJECTED:
    case TELNYX_SYNC_LABELS.FAILED:
      return 'p-red'
    case TELNYX_SYNC_LABELS.SYNCING:
      return 'p-cyan'
    case TELNYX_SYNC_LABELS.OUT_OF_SYNC:
      return 'p-amber'
    default:
      return 'muted'
  }
}

export function localStatusPillClass(label) {
  return label === LOCAL_STATUS_LABELS.DRAFT ? 'p-amber' : 'p-green'
}

export function formatLastSyncedAt(iso) {
  if (!iso) return null
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}
