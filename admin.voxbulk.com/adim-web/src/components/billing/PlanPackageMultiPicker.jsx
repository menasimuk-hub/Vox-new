import React, { useEffect, useMemo, useRef, useState } from 'react'
import { apiFetch } from '@/lib/api'

const LINE_ORDER = { voxbulk: 0, customer_feedback: 1, campaign: 2 }

function groupLabel(p) {
  return p.group_label || p.picker_subtitle?.split(' · ')[0] || p.product_line || 'Plans'
}

function planMeta(p) {
  const title = p.picker_title || p.name || p.code
  const region = p.region || (p.product_line === 'voxbulk' ? 'Global' : '')
  const currency = p.currency || ''
  const bits = [region, currency ? `(${currency})` : ''].filter(Boolean).join(' ')
  return { title, bits, price: p.price_display || null }
}

/**
 * White dropdown multi-package picker — one plan per service (Core + Feedback).
 * Uses GET /admin/products/assignable-plans.
 */
export default function PlanPackageMultiPicker({
  corePlanId,
  feedbackPlanId,
  onChangeCore,
  onChangeFeedback,
  disabled,
  className = '',
}) {
  const [items, setItems] = useState([])
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(true)
  const rootRef = useRef(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    apiFetch('/admin/products/assignable-plans')
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
  }, [])

  useEffect(() => {
    if (!open) return undefined
    const onDoc = (e) => {
      if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [open])

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
  }, [filtered])

  const selectedCore = items.find((p) => String(p.id) === String(corePlanId || ''))
  const selectedFeedback = items.find((p) => String(p.id) === String(feedbackPlanId || ''))

  const isChecked = (p) => {
    const id = String(p.id)
    if (p.product_line === 'customer_feedback') return id === String(feedbackPlanId || '')
    return id === String(corePlanId || '')
  }

  const togglePlan = (p) => {
    const id = String(p.id)
    const checked = isChecked(p)
    if (p.product_line === 'customer_feedback') {
      onChangeFeedback(checked ? null : id)
      return
    }
    onChangeCore(checked ? null : id)
  }

  const chips = [selectedCore, selectedFeedback].filter(Boolean)

  const triggerLabel =
    chips.length === 0
      ? loading
        ? 'Loading packages…'
        : 'Select billing packages…'
      : `${chips.length} package${chips.length === 1 ? '' : 's'} selected`

  return (
    <div className={`planPackagePicker ${className}`.trim()} ref={rootRef}>
      <button
        type="button"
        className="planPackagePicker-trigger"
        onClick={() => !disabled && !loading && setOpen((v) => !v)}
        disabled={disabled || loading}
        aria-expanded={open}
      >
        <span className="planPackagePicker-triggerText">{triggerLabel}</span>
        <span className="planPackagePicker-chevron">{open ? '▴' : '▾'}</span>
      </button>

      {chips.length > 0 ? (
        <div className="planPackagePicker-chips">
          {selectedCore ? (
            <span className="planPackagePicker-chip" key={selectedCore.id}>
              <span className="planPackagePicker-chipService">{selectedCore.group_label || 'Core platform'}</span>
              <span className="planPackagePicker-chipName">
                {planMeta(selectedCore).title}
                {planMeta(selectedCore).bits ? ` · ${planMeta(selectedCore).bits}` : ''}
              </span>
              <button type="button" className="planPackagePicker-chipRemove" onClick={() => onChangeCore(null)} aria-label="Remove core plan">
                ×
              </button>
            </span>
          ) : null}
          {selectedFeedback ? (
            <span className="planPackagePicker-chip" key={selectedFeedback.id}>
              <span className="planPackagePicker-chipService">{selectedFeedback.group_label || 'Customer Feedback'}</span>
              <span className="planPackagePicker-chipName">
                {planMeta(selectedFeedback).title}
                {planMeta(selectedFeedback).bits ? ` · ${planMeta(selectedFeedback).bits}` : ''}
              </span>
              <button
                type="button"
                className="planPackagePicker-chipRemove"
                onClick={() => onChangeFeedback(null)}
                aria-label="Remove feedback plan"
              >
                ×
              </button>
            </span>
          ) : null}
        </div>
      ) : null}

      {open ? (
        <div className="planPackagePicker-panel">
          <input
            type="search"
            className="planPackagePicker-search"
            placeholder="Search by service, package, or currency…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <div className="planPackagePicker-list">
            {groupedItems.length === 0 ? (
              <div className="planPackagePicker-empty">No packages match your search.</div>
            ) : (
              groupedItems.map(([label, plans]) => (
                <div className="planPackagePicker-group" key={label}>
                  <div className="planPackagePicker-groupTitle">{label}</div>
                  {plans.map((p) => {
                    const { title, bits, price } = planMeta(p)
                    const checked = isChecked(p)
                    return (
                      <label className={`planPackagePicker-option${checked ? ' selected' : ''}`} key={p.id}>
                        <input type="checkbox" checked={checked} onChange={() => togglePlan(p)} />
                        <span className="planPackagePicker-optionBody">
                          <span className="planPackagePicker-optionTitle">{title}</span>
                          <span className="planPackagePicker-optionMeta">
                            {[bits, price].filter(Boolean).join(' · ')}
                          </span>
                        </span>
                      </label>
                    )
                  })}
                </div>
              ))
            )}
          </div>
          <div className="planPackagePicker-foot">Select one package per service. Core platform overrides org C.P billing when active.</div>
        </div>
      ) : null}
    </div>
  )
}
