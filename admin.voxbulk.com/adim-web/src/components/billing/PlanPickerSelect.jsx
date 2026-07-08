import React, { useEffect, useMemo, useState } from 'react'
import { apiFetch } from '@/lib/api'

const LINE_ORDER = { voxbulk: 0, customer_feedback: 1, campaign: 2 }

function itemValue(p, valueKey) {
  return valueKey === 'id' ? String(p.id || '') : String(p.code || '')
}

function optionLabel(p, grouped) {
  if (grouped) {
    const title = p.picker_title || p.name || p.code
    const region = p.region || (p.product_line === 'voxbulk' ? 'Global' : '')
    const currency = p.currency || ''
    const suffix = currency ? `${region} (${currency})` : region
    return suffix ? `${title} · ${suffix}` : title
  }
  return p.picker_label || `${p.name} (${p.code})`
}

function groupLabel(p) {
  return p.group_label || p.picker_subtitle?.split(' · ')[0] || p.product_line || 'Plans'
}

/**
 * Searchable plan picker with title + subtitle labels.
 * Uses GET /admin/products/assignable-plans — display only, no billing changes.
 */
export default function PlanPickerSelect({
  value,
  onChange,
  productLine,
  marketZone,
  placeholder = 'Select plan…',
  disabled,
  className = 'occ-modal-input',
  id,
  valueKey = 'code',
  grouped = false,
}) {
  const [items, setItems] = useState([])
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    const params = new URLSearchParams()
    if (productLine) params.set('product_line', productLine)
    if (marketZone) params.set('market_zone', marketZone)
    setLoading(true)
    apiFetch(`/admin/products/assignable-plans?${params.toString()}`)
      .then((data) => {
        if (!cancelled) setItems(Array.isArray(data) ? data : [])
      })
      .catch(() => {
        if (!cancelled) setItems([])
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [productLine, marketZone])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return items
    return items.filter(
      (p) =>
        String(p.picker_label || '').toLowerCase().includes(q) ||
        String(p.code || '').toLowerCase().includes(q) ||
        String(p.picker_title || '').toLowerCase().includes(q) ||
        String(p.group_label || '').toLowerCase().includes(q) ||
        String(p.currency || '').toLowerCase().includes(q),
    )
  }, [items, query])

  const groupedItems = useMemo(() => {
    if (!grouped) return null
    const buckets = new Map()
    for (const p of filtered) {
      const key = groupLabel(p)
      if (!buckets.has(key)) buckets.set(key, [])
      buckets.get(key).push(p)
    }
    return [...buckets.entries()].sort((a, b) => {
      const lineA = a[1][0]?.product_line || ''
      const lineB = b[1][0]?.product_line || ''
      return (LINE_ORDER[lineA] ?? 9) - (LINE_ORDER[lineB] ?? 9)
    })
  }, [filtered, grouped])

  const selected = items.find((p) => itemValue(p, valueKey) === String(value || ''))

  const renderOptions = () => {
    if (grouped && groupedItems) {
      return groupedItems.map(([label, plans]) => (
        <optgroup key={label} label={label}>
          {plans.map((p) => (
            <option key={itemValue(p, valueKey)} value={itemValue(p, valueKey)}>
              {optionLabel(p, true)}
            </option>
          ))}
        </optgroup>
      ))
    }
    return filtered.map((p) => (
      <option key={itemValue(p, valueKey)} value={itemValue(p, valueKey)}>
        {optionLabel(p, false)}
      </option>
    ))
  }

  return (
    <div className="planPickerWrap">
      <input
        type="search"
        className={className}
        placeholder={loading ? 'Loading plans…' : 'Search plans…'}
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        disabled={disabled || loading}
        style={{ marginBottom: 6 }}
      />
      <select
        id={id}
        className={className}
        value={value || ''}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled || loading}
        size={filtered.length > 8 ? 8 : Math.max(filtered.length, 2)}
        style={{ minHeight: 120 }}
      >
        <option value="">{placeholder}</option>
        {renderOptions()}
      </select>
      {selected ? (
        <p className="muted" style={{ fontSize: 12, margin: '6px 0 0' }}>
          <strong>{selected.group_label || selected.picker_subtitle?.split(' · ')[0] || 'Plan'}</strong>
          <br />
          {selected.picker_title || selected.name}
          {selected.region || selected.currency
            ? ` · ${[selected.region, selected.currency ? `(${selected.currency})` : ''].filter(Boolean).join(' ')}`
            : ''}
          {selected.price_display ? ` · ${selected.price_display}` : ''}
        </p>
      ) : null}
    </div>
  )
}
