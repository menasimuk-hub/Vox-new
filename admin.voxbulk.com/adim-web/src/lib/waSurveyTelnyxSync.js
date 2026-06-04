/** WhatsApp template category + Telnyx sync labels (must match backend). */

export const WA_TEMPLATE_CATEGORY_OPTIONS = [
  { value: 'MARKETING', label: 'Marketing' },
  { value: 'UTILITY', label: 'Utility' },
  { value: 'AUTHENTICATION', label: 'Authentication' },
]

export const TELNYX_SYNC_LABELS = {
  NOT_SYNCED: 'Not synced',
  SYNCING: 'Syncing',
  SYNCED: 'Synced to Telnyx',
  PENDING: 'Pending approval',
  APPROVED: 'Approved',
  REJECTED: 'Rejected',
  FAILED: 'Sync failed',
}

export function isValidWaTemplateCategory(value) {
  return WA_TEMPLATE_CATEGORY_OPTIONS.some((opt) => opt.value === String(value || '').trim().toUpperCase())
}

export function validateCategoryBeforeSync(category) {
  const cat = String(category || '').trim().toUpperCase()
  if (!cat) {
    return 'Template Category is required before syncing to Telnyx.'
  }
  if (!isValidWaTemplateCategory(cat)) {
    return 'Template Category must be MARKETING, UTILITY, or AUTHENTICATION.'
  }
  return null
}

export function telnyxSyncPillClass(label) {
  switch (label) {
    case TELNYX_SYNC_LABELS.APPROVED:
      return 'p-green'
    case TELNYX_SYNC_LABELS.PENDING:
      return 'p-amber'
    case TELNYX_SYNC_LABELS.REJECTED:
    case TELNYX_SYNC_LABELS.FAILED:
      return 'p-red'
    case TELNYX_SYNC_LABELS.SYNCING:
      return 'p-cyan'
    case TELNYX_SYNC_LABELS.SYNCED:
      return 'p-green'
    default:
      return 'muted'
  }
}

export function resolveTelnyxSyncLabel(template) {
  return template?.telnyx_sync_label || template?.sync_status_label || TELNYX_SYNC_LABELS.NOT_SYNCED
}
