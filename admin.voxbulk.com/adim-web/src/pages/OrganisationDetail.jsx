import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { orgStatusPill, subscriptionLabel } from '../lib/marketZone'

function fmtWhen(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString()
}

function UsageMeter({ label, used, included, percent }) {
  const pct = Math.min(100, Number(percent || 0))
  return (
    <div className='usageMeter'>
      <div className='usageMeterHead'>
        <span>{label}</span>
        <span className='muted'>
          {used ?? 0} / {included ?? 0}
        </span>
      </div>
      <div className='usageMeterTrack'>
        <div className='usageMeterFill' style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

export default function OrganisationDetail() {
  const { orgId } = useParams()
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [loadError, setLoadError] = useState('')
  const [busy, setBusy] = useState(false)
  const [walletAmount, setWalletAmount] = useState('50')
  const [walletNote, setWalletNote] = useState('')
  const [walletBusy, setWalletBusy] = useState(false)

  const org = data?.organisation
  const pill = useMemo(() => orgStatusPill(org), [org])

  const refresh = useCallback(async () => {
    if (!orgId) return
    setLoadError('')
    setBusy(true)
    try {
      const res = await apiFetch(`/admin/organisations/${encodeURIComponent(orgId)}/operations`)
      setData(res)
    } catch (e) {
      setLoadError(e?.message || 'Could not load organisation')
      setData(null)
    } finally {
      setBusy(false)
    }
  }, [orgId])

  useEffect(() => {
    refresh()
  }, [refresh])

  const creditWallet = async () => {
    const gbp = Number(walletAmount)
    if (!Number.isFinite(gbp) || gbp <= 0) {
      window.alert('Enter a positive amount')
      return
    }
    setWalletBusy(true)
    try {
      await apiFetch(`/admin/organisations/${encodeURIComponent(orgId)}/wallet/credit`, {
        method: 'POST',
        body: JSON.stringify({
          amount_pence: Math.round(gbp * 100),
          note: walletNote.trim() || undefined,
        }),
      })
      setWalletNote('')
      await refresh()
    } catch (e) {
      window.alert(e?.message || 'Wallet top-up failed')
    } finally {
      setWalletBusy(false)
    }
  }

  const openProfile = () => {
    localStorage.setItem('voxbulk_admin_selected_org_id', orgId)
    navigate('/organisations/profile')
  }

  if (!orgId) {
    return (
      <div className='card'>
        <div className='cardBody'>Missing organisation id.</div>
      </div>
    )
  }

  return (
    <>
      {loadError && (
        <div className='card alertCard'>
          <div className='cardBody alertText'>{loadError}</div>
        </div>
      )}

      <div className='pageTop'>
        <div>
          <div className='breadcrumb muted' style={{ marginBottom: 8, fontSize: 13 }}>
            <Link to='/organisations'>Organisations</Link>
            {org?.market_zone ? (
              <>
                {' '}
                /{' '}
                <Link to={`/organisations/zone/${org.market_zone}`}>{org.market_label || org.market_zone}</Link>
              </>
            ) : null}{' '}
            / {org?.name || '…'}
          </div>
          <h1>{org?.name || 'Organisation'}</h1>
          <p>
            {org?.market_label || '—'}
            {org?.city || org?.country ? ` · ${[org.city, org.country].filter(Boolean).join(', ')}` : ''}
          </p>
        </div>
        <div className='actions'>
          <button className='btn' type='button' disabled={busy} onClick={refresh}>
            {busy ? 'Loading…' : 'Refresh'}
          </button>
          <button className='btn soft' type='button' onClick={openProfile}>
            Full profile
          </button>
        </div>
      </div>

      <div className='grid-4' style={{ marginBottom: 16 }}>
        <div className='card stat'>
          <div className='statValue'>{org?.user_count ?? '—'}</div>
          <div className='muted'>Users</div>
        </div>
        <div className='card stat'>
          <div className='statValue'>{org?.plan_name || org?.plan_code || '—'}</div>
          <div className='muted'>{subscriptionLabel(org?.subscription_status)}</div>
        </div>
        <div className='card stat'>
          <div className='statValue'>
            <span className={`pill ${pill.cls}`}>{pill.text}</span>
          </div>
          <div className='muted'>Account status</div>
        </div>
        <div className='card stat'>
          <div className='statValue'>{org?.wallet_balance_display || '—'}</div>
          <div className='muted'>Wallet balance</div>
        </div>
      </div>

      <div className='card' style={{ marginBottom: 16 }}>
        <div className='cardHead'>
          <h3>Finance summary</h3>
          {data?.subscription_finance?.cancel_at_period_end ? <span className='pill p-amber'>Cancel at period end</span> : null}
        </div>
        <div className='cardBody detailGrid'>
          <div>
            <span className='muted'>Plan</span>
            <div>{org?.plan_name || org?.plan_code || '—'}</div>
          </div>
          <div>
            <span className='muted'>Next billing</span>
            <div>{data?.subscription_finance?.next_billing_date ? fmtWhen(data.subscription_finance.next_billing_date) : '—'}</div>
          </div>
          <div>
            <span className='muted'>Next charge</span>
            <div>{data?.subscription_finance?.amount_next_payment_display || '—'}</div>
          </div>
          <div>
            <span className='muted'>Cancellation</span>
            <div>{data?.cancellation_preview?.status || data?.subscription_finance?.cancellation_status || 'none'}</div>
          </div>
        </div>
        <div className='cardBody' style={{ paddingTop: 0 }}>
          <div className='actions' style={{ flexWrap: 'wrap' }}>
            <button type='button' className='btn soft' onClick={openProfile}>Full profile (plan)</button>
            <Link className='btn soft' to='/organisations/all-users' onClick={() => localStorage.setItem('voxbulk_admin_selected_org_id', orgId)}>Finance console</Link>
          </div>
        </div>
      </div>

      <div className='grid-2' style={{ marginBottom: 16, alignItems: 'start' }}>
        <div className='card'>
          <div className='cardHead'>
            <h3>Contact & billing</h3>
          </div>
          <div className='cardBody detailGrid'>
            <div>
              <span className='muted'>Contact</span>
              <div>{org?.contact_name || '—'}</div>
            </div>
            <div>
              <span className='muted'>Email</span>
              <div>{org?.contact_email || '—'}</div>
            </div>
            <div>
              <span className='muted'>Phone</span>
              <div>{org?.contact_phone || '—'}</div>
            </div>
            <div>
              <span className='muted'>Created</span>
              <div>{fmtWhen(org?.created_at)}</div>
            </div>
            <div>
              <span className='muted'>Branches</span>
              <div>{org?.branch_count ?? 0}</div>
            </div>
          </div>
        </div>

        <div className='card'>
          <div className='cardHead'>
            <h3>Top up wallet</h3>
          </div>
          <div className='cardBody'>
            <p className='muted' style={{ marginBottom: 12, fontSize: 14 }}>
              Credit this organisation&apos;s prepaid wallet ({org?.currency_symbol || '£'} amounts stored as GBP pence
              base).
            </p>
            <div className='filters' style={{ marginBottom: 12 }}>
              <input
                className='input'
                type='number'
                min='0'
                step='0.01'
                value={walletAmount}
                onChange={(e) => setWalletAmount(e.target.value)}
                placeholder='Amount'
              />
              <input
                className='input'
                value={walletNote}
                onChange={(e) => setWalletNote(e.target.value)}
                placeholder='Note (optional)'
              />
            </div>
            <button className='btn primary' type='button' disabled={walletBusy} onClick={creditWallet}>
              {walletBusy ? 'Crediting…' : 'Credit wallet'}
            </button>
          </div>
        </div>
      </div>

      <div className='card' style={{ marginBottom: 16 }}>
        <div className='cardHead'>
          <h3>Usage this period</h3>
          {data?.usage?.period_start ? (
            <span className='muted' style={{ fontSize: 13 }}>
              {fmtWhen(data.usage.period_start)} → {fmtWhen(data.usage.period_end)}
            </span>
          ) : null}
        </div>
        <div className='cardBody'>
          {!data?.usage && <p className='muted'>No usage record for the current billing period.</p>}
          {data?.usage ? (
            <div className='usageGrid'>
              <UsageMeter label='Calls' {...data.usage.calls} />
              <UsageMeter label='WhatsApp' {...data.usage.whatsapp} />
              <UsageMeter label='SMS' {...data.usage.sms} />
              <div className='usageMeter'>
                <div className='usageMeterHead'>
                  <span>Pack credits</span>
                  <span className='muted'>
                    {data.usage.pack_credits?.used ?? 0} / {data.usage.pack_credits?.included ?? 0}
                  </span>
                </div>
              </div>
              {data.usage.estimated_overage_gbp != null ? (
                <p className='muted' style={{ fontSize: 13 }}>
                  Estimated overage: {org?.currency_symbol || '£'}
                  {Number(data.usage.estimated_overage_gbp).toFixed(2)}
                </p>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>

      <div className='card' style={{ marginBottom: 16 }}>
        <div className='cardHead'>
          <h3>Running tasks</h3>
          <span className='pill p-cyan'>{data?.running_orders?.length ?? 0}</span>
        </div>
        <div className='cardBody'>
          <div className='tableWrap'>
            <table className='table'>
              <thead>
                <tr>
                  <th>Service</th>
                  <th>Title</th>
                  <th>Status</th>
                  <th>Payment</th>
                  <th>Updated</th>
                </tr>
              </thead>
              <tbody>
                {(data?.running_orders || []).map((o) => (
                  <tr key={o.id}>
                    <td>{o.service_code || '—'}</td>
                    <td>{o.title || o.id}</td>
                    <td>{o.status || '—'}</td>
                    <td>{o.payment_status || '—'}</td>
                    <td>{fmtWhen(o.updated_at || o.created_at)}</td>
                  </tr>
                ))}
                {data && (!data.running_orders || data.running_orders.length === 0) && (
                  <tr>
                    <td colSpan={5}>No running or draft tasks.</td>
                  </tr>
                )}
                {!data && (
                  <tr>
                    <td colSpan={5}>Loading…</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className='grid-2' style={{ alignItems: 'start' }}>
        <div className='card'>
          <div className='cardHead'>
            <h3>Users</h3>
            <span className='pill p-cyan'>{data?.users?.length ?? 0}</span>
          </div>
          <div className='cardBody'>
            <div className='tableWrap'>
              <table className='table'>
                <thead>
                  <tr>
                    <th>Email</th>
                    <th>Role</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {(data?.users || []).map((u) => (
                    <tr key={u.user_id}>
                      <td>{u.email}</td>
                      <td>{u.role || '—'}</td>
                      <td>{u.is_active ? 'Active' : 'Blocked'}</td>
                    </tr>
                  ))}
                  {data && (!data.users || data.users.length === 0) && (
                    <tr>
                      <td colSpan={3}>No users linked.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <div className='card'>
          <div className='cardHead'>
            <h3>Invoices</h3>
            <span className='pill p-cyan'>{data?.invoices?.length ?? 0}</span>
          </div>
          <div className='cardBody'>
            <div className='tableWrap'>
              <table className='table'>
                <thead>
                  <tr>
                    <th>Number</th>
                    <th>Status</th>
                    <th>Total</th>
                    <th>Date</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {(data?.invoices || []).map((inv) => (
                    <tr key={inv.id}>
                      <td>{inv.invoice_number || inv.id}</td>
                      <td>{inv.status || '—'}</td>
                      <td>{inv.total_display || inv.total_gbp || '—'}</td>
                      <td>{fmtWhen(inv.created_at)}</td>
                      <td>
                        <Link
                          className='btn soft xs'
                          to='/organisations/all-users'
                          onClick={() => localStorage.setItem('voxbulk_admin_selected_org_id', orgId)}
                        >
                          In OCC
                        </Link>
                      </td>
                    </tr>
                  ))}
                  {data && (!data.invoices || data.invoices.length === 0) && (
                    <tr>
                      <td colSpan={5}>No invoices yet.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>

      {data?.recent_orders?.length > 0 ? (
        <div className='card' style={{ marginTop: 16 }}>
          <div className='cardHead'>
            <h3>Recent service orders</h3>
          </div>
          <div className='cardBody'>
            <div className='tableWrap'>
              <table className='table'>
                <thead>
                  <tr>
                    <th>Service</th>
                    <th>Title</th>
                    <th>Status</th>
                    <th>Created</th>
                  </tr>
                </thead>
                <tbody>
                  {data.recent_orders.map((o) => (
                    <tr key={o.id}>
                      <td>{o.service_code}</td>
                      <td>{o.title || o.id}</td>
                      <td>{o.status}</td>
                      <td>{fmtWhen(o.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      ) : null}
    </>
  )
}
