import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { apiFetch } from '../lib/api'

const TABS = [
  { key: 'all', label: 'All offers', icon: 'ti-ticket' },
  { key: 'active', label: 'Active', icon: 'ti-circle-check' },
  { key: 'expired', label: 'Expired / used', icon: 'ti-clock-off' },
  { key: 'sales', label: 'From lead sales', icon: 'ti-phone-call' },
]

function initials(name, code) {
  const source = String(name || code || '?').trim()
  const parts = source.split(/\s+/).filter(Boolean)
  if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase()
  return source.slice(0, 2).toUpperCase()
}

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

  return (
    <>
      <div className='pageTop'>
        <div>
          <h1>Promo offers</h1>
          <p>
            Signup promo codes for sales and marketing. Share the link in email or WhatsApp — customers land on signup
            with plan and trial pre-filled. Auto-created from{' '}
            <Link to='/marketing/lead-sales'>Lead sales</Link> when you send an offer.
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

      <div className='pageShell productsPageShell'>
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
                      <th>Code</th>
                      <th>Plan / type</th>
                      <th>Trial & limits</th>
                      <th>Prospect</th>
                      <th>Redemptions</th>
                      <th>Expires</th>
                      <th>Status</th>
                      <th style={{ textAlign: 'right' }}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((row) => {
                      const status = promoStatus(row)
                      const busy = busyId === row.id
                      return (
                        <tr key={row.id} className={status === 'active' ? '' : 'isStopped'}>
                          <td>
                            <div className='productIdentity'>
                              <span className='productAvatar'>
                                <i className='ti ti-ticket' />
                              </span>
                              <div>
                                <strong>{row.name || row.code}</strong>
                                <span className='productSub'>
                                  {row.lead_sales_task_id ? 'Lead sales offer' : 'Manual promo'}
                                  {row.created_at ? ` · ${formatShortDate(row.created_at)}` : ''}
                                </span>
                              </div>
                            </div>
                          </td>
                          <td>
                            <button type='button' className='promoCodeBtn' onClick={() => copyCode(row.code)} title='Copy code'>
                              <code className='productCode'>{row.code}</code>
                            </button>
                          </td>
                          <td>
                            <code className='productCode'>{offerTypeLabel(row)}</code>
                          </td>
                          <td className='mutedCell'>{limitsLine(row)}</td>
                          <td>
                            {row.prospect_name || row.prospect_email || row.prospect_phone ? (
                              <div className='leadIdentity' style={{ gap: 10 }}>
                                <span className='leadAvatar' style={{ width: 32, height: 32, fontSize: 11 }}>
                                  {initials(row.prospect_name, row.code)}
                                </span>
                                <div>
                                  <strong style={{ fontSize: 12.5 }}>{row.prospect_name || 'Prospect'}</strong>
                                  <span className='leadSub muted'>{row.prospect_email || row.prospect_phone || '—'}</span>
                                </div>
                              </div>
                            ) : (
                              <span className='muted'>—</span>
                            )}
                          </td>
                          <td>
                            <strong>{row.redemption_count}</strong>
                            <span className='muted'> / {row.max_redemptions}</span>
                          </td>
                          <td className='mutedCell'>{formatWhen(row.expires_at)}</td>
                          <td>
                            <span className={statusPillClass(status)}>{statusLabel(status)}</span>
                          </td>
                          <td>
                            <div className='productsRowActions'>
                              <button type='button' className='btn soft' onClick={() => copyLink(row)} disabled={!row.signup_url}>
                                Copy link
                              </button>
                              {row.lead_sales_task_id ? (
                                <Link className='btn soft' to={`/marketing/lead-sales/${row.lead_sales_task_id}`}>
                                  Lead
                                </Link>
                              ) : null}
                              <button type='button' className='btn soft' disabled={busy} onClick={() => toggleActive(row)}>
                                {busy ? '…' : row.is_active ? 'Deactivate' : 'Activate'}
                              </button>
                            </div>
                          </td>
                        </tr>
                      )
                    })}
                    {!filtered.length ? (
                      <tr>
                        <td colSpan={9}>
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
    </>
  )
}
