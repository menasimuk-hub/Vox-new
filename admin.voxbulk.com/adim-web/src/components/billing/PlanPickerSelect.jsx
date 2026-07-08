import React, { useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../lib/api'

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
        String(p.picker_title || '').toLowerCase().includes(q),
    )
  }, [items, query])

  const selected = items.find((p) => p.code === value)

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
        {filtered.map((p) => (
          <option key={p.code} value={p.code}>
            {p.picker_label || `${p.name} (${p.code})`}
          </option>
        ))}
      </select>
      {selected ? (
        <p className="muted" style={{ fontSize: 12, margin: '6px 0 0' }}>
          <strong>{selected.picker_title}</strong>
          <br />
          {selected.picker_subtitle}
          {selected.price_display ? ` · ${selected.price_display}` : ''}
        </p>
      ) : null}
    </div>
  )
}
