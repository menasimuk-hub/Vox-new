export const VAR_LABELS = ['First name', 'Business / service', 'Survey link', 'Service date']

const DEFAULT_EXAMPLES = ['Alex', 'Northgate Dental', 'https://example.com/s/abc', 'Monday 9am']

export function varIndexesFromText(text) {
  const found = new Set()
  for (const m of String(text || '').matchAll(/\{\{(\d+)\}\}/g)) {
    found.add(parseInt(m[1], 10))
  }
  return [...found].sort((a, b) => a - b)
}

export function ensureExampleValues(body, header = '', values = []) {
  const ids = varIndexesFromText(`${header || ''} ${body || ''}`)
  const max = ids.length ? Math.max(...ids) : Math.max(1, (values || []).length)
  const next = [...(values || [])]
  while (next.length < max) {
    next.push(DEFAULT_EXAMPLES[next.length] || `Sample ${next.length + 1}`)
  }
  return next
}

export function substituteTemplateVars(text, values = []) {
  let out = String(text || '')
  values.forEach((value, index) => {
    out = out.replace(new RegExp(`\\{\\{${index + 1}\\}\\}`, 'g'), String(value ?? ''))
  })
  return out
}

export function previewButtonsFromTemplate(tpl) {
  const preview = tpl?.preview || {}
  const raw = preview.buttons || tpl?.buttons_preview || []
  if (Array.isArray(raw) && raw.length) {
    return raw.map((b, i) => ({
      label: b.label || b.text || 'Button',
      url: b.url || '',
      phone_number: b.phone_number || '',
    }))
  }
  const bt = tpl?.button_type
  const defs = Array.isArray(tpl?.buttons) ? tpl.buttons : []
  if (bt === 'none' || !defs.length) return []
  return defs.map((b) => ({
    label: b.text || 'Button',
    url: b.url || '',
    phone_number: b.phone_number || '',
  }))
}
