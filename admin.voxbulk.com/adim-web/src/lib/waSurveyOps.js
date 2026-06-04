/** Helpers for WA Survey operations UI (P6). */

export function isWaSurveyOrder(config) {
  if (!config || typeof config !== 'object') return false
  const channel = String(config.survey_channel || config.channel || '').toLowerCase()
  if (channel === 'whatsapp') return true
  const lists = [config.launch_channels, config.channels].filter(Array.isArray)
  for (const list of lists) {
    if (list.some((c) => String(c).toLowerCase() === 'whatsapp')) return true
  }
  return false
}

export function waSessionStatusPill(status) {
  const s = String(status || '').toLowerCase()
  if (s === 'active') return 'leadPill leadPillHold'
  if (s === 'completed') return 'leadPill leadPillAdvance'
  if (['failed', 'abandoned', 'expired'].includes(s)) return 'leadPill leadPillDecline'
  return 'leadPill leadPillNeutral'
}

export function deliveryOkBadge(delivery) {
  if (!delivery || !delivery.sent_at) return { label: 'Not sent', className: 'leadPill leadPillNeutral' }
  if (delivery.ok) return { label: 'Delivered', className: 'leadPill leadPillAdvance' }
  return { label: 'Failed', className: 'leadPill leadPillDecline' }
}
