import React, { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import './salesTeam.css'

/* Same SVG icons as sales-team-dashboard.html */
const IconEdit = () => (
  <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2'><path d='M12 20h9' /><path d='M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z' /></svg>
)
const IconReset = () => (
  <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2'><path d='M3 12a9 9 0 1 0 2.6-6.3' /><path d='M3 4v5h5' /></svg>
)
const IconDelete = () => (
  <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2'><path d='M3 6h18' /><path d='M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2' /><path d='M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6' /><path d='M10 11v6M14 11v6' /></svg>
)
const IconFreeze = () => (
  <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2'><path d='M12 2v20M4.9 4.9l14.2 14.2M19.1 4.9 4.9 19.1M2 12h20' /></svg>
)
const IconUnfreeze = () => (
  <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2'><circle cx='12' cy='12' r='10' /><path d='M9 12l2 2 4-4' /></svg>
)
const IconProfile = () => (
  <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2'><path d='M4 20c0-3.3 3.6-5.5 8-5.5s8 2.2 8 5.5' /><circle cx='12' cy='8' r='4' /></svg>
)
const IconSearch = () => (
  <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2'><circle cx='11' cy='11' r='7' /><path d='M21 21l-4.3-4.3' /></svg>
)
const IconPlus = () => (
  <svg width='15' height='15' viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2.4'><path d='M12 5v14M5 12h14' /></svg>
)
const IconClose = () => (
  <svg width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2'><path d='M18 6L6 18M6 6l12 12' /></svg>
)
const IconBack = () => (
  <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2'><path d='M15 18l-6-6 6-6' /></svg>
)
const IconEmptyPeople = () => (
  <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='1.5'><path d='M17 21v-2a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v2' /><circle cx='10' cy='7' r='4' /></svg>
)

function money(minor) {
  const n = Number(minor || 0) / 100
  return `£${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function genPassword() {
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#'
  let out = 'Temp#'
  for (let i = 0; i < 6; i++) out += chars[Math.floor(Math.random() * chars.length)]
  return out
}

function tabFromPath(pathname, search) {
  const q = new URLSearchParams(search || '')
  if (q.get('tab') === 'partners' || String(pathname || '').includes('partner-channel')) return 'partners'
  return 'salesman'
}

function commLabel(rep) {
  const t = String(rep.commission_type || 'month2')
  if (t === 'month2') return `2nd Month · ${Number(rep.commission_pct || 0)}%`
  if (t === 'fixed') return `On Payment · ${money(rep.commission_fixed_minor)}`
  return `On Payment · ${Number(rep.commission_pct || 0)}%`
}

function commBadgeClass(rep) {
  const t = String(rep.commission_type || 'month2')
  if (t === 'month2') return 'badge-comm'
  if (t === 'fixed') return 'badge-comm2'
  return 'badge-comm3'
}

function commTypeFullLabel(rep) {
  const t = String(rep.commission_type || 'month2')
  if (t === 'month2') return 'Paid on 2nd Month (%)'
  if (t === 'fixed') return 'Paid When Customer Pays — Fixed'
  return 'Paid When Customer Pays — Percentage'
}

function commValueLabel(rep) {
  if (String(rep.commission_type || '') === 'fixed') return money(rep.commission_fixed_minor)
  return `${Number(rep.commission_pct || 0)}%`
}

const EMPTY_FORM = {
  name: '',
  email: '',
  password: '',
  mobile: '',
  promo_code: '',
  company_name: '',
  commission_type: 'month2',
  commission_pct: '',
  commission_fixed_gbp: '',
  payout_method: 'bank',
  bank_holder_name: '',
  bank_name: '',
  bank_sort_code: '',
  bank_account_number: '',
  bank_address: '',
  paypal_email: '',
}

export default function SalesTeam() {
  const location = useLocation()
  const navigate = useNavigate()
  const [tab, setTab] = useState(() => tabFromPath(location.pathname, location.search))
  const [reps, setReps] = useState([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [search, setSearch] = useState('')
  const [toast, setToast] = useState('')

  const [showForm, setShowForm] = useState(false)
  const [editId, setEditId] = useState(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [formErr, setFormErr] = useState('')

  const [pwRep, setPwRep] = useState(null)
  const [pwValue, setPwValue] = useState('')

  const [profileRep, setProfileRep] = useState(null)
  const [profile, setProfile] = useState(null)
  const [invoiceOpen, setInvoiceOpen] = useState(null)

  const kind = tab === 'partners' ? 'partner_channel' : 'salesman'

  const showToast = (msg) => {
    setToast(msg)
    window.setTimeout(() => setToast(''), 2600)
  }

  const load = async () => {
    setLoading(true)
    try {
      const res = await apiFetch(`/admin/sales-reps?kind=${kind}`)
      setReps(res?.items || [])
    } catch (e) {
      showToast(e?.message || 'Failed to load')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    setTab(tabFromPath(location.pathname, location.search))
  }, [location.pathname, location.search])

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab])

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return reps
    return reps.filter((r) =>
      [r.name, r.email, r.mobile, r.promo_code].some((v) => String(v || '').toLowerCase().includes(q))
    )
  }, [reps, search])

  const switchTab = (next) => {
    setTab(next)
    setProfileRep(null)
    setProfile(null)
    setInvoiceOpen(null)
    setSearch('')
    navigate(next === 'partners' ? '/marketing/partner-channel-sales' : '/marketing/salesmen')
  }

  const openAdd = () => {
    setEditId(null)
    setForm({
      ...EMPTY_FORM,
      commission_type: tab === 'partners' ? 'percent' : 'month2',
      password: genPassword(),
      payout_method: 'bank',
    })
    setFormErr('')
    setShowForm(true)
  }

  const openEdit = (rep) => {
    const p = rep.payout || {}
    setEditId(rep.id)
    setForm({
      name: rep.name || '',
      email: rep.email || '',
      password: '',
      mobile: rep.mobile || '',
      promo_code: rep.promo_code || '',
      company_name: rep.company_name || '',
      commission_type: rep.commission_type || 'month2',
      commission_pct: String(rep.commission_pct ?? ''),
      commission_fixed_gbp: rep.commission_fixed_minor != null ? String(Number(rep.commission_fixed_minor) / 100) : '',
      payout_method: p.payout_method || 'bank',
      bank_holder_name: p.bank_holder_name || '',
      bank_name: p.bank_name || '',
      bank_sort_code: p.bank_sort_code || '',
      bank_account_number: p.bank_account_number || '',
      bank_address: p.bank_address || '',
      paypal_email: p.paypal_email || '',
    })
    setFormErr('')
    setShowForm(true)
  }

  const saveForm = async () => {
    setBusy(true)
    setFormErr('')
    const fixedMinor = form.commission_type === 'fixed'
      ? Math.round(parseFloat(form.commission_fixed_gbp || '0') * 100)
      : 0
    const payload = {
      name: form.name,
      email: form.email,
      password: form.password,
      mobile: form.mobile,
      promo_code: form.promo_code,
      company_name: form.company_name,
      kind,
      commission_type: form.commission_type,
      commission_pct: form.commission_pct || '15',
      commission_fixed_minor: fixedMinor,
      payout: {
        payout_method: form.payout_method,
        bank_holder_name: form.bank_holder_name,
        bank_name: form.bank_name,
        bank_sort_code: form.bank_sort_code,
        bank_account_number: form.bank_account_number,
        bank_address: form.bank_address,
        paypal_email: form.paypal_email,
      },
    }
    try {
      if (editId) {
        const patch = { ...payload }
        delete patch.email
        delete patch.password
        delete patch.kind
        await apiFetch(`/admin/sales-reps/${editId}`, { method: 'PATCH', body: JSON.stringify(patch) })
        showToast('Saved')
      } else {
        if (!form.commission_type) {
          setFormErr('Please select a commission type.')
          setBusy(false)
          return
        }
        if (!form.payout_method) {
          setFormErr('Please select a payout method.')
          setBusy(false)
          return
        }
        await apiFetch('/admin/sales-reps', { method: 'POST', body: JSON.stringify(payload) })
        showToast('Created')
      }
      setShowForm(false)
      await load()
      if (profileRep && editId === profileRep.id) await openProfile(profileRep)
    } catch (e) {
      setFormErr(e?.message || 'Save failed')
    } finally {
      setBusy(false)
    }
  }

  const resetPassword = async () => {
    if (!pwRep) return
    setBusy(true)
    try {
      await apiFetch(`/admin/sales-reps/${pwRep.id}/reset-password`, {
        method: 'POST',
        body: JSON.stringify({ password: pwValue }),
      })
      showToast('Password reset')
      setPwRep(null)
      setPwValue('')
    } catch (e) {
      showToast(e?.message || 'Reset failed')
    } finally {
      setBusy(false)
    }
  }

  const toggleFreeze = async (rep) => {
    setBusy(true)
    try {
      await apiFetch(`/admin/sales-reps/${rep.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ is_active: !rep.is_active }),
      })
      showToast(`${rep.name} ${rep.is_active ? 'has been frozen.' : 'has been reactivated.'}`)
      await load()
      if (profileRep?.id === rep.id) await openProfile({ ...rep, is_active: !rep.is_active })
    } catch (e) {
      showToast(e?.message || 'Update failed')
    } finally {
      setBusy(false)
    }
  }

  const deleteRep = async (rep) => {
    if (!window.confirm(`Delete ${rep.name}? This cannot be undone.`)) return
    setBusy(true)
    try {
      await apiFetch(`/admin/sales-reps/${rep.id}`, { method: 'DELETE' })
      showToast(`${rep.name} was deleted.`)
      if (profileRep?.id === rep.id) {
        setProfileRep(null)
        setProfile(null)
      }
      await load()
    } catch (e) {
      showToast(e?.message || 'Delete failed')
    } finally {
      setBusy(false)
    }
  }

  const openProfile = async (rep) => {
    setProfileRep(rep)
    setInvoiceOpen(null)
    try {
      const res = await apiFetch(`/admin/sales-reps/${rep.id}/dashboard`)
      setProfile(res)
      if (res?.rep) setProfileRep(res.rep)
    } catch (e) {
      showToast(e?.message || 'Failed to load profile')
    }
  }

  const openInvoice = async (invoiceId) => {
    try {
      const res = await apiFetch(`/admin/sales-reps/payout-invoices/${invoiceId}`)
      setInvoiceOpen(res?.invoice || null)
    } catch (e) {
      showToast(e?.message || 'Failed to open invoice')
    }
  }

  const approvePay = async (invoiceId) => {
    if (!window.confirm('Approve this invoice and mark as paid?')) return
    setBusy(true)
    try {
      await apiFetch(`/admin/sales-reps/payout-invoices/${invoiceId}/approve-pay`, { method: 'POST', body: '{}' })
      showToast('Approved and marked as paid.')
      setInvoiceOpen(null)
      if (profileRep) await openProfile(profileRep)
    } catch (e) {
      showToast(e?.message || 'Approve failed')
    } finally {
      setBusy(false)
    }
  }

  const rejectInvoice = async (invoiceId) => {
    if (!window.confirm('Reject this invoice? Commission returns to available.')) return
    setBusy(true)
    try {
      await apiFetch(`/admin/sales-reps/payout-invoices/${invoiceId}/reject`, {
        method: 'POST',
        body: JSON.stringify({ reason: '' }),
      })
      showToast('Invoice rejected.')
      setInvoiceOpen(null)
      if (profileRep) await openProfile(profileRep)
    } catch (e) {
      showToast(e?.message || 'Reject failed')
    } finally {
      setBusy(false)
    }
  }

  const renderTable = (typeKey) => {
    const emptyLabel = typeKey === 'salesman'
      ? 'No salesmen yet. Click "Add Sales Man" to create one.'
      : 'No sales partners yet. Click "Add Sales Partner" to create one.'
    return (
      <section className={`panel ${tab === typeKey ? 'active' : ''}`}>
        <div className='toolbar'>
          <div className='search-box'>
            <IconSearch />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={typeKey === 'salesman' ? 'Search salesman...' : 'Search partners...'}
            />
          </div>
          <button type='button' className='btn btn-primary' onClick={openAdd}>
            <IconPlus />
            {typeKey === 'salesman' ? 'Add Sales Man' : 'Add Sales Partner'}
          </button>
        </div>
        <div className='table-card'>
          {loading ? (
            <div className='empty-state'>Loading…</div>
          ) : filtered.length === 0 ? (
            <div className='empty-state'>
              <IconEmptyPeople />
              <div>{emptyLabel}</div>
            </div>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Mobile</th>
                  <th>Commission</th>
                  <th>Promo Code</th>
                  <th>Status</th>
                  <th style={{ textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((rep) => (
                  <tr key={rep.id} className={rep.is_active ? '' : 'frozen'}>
                    <td data-label='Name'>
                      <div className='person-cell'>
                        <div>
                          <div className='person-name'>{rep.name}</div>
                          <div className='person-email'>{rep.email}</div>
                        </div>
                      </div>
                    </td>
                    <td data-label='Mobile'>{rep.mobile || '—'}</td>
                    <td data-label='Commission'>
                      <span className={`badge ${commBadgeClass(rep)}`}>{commLabel(rep)}</span>
                    </td>
                    <td data-label='Promo Code'><span className='promo-tag'>{rep.promo_code || '—'}</span></td>
                    <td data-label='Status'>
                      {rep.is_active
                        ? <span className='badge badge-active'>Active</span>
                        : <span className='badge badge-frozen'>Frozen</span>}
                    </td>
                    <td data-label='Actions'>
                      <div className='actions' style={{ justifyContent: 'flex-end' }}>
                        <button type='button' className='icon-btn profile' title='Profile & commission' onClick={() => openProfile(rep)}><IconProfile /></button>
                        <button type='button' className='icon-btn edit' title='Edit' onClick={() => openEdit(rep)}><IconEdit /></button>
                        <button type='button' className='icon-btn reset' title='Reset password' onClick={() => { setPwRep(rep); setPwValue(genPassword()) }}><IconReset /></button>
                        <button type='button' className='icon-btn freeze' title={rep.is_active ? 'Freeze' : 'Unfreeze'} onClick={() => toggleFreeze(rep)}>
                          {rep.is_active ? <IconFreeze /> : <IconUnfreeze />}
                        </button>
                        <button type='button' className='icon-btn delete' title='Delete' onClick={() => deleteRep(rep)}><IconDelete /></button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>
    )
  }

  if (profileRep && profile) {
    const stats = profile.stats || {}
    const wallet = stats.wallet || {}
    const payout = stats.payout || profileRep.payout || {}
    const invoices = stats.payout_invoices || []
    const commissions = stats.commissions || []
    const joined = (profileRep.created_at || '').slice(0, 10)

    return (
      <div className='stm'>
        <div className='wrap wide'>
          <button type='button' className='back-link' onClick={() => { setProfileRep(null); setProfile(null); setInvoiceOpen(null) }}>
            <IconBack /> Back to list
          </button>

          <div className='profile-top'>
            <div className='profile-id'>
              <div>
                <h2>{profileRep.name}</h2>
                <div className='meta'>
                  <span>{profileRep.email}</span>
                  <span>{profileRep.mobile || '—'}</span>
                  <span>
                    {profileRep.is_active
                      ? <span className='badge badge-active'>Active</span>
                      : <span className='badge badge-frozen'>Frozen</span>}
                  </span>
                </div>
              </div>
            </div>
            <div className='profile-top-actions'>
              <button type='button' className='icon-btn edit' title='Edit' onClick={() => openEdit(profileRep)}><IconEdit /></button>
              <button type='button' className='icon-btn reset' title='Reset password' onClick={() => { setPwRep(profileRep); setPwValue(genPassword()) }}><IconReset /></button>
              <button type='button' className='icon-btn freeze' title={profileRep.is_active ? 'Freeze' : 'Unfreeze'} onClick={() => toggleFreeze(profileRep)}>
                {profileRep.is_active ? <IconFreeze /> : <IconUnfreeze />}
              </button>
              <button type='button' className='icon-btn delete' title='Delete' onClick={() => deleteRep(profileRep)}><IconDelete /></button>
            </div>
          </div>

          <div className='stat-grid'>
            <div className='stat-box'>
              <div className='label'>Total Sales</div>
              <div className='value'>{money(wallet.revenue_minor)}</div>
            </div>
            <div className='stat-box'>
              <div className='label'>Total Commission</div>
              <div className='value'>{money(wallet.commission_minor)}</div>
            </div>
            <div className='stat-box paid'>
              <div className='label'>Paid</div>
              <div className='value'>{money(wallet.commission_paid_minor)}</div>
            </div>
            <div className='stat-box requested'>
              <div className='label'>Awaiting Approval</div>
              <div className='value'>{money(wallet.commission_requested_minor)}</div>
            </div>
            <div className='stat-box pending'>
              <div className='label'>No Invoice Yet</div>
              <div className='value'>{money(wallet.commission_available_minor)}</div>
            </div>
          </div>

          <div className='profile-grid'>
            <div>
              <div className='profile-card'>
                <h3>Payout Details</h3>
                {payout.payout_method === 'paypal' ? (
                  <>
                    <div className='profile-row'><span className='k'>Method</span><span className='v'>PayPal</span></div>
                    <div className='profile-row'><span className='k'>PayPal Email</span><span className='v'>{payout.paypal_email || '—'}</span></div>
                  </>
                ) : (
                  <>
                    <div className='profile-row'><span className='k'>Method</span><span className='v'>Bank Account</span></div>
                    <div className='profile-row'><span className='k'>Account Holder</span><span className='v'>{payout.bank_holder_name || '—'}</span></div>
                    <div className='profile-row'><span className='k'>Bank</span><span className='v'>{payout.bank_name || '—'}</span></div>
                    <div className='profile-row'><span className='k'>Sort code</span><span className='v'>{payout.bank_sort_code || '—'}</span></div>
                    <div className='profile-row'>
                      <span className='k'>Account number</span>
                      <span className='v' style={{ fontFamily: "'SF Mono',Menlo,monospace", fontSize: 12.5 }}>{payout.bank_account_number || '—'}</span>
                    </div>
                    {payout.bank_address ? (
                      <div className='profile-row'><span className='k'>Address</span><span className='v'>{payout.bank_address}</span></div>
                    ) : null}
                  </>
                )}
                <h3 style={{ marginTop: 20 }}>Commission Setup</h3>
                <div className='profile-row'><span className='k'>Type</span><span className='v'>{commTypeFullLabel(profileRep)}</span></div>
                <div className='profile-row'><span className='k'>Value</span><span className='v'>{commValueLabel(profileRep)}</span></div>
                <div className='profile-row'><span className='k'>Promo Code</span><span className='v'>{profileRep.promo_code || '—'}</span></div>
                <h3 style={{ marginTop: 20 }}>Account</h3>
                <div className='profile-row'><span className='k'>Status</span><span className='v'>{profileRep.is_active ? 'Active' : 'Frozen'}</span></div>
                <div className='profile-row'><span className='k'>Joined</span><span className='v'>{joined || '—'}</span></div>
              </div>
            </div>

            <div className='profile-card'>
              <div className='comm-history-head'>
                <h3>Commission &amp; Invoices</h3>
              </div>
              <div className='table-card' style={{ boxShadow: 'none' }}>
                <table>
                  <thead>
                    <tr>
                      <th>Invoice</th>
                      <th>Amount</th>
                      <th>Status</th>
                      <th style={{ textAlign: 'right' }}>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {invoices.length === 0 ? (
                      <tr><td colSpan={4} className='empty-state' style={{ padding: '34px 20px' }}>No payout invoices yet.</td></tr>
                    ) : invoices.map((inv) => (
                      <tr key={inv.id}>
                        <td data-label='Invoice'>
                          {inv.invoice_number}
                          <span className='invoice-no'>{(inv.submitted_at || '').slice(0, 10)}</span>
                        </td>
                        <td data-label='Amount'>{inv.amount_display || money(inv.amount_minor)}</td>
                        <td data-label='Status'>
                          {inv.status === 'paid' ? <span className='badge badge-paid'>Paid{(inv.resolved_at ? ` · ${String(inv.resolved_at).slice(0, 10)}` : '')}</span>
                            : inv.status === 'submitted' ? <span className='badge badge-requested'>Awaiting Approval</span>
                              : inv.status === 'rejected' ? <span className='badge badge-rejected'>Rejected</span>
                                : <span className='badge badge-pending'>{inv.status}</span>}
                        </td>
                        <td data-label='Action'>
                          <div className='action-stack'>
                            <button type='button' className='mark-btn to-invoice' onClick={() => openInvoice(inv.id)}>Open</button>
                            {inv.status === 'submitted' ? (
                              <>
                                <button type='button' className='mark-btn to-paid' disabled={busy} onClick={() => approvePay(inv.id)}>Approve &amp; Pay</button>
                                <button type='button' className='mark-btn to-reject' disabled={busy} onClick={() => rejectInvoice(inv.id)}>Reject</button>
                              </>
                            ) : null}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {invoiceOpen ? (
                <div style={{ marginTop: 14, padding: 14, border: '1px solid var(--border)', borderRadius: 10, background: 'var(--panel-soft)' }}>
                  <strong>{invoiceOpen.invoice_number}</strong>
                  <div style={{ marginTop: 6, fontSize: 13.5 }}>{invoiceOpen.amount_display || money(invoiceOpen.amount_minor)}</div>
                  <div style={{ marginTop: 6, fontSize: 13, color: 'var(--ink-soft)' }}>{invoiceOpen.payout_method_summary}</div>
                  {invoiceOpen.notes ? <div style={{ marginTop: 8, fontSize: 13.5 }}>Notes: {invoiceOpen.notes}</div> : null}
                  {invoiceOpen.payout_snapshot ? (
                    <div style={{ marginTop: 10, fontSize: 12.5 }}>
                      {Object.entries(invoiceOpen.payout_snapshot).filter(([, v]) => v).map(([k, v]) => (
                        <div key={k} className='profile-row'><span className='k'>{k}</span><span className='v'>{String(v)}</span></div>
                      ))}
                    </div>
                  ) : null}
                </div>
              ) : null}

              <div className='comm-history-head' style={{ marginTop: 22 }}>
                <h3>Commission ledger</h3>
              </div>
              <div className='table-card' style={{ boxShadow: 'none' }}>
                <table>
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th>Customer</th>
                      <th>Commission</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {commissions.length === 0 ? (
                      <tr><td colSpan={4} className='empty-state' style={{ padding: '34px 20px' }}>No commission records yet.</td></tr>
                    ) : commissions.map((c) => (
                      <tr key={c.id}>
                        <td data-label='Date'>{(c.created_at || '').slice(0, 10)}</td>
                        <td data-label='Customer'>{c.org_name || c.org_id}</td>
                        <td data-label='Commission'>{money(c.amount_minor)}</td>
                        <td data-label='Status'>
                          {c.status === 'paid' ? <span className='badge badge-paid'>Paid</span>
                            : c.status === 'requested' ? <span className='badge badge-requested'>Awaiting Approval</span>
                              : <span className='badge badge-pending'>No Invoice Yet</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>

        {renderModals()}
        <div className={`toast ${toast ? 'show' : ''}`}>{toast}</div>
      </div>
    )
  }

  function renderModals() {
    return (
      <>
        <div className={`modal-overlay ${showForm ? 'active' : ''}`}>
          <div className='modal'>
            <div className='modal-head'>
              <h2>{editId ? (tab === 'salesman' ? 'Edit Sales Man' : 'Edit Sales Partner') : (tab === 'salesman' ? 'Add Sales Man' : 'Add Sales Partner')}</h2>
              <button type='button' className='modal-close' onClick={() => setShowForm(false)}><IconClose /></button>
            </div>
            <div className='modal-body'>
              {formErr ? <p className='form-error'>{formErr}</p> : null}
              <div className='field'>
                <label>Full Name</label>
                <input type='text' value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder='e.g. Ahmed Khaled' />
              </div>
              {!editId ? (
                <>
                  <div className='field'>
                    <label>Email</label>
                    <input type='email' value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder='name@company.com' />
                  </div>
                  <div className='field'>
                    <label>Temporary Password <span className='hint'>shared with them at first login</span></label>
                    <div className='pw-row'>
                      <input type='text' value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
                      <button type='button' className='btn btn-ghost pw-gen' onClick={() => setForm({ ...form, password: genPassword() })}>Generate</button>
                    </div>
                  </div>
                </>
              ) : null}
              <div className='field'>
                <label>Mobile Number</label>
                <input type='tel' value={form.mobile} onChange={(e) => setForm({ ...form, mobile: e.target.value })} placeholder='+44 7700 900123' />
              </div>

              <div className='field'>
                <label>Commission Type</label>
                <div className='comm-options'>
                  {[
                    { id: 'month2', title: 'Paid on 2nd Month (%)', desc: 'Held and paid out one month after the customer pays, as a percentage of the sale.', suffix: '%' },
                    { id: 'fixed', title: 'Paid When Customer Pays — Fixed Amount', desc: 'Released as soon as the customer pays, as a flat amount per sale.', suffix: 'GBP' },
                    { id: 'percent', title: 'Paid When Customer Pays — Percentage', desc: 'Released as soon as the customer pays, as a percentage of the sale.', suffix: '%' },
                  ].map((opt) => (
                    <label key={opt.id} className={`comm-option ${form.commission_type === opt.id ? 'selected' : ''}`} id={`opt-${opt.id}`}>
                      <input
                        type='radio'
                        name='commtype'
                        checked={form.commission_type === opt.id}
                        onChange={() => setForm({ ...form, commission_type: opt.id })}
                      />
                      <div>
                        <div className='co-title'>{opt.title}</div>
                        <div className='co-desc'>{opt.desc}</div>
                        <div className={`comm-value-row ${form.commission_type === opt.id ? 'active' : ''}`}>
                          <div className='suffix-input'>
                            {opt.id === 'fixed' ? (
                              <input
                                type='number'
                                min='0'
                                step='0.01'
                                placeholder='e.g. 250'
                                value={form.commission_fixed_gbp}
                                onChange={(e) => setForm({ ...form, commission_fixed_gbp: e.target.value })}
                              />
                            ) : (
                              <input
                                type='number'
                                min='0'
                                max='100'
                                step='0.1'
                                placeholder='e.g. 10'
                                value={form.commission_pct}
                                onChange={(e) => setForm({ ...form, commission_pct: e.target.value })}
                              />
                            )}
                            <span>{opt.suffix}</span>
                          </div>
                        </div>
                      </div>
                    </label>
                  ))}
                </div>
              </div>

              <div className='field'>
                <label>Promo Code</label>
                <input type='text' value={form.promo_code} onChange={(e) => setForm({ ...form, promo_code: e.target.value.toUpperCase() })} placeholder='e.g. AHMED10' style={{ textTransform: 'uppercase' }} />
              </div>

              <div className='field'>
                <label>Payout Method <span className='hint'>where you'll wire their money</span></label>
                <div className='comm-options'>
                  <label className={`comm-option ${form.payout_method === 'bank' ? 'selected' : ''}`}>
                    <input type='radio' name='paytype' checked={form.payout_method === 'bank'} onChange={() => setForm({ ...form, payout_method: 'bank' })} />
                    <div style={{ flex: 1 }}>
                      <div className='co-title'>Bank Account</div>
                      <div className={`comm-value-row ${form.payout_method === 'bank' ? 'active' : ''}`}>
                        <div className='field' style={{ marginBottom: 10 }}>
                          <label style={{ fontSize: 11.5 }}>Account Holder / Company Name</label>
                          <input type='text' value={form.bank_holder_name} onChange={(e) => setForm({ ...form, bank_holder_name: e.target.value })} placeholder='Name on the account' />
                        </div>
                        <div className='field' style={{ marginBottom: 10 }}>
                          <label style={{ fontSize: 11.5 }}>Bank Name</label>
                          <input type='text' value={form.bank_name} onChange={(e) => setForm({ ...form, bank_name: e.target.value })} placeholder='e.g. Barclays, HSBC' />
                        </div>
                        <div className='field' style={{ marginBottom: 10 }}>
                          <label style={{ fontSize: 11.5 }}>Sort Code</label>
                          <input type='text' value={form.bank_sort_code} onChange={(e) => setForm({ ...form, bank_sort_code: e.target.value })} placeholder='e.g. 20-00-00' />
                        </div>
                        <div className='field' style={{ marginBottom: 10 }}>
                          <label style={{ fontSize: 11.5 }}>Account Number</label>
                          <input type='text' value={form.bank_account_number} onChange={(e) => setForm({ ...form, bank_account_number: e.target.value })} placeholder='e.g. 12345678' />
                        </div>
                        <div className='field' style={{ marginBottom: 0 }}>
                          <label style={{ fontSize: 11.5 }}>Address <span className='hint'>optional</span></label>
                          <input type='text' value={form.bank_address} onChange={(e) => setForm({ ...form, bank_address: e.target.value })} placeholder='Bank / account address' />
                        </div>
                      </div>
                    </div>
                  </label>
                  <label className={`comm-option ${form.payout_method === 'paypal' ? 'selected' : ''}`}>
                    <input type='radio' name='paytype' checked={form.payout_method === 'paypal'} onChange={() => setForm({ ...form, payout_method: 'paypal' })} />
                    <div style={{ flex: 1 }}>
                      <div className='co-title'>PayPal</div>
                      <div className={`comm-value-row ${form.payout_method === 'paypal' ? 'active' : ''}`}>
                        <div className='field' style={{ marginBottom: 0 }}>
                          <label style={{ fontSize: 11.5 }}>PayPal Email</label>
                          <input type='email' value={form.paypal_email} onChange={(e) => setForm({ ...form, paypal_email: e.target.value })} placeholder='name@paypal.com' />
                        </div>
                      </div>
                    </div>
                  </label>
                </div>
              </div>
            </div>
            <div className='modal-foot'>
              <button type='button' className='btn btn-ghost' onClick={() => setShowForm(false)}>Cancel</button>
              <button type='button' className='btn btn-primary' disabled={busy} onClick={saveForm}>Save</button>
            </div>
          </div>
        </div>

        <div className={`modal-overlay ${pwRep ? 'active' : ''}`}>
          <div className='modal' style={{ maxWidth: 380 }}>
            <div className='modal-head'>
              <h2>Reset Password</h2>
              <button type='button' className='modal-close' onClick={() => setPwRep(null)}><IconClose /></button>
            </div>
            <div className='modal-body'>
              <p style={{ marginTop: 0, fontSize: 13.5, color: 'var(--ink-soft)' }}>
                Set a new temporary password for <strong style={{ color: 'var(--ink)' }}>{pwRep?.name}</strong>.
              </p>
              <div className='field'>
                <label>New Temporary Password</label>
                <div className='pw-row'>
                  <input type='text' value={pwValue} onChange={(e) => setPwValue(e.target.value)} />
                  <button type='button' className='btn btn-ghost pw-gen' onClick={() => setPwValue(genPassword())}>Generate</button>
                </div>
              </div>
            </div>
            <div className='modal-foot'>
              <button type='button' className='btn btn-ghost' onClick={() => setPwRep(null)}>Cancel</button>
              <button type='button' className='btn btn-primary' disabled={busy || pwValue.length < 6} onClick={resetPassword}>Reset Password</button>
            </div>
          </div>
        </div>
      </>
    )
  }

  return (
    <div className='stm'>
      <div className='wrap'>
        <header className='page-head'>
          <h1>Sales Team</h1>
          <p>Manage salesmen and sales partners, their access, and commission setup.</p>
        </header>

        <div className='tabs'>
          <button type='button' className={`tab-btn ${tab === 'salesman' ? 'active' : ''}`} onClick={() => switchTab('salesman')}>Sales Man</button>
          <button type='button' className={`tab-btn ${tab === 'partners' ? 'active' : ''}`} onClick={() => switchTab('partners')}>Sales Partners</button>
        </div>

        {renderTable('salesman')}
        {renderTable('partners')}
      </div>

      {renderModals()}
      <div className={`toast ${toast ? 'show' : ''}`}>{toast}</div>
    </div>
  )
}
