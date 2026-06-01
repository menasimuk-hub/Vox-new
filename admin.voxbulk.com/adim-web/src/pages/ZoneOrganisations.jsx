import React, { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { orgStatusPill, subscriptionLabel, zoneFromParam, ZONE_CONFIG } from '../lib/marketZone'

export default function ZoneOrganisations() {
  const { zone: zoneParam } = useParams()
  const zone = zoneFromParam(zoneParam)
  const navigate = useNavigate()
  const config = zone ? ZONE_CONFIG[zone] : null

  const [items, setItems] = useState(null)
  const [listError, setListError] = useState('')
  const [search, setSearch] = useState('')
  const [busy, setBusy] = useState(false)

  const title = useMemo(() => (config ? config.title : 'Zone'), [config])

  useEffect(() => {
    if (!zone) return
    let cancelled = false
    setListError('')
    setBusy(true)
    ;(async () => {
      try {
        const qs = new URLSearchParams()
        if (search.trim()) qs.set('search', search.trim())
        qs.set('zone', zone)
        qs.set('limit', '200')
        const data = await apiFetch(`/admin/organisations?${qs.toString()}`)
        if (!cancelled) setItems(Array.isArray(data) ? data : [])
      } catch (e) {
        if (!cancelled) {
          setItems([])
          setListError(e?.message || 'Could not load organisations')
        }
      } finally {
        if (!cancelled) setBusy(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [zone, search])

  if (!zone || !config) {
    return (
      <div className='card'>
        <div className='cardBody'>Unknown zone. Choose GB, USA, Canada, or Australia from the sidebar.</div>
      </div>
    )
  }

  return (
    <>
      {listError && (
        <div className='card alertCard'>
          <div className='cardBody alertText'>{listError}</div>
        </div>
      )}
      <div className='pageTop'>
        <div>
          <h1>
            {config.flag} {config.label}
          </h1>
          <p>
            Organisations registered in {title}. Tax, agents, and pricing follow this market zone.
          </p>
        </div>
        <div className='actions'>
          <button className='btn' type='button' disabled={busy} onClick={() => setSearch((s) => s)}>
            Refresh
          </button>
        </div>
      </div>

      <div className='card' style={{ marginBottom: 16 }}>
        <div className='cardBody'>
          <div className='filters'>
            <input
              className='input'
              placeholder={`Search ${title} organisations…`}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
        </div>
      </div>

      <div className='card'>
        <div className='cardHead'>
          <h3>{title} organisations</h3>
          <span className='pill p-cyan'>{items ? `${items.length}` : '—'}</span>
        </div>
        <div className='cardBody'>
          <div className='tableWrap'>
            <table className='table'>
              <thead>
                <tr>
                  <th>Organisation</th>
                  <th>Users</th>
                  <th>Subscription</th>
                  <th>Status</th>
                  <th>Wallet</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {(items || []).map((o) => {
                  const pill = orgStatusPill(o)
                  return (
                    <tr key={o.id}>
                      <td>
                        <div className='cellStack'>
                          <strong>{o.name}</strong>
                          <span className='muted cellSub'>
                            {o.city || o.country
                              ? `${o.city || ''}${o.city && o.country ? ', ' : ''}${o.country || ''}`
                              : o.contact_email || '—'}
                          </span>
                        </div>
                      </td>
                      <td>{o.user_count ?? 0}</td>
                      <td>
                        <div className='cellStack'>
                          <span>{o.plan_name || o.plan_code || '—'}</span>
                          <span className='muted cellSub'>{subscriptionLabel(o.subscription_status)}</span>
                        </div>
                      </td>
                      <td>
                        <span className={`pill ${pill.cls}`}>{pill.text}</span>
                      </td>
                      <td>{o.wallet_balance_display || '—'}</td>
                      <td>
                        <button
                          className='btn soft'
                          type='button'
                          onClick={() => {
                            localStorage.setItem('voxbulk_admin_selected_org_id', o.id)
                            navigate(`/organisations/${encodeURIComponent(o.id)}`)
                          }}
                        >
                          Edit
                        </button>
                      </td>
                    </tr>
                  )
                })}
                {!items && (
                  <tr>
                    <td colSpan={6}>Loading…</td>
                  </tr>
                )}
                {items && items.length === 0 && (
                  <tr>
                    <td colSpan={6}>No organisations in this zone yet.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </>
  )
}
