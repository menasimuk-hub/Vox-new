import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Activity, ClipboardList, Pause, Phone, PhoneCall, Play, RefreshCw, Square, Users } from 'lucide-react'
import { apiFetch } from '../lib/api'

function surveyResponded(report) {
  return Number(report?.completed ?? report?.sent ?? 0)
}

const EMPTY_CONTACT = { name: '', phone: '', email: '', status: '' }

function fmtWhen(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString()
}

function statusPill(status, paymentStatus) {
  if (status === 'running') return 'leadPill leadPillAdvance'
  if (status === 'paused') return 'leadPill leadPillHold'
  if (paymentStatus === 'rejected') return 'leadPill leadPillDecline'
  if (status === 'completed') return 'leadPill leadPillNeutral'
  return 'leadPill'
}

function contactPill(status) {
  const s = String(status || 'pending').toLowerCase()
  if (s === 'calling') return 'leadPill leadPillHold'
  if (s === 'completed') return 'leadPill leadPillAdvance'
  if (['failed', 'no_answer', 'busy'].includes(s)) return 'leadPill leadPillDecline'
  return 'leadPill leadPillNeutral'
}

function StatCard({ label, value, hint }) {
  return (
    <div className="card stat runningSurveyStat">
      <div className="statValue">{value}</div>
      <div className="muted">{label}</div>
      {hint ? <div className="muted runningSurveyStatHint">{hint}</div> : null}
    </div>
  )
}

export default function RunningSurveys() {
  const [orders, setOrders] = useState([])
  const [overview, setOverview] = useState(null)
  const [selected, setSelected] = useState(null)
  const [audit, setAudit] = useState([])
  const [panelTab, setPanelTab] = useState('overview')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busyKey, setBusyKey] = useState('')
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

  const runAction = async (orderId, action, body, busy = orderId) => {
    setBusyKey(busy)
    setError('')
    try {
      await apiFetch(`/admin/platform-services/orders/${encodeURIComponent(orderId)}/${action}`, {
        method: 'POST',
        body: body ? JSON.stringify(body) : undefined,
      })
      await load()
      await loadDetail(orderId)
    } catch (e) {
      setError(e?.message || `${action} failed`)
    } finally {
      setBusyKey('')
    }
  }

  const openRow = async (order) => {
    setPanelTab('overview')
    setEditingId(null)
    setContactDetail(null)
    setError('')
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
    setBusyKey(`save-${editingId}`)
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
      setBusyKey('')
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

  const runAiCall = async (recipient, retry = false) => {
    if (!selected?.id) return
    setBusyKey(`call-${recipient.id}`)
    setError('')
    try {
      const row = await apiFetch(
        `/admin/platform-services/orders/${encodeURIComponent(selected.id)}/recipients/${encodeURIComponent(recipient.id)}/call-now`,
        { method: 'POST', body: JSON.stringify({ retry }) },
      )
      setSelected(row)
      setContactDetail(null)
    } catch (e) {
      setError(e?.message || 'Could not start AI call')
    } finally {
      setBusyKey('')
    }
  }

  const dialNext = async () => {
    if (!selected?.id) return
    setBusyKey('dial-next')
    setError('')
    try {
      const row = await apiFetch(
        `/admin/platform-services/orders/${encodeURIComponent(selected.id)}/dial-next`,
        { method: 'POST' },
      )
      setSelected(row)
    } catch (e) {
      setError(e?.message || 'Could not dial next contact')
    } finally {
      setBusyKey('')
    }
  }

  const reanalyzeOrder = async () => {
    if (!selected?.id) return
    setBusyKey('reanalyze-order')
    setError('')
    try {
      const row = await apiFetch(
        `/admin/platform-services/orders/${encodeURIComponent(selected.id)}/reanalyze`,
        { method: 'POST' },
      )
      setSelected(row)
    } catch (e) {
      setError(e?.message || 'Could not re-analyze survey')
    } finally {
      setBusyKey('')
    }
  }

  const reanalyzeContact = async (recipientId) => {
    if (!selected?.id) return
    setBusyKey(`reanalyze-${recipientId}`)
    setError('')
    try {
      const row = await apiFetch(
        `/admin/platform-services/orders/${encodeURIComponent(selected.id)}/recipients/${encodeURIComponent(recipientId)}/reanalyze`,
        { method: 'POST' },
      )
      setSelected(row)
      const detail = await apiFetch(
        `/admin/platform-services/orders/${encodeURIComponent(selected.id)}/recipients/${encodeURIComponent(recipientId)}`,
      )
      setContactDetail(detail)
    } catch (e) {
      setError(e?.message || 'Could not re-analyze contact')
    } finally {
      setBusyKey('')
    }
  }

  const recipients = selected?.recipients || []
  const config = selected?.config || {}
  const report = selected?.report || {}
  const analysis = report?.analysis || {}
  const isRunning = selected?.status === 'running'

  const overviewCards = useMemo(
    () => [
      { label: 'Live surveys', value: overview?.live ?? '—', hint: `${overview?.scheduled ?? 0} scheduled` },
      { label: 'Running now', value: overview?.running ?? '—', hint: `${overview?.paused ?? 0} paused` },
      { label: 'Completed', value: overview?.completed ?? '—', hint: 'All time' },
      { label: 'Failed payments', value: overview?.failed_payments ?? '—', hint: `${overview?.pending_payment_approval ?? 0} pending approval` },
    ],
    [overview],
  )

  const timeline = audit.length ? audit : selected?.audit_timeline || []

  return (
    <>
      <div className="pageTop">
        <div>
          <h1>Running surveys</h1>
          <p>
            Operate customer AI phone surveys. Use <strong>Start survey</strong> to launch outbound calls for the customer,
            then <strong>Run AI call</strong> on individual contacts when needed.
          </p>
        </div>
        <div className="actions">
          <button type="button" className="btn soft" onClick={load} disabled={loading}>
            <RefreshCw size={15} />
            Refresh
          </button>
        </div>
      </div>

      {error ? <div className="note runningSurveyError">{error}</div> : null}

      <div className="grid-4 runningSurveyStats">
        {overviewCards.map((c) => (
          <StatCard key={c.label} label={c.label} value={c.value} hint={c.hint} />
        ))}
      </div>

      <div className="note runningSurveyGuide">
        <strong>How to run calls for a customer</strong>
        <ol>
          <li>Select a survey from the list below.</li>
          <li>Confirm payment is approved and the script is approved.</li>
          <li>Click <strong>Start survey</strong> — the AI dials the first pending contact automatically.</li>
          <li>Use <strong>Dial next contact</strong> while running, or <strong>Run AI call</strong> on a specific row in Contacts.</li>
          <li>The plain <strong>Phone</strong> link is for your handset only; it does not trigger the customer&apos;s AI survey.</li>
        </ol>
      </div>

      <div className="card runningSurveyListCard">
        <div className="cardHead">
          <h3><ClipboardList size={16} /> Active surveys</h3>
        </div>
        <div className="cardBody">
          {loading ? <div className="muted">Loading surveys…</div> : null}
          {!loading && !orders.length ? (
            <div className="muted">No active surveys right now.</div>
          ) : null}
          {!loading && orders.length ? (
            <div className="tableWrap">
              <table className="table runningSurveyTable">
                <thead>
                  <tr>
                    <th>Survey</th>
                    <th>Organisation</th>
                    <th>Owner</th>
                    <th>Status</th>
                    <th>Progress</th>
                    <th>Quote</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {orders.map((o) => {
                    const sent = surveyResponded(o.report)
                    const total = o.recipient_count || 0
                    return (
                      <tr key={o.id} className={selected?.id === o.id ? 'isSelected' : ''}>
                        <td><strong>{o.title}</strong></td>
                        <td>{o.org_name || o.org_id}</td>
                        <td>{o.owner_email || '—'}</td>
                        <td><span className={statusPill(o.status, o.payment_status)}>{o.status_label || o.status}</span></td>
                        <td>{sent} / {total}</td>
                        <td>{o.quote_total_gbp || '—'}</td>
                        <td>
                          <button type="button" className="btn soft bsm" onClick={() => openRow(o)}>
                            Manage
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          ) : null}
        </div>
      </div>

      {selected ? (
        <div className="card runningSurveyDetailCard">
          <div className="cardHead runningSurveyDetailHead">
            <div>
              <h3>{selected.title}</h3>
              <div className="muted runningSurveyDetailSub">
                {selected.org_name} · {selected.owner_email} · {selected.recipient_count} contacts · {selected.quote_total_gbp}
              </div>
            </div>
            <span className={statusPill(selected.status, selected.payment_status)}>{selected.status_label || selected.status}</span>
          </div>

          <div className="cardBody">
            {selected.next_action?.hint ? (
              <div className="note runningSurveyNext">
                <strong>Next step:</strong> {selected.next_action.label} — {selected.next_action.hint}
              </div>
            ) : null}

            <div className="runningSurveyActionBar">
              <button type="button" className="btn primary bsm" disabled={busyKey === selected.id} onClick={() => runAction(selected.id, 'start')}>
                <Play size={14} /> Start survey
              </button>
              <button type="button" className="btn soft bsm" disabled={!isRunning || busyKey === 'dial-next'} onClick={dialNext}>
                <PhoneCall size={14} /> Dial next contact
              </button>
              <button type="button" className="btn soft bsm" disabled={busyKey === selected.id} onClick={() => runAction(selected.id, 'pause')}>
                <Pause size={14} /> Pause
              </button>
              <button type="button" className="btn soft bsm" disabled={busyKey === selected.id} onClick={() => runAction(selected.id, 'resume')}>
                <Play size={14} /> Resume
              </button>
              <button type="button" className="btn soft bsm" disabled={busyKey === selected.id} onClick={() => runAction(selected.id, 'stop', { reason: 'Stopped by admin' })}>
                <Square size={14} /> Stop
              </button>
              <button type="button" className="btn soft bsm" disabled={busyKey === 'reanalyze-order'} onClick={reanalyzeOrder}>
                <RefreshCw size={14} /> Re-analyze all
              </button>
              {selected.org_phone ? (
                <a className="btn soft bsm" href={`tel:${selected.org_phone}`}><Phone size={14} /> Phone clinic</a>
              ) : null}
              {selected.owner_email ? (
                <a className="btn soft bsm" href={`mailto:${selected.owner_email}`}>Email owner</a>
              ) : null}
            </div>

            <div className="runningSurveyTabs">
              <button type="button" className={`runningSurveyTab${panelTab === 'overview' ? ' on' : ''}`} onClick={() => setPanelTab('overview')}>Overview</button>
              <button type="button" className={`runningSurveyTab${panelTab === 'contacts' ? ' on' : ''}`} onClick={() => setPanelTab('contacts')}>
                <Users size={14} /> Contacts ({recipients.length})
              </button>
              <button type="button" className={`runningSurveyTab${panelTab === 'audit' ? ' on' : ''}`} onClick={() => setPanelTab('audit')}>
                <Activity size={14} /> Audit
              </button>
            </div>

            {panelTab === 'overview' ? (
              <div className="runningSurveyMetaGrid">
                <div className="runningSurveyMetaBlock">
                  <div className="runningSurveyMetaLabel">Payment</div>
                  <div>{selected.payment_status} · {selected.payment_method || 'none'}</div>
                </div>
                <div className="runningSurveyMetaBlock">
                  <div className="runningSurveyMetaLabel">Schedule</div>
                  <div>{fmtWhen(selected.scheduled_start_at)} → {fmtWhen(selected.scheduled_end_at)}</div>
                </div>
                <div className="runningSurveyMetaBlock">
                  <div className="runningSurveyMetaLabel">Script</div>
                  <div>{config.script_approved ? 'Approved' : 'Not approved'}</div>
                </div>
                <div className="runningSurveyMetaBlock">
                  <div className="runningSurveyMetaLabel">Goal</div>
                  <div>{config.goal || '—'}</div>
                </div>
                <div className="runningSurveyMetaBlock">
                  <div className="runningSurveyMetaLabel">Call progress</div>
                  <div>{surveyResponded(report)} responded · {report.failed || 0} failed · {Math.max(0, (selected.recipient_count || 0) - surveyResponded(report) - (report.failed || 0))} pending</div>
                </div>
                <div className="runningSurveyMetaBlock">
                  <div className="runningSurveyMetaLabel">AI analysis</div>
                  <div>{analysis.analyzed_count ?? 0} analysed · {analysis.pending_analysis ?? 0} pending</div>
                </div>
                <div className="runningSurveyMetaBlock">
                  <div className="runningSurveyMetaLabel">Started</div>
                  <div>{fmtWhen(selected.started_at)}</div>
                </div>
              </div>
            ) : null}

            {panelTab === 'contacts' ? (
              <div className="runningSurveyContactsPane">
                {detailLoading ? <div className="muted">Loading contact detail…</div> : null}

                {contactDetail ? (
                  <div className="runningSurveyContactDetail">
                    <div className="runningSurveyContactDetailHead">
                      <div>
                        <strong>{contactDetail.contact?.name || contactDetail.recipient?.name}</strong>
                        <div className="muted">{contactDetail.contact?.phone} · {contactDetail.contact?.email || 'No email'}</div>
                      </div>
                      <div className="runningSurveyRowActions">
                        <button
                          type="button"
                          className="btn soft bsm"
                          disabled={busyKey === `reanalyze-${contactDetail.recipient?.id}`}
                          onClick={() => reanalyzeContact(contactDetail.recipient?.id)}
                        >
                          {busyKey === `reanalyze-${contactDetail.recipient?.id}` ? 'Re-analysing…' : 'Re-analyze'}
                        </button>
                        <button type="button" className="btn soft bsm" onClick={() => setContactDetail(null)}>Close</button>
                      </div>
                    </div>
                    <div className="muted">Status: {contactDetail.contact?.status || contactDetail.recipient?.status}</div>
                    {contactDetail.recipient?.short_summary ? <p><strong>Summary:</strong> {contactDetail.recipient.short_summary}</p> : null}
                    {contactDetail.recipient?.analysis_error ? (
                      <p className="note">Analysis error: {contactDetail.recipient.analysis_error}</p>
                    ) : null}
                    {contactDetail.recipient?.transcript ? (
                      <pre className="runningSurveyTranscript">{contactDetail.recipient.transcript}</pre>
                    ) : null}
                  </div>
                ) : null}

                {editingId ? (
                  <div className="runningSurveyEditPanel">
                    <div className="runningSurveyEditTitle">Edit contact</div>
                    <div className="runningSurveyEditGrid">
                      <label>Name<input className="input" value={editForm.name} onChange={(e) => setEditForm((f) => ({ ...f, name: e.target.value }))} /></label>
                      <label>Phone<input className="input" value={editForm.phone} onChange={(e) => setEditForm((f) => ({ ...f, phone: e.target.value }))} /></label>
                      <label>Email<input className="input" value={editForm.email} onChange={(e) => setEditForm((f) => ({ ...f, email: e.target.value }))} /></label>
                      <label>Status<input className="input" value={editForm.status} onChange={(e) => setEditForm((f) => ({ ...f, status: e.target.value }))} /></label>
                    </div>
                    <div className="runningSurveyActionBar">
                      <button type="button" className="btn primary bsm" disabled={busyKey === `save-${editingId}`} onClick={saveContact}>Save</button>
                      <button type="button" className="btn soft bsm" onClick={() => setEditingId(null)}>Cancel</button>
                    </div>
                  </div>
                ) : null}

                <div className="tableWrap">
                  <table className="table runningSurveyContactsTable">
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>Name</th>
                        <th>Phone</th>
                        <th>Email</th>
                        <th>Status</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {recipients.map((r) => {
                        const canAiCall = isRunning && r.status !== 'calling'
                        const canRetry = ['failed', 'no_answer', 'busy', 'completed'].includes(String(r.status || '').toLowerCase())
                        return (
                          <tr key={r.id}>
                            <td>{r.row_number}</td>
                            <td>{r.name}</td>
                            <td>{r.phone}</td>
                            <td>{r.email || '—'}</td>
                            <td><span className={contactPill(r.status)}>{r.status || 'pending'}</span></td>
                            <td>
                              <div className="runningSurveyRowActions">
                                <button
                                  type="button"
                                  className="btn primary bsm"
                                  disabled={!canAiCall || busyKey === `call-${r.id}`}
                                  title={isRunning ? 'Place AI survey call via Telnyx' : 'Start the survey first'}
                                  onClick={() => runAiCall(r, canRetry)}
                                >
                                  {busyKey === `call-${r.id}` ? 'Calling…' : canRetry ? 'Call again' : 'Run AI call'}
                                </button>
                                {r.phone ? <a className="btn soft bsm" href={`tel:${r.phone}`}>Phone</a> : null}
                                <button type="button" className="btn soft bsm" onClick={() => startEditContact(r)}>Edit</button>
                                <button type="button" className="btn soft bsm" onClick={() => openContactDetail(r.id)}>Details</button>
                              </div>
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : null}

            {panelTab === 'audit' ? (
              <ul className="runningSurveyAuditList">
                {timeline.map((ev, idx) => (
                  <li key={`${ev.at}-${idx}`}>
                    <div className="runningSurveyAuditLabel">{ev.label}</div>
                    <div className="muted">{fmtWhen(ev.at)}</div>
                    {ev.detail ? <div className="runningSurveyAuditDetail">{ev.detail}</div> : null}
                  </li>
                ))}
                {!timeline.length ? <li className="muted">No audit events yet.</li> : null}
              </ul>
            ) : null}
          </div>
        </div>
      ) : (
        <div className="card runningSurveyEmptyDetail">
          <div className="cardBody muted">Select a survey and click <strong>Manage</strong> to control calls and contacts.</div>
        </div>
      )}
    </>
  )
}
