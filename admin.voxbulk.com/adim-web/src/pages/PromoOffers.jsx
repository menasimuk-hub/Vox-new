import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { apiFetch } from '../lib/api'

const TABS = [
  { key: 'all', label: 'All offers', icon: 'ti-ticket' },
  { key: 'active', label: 'Active', icon: 'ti-circle-check' },
  { key: 'expired', label: 'Expired / used', icon: 'ti-clock-off' },
  { key: 'sales', label: 'From lead sales', icon: 'ti-phone-call' },
]

function formatWhen(value) {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString(undefined, { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function formatShortDate(value) {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
}

function isExpired(row) {
  if (!row?.expires_at) return false
  return new Date(row.expires_at).getTime() < Date.now()
}

function isExhausted(row) {
  return Number(row?.redemption_count || 0) >= Number(row?.max_redemptions || 1)
}

function promoStatus(row) {
  if (!row?.is_active) return 'inactive'
  if (isExpired(row)) return 'expired'
  if (isExhausted(row)) return 'exhausted'
  return 'active'
}

function statusPillClass(status) {
  if (status === 'active') return 'productStatusPill isActive'
  if (status === 'inactive') return 'productStatusPill isStopped'
  return 'leadPill leadPillHold'
}

function statusLabel(status) {
  if (status === 'active') return 'Active'
  if (status === 'inactive') return 'Inactive'
  if (status === 'expired') return 'Expired'
  return 'Fully redeemed'
}

function limitsLine(row) {
  if (row.benefit_summary) return row.benefit_summary
  if (row.offer_type === 'survey_credits') {
    return `${row.survey_contacts_included || 0} survey contacts`
  }
  if (row.offer_type === 'interview_credits') {
    return `${row.interview_contacts_included || 0} interviews`
  }
  const parts = []
  if (row.calls_included) parts.push(`${row.calls_included} calls`)
  if (row.whatsapp_included) parts.push(`${row.whatsapp_included} WhatsApp`)
  if (row.trial_days) parts.push(`${row.trial_days}-day trial`)
  return parts.join(' · ') || 'Plan defaults'
}

function offerTypeLabel(row) {
  if (row.benefit_summary) {
    const sk = row.service_kind || ''
    const bk = row.benefit_kind === 'discount' ? 'Discount' : 'Free'
    return `${bk} · ${sk || row.offer_type || 'promo'}`
  }
  if (row.offer_type === 'survey_credits') return 'Survey promo'
  if (row.offer_type === 'interview_credits') return 'Interview promo'
  return row.plan_code || 'Subscription'
}

export default function PromoOffers() {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') || 'all'
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [msg, setMsg] = useState(params.get('created') ? 'Promo offer created.' : '')
  const [busyId, setBusyId] = useState('')
  const [query, setQuery] = useState('')
  const [applyPromo, setApplyPromo] = useState(null)
  const [orgQuery, setOrgQuery] = useState('')
  const [orgs, setOrgs] = useState([])
  const [selectedOrgIds, setSelectedOrgIds] = useState([])
  const [applying, setApplying] = useState(false)
  const [applyResult, setApplyResult] = useState(null)

  const load = useCallback(async () => {
    setError('')
    const data = await apiFetch('/admin/promo-offers')
    setRows(Array.isArray(data) ? data : [])
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      try {
        await load()
      } catch (e) {
        if (!cancelled) setError(e?.message || 'Could not load promo offers')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [load])

  const stats = useMemo(() => {
    const active = rows.filter((r) => promoStatus(r) === 'active')
    const sales = rows.filter((r) => r.lead_sales_task_id)
    const redeemed = rows.filter((r) => Number(r.redemption_count || 0) > 0)
    return {
      total: rows.length,
      active: active.length,
      sales: sales.length,
      redeemed: redeemed.length,
    }
  }, [rows])

  const tabCounts = useMemo(
    () => ({
      all: rows.length,
      active: rows.filter((r) => promoStatus(r) === 'active').length,
      expired: rows.filter((r) => ['expired', 'exhausted'].includes(promoStatus(r))).length,
      sales: rows.filter((r) => r.lead_sales_task_id).length,
    }),
    [rows],
  )

  const filtered = useMemo(() => {
    let list = rows
    if (tab === 'active') list = list.filter((r) => promoStatus(r) === 'active')
    if (tab === 'expired') list = list.filter((r) => ['expired', 'exhausted'].includes(promoStatus(r)))
    if (tab === 'sales') list = list.filter((r) => r.lead_sales_task_id)

    const q = query.trim().toLowerCase()
    if (!q) return list
    return list.filter((r) => {
      const hay = [
        r.code,
        r.name,
        r.plan_code,
        r.prospect_name,
        r.prospect_email,
        r.prospect_phone,
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase()
      return hay.includes(q)
    })
  }, [rows, tab, query])

  const setTab = (next) => {
    const nextParams = new URLSearchParams(params)
    if (next === 'all') nextParams.delete('tab')
    else nextParams.set('tab', next)
    nextParams.delete('created')
    setParams(nextParams)
  }

  const copyLink = async (row) => {
    const url = row.signup_url
    if (!url) return
    try {
      await navigator.clipboard.writeText(url)
      setMsg(`Copied signup link for ${row.code}.`)
    } catch {
      window.prompt('Copy signup link:', url)
    }
  }

  const copyCode = async (code) => {
    if (!code) return
    try {
      await navigator.clipboard.writeText(code)
      setMsg(`Copied promo code ${code}.`)
    } catch {
      window.prompt('Copy promo code:', code)
    }
  }

  const toggleActive = async (row) => {
    setBusyId(row.id)
    setMsg('')
    try {
      await apiFetch(`/admin/promo-offers/${row.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ is_active: !row.is_active }),
      })
      await load()
      setMsg(row.is_active ? `Deactivated ${row.code}.` : `Activated ${row.code}.`)
    } catch (e) {
      setError(e?.message || 'Could not update promo')
    } finally {
      setBusyId('')
    }
  }

  const openApply = (row) => {
    setApplyPromo(row)
    setOrgQuery('')
    setOrgs([])
    setSelectedOrgIds([])
    setApplyResult(null)
    setError('')
  }

  const closeApply = () => {
    setApplyPromo(null)
    setOrgQuery('')
    setOrgs([])
    setSelectedOrgIds([])
    setApplyResult(null)
  }

  const searchOrgs = async () => {
    try {
      const data = await apiFetch(`/admin/organisations?search=${encodeURIComponent(orgQuery || '')}&limit=40`)
      setOrgs(Array.isArray(data) ? data : data?.items || data?.organisations || [])
    } catch (e) {
      setError(e?.message || 'Could not search organisations')
      setOrgs([])
    }
  }

  const toggleOrg = (id) => {
    setSelectedOrgIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))
  }

  const applyToSelectedOrgs = async () => {
    if (!applyPromo?.id || selectedOrgIds.length === 0) return
    setApplying(true)
    setApplyResult(null)
    setError('')
    try {
      const res = await apiFetch(`/admin/promo-offers/${applyPromo.id}/apply`, {
        method: 'POST',
        body: JSON.stringify({ org_ids: selectedOrgIds }),
      })
      setApplyResult(res)
      await load()
      const applied = Number(res?.applied || 0)
      const failed = Number(res?.failed || 0)
      setMsg(
        applied
          ? `Applied ${applyPromo.code} to ${applied} organisation(s)${failed ? ` · ${failed} skipped` : ''}.`
          : failed
            ? `No orgs applied (${failed} skipped — already redeemed or invalid).`
            : 'Apply finished.',
      )
    } catch (e) {
      setError(e?.message || 'Could not apply promo to organisations')
    } finally {
      setApplying(false)
    }
  }

  return (
    <>
      <div className='pageTop'>
        <div>
          <h1>Promo offers</h1>
          <p>
            Create a code, then either share the signup link, let the customer enter it in Dashboard → Billing, or use{' '}
            <strong>Apply to orgs</strong> / Org Control Center to assign it yourself to one or more organisations.
          </p>
        </div>
        <div className='actions'>
          <button type='button' className='btn soft' onClick={() => load()} disabled={loading}>
            <i className='ti ti-refresh' /> {loading ? 'Loading…' : 'Refresh'}
          </button>
          <Link className='btn soft' to='/marketing/lead-sales'>
            <i className='ti ti-phone-call' /> Lead sales
          </Link>
          <Link className='btn soft' to='/billing/products?tab=subscription'>
            <i className='ti ti-credit-card' /> Subscription plans
          </Link>
          <button type='button' className='btn primary' onClick={() => navigate('/marketing/promo-offers/new')}>
            <i className='ti ti-plus' /> New promo offer
          </button>
        </div>
      </div>

      <div className='pageShell productsPageShell promoOffersShell'>
        {error ? (
          <div className='note noteWarn' style={{ marginBottom: 14 }}>
            {error}
          </div>
        ) : null}
        {msg ? (
          <div className='note' style={{ marginBottom: 14 }}>
            {msg}
          </div>
        ) : null}

        <div className='productsHub'>
          <div className='productsTabBar' role='tablist'>
            {TABS.map(({ key, label, icon }) => (
              <button
                key={key}
                type='button'
                role='tab'
                aria-selected={tab === key}
                className={`productsTabBtn ${tab === key ? 'active' : ''}`}
                onClick={() => setTab(key)}
              >
                <i className={`ti ${icon}`} />
                {label}
                <span className='productsTabCount'>{tabCounts[key] ?? 0}</span>
              </button>
            ))}
          </div>

          <div className='productsPanel' role='tabpanel'>
            <div className='productsStats'>
              <div className='productsStat'>
                <label>Total promos</label>
                <strong>{stats.total}</strong>
                <span>Manual + lead sales offers</span>
              </div>
              <div className='productsStat'>
                <label>Active now</label>
                <strong>{stats.active}</strong>
                <span>Valid code, not expired or used up</span>
              </div>
              <div className='productsStat'>
                <label>From lead sales</label>
                <strong>{stats.sales}</strong>
                <span>Auto-created on offer send</span>
              </div>
              <div className='productsStat'>
                <label>Redeemed</label>
                <strong>{stats.redeemed}</strong>
                <span>At least one signup completed</span>
              </div>
            </div>

            <div className='productsToolbar'>
              <h2 className='productsToolbarTitle'>
                <i className='ti ti-list-details' />
                {tab === 'active'
                  ? 'Active promo offers'
                  : tab === 'expired'
                    ? 'Expired or fully redeemed'
                    : tab === 'sales'
                      ? 'Lead sales promos'
                      : 'All promo offers'}
              </h2>
              <div className='promoToolbarSearch'>
                <i className='ti ti-search' />
                <input
                  className='input promoSearchInput'
                  type='search'
                  placeholder='Search code, name, prospect…'
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
              </div>
              <span className='pill p-cyan'>{filtered.length} shown</span>
            </div>

            {loading ? (
              <div className='note'>Loading promo offers…</div>
            ) : (
              <div className='productsTableWrap'>
                <table className='productsTable'>
                  <thead>
                    <tr>
                      <th>Offer</th>
                      <th>Benefit</th>
                      <th>Uses</th>
                      <th>Expires</th>
                      <th>Status</th>
                      <th style={{ textAlign: 'right' }}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((row) => {
                      const status = promoStatus(row)
                      const busy = busyId === row.id
                      const prospectLine = [row.prospect_name, row.prospect_email || row.prospect_phone]
                        .filter(Boolean)
                        .join(' · ')
                      return (
                        <tr key={row.id} className={status === 'active' ? '' : 'isStopped'}>
                          <td className='promoOfferCell'>
                            <div className='productIdentity'>
                              <span className='productAvatar'>
                                <i className='ti ti-ticket' />
                              </span>
                              <div>
                                <strong title={row.name || row.code}>{row.name || row.code}</strong>
                                <button
                                  type='button'
                                  className='promoCodeChip'
                                  onClick={() => copyCode(row.code)}
                                  title='Copy code'
                                >
                                  <i className='ti ti-copy' />
                                  <span>{row.code}</span>
                                </button>
                                <span className='productSub'>
                                  {row.lead_sales_task_id ? 'Lead sales' : 'Manual'}
                                  {row.created_at ? ` · ${formatShortDate(row.created_at)}` : ''}
                                  {prospectLine ? ` · ${prospectLine}` : ''}
                                </span>
                              </div>
                            </div>
                          </td>
                          <td className='promoBenefitCell'>
                            <strong style={{ color: 'var(--t1)', display: 'block', fontSize: 12.5 }}>
                              {offerTypeLabel(row)}
                            </strong>
                            <span className='muted' title={limitsLine(row)}>
                              {limitsLine(row)}
                            </span>
                          </td>
                          <td>
                            <strong>{row.redemption_count}</strong>
                            <span className='muted'> / {row.max_redemptions}</span>
                          </td>
                          <td className='mutedCell' title={formatWhen(row.expires_at)}>
                            {formatShortDate(row.expires_at)}
                          </td>
                          <td>
                            <span className={statusPillClass(status)}>{statusLabel(status)}</span>
                          </td>
                          <td>
                            <div className='promoIconActions'>
                              <button
                                type='button'
                                className='promoIconBtn'
                                onClick={() => openApply(row)}
                                disabled={!row.is_active}
                                title='Apply to organisations'
                                aria-label='Apply to organisations'
                              >
                                <i className='ti ti-building-community' />
                              </button>
                              <button
                                type='button'
                                className='promoIconBtn'
                                onClick={() => copyLink(row)}
                                disabled={!row.signup_url}
                                title='Copy signup link'
                                aria-label='Copy signup link'
                              >
                                <i className='ti ti-link' />
                              </button>
                              {row.lead_sales_task_id ? (
                                <Link
                                  className='promoIconBtn'
                                  to={`/marketing/lead-sales/${row.lead_sales_task_id}`}
                                  title='Open lead sales task'
                                  aria-label='Open lead sales task'
                                >
                                  <i className='ti ti-phone-call' />
                                </Link>
                              ) : null}
                              <button
                                type='button'
                                className={`promoIconBtn${row.is_active ? ' isDanger' : ''}`}
                                disabled={busy}
                                onClick={() => toggleActive(row)}
                                title={row.is_active ? 'Deactivate' : 'Activate'}
                                aria-label={row.is_active ? 'Deactivate' : 'Activate'}
                              >
                                <i className={`ti ${busy ? 'ti-loader-2' : row.is_active ? 'ti-player-pause' : 'ti-player-play'}`} />
                              </button>
                            </div>
                          </td>
                        </tr>
                      )
                    })}
                    {!filtered.length ? (
                      <tr>
                        <td colSpan={6}>
                          <div className='productsEmpty'>
                            {query
                              ? 'No promos match your search.'
                              : tab === 'all'
                                ? 'No promo offers yet.'
                                : 'No promos in this view.'}
                            {!query && tab === 'all' ? (
                              <>
                                {' '}
                                <button
                                  type='button'
                                  className='btn primary'
                                  style={{ marginTop: 12 }}
                                  onClick={() => navigate('/marketing/promo-offers/new')}
                                >
                                  Create promo offer
                                </button>
                              </>
                            ) : null}
                          </div>
                        </td>
                      </tr>
                    ) : null}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </div>

      {applyPromo ? (
        <div
          role='dialog'
          aria-modal='true'
          onClick={closeApply}
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 80,
            background: 'rgba(15, 23, 42, 0.45)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 16,
          }}
        >
          <div
            className='card'
            style={{ width: '100%', maxWidth: 560, background: '#fff', padding: 20, borderRadius: 12 }}
            onClick={(e) => e.stopPropagation()}
          >
            <h2 style={{ marginTop: 0, marginBottom: 8 }}>Apply {applyPromo.code} to organisations</h2>
            <p className='muted' style={{ marginTop: 0 }}>
              {applyPromo.benefit_summary || applyPromo.name || applyPromo.code}. Search, tick one or more orgs, then
              apply. Already-redeemed orgs are skipped.
            </p>
            <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
              <input
                className='input'
                style={{ flex: 1 }}
                placeholder='Search organisation name…'
                value={orgQuery}
                onChange={(e) => setOrgQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    void searchOrgs()
                  }
                }}
              />
              <button type='button' className='btn soft' onClick={() => void searchOrgs()}>
                Search
              </button>
            </div>
            <div style={{ maxHeight: 280, overflow: 'auto', border: '1px solid #e5e7eb', borderRadius: 8, padding: 8, marginBottom: 12 }}>
              {orgs.length === 0 ? (
                <p className='muted' style={{ margin: 8 }}>
                  Search to find organisations.
                </p>
              ) : (
                orgs.map((o) => (
                  <label key={o.id} style={{ display: 'flex', gap: 8, padding: 8, cursor: 'pointer' }}>
                    <input
                      type='checkbox'
                      checked={selectedOrgIds.includes(o.id)}
                      onChange={() => toggleOrg(o.id)}
                    />
                    <span>
                      <strong>{o.name}</strong>
                      <span className='muted'> · {String(o.id || '').slice(0, 8)}</span>
                    </span>
                  </label>
                ))
              )}
            </div>
            {applyResult ? (
              <div className='note' style={{ marginBottom: 12, fontSize: 12 }}>
                Applied {applyResult.applied ?? 0} · failed/skipped {applyResult.failed ?? 0}
              </div>
            ) : null}
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button type='button' className='btn soft' onClick={closeApply}>
                Close
              </button>
              <button
                type='button'
                className='btn primary'
                disabled={applying || selectedOrgIds.length === 0}
                onClick={() => void applyToSelectedOrgs()}
              >
                {applying ? 'Applying…' : `Apply to ${selectedOrgIds.length || 0} org(s)`}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  )
}
