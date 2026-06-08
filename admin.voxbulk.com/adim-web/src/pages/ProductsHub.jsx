import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { apiFetch } from '../lib/api'

const TABS = [
  { key: 'all', label: 'All products', icon: 'ti-box' },
  { key: 'subscription', label: 'Subscriptions', icon: 'ti-repeat' },
  { key: 'campaign', label: 'Campaign packs', icon: 'ti-speakerphone' },
]

function money(pence) {
  return `£${(Number(pence || 0) / 100).toFixed(0)}`
}

function limitsSummary(row) {
  if (row.product_type !== 'subscription') return `${row.pricing_rules_count || 0} pricing rules`
  const parts = []
  if (row.calls_included) parts.push(`${row.calls_included} calls`)
  if (row.whatsapp_included) parts.push(`${row.whatsapp_included} WhatsApp`)
  if (row.sms_included) parts.push(`${row.sms_included} SMS`)
  return parts.join(' · ') || 'No limits set'
}

function productIcon(row) {
  return row.product_type === 'subscription' ? 'ti-credit-card' : 'ti-package'
}

export default function ProductsHub() {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') || 'all'
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busyId, setBusyId] = useState('')

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

  const filtered = useMemo(() => {
    if (tab === 'subscription') return rows.filter((r) => r.product_type === 'subscription')
    if (tab === 'campaign') return rows.filter((r) => r.product_type === 'campaign')
    return rows
  }, [rows, tab])

  const stats = useMemo(() => {
    const subs = rows.filter((r) => r.product_type === 'subscription')
    const campaigns = rows.filter((r) => r.product_type === 'campaign')
    return {
      total: rows.length,
      activeSubs: subs.filter((r) => r.is_active).length,
      activeCampaigns: campaigns.filter((r) => r.is_active).length,
      stopped: rows.filter((r) => !r.is_active).length,
    }
  }, [rows])

  const tabCounts = useMemo(
    () => ({
      all: rows.length,
      subscription: rows.filter((r) => r.product_type === 'subscription').length,
      campaign: rows.filter((r) => r.product_type === 'campaign').length,
    }),
    [rows],
  )

  const setTab = (next) => {
    setParams(next === 'all' ? {} : { tab: next })
  }

  const toggleActive = async (row) => {
    if (row.product_type !== 'subscription') {
      setBusyId(row.id)
      try {
        await apiFetch(`/admin/platform-services/${encodeURIComponent(row.id)}`, {
          method: 'PUT',
          body: JSON.stringify({ is_active: !row.is_active }),
        })
        await load()
      } catch (e) {
        setError(e?.message || 'Could not update status')
      } finally {
        setBusyId('')
      }
      return
    }
    setBusyId(row.id)
    try {
      await apiFetch(`/admin/products/plans/${encodeURIComponent(row.id)}/active`, {
        method: 'PATCH',
        body: JSON.stringify({ is_active: !row.is_active }),
      })
      await load()
    } catch (e) {
      setError(e?.message || 'Could not update status')
    } finally {
      setBusyId('')
    }
  }

  const duplicatePlan = async (row) => {
    setBusyId(`dup-${row.id}`)
    setError('')
    try {
      const created = await apiFetch(`/admin/products/plans/${encodeURIComponent(row.id)}/duplicate`, { method: 'POST' })
      await load()
      if (created?.id) navigate(`/billing/products/plan/${created.id}/edit`)
    } catch (e) {
      setError(e?.message || 'Duplicate failed')
    } finally {
      setBusyId('')
    }
  }

  const deletePlan = async (row) => {
    if (!window.confirm(`Delete plan "${row.name}" (${row.code})?`)) return
    setBusyId(`del-${row.id}`)
    setError('')
    try {
      await apiFetch(`/admin/products/plans/${encodeURIComponent(row.id)}`, { method: 'DELETE' })
      await load()
    } catch (e) {
      setError(e?.message || 'Delete failed')
    } finally {
      setBusyId('')
    }
  }

  return (
    <>
      <div className="pageTop">
        <div>
          <h1>Products hub</h1>
          <p>
            Full-width catalogue for monthly subscription packages and one-off campaign packs. Active products appear on
            signup and sales offer flows.
          </p>
        </div>
        <div className="actions">
          <button type="button" className="btn soft" onClick={() => load()} disabled={loading}>
            <i className="ti ti-refresh" /> Refresh
          </button>
          <button type="button" className="btn primary" onClick={() => navigate('/billing/products/plan/new')}>
            <i className="ti ti-plus" /> New subscription plan
          </button>
        </div>
      </div>

      <div className="pageShell productsPageShell">
        {error ? (
          <div className="note noteWarn" style={{ marginBottom: 14 }}>
            {error}
          </div>
        ) : null}

        <div className="productsHub">
          <div className="productsTabBar" role="tablist">
            {TABS.map(({ key, label, icon }) => (
              <button
                key={key}
                type="button"
                role="tab"
                aria-selected={tab === key}
                className={`productsTabBtn ${tab === key ? 'active' : ''}`}
                onClick={() => setTab(key)}
              >
                <i className={`ti ${icon}`} />
                {label}
                <span className="productsTabCount">{tabCounts[key] ?? 0}</span>
              </button>
            ))}
          </div>

          <div className="productsPanel" role="tabpanel">
            <div className="productsStats">
              <div className="productsStat">
                <label>Total products</label>
                <strong>{stats.total}</strong>
                <span>Subscriptions + campaign packs</span>
              </div>
              <div className="productsStat">
                <label>Active subscriptions</label>
                <strong>{stats.activeSubs}</strong>
                <span>Shown on signup &amp; sales offers</span>
              </div>
              <div className="productsStat">
                <label>Active campaigns</label>
                <strong>{stats.activeCampaigns}</strong>
                <span>Survey / interview packs</span>
              </div>
              <div className="productsStat">
                <label>Stopped</label>
                <strong>{stats.stopped}</strong>
                <span>Hidden from new customers</span>
              </div>
            </div>

            <div className="productsToolbar">
              <h2 className="productsToolbarTitle">
                <i className="ti ti-list-details" />
                {tab === 'subscription' ? 'Subscription plans' : tab === 'campaign' ? 'Campaign packs' : 'All products'}
              </h2>
              <span className="pill p-cyan">{filtered.length} shown</span>
            </div>

            {loading ? (
              <div className="note">Loading products…</div>
            ) : (
              <div className="productsTableWrap">
                <table className="productsTable">
                  <thead>
                    <tr>
                      <th>Product</th>
                      <th>Code</th>
                      <th>Type</th>
                      <th>Price / rules</th>
                      <th>Limits</th>
                      <th>Status</th>
                      <th style={{ textAlign: 'right' }}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((row) => (
                      <tr key={`${row.product_type}-${row.id}`} className={row.is_active ? '' : 'isStopped'}>
                        <td>
                          <div className="productIdentity">
                            <span className={`productAvatar ${row.product_type === 'campaign' ? 'isCampaign' : ''}`}>
                              <i className={`ti ${productIcon(row)}`} />
                            </span>
                            <div>
                              <strong>{row.name}</strong>
                              <span className="productSub">
                                {row.product_type === 'subscription'
                                  ? `${row.service_kind || 'dental'} · ${row.interval || 'monthly'}`
                                  : row.description || 'One-off campaign pricing'}
                              </span>
                            </div>
                          </div>
                        </td>
                        <td>
                          <code className="productCode">{row.code}</code>
                        </td>
                        <td>
                          <span
                            className={`productTypePill ${
                              row.product_type === 'subscription' ? 'isSubscription' : 'isCampaign'
                            }`}
                          >
                            {row.product_type === 'subscription' ? 'Subscription' : 'Campaign'}
                          </span>
                        </td>
                        <td>
                          {row.product_type === 'subscription' ? (
                            <div className="productPrice">
                              {money(row.price_gbp_pence)}
                              <span> / {row.interval === 'yearly' ? 'year' : 'month'}</span>
                            </div>
                          ) : (
                            <span className="muted">{row.pricing_rules_count || 0} pricing rules</span>
                          )}
                        </td>
                        <td className="mutedCell">{limitsSummary(row)}</td>
                        <td>
                          <span className={`productStatusPill ${row.is_active ? 'isActive' : 'isStopped'}`}>
                            {row.is_active ? 'Active' : 'Stopped'}
                          </span>
                        </td>
                        <td>
                          <div className="productsRowActions">
                            {row.product_type === 'subscription' ? (
                              <>
                                <button
                                  type="button"
                                  className="btn soft"
                                  onClick={() => navigate(`/billing/products/plan/${row.id}/edit`)}
                                >
                                  Edit
                                </button>
                                <button
                                  type="button"
                                  className="btn soft"
                                  disabled={busyId === `dup-${row.id}`}
                                  onClick={() => duplicatePlan(row)}
                                >
                                  Duplicate
                                </button>
                                <button
                                  type="button"
                                  className="btn soft"
                                  disabled={busyId === row.id}
                                  onClick={() => toggleActive(row)}
                                >
                                  {row.is_active ? 'Stop' : 'Activate'}
                                </button>
                                <button
                                  type="button"
                                  className="btn soft"
                                  disabled={busyId === `del-${row.id}`}
                                  onClick={() => deletePlan(row)}
                                >
                                  Delete
                                </button>
                              </>
                            ) : (
                              <>
                                <Link className="btn soft" to="/pricing/services">
                                  Edit pricing
                                </Link>
                                <button
                                  type="button"
                                  className="btn soft"
                                  disabled={busyId === row.id}
                                  onClick={() => toggleActive(row)}
                                >
                                  {row.is_active ? 'Stop' : 'Activate'}
                                </button>
                              </>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                    {!filtered.length ? (
                      <tr>
                        <td colSpan={7}>
                          <div className="productsEmpty">
                            No products in this view.
                            {tab === 'subscription' ? (
                              <>
                                {' '}
                                <button
                                  type="button"
                                  className="btn primary"
                                  style={{ marginTop: 12 }}
                                  onClick={() => navigate('/billing/products/plan/new')}
                                >
                                  Create subscription plan
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
