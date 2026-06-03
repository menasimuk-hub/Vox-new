/** Format WA Survey admin API success/error payloads for banners. */

function asObject(value) {
  return value && typeof value === 'object' && !Array.isArray(value) ? value : null
}

export function formatWaSurveyError(err, fallback = 'Request failed') {
  const data = asObject(err?.data)
  const detail = asObject(data?.detail) || asObject(err?.detail)
  const message =
    detail?.message ||
    (typeof data?.detail === 'string' ? data.detail : null) ||
    (typeof data?.message === 'string' ? data.message : null) ||
    err?.message ||
    fallback
  const lines = [message]
  if (detail?.template_name) lines.push(`Template: ${detail.template_name}`)
  if (detail?.provider_error) lines.push(`Provider: ${detail.provider_error}`)
  if (detail?.status_code) lines.push(`HTTP ${detail.status_code}`)
  if (detail?.telnyx_request_mode) lines.push(`Mode: ${detail.telnyx_request_mode}`)
  if (err?.status && !detail?.status_code) lines.push(`HTTP ${err.status}`)
  return {
    message,
    detailText: lines.join('\n'),
    severity: 'error',
    templateName: detail?.template_name || null,
    providerError: detail?.provider_error || null,
    statusCode: detail?.status_code || err?.status || null,
  }
}

export function formatSyncSummary(summary) {
  const s = summary || {}
  const counts = s.counts || s
  const severity = s.severity || (s.success === false ? 'error' : 'ok')
  const message =
    s.message ||
    `Sync completed: ${counts.imported || 0} imported, ${counts.updated || 0} updated, ${counts.skipped || 0} skipped, ${counts.failed || 0} failed.`
  const lines = [message]
  if (s.filter_description) lines.push(s.filter_description)
  if (Array.isArray(s.errors) && s.errors[0]) lines.push(`Error: ${s.errors[0]}`)
  if (s.provider_error) lines.push(`Provider: ${s.provider_error}`)
  return {
    message,
    detailText: lines.join('\n'),
    severity,
    counts,
    success: s.success !== false && severity !== 'error',
  }
}

export function formatActionSuccess(result, fallback = 'Done') {
  const r = result || {}
  const message = r.message || fallback
  const lines = [message]
  if (r.template_name) lines.push(`Template: ${r.template_name}`)
  if (r.to_number) lines.push(`Sent to: ${r.to_number}`)
  if (r.telnyx_request_mode) lines.push(`Mode: ${r.telnyx_request_mode}`)
  if (r.external_id) lines.push(`Telnyx ID: ${r.external_id}`)
  if (r.approval_status) lines.push(`Approval: ${r.approval_status}`)
  return { message, detailText: lines.join('\n'), severity: 'ok', success: true }
}
