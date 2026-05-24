import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../lib/api'

function statusTone(order) {
  if (order.status === 'running') return 'pill ok'
  if (order.status === 'paused') return 'pill warn'
  if (order.payment_status === 'rejected') return 'pill bad'
  return 'pill'
}

function fmtWhen(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString()
}

const EMPTY_CONTACT = { name: '', phone: '', email: '', status: '' }

export default function RunningSurveys() {
  const [orders, setOrders] = useState([])
  const [overview, setOverview] = useState(null)
  const [selected, setSelected] = useState(null)
  const [audit, setAudit] = useState([])
  const [panelTab, setPanelTab] = useState('info')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busyId, setBusyId] = useState('')
  const [editingId, setEditingId] = useState(null)
  const [editForm, setEditForm] = useState(EMPTY_CONTACT)
  const [contactDetail, setContactDetail] = useState(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const load = useCallback(async () => {
    setError('')
    const [rows, stats] = await Promise.all([
      apiFetch('/admin/platform-services/orders?service_code=survey&live_only=true'),
      apiFetch('/admin/platform-services/surveys/overview'),
    ])
    setOrders(Array.isArray(rows) ? rows : [])
    setOverview(stats || null)
  }, [])

  const loadDetail = useCallback(async (orderId) => {
    if (!orderId) return
    const [row, auditRes] = await Promise.all([
      apiFetch(`/admin/platform-services/orders/${encodeURIComponent(orderId)}`),
      apiFetch(`/admin/platform-services/orders/${encodeURIComponent(orderId)}/audit`),
    ])
    setSelected(row)
    setAudit(auditRes?.timeline || [])
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      try {
        await load()
      } catch (e) {
        if (!cancelled) setError(e?.message || 'Could not load surveys')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [load])

  const runAction = async (orderId, action, body) => {
    setBusyId(orderId)
    setError('')
    try {
      const row = await apiFetch(`/admin/platform-services/orders/${encodeURIComponent(orderId)}/${action}`, {
        method: 'POST',
        body: body ? JSON.stringify(body) : undefined,
      })
      setSelected(row)
      await load()
      await loadDetail(orderId)
    } catch (e) {
      setError(e?.message || `${action} failed`)
    } finally {
      setBusyId('')
    }
  }

  const openRow = async (order) => {
    setPanelTab('info')
    setEditingId(null)
    setContactDetail(null)
    try {
      await loadDetail(order.id)
    } catch (e) {
      setError(e?.message || 'Could not load survey detail')
    }
  }

  const startEditContact = (recipient) => {
    setEditingId(recipient.id)
    setEditForm({
      name: recipient.name || '',
      phone: recipient.phone || '',
      email: recipient.email || '',
      status: recipient.status || '',
    })
    setContactDetail(null)
    setPanelTab('contacts')
  }

  const saveContact = async () => {
    if (!selected?.id || !editingId) return
    setBusyId(editingId)
    setError('')
    try {
      await apiFetch(
        `/admin/platform-services/orders/${encodeURIComponent(selected.id)}/recipients/${encodeURIComponent(editingId)}`,
        { method: 'PATCH', body: JSON.stringify(editForm) },
      )
      await loadDetail(selected.id)
      setEditingId(null)
    } catch (e) {
      setError(e?.message || 'Could not save contact')
    } finally {
      setBusyId('')
    }
  }

  const openContactDetail = async (recipientId) => {
    if (!selected?.id) return
    setDetailLoading(true)
    setContactDetail(null)
    setEditingId(null)
    try {
      const detail = await apiFetch(
        `/admin/platform-services/orders/${encodeURIComponent(selected.id)}/recipients/${encodeURIComponent(recipientId)}`,
      )
      setContactDetail(detail)
      setPanelTab('contacts')
    } catch (e) {
      setError(e?.message || 'Could not load contact detail')
    } finally {
      setDetailLoading(false)
    }
  }

  const recipients = selected?.recipients || []
  const config = selected?.config || {}

  const overviewCards = useMemo(
    () => [
      { label: 'Live surveys', value: overview?.live ?? '—' },
      { label: 'Running', value: overview?.running ?? '—' },
      { label: 'Paused', value: overview?.paused ?? '—' },
      { label: 'Failed payments', value: overview?.failed_payments ?? '—' },
    ],
    [overview],
  )

  return (
    <>
      <div className="pageTop">
        <div>
          <h1>Running surveys</h1>
          <p>Monitor live campaigns, edit contacts, call recipients, and support customers in real time.</p>
        </div>
        <div className="actions">
          <button type="button" className="btn soft" onClick={load}>Refresh</button>
        </div>
      </div>

      {error ? <div className="note" style={{ borderColor: 'rgba(220,38,38,0.35)', marginBottom: 12 }}>{error}</div> : null}

      <div className="kpiGrid" style={{ marginBottom: 16 }}>
        {overviewCards.map((c) => (
          <div key={c.label} className="kpiCard">
            <div className="kpiLabel">{c.label}</div>
            <div className="kpiValue">{c.value}</div>
          </div>
        ))}
      </div>

      <div className="grid2">
        <div className="card">
          <div className="cardHead"><h3>Active surveys</h3></div>
          <div className="cardBody">
            {loading ? <div className="muted">Loading…</div> : null}
            {!loading && !orders.length ? <div className="muted">No active surveys right now.</div> : null}
            {!loading && orders.length ? (
              <table className="table">
                <thead>
                  <tr>
                    <th>Survey</th>
                    <th>Organisation</th>
                    <th>Status</th>
                    <th>Contacts</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {orders.map((o) => (
                    <tr key={o.id} className={selected?.id === o.id ? 'rowActive' : ''}>
                      <td>{o.title}</td>
                      <td>{o.org_name || o.org_id}</td>
                      <td><span className={statusTone(o)}>{o.status_label || o.status}</span></td>
                      <td>{o.recipient_count}</td>
                      <td><button type="button" className="btn soft bsm" onClick={() => openRow(o)}>Open</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : null}
          </div>
        </div>

        <div className="card">
          <div className="cardHead"><h3>Survey control panel</h3></div>
          <div className="cardBody">
            {!selected ? <div className="muted">Select a survey to view details, contacts, and audit history.</div> : null}
            {selected ? (
              <>
                <div className="tabRow" style={{ marginBottom: 12 }}>
                  <button type="button" className={`tabBtn${panelTab === 'info' ? ' on' : ''}`} onClick={() => setPanelTab('info')}>Info</button>
                  <button type="button" className={`tabBtn${panelTab === 'contacts' ? ' on' : ''}`} onClick={() => setPanelTab('contacts')}>Contacts ({recipients.length})</button>
                  <button type="button" className={`tabBtn${panelTab === 'audit' ? ' on' : ''}`} onClick={() => setPanelTab('audit')}>Audit</button>
                </div>

                {panelTab === 'info' ? (
                  <>
                    <div style={{ marginBottom: 12 }}>
                      <div style={{ fontWeight: 700, fontSize: 16 }}>{selected.title}</div>
                      <div className="muted">{selected.org_name} · {selected.owner_email}</div>
                      <div className="muted">{selected.recipient_count} contacts · {selected.quote_total_gbp}</div>
                    </div>
                    {selected.next_action?.hint ? (
                      <div className="note" style={{ marginBottom: 12 }}>
                        <strong>Next:</strong> {selected.next_action.label} — {selected.next_action.hint}
                      </div>
                    ) : null}
                    <div className="muted" style={{ fontSize: 13, lineHeight: 1.7, marginBottom: 12 }}>
                      <div><strong>Payment:</strong> {selected.payment_status} ({selected.payment_method || 'none'})</div>
                      <div><strong>Schedule:</strong> {fmtWhen(selected.scheduled_start_at)} → {fmtWhen(selected.scheduled_end_at)}</div>
                      <div><strong>Prompt approved:</strong> {config.script_approved ? 'Yes' : 'No'}</div>
                      <div><strong>Goal:</strong> {config.goal || '—'}</div>
                    </div>
                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                      <button type="button" className="btn primary bsm" disabled={busyId === selected.id} onClick={() => runAction(selected.id, 'start')}>Start</button>
                      <button type="button" className="btn soft bsm" disabled={busyId === selected.id} onClick={() => runAction(selected.id, 'pause')}>Pause</button>
                      <button type="button" className="btn soft bsm" disabled={busyId === selected.id} onClick={() => runAction(selected.id, 'resume')}>Resume</button>
                      <button type="button" className="btn soft bsm" disabled={busyId === selected.id} onClick={() => runAction(selected.id, 'stop', { reason: 'Stopped by admin' })}>Stop</button>
                      {selected.org_phone ? (
                        <a className="btn soft bsm" href={`tel:${selected.org_phone}`}>Call clinic</a>
                      ) : null}
                      {selected.owner_email ? (
                        <a className="btn soft bsm" href={`mailto:${selected.owner_email}`}>Email owner</a>
                      ) : null}
                    </div>
                  </>
                ) : null}

                {panelTab === 'contacts' ? (
                  <>
                    {detailLoading ? <div className="muted">Loading contact detail…</div> : null}
                    {contactDetail ? (
                      <div className="note" style={{ marginBottom: 12 }}>
                        <div style={{ fontWeight: 700, marginBottom: 6 }}>{contactDetail.contact?.name || contactDetail.recipient?.name}</div>
                        <div className="muted">{contactDetail.contact?.phone} · {contactDetail.contact?.email || 'No email'}</div>
                        <div className="muted">Status: {contactDetail.contact?.status || contactDetail.recipient?.status}</div>
                        {contactDetail.recipient?.call_summary ? <div style={{ marginTop: 8 }}>{contactDetail.recipient.call_summary}</div> : null}
                        {contactDetail.recipient?.transcript ? (
                          <pre style={{ whiteSpace: 'pre-wrap', fontSize: 12, marginTop: 8, maxHeight: 180, overflow: 'auto' }}>{contactDetail.recipient.transcript}</pre>
                        ) : null}
                        <button type="button" className="btn soft bsm" style={{ marginTop: 8 }} onClick={() => setContactDetail(null)}>Close detail</button>
                      </div>
                    ) : null}
                    {editingId ? (
                      <div className="note" style={{ marginBottom: 12 }}>
                        <div style={{ fontWeight: 700, marginBottom: 8 }}>Edit contact</div>
                        <div className="formGrid">
                          <label>Name<input value={editForm.name} onChange={(e) => setEditForm((f) => ({ ...f, name: e.target.value }))} /></label>
                          <label>Phone<input value={editForm.phone} onChange={(e) => setEditForm((f) => ({ ...f, phone: e.target.value }))} /></label>
                          <label>Email<input value={editForm.email} onChange={(e) => setEditForm((f) => ({ ...f, email: e.target.value }))} /></label>
                          <label>Status<input value={editForm.status} onChange={(e) => setEditForm((f) => ({ ...f, status: e.target.value }))} /></label>
                        </div>
                        <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                          <button type="button" className="btn primary bsm" disabled={busyId === editingId} onClick={saveContact}>Save</button>
                          <button type="button" className="btn soft bsm" onClick={() => setEditingId(null)}>Cancel</button>
                          {editForm.phone ? <a className="btn soft bsm" href={`tel:${editForm.phone}`}>Call</a> : null}
                        </div>
                      </div>
                    ) : null}
                    <table className="table compact">
                      <thead>
                        <tr>
                          <th>#</th>
                          <th>Name</th>
                          <th>Phone</th>
                          <th>Email</th>
                          <th>Status</th>
                          <th></th>
                        </tr>
                      </thead>
                      <tbody>
                        {recipients.map((r) => (
                          <tr key={r.id}>
                            <td>{r.row_number}</td>
                            <td>{r.name}</td>
                            <td>{r.phone}</td>
                            <td>{r.email || '—'}</td>
                            <td>{r.status}</td>
                            <td style={{ whiteSpace: 'nowrap' }}>
                              <a className="btn soft bsm" href={`tel:${r.phone}`}>Call</a>{' '}
                              <button type="button" className="btn soft bsm" onClick={() => startEditContact(r)}>Edit</button>{' '}
                              <button type="button" className="btn soft bsm" onClick={() => openContactDetail(r.id)}>Info</button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </>
                ) : null}

                {panelTab === 'audit' ? (
                  <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
                    {(audit.length ? audit : selected.audit_timeline || []).map((ev, idx) => (
                      <li key={`${ev.at}-${idx}`} style={{ padding: '8px 0', borderBottom: '1px solid var(--border, #eee)' }}>
                        <div style={{ fontWeight: 600 }}>{ev.label}</div>
                        <div className="muted" style={{ fontSize: 12 }}>{fmtWhen(ev.at)}</div>
                        {ev.detail ? <div style={{ fontSize: 12, marginTop: 4 }}>{ev.detail}</div> : null}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </>
            ) : null}
          </div>
        </div>
      </div>
    </>
  )
}
