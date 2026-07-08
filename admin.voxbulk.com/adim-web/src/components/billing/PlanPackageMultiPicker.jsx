import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { apiFetch } from '@/lib/api'

const LINE_ORDER = { voxbulk: 0, customer_feedback: 1, campaign: 2 }
const PANEL_GAP = 6
const VIEWPORT_PAD = 12

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
 * Multi-package picker — portal dropdown (escapes overflow:hidden parents).
 * One plan per service: Core platform + Customer Feedback.
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
  const [panelStyle, setPanelStyle] = useState(null)
  const rootRef = useRef(null)
  const triggerRef = useRef(null)
  const panelRef = useRef(null)

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

  const positionPanel = useCallback(() => {
    const trigger = triggerRef.current
    if (!trigger) return
    const rect = trigger.getBoundingClientRect()
    const vw = window.innerWidth
    const vh = window.innerHeight
    const width = Math.min(Math.max(rect.width, 320), 440)
    let left = rect.left
    if (left + width > vw - VIEWPORT_PAD) left = vw - width - VIEWPORT_PAD
    if (left < VIEWPORT_PAD) left = VIEWPORT_PAD

    const spaceBelow = vh - rect.bottom - PANEL_GAP - VIEWPORT_PAD
    const spaceAbove = rect.top - PANEL_GAP - VIEWPORT_PAD
    const preferBelow = spaceBelow >= 200 || spaceBelow >= spaceAbove
    const maxHeight = Math.min(360, Math.max(160, preferBelow ? spaceBelow : spaceAbove))

    if (preferBelow) {
      setPanelStyle({
        position: 'fixed',
        top: rect.bottom + PANEL_GAP,
        left,
        width,
        maxHeight,
        zIndex: 10050,
      })
    } else {
      setPanelStyle({
        position: 'fixed',
        bottom: vh - rect.top + PANEL_GAP,
        left,
        width,
        maxHeight,
        zIndex: 10050,
      })
    }
  }, [])

  useLayoutEffect(() => {
    if (!open) return undefined
    positionPanel()
    const onReflow = () => positionPanel()
    window.addEventListener('resize', onReflow)
    window.addEventListener('scroll', onReflow, true)
    return () => {
      window.removeEventListener('resize', onReflow)
      window.removeEventListener('scroll', onReflow, true)
    }
  }, [open, positionPanel, items.length])

  useEffect(() => {
    if (!open) return undefined
    const onDoc = (e) => {
      const t = e.target
      if (rootRef.current?.contains(t) || panelRef.current?.contains(t)) return
      setOpen(false)
    }
    const onKey = (e) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDoc)
      document.removeEventListener('keydown', onKey)
    }
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

  const panel = open && panelStyle
    ? createPortal(
        <>
          <div className="planPackagePicker-backdrop" aria-hidden onClick={() => setOpen(false)} />
          <div
            ref={panelRef}
            className="planPackagePicker-panel planPackagePicker-panel--portal"
            style={panelStyle}
            role="listbox"
            aria-multiselectable="true"
          >
            <div className="planPackagePicker-panelHead">
              <span className="planPackagePicker-panelTitle">Billing packages</span>
              <button type="button" className="planPackagePicker-panelClose" onClick={() => setOpen(false)} aria-label="Close">
                ×
              </button>
            </div>
            <input
              type="search"
              className="planPackagePicker-search"
              placeholder="Search service, package, currency…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              autoFocus
            />
            <div className="planPackagePicker-list" style={{ maxHeight: Math.max(120, (panelStyle.maxHeight || 280) - 108) }}>
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
                        <button
                          type="button"
                          key={p.id}
                          className={`planPackagePicker-option${checked ? ' selected' : ''}`}
                          onClick={() => togglePlan(p)}
                          role="option"
                          aria-selected={checked}
                        >
                          <span className={`planPackagePicker-check${checked ? ' on' : ''}`} aria-hidden>
                            {checked ? '✓' : ''}
                          </span>
                          <span className="planPackagePicker-optionBody">
                            <span className="planPackagePicker-optionTitle">{title}</span>
                            <span className="planPackagePicker-optionMeta">
                              {[bits, price].filter(Boolean).join(' · ')}
                            </span>
                          </span>
                        </button>
                      )
                    })}
                  </div>
                ))
              )}
            </div>
            <div className="planPackagePicker-foot">
              Pick up to one per service — Core platform + Customer Feedback.
            </div>
          </div>
        </>,
        document.body,
      )
    : null

  return (
    <div className={`planPackagePicker ${open ? 'open' : ''} ${className}`.trim()} ref={rootRef}>
      <button
        ref={triggerRef}
        type="button"
        className={`planPackagePicker-trigger${open ? ' open' : ''}`}
        onClick={() => !disabled && !loading && setOpen((v) => !v)}
        disabled={disabled || loading}
        aria-expanded={open}
        aria-haspopup="listbox"
      >
        <span className="planPackagePicker-triggerMain">
          {chips.length === 0 ? (
            <span className="planPackagePicker-placeholder">
              {loading ? 'Loading packages…' : 'Choose billing packages…'}
            </span>
          ) : (
            <span className="planPackagePicker-summary">
              {chips.length} package{chips.length === 1 ? '' : 's'} selected — click to change
            </span>
          )}
        </span>
        <span className="planPackagePicker-chevron" aria-hidden>
          {open ? '▴' : '▾'}
        </span>
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

      {panel}
    </div>
  )
}
