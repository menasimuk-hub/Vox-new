import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import {
  FILTER_OPTIONS,
  GROUP_ORDER,
  REGION_COLORS,
  computeStats,
  filterRows,
  formatPriceCell,
  groupIconBg,
  groupTextColor,
  tierColors,
  tierSummaryRows,
} from './productsHubUtils'
import './productsHubTheme.css'

const GROUP_ACTIONS = {
  voxbulk: [{ label: 'Edit core pricing', to: '/pricing/plans' }],
  customer_feedback: [
    { label: 'Edit feedback pricing', to: '/customer-feedback/packages' },
    { label: 'Feedback hub', to: '/customer-feedback/overview' },
  ],
  campaign: [{ label: 'Campaign pricing', to: '/pricing/services' }],
}

function StatusBadge({ active }) {
  return (
    <span className={`phStatus ${active ? 'active' : 'stopped'}`}>
      {active ? 'Active' : 'Stopped'}
    </span>
  )
}

function RegionBadge({ region }) {
  const rc = REGION_COLORS[region] || REGION_COLORS.Global
  return (
    <span className="phRegionBadge" style={{ background: rc.bg, color: rc.text }}>
      <span className="phRegionDot" style={{ background: rc.text }} />
      {region}
    </span>
  )
}

function PriceCell({ row }) {
  const { text, gap } = formatPriceCell(row)
  if (text === '—') return <span className="phPrice">—</span>
  return (
    <span className={`phPrice ${gap ? 'gap' : ''}`}>
      {text}
      {gap ? <span className="phGapFlag">no price</span> : null}
    </span>
  )
}

function ProductRow({ row, selected, onSelect }) {
  const tc = tierColors(row)
  const key = `${row.product_type}-${row.id}`
  return (
    <tr
      key={key}
      className={selected ? 'selected' : ''}
      onClick={() => onSelect(row)}
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter') onSelect(row)
      }}
    >
      <td className="phAccentCell">
        <div className="phAccentBar" style={{ background: tc.bar }} />
      </td>
      <td>
        <div className="phPlanName">
          {row.name}
          <span className="phTierChip" style={{ background: tc.chipBg, color: tc.chipText }}>
            {String(row.tier_key || '').replace(/_/g, ' ')}
          </span>
        </div>
      </td>
      <td>
        <span className="phCode">{row.code}</span>
      </td>
      <td>
        <RegionBadge region={row.region || 'Global'} />
      </td>
      <td>
        <PriceCell row={row} />
      </td>
      <td className="phFeaturesCol">
        <span className="phFeatures" title={Array.isArray(row.features) ? row.features.join('\n') : ''}>
          {row.features_summary || '—'}
        </span>
      </td>
      <td>
        <StatusBadge active={row.is_active} />
      </td>
      <td style={{ textAlign: 'right', color: 'var(--ph-ink-faint)' }}>›</td>
    </tr>
  )
}

function DetailPanel({ row, draft, setDraft, onClose, onSave, saving, isMobile }) {
  if (!row) return null
  const tc = tierColors(row)
  const isCampaign = row.product_type === 'campaign'
  const isSubscription = row.product_type === 'subscription'

  const panel = (
    <div className={`phPanel ${isMobile ? '' : 'phPanelDesktop'}`}>
      <div className="phPanelHead">
        <span className="phPanelDot" style={{ background: tc.bar }} />
        <div style={{ flex: 1 }}>
          <h3>{draft.name || row.name}</h3>
          <div className="phPanelSub">{row.picker_subtitle || row.group_label}</div>
          <span className="phCode">{row.code}</span>
        </div>
        <button type="button" className="phPanelClose" onClick={onClose} aria-label="Close">
          ✕
        </button>
      </div>
      <div className="phPanelBody">
        {isSubscription ? (
          <>
            <div>
              <label htmlFor="phName">Plan name (shown on dashboard &amp; website)</label>
              <input
                id="phName"
                value={draft.name}
                onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))}
              />
            </div>
            <div>
              <label htmlFor="phDesc">Subtitle / description</label>
              <textarea
                id="phDesc"
                rows={2}
                value={draft.description}
                onChange={(e) => setDraft((d) => ({ ...d, description: e.target.value }))}
              />
            </div>
            <div>
              <label htmlFor="phFeatures">Features (one per line)</label>
              <textarea
                id="phFeatures"
                rows={4}
                value={draft.featuresText}
                onChange={(e) => setDraft((d) => ({ ...d, featuresText: e.target.value }))}
              />
            </div>
          </>
        ) : (
          <div className="phPanelReadonly">{row.description || row.limits_summary}</div>
        )}
        <div>
          <label>Price (read-only — edit in pricing page)</label>
          <div className="phPanelReadonly">
            <PriceCell row={row} />
          </div>
        </div>
        <div>
          <label>Features preview (dashboard &amp; website)</label>
          <ul className="phFeaturesPreview">
            {(Array.isArray(row.features) ? row.features : []).map((f) => (
              <li key={f}>{f}</li>
            ))}
          </ul>
        </div>
        <div>
          <label>Limits (read-only)</label>
          <div className="phPanelReadonly">{row.limits_summary || '—'}</div>
        </div>
        <div>
          <label>Region</label>
          <div className="phPanelReadonly">
            <RegionBadge region={row.region || 'Global'} />
          </div>
        </div>
        <div>
          <label>Status</label>
          <div className="phStatusSwitch">
            <button
              type="button"
              className={`phStatusOpt ${draft.is_active ? 'on-active' : ''}`}
              onClick={() => setDraft((d) => ({ ...d, is_active: true }))}
            >
              Active
            </button>
            <button
              type="button"
              className={`phStatusOpt ${!draft.is_active ? 'on-stopped' : ''}`}
              onClick={() => setDraft((d) => ({ ...d, is_active: false }))}
            >
              Stopped
            </button>
          </div>
        </div>
      </div>
      <div className="phPanelFoot">
        {isSubscription ? (
          <button type="button" className="phBtn phBtnSolid" disabled={saving} onClick={onSave}>
            {saving ? 'Saving…' : 'Save copy & status'}
          </button>
        ) : (
          <button type="button" className="phBtn phBtnSolid" disabled={saving} onClick={onSave}>
            {saving ? 'Saving…' : 'Save status'}
          </button>
        )}
        <Link className="phBtn phBtnLink" to={row.pricing_url || '/pricing/plans'}>
          Edit pricing →
        </Link>
        {row.preview_dashboard_url ? (
          <a
            className="phBtn phBtnGhost"
            href={`https://dashboard.voxbulk.com${row.preview_dashboard_url}`}
            target="_blank"
            rel="noreferrer"
          >
            Preview on dashboard ↗
          </a>
        ) : null}
        {row.preview_website_url ? (
          <a className="phBtn phBtnGhost" href={row.preview_website_url} target="_blank" rel="noreferrer">
            Preview on website ↗
          </a>
        ) : null}
        <button type="button" className="phBtn phBtnGhost" onClick={onClose}>
          Close
        </button>
      </div>
    </div>
  )

  if (isMobile) {
    return (
      <div className="phOverlay phOverlayMobile" onClick={(e) => e.target === e.currentTarget && onClose()}>
        {panel}
      </div>
    )
  }
  return panel
}

export default function ProductsHub() {
  const [searchParams] = useSearchParams()
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [filter, setFilter] = useState('all')
  const [query, setQuery] = useState('')
  const [gapsOnly, setGapsOnly] = useState(false)
  const [selected, setSelected] = useState(null)
  const [draft, setDraft] = useState(null)
  const [saving, setSaving] = useState(false)
  const [toast, setToast] = useState('')
  const [expandedTiers, setExpandedTiers] = useState(() => new Set())
  const [isMobile, setIsMobile] = useState(() => typeof window !== 'undefined' && window.innerWidth <= 960)

  const load = useCallback(async () => {
    setError('')
    const data = await apiFetch('/admin/products')
    setRows(Array.isArray(data) ? data : [])
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      try {
        await load()
      } catch (e) {
        if (!cancelled) setError(e?.message || 'Could not load products')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [load])

  useEffect(() => {
    const onResize = () => setIsMobile(window.innerWidth <= 960)
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  useEffect(() => {
    const highlight = searchParams.get('highlight')
    if (!highlight || !rows.length) return
    const row = rows.find((r) => r.code === highlight)
    if (row) openRow(row)
  }, [rows, searchParams])

  const filtered = useMemo(() => filterRows(rows, { filter, query, gapsOnly }), [rows, filter, query, gapsOnly])
  const stats = useMemo(() => computeStats(rows), [rows])

  const grouped = useMemo(() => {
    const map = new Map()
    for (const row of filtered) {
      const line = row.product_line || 'other'
      if (!map.has(line)) map.set(line, [])
      map.get(line).push(row)
    }
    return GROUP_ORDER.filter((k) => map.has(k)).map((k) => ({
      key: k,
      label: map.get(k)[0]?.group_label || k,
      rows: map.get(k),
    }))
  }, [filtered])

  function openRow(row) {
    setSelected(row)
    setDraft({
      name: row.name || '',
      description: row.description || '',
      featuresText: Array.isArray(row.features) ? row.features.join('\n') : '',
      is_active: Boolean(row.is_active),
    })
  }

  function closePanel() {
    setSelected(null)
    setDraft(null)
  }

  function toggleTier(groupKey, tierKey) {
    const id = `${groupKey}:${tierKey}`
    setExpandedTiers((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  async function savePanel() {
    if (!selected || !draft) return
    setSaving(true)
    setError('')
    try {
      if (selected.product_type === 'campaign') {
        await apiFetch(`/admin/platform-services/${encodeURIComponent(selected.id)}`, {
          method: 'PUT',
          body: JSON.stringify({ is_active: draft.is_active }),
        })
      } else {
        await apiFetch(`/admin/products/plans/${encodeURIComponent(selected.id)}/copy`, {
          method: 'PATCH',
          body: JSON.stringify({
            name: draft.name,
            description: draft.description,
            features_text: draft.featuresText,
            is_active: draft.is_active,
          }),
        })
      }
      await load()
      setToast(`Saved “${draft.name || selected.name}”`)
      setTimeout(() => setToast(''), 2400)
      closePanel()
    } catch (e) {
      setError(e?.message || 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  function renderGroupBody(groupKey, groupRows) {
    if (groupKey === 'customer_feedback' && !query && !gapsOnly) {
      const summaries = tierSummaryRows(groupRows)
      return summaries.flatMap((summary) => {
        const tierId = `${groupKey}:${summary.tierKey}`
        const expanded = expandedTiers.has(tierId)
        const summaryRow = (
          <tr
            key={`tier-${tierId}`}
            className="phTierSummary"
            onClick={() => toggleTier(groupKey, summary.tierKey)}
          >
            <td className="phAccentCell">
              <div className="phAccentBar" style={{ background: tierColors(summary.rows[0]).bar }} />
            </td>
            <td colSpan={2}>
              <button type="button" className="phExpandBtn" aria-label={expanded ? 'Collapse' : 'Expand'}>
                {expanded ? '▾' : '▸'}
              </button>
              {summary.name}
              <span className="phTierChip" style={{ marginLeft: 8 }}>
                {summary.regionCount} markets
              </span>
            </td>
            <td>—</td>
            <td>
              <span className="phPrice">{summary.priceRange.join(' – ')}</span>
              {summary.anyGap ? <span className="phGapFlag">gaps</span> : null}
            </td>
            <td className="phFeaturesCol">
              <span className="phFeatures">{summary.rows[0]?.features_summary || summary.rows[0]?.limits_summary}</span>
            </td>
            <td>
              <span className="phLimits">
                {summary.activeCount}/{summary.regionCount} active
              </span>
            </td>
            <td />
          </tr>
        )
        if (!expanded) return [summaryRow]
        return [
          summaryRow,
          ...summary.rows.map((row) => (
            <ProductRow
              key={`${row.product_type}-${row.id}`}
              row={row}
              selected={selected?.id === row.id}
              onSelect={openRow}
            />
          )),
        ]
      })
    }
    return groupRows.map((row) => (
      <ProductRow
        key={`${row.product_type}-${row.id}`}
        row={row}
        selected={selected?.id === row.id}
        onSelect={openRow}
      />
    ))
  }

  return (
    <div className="phHub">
      <header>
        <div className="phTitleBlock">
          <div className="phLogo">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#9C4B28" strokeWidth="2">
              <rect x="3" y="3" width="7" height="7" rx="1.5" />
              <rect x="14" y="3" width="7" height="7" rx="1.5" />
              <rect x="3" y="14" width="7" height="7" rx="1.5" />
              <rect x="14" y="14" width="7" height="7" rx="1.5" />
            </svg>
          </div>
          <div>
            <h1>Products hub</h1>
            <p>
              Catalogue for Core platform, Customer Feedback, and campaign packs. Edit marketing copy here; change
              prices in <Link className="phIntroLink" to="/pricing/plans">Core platform pricing</Link> or{' '}
              <Link className="phIntroLink" to="/customer-feedback/packages">Customer feedback pricing</Link>.
            </p>
          </div>
        </div>
        <div className="phStatRow">
          <div className="phStat">
            <b>{stats.total}</b>
            <span>Total</span>
          </div>
          <div className="phStat">
            <b>{stats.active}</b>
            <span>Active</span>
          </div>
          <div className="phStat">
            <b>{stats.stopped}</b>
            <span>Stopped</span>
          </div>
          <div className="phStat">
            <b>{stats.gaps}</b>
            <span>Price gaps</span>
          </div>
        </div>
      </header>

      {error ? (
        <div className="note noteWarn" style={{ marginBottom: 14 }}>
          {error}
        </div>
      ) : null}

      <div className="phLegend">
        <span>
          <b>How to read this:</b> same-named tiers repeat across regions — left stripe colour = tier within product
          line.
        </span>
        <span className="swatch">
          <RegionBadge region="US" /> region from plan code
        </span>
        <span className="swatch">
          <span className="phPrice gap">£0</span>
          <span className="phGapFlag">no price</span> missing regional price
        </span>
      </div>

      <div className="phControls">
        <input
          className="phSearch"
          type="search"
          placeholder="Search by name or code…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        {FILTER_OPTIONS.map(({ key, label }) => (
          <button
            key={key}
            type="button"
            className={`phFilterBtn ${filter === key ? 'active' : ''}`}
            onClick={() => setFilter(key)}
          >
            {label}
          </button>
        ))}
        <label className="phToggleGap">
          <input type="checkbox" checked={gapsOnly} onChange={(e) => setGapsOnly(e.target.checked)} />
          Show pricing gaps only
        </label>
        <button type="button" className="phFilterBtn" onClick={() => load()} disabled={loading}>
          Refresh
        </button>
      </div>

      <div className={`phHubLayout ${selected && !isMobile ? 'hasPanel' : ''}`}>
        <div>
          {loading ? (
            <div className="phEmpty">Loading products…</div>
          ) : grouped.length === 0 ? (
            <div className="phEmpty">No plans match this filter.</div>
          ) : (
            grouped.map(({ key, label, rows: groupRows }) => (
              <section key={key} className="phGroup">
                <div className="phGroupHead">
                  <div className="phGroupIcon" style={{ background: groupIconBg(key), color: groupTextColor(key) }}>
                    ●
                  </div>
                  <h2>{label}</h2>
                  <span className="phGroupCount">
                    {groupRows.length} plan{groupRows.length === 1 ? '' : 's'}
                  </span>
                  <span className="phGroupLine" />
                  {(GROUP_ACTIONS[key] || []).map((action) => (
                    <Link key={action.to} className="phGroupAction" to={action.to}>
                      {action.label} →
                    </Link>
                  ))}
                </div>
                <div className="phTableCard">
                  <table>
                    <thead>
                      <tr>
                        <th className="phAccentCell" />
                        <th>Plan</th>
                        <th>Code</th>
                        <th>Region</th>
                        <th>Price</th>
                        <th className="phFeaturesCol">Features (dashboard &amp; website)</th>
                        <th>Status</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>{renderGroupBody(key, groupRows)}</tbody>
                  </table>
                </div>
              </section>
            ))
          )}
        </div>

        {selected && !isMobile ? (
          <DetailPanel
            row={selected}
            draft={draft}
            setDraft={setDraft}
            onClose={closePanel}
            onSave={savePanel}
            saving={saving}
            isMobile={false}
          />
        ) : null}
      </div>

      {selected && isMobile ? (
        <DetailPanel
          row={selected}
          draft={draft}
          setDraft={setDraft}
          onClose={closePanel}
          onSave={savePanel}
          saving={saving}
          isMobile
        />
      ) : null}

      <div className={`phToast ${toast ? 'show' : ''}`}>{toast}</div>
    </div>
  )
}
