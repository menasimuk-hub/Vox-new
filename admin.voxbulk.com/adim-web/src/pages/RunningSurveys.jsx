import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Activity, CheckCircle2, ClipboardList, MessageCircle, Pause, Phone, PhoneCall, Play, RefreshCw, Square, TriangleAlert, Users } from 'lucide-react'
import { apiFetch } from '../lib/api'
import { isWaSurveyOrder, waSessionStatusPill, deliveryOkBadge } from '../lib/waSurveyOps'
import WaSurveySessionPanel from '../components/WaSurveySessionPanel'
import OrderAdminBillingPanel from '../components/OrderAdminBillingPanel'
import { formatDurationSeconds } from '../lib/serviceOrderAdmin'
import { KpiCard } from '@/components/ui/KpiCard'
import '../styles/ops-theme.css'

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
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const detailRef = useRef(null)
  const [orders, setOrders] = useState([])
  const [overview, setOverview] = useState(null)
  const [selected, setSelected] = useState(null)
  const [audit, setAudit] = useState([])
  const [panelTab, setPanelTab] = useState('overview')
  const [listTab, setListTab] = useState('running')
  const [searchQuery, setSearchQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busyKey, setBusyKey] = useState('')
  const [editingId, setEditingId] = useState(null)
  const [editForm, setEditForm] = useState(EMPTY_CONTACT)
  const [contactDetail, setContactDetail] = useState(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [waSessions, setWaSessions] = useState([])
  const [waSessionsLoading, setWaSessionsLoading] = useState(false)
  const [selectedWaSessionId, setSelectedWaSessionId] = useState(null)
  const [waSessionDetail, setWaSessionDetail] = useState(null)

  const load = useCallback(async () => {
    setError('')
    const [rows, stats] = await Promise.all([
      apiFetch('/admin/platform-services/orders?service_code=survey'),
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
    const cfg = row?.config || {}
    if (isWaSurveyOrder(cfg)) {
      setWaSessionsLoading(true)
      try {
        const sess = await apiFetch(
          `/admin/platform-services/surveys/wa-sessions?order_id=${encodeURIComponent(orderId)}&limit=200`,
        )
        setWaSessions(sess?.sessions || [])
      } catch {
        setWaSessions([])
      } finally {
        setWaSessionsLoading(false)
      }
    } else {
      setWaSessions([])
    }
    setSelectedWaSessionId(null)
    setWaSessionDetail(null)
  }, [])

  const openWaSession = async (sessionId) => {
    setSelectedWaSessionId(sessionId)
    setWaSessionDetail(null)
    setError('')
    try {
      const detail = await apiFetch(
        `/admin/platform-services/surveys/wa-sessions/${encodeURIComponent(sessionId)}`,
      )
      setWaSessionDetail(detail)
      setPanelTab('wa-sessions')
    } catch (e) {
      setError(e?.message || 'Could not load WA session')
    }
  }

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

  useEffect(() => {
    const orderId = searchParams.get('order')
    if (!orderId || loading) return
    let cancelled = false
    ;(async () => {
      setPanelTab('overview')
      try {
        await loadDetail(orderId)
        if (!cancelled) {
          window.requestAnimationFrame(() => {
            detailRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
          })
        }
      } catch (e) {
        if (!cancelled) setError(e?.message || 'Could not load order detail')
      }
    })()
    return () => {
      cancelled = true
    }
  }, [searchParams, loading, loadDetail])

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
      window.requestAnimationFrame(() => {
        detailRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
      })
    } catch (e) {
      setError(e?.message || 'Could not load survey detail')
    }
  }

  const closeDetail = () => {
    setSelected(null)
    setEditingId(null)
    setContactDetail(null)
    setWaSessionDetail(null)
    setSelectedWaSessionId(null)
    if (searchParams.get('order')) {
      navigate('/operations/running-surveys', { replace: true })
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
  const isWaOrder = isWaSurveyOrder(config)

  const overviewCards = useMemo(
    () => [
      { label: 'Live surveys', value: overview?.live ?? '—', hint: `${overview?.scheduled ?? 0} scheduled`, icon: Activity, tone: 'info' },
      { label: 'Running now', value: overview?.running ?? '—', hint: `${overview?.paused ?? 0} paused`, icon: Play, tone: 'success' },
      { label: 'Completed', value: overview?.completed ?? '—', hint: 'All time', icon: CheckCircle2, tone: 'primary' },
      { label: 'Failed payments', value: overview?.failed_payments ?? '—', hint: `${overview?.pending_payment_approval ?? 0} pending approval`, icon: TriangleAlert, tone: 'danger' },
    ],
    [overview],
  )

  const timeline = audit.length ? audit : selected?.audit_timeline || []

  const filteredOrders = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    return orders.filter((o) => {
      if (listTab === 'running' && !o.is_live) return false
      if (listTab === 'finished' && !o.is_finished) return false
      if (!q) return true
      return (
        String(o.title || '').toLowerCase().includes(q) ||
        String(o.org_name || '').toLowerCase().includes(q)
      )
    })
  }, [orders, listTab, searchQuery])

  return (
    <div className="opsTheme">
      <div className="pageTop">
        <div>
          <h1>Survey operations</h1>
          <p>
            Monitor running and finished surveys. Phone orders use AI dial; WhatsApp orders use adaptive WA sessions — see{' '}
            <Link to="/operations/wa-survey-insights" style={{ color: 'var(--grn)' }}>WA Survey insights</Link>.
          </p>
        </div>
        <div className="actions">
          <input
            className="input runningSurveySearch"
            type="search"
            placeholder="Search survey or company…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          <button type="button" className="btn soft" onClick={load} disabled={loading}>
            <RefreshCw size={15} />
            Refresh
          </button>
        </div>
      </div>

      {error ? <div className="note runningSurveyError">{error}</div> : null}

      {selected ? (
        <div className="card runningSurveyDetailCard runningSurveyDetailCard--top" ref={detailRef}>
          <div className="cardHead runningSurveyDetailHead">
            <div>
              <h3>{selected.title}</h3>
              <div className="muted runningSurveyDetailSub">
                {selected.org_name} · {selected.owner_email} · {selected.recipient_count} contacts
              </div>
            </div>
            <div className="runningSurveyDetailHeadActions">
              <span className={statusPill(selected.status, selected.payment_status)}>{selected.status_label || selected.status}</span>
              <Link className="btn soft bsm" to={`/operations/orders/${encodeURIComponent(selected.id)}`}>Full order view</Link>
              <button type="button" className="btn soft bsm" onClick={closeDetail}>Close</button>
            </div>
          </div>

          <div className="cardBody">
            {selected.next_action?.hint ? (
              <div className="note runningSurveyNext">
                <strong>Next step:</strong> {selected.next_action.label} — {selected.next_action.hint}
              </div>
            ) : null}

            <OrderAdminBillingPanel order={selected} showCallTable={false} showFootnote={false} />

            <div className="runningSurveyTabs">
              <button type="button" className={`runningSurveyTab${panelTab === 'overview' ? ' on' : ''}`} onClick={() => setPanelTab('overview')}>Overview</button>
              <button type="button" className={`runningSurveyTab${panelTab === 'contacts' ? ' on' : ''}`} onClick={() => setPanelTab('contacts')}>
                <Users size={14} /> Contacts ({recipients.length})
              </button>
              <button type="button" className={`runningSurveyTab${panelTab === 'audit' ? ' on' : ''}`} onClick={() => setPanelTab('audit')}>
                <Activity size={14} /> Audit
              </button>
              {isWaOrder ? (
                <button type="button" className={`runningSurveyTab${panelTab === 'wa-sessions' ? ' on' : ''}`} onClick={() => setPanelTab('wa-sessions')}>
                  <MessageCircle size={14} /> WA sessions ({waSessions.length})
                </button>
              ) : null}
            </div>

            {panelTab === 'overview' ? (
              <div className="runningSurveyMetaGrid">
                <div className="runningSurveyMetaBlock">
                  <div className="runningSurveyMetaLabel">Schedule</div>
                  <div className="runningSurveyMetaValue">{fmtWhen(selected.scheduled_start_at)} → {fmtWhen(selected.scheduled_end_at)}</div>
                </div>
                <div className="runningSurveyMetaBlock">
                  <div className="runningSurveyMetaLabel">Script</div>
                  <div className={`runningSurveyMetaValue${config.script_approved ? ' isOk' : ' isWarn'}`}>{config.script_approved ? 'Approved' : 'Not approved'}</div>
                </div>
                <div className="runningSurveyMetaBlock">
                  <div className="runningSurveyMetaLabel">Goal</div>
                  <div className="runningSurveyMetaValue">{config.goal || '—'}</div>
                </div>
                {isWaOrder ? (
                  <div className="runningSurveyMetaBlock">
                    <div className="runningSurveyMetaLabel">WhatsApp flow</div>
                    <div className="runningSurveyMetaValue">{config.flow_engine || 'linear'}</div>
                  </div>
                ) : null}
                <div className="runningSurveyMetaBlock">
                  <div className="runningSurveyMetaLabel">Call progress</div>
                  <div className="runningSurveyMetaValue">{surveyResponded(report)} responded · {report.failed || 0} failed · {Math.max(0, (selected.recipient_count || 0) - surveyResponded(report) - (report.failed || 0))} pending</div>
                </div>
                <div className="runningSurveyMetaBlock">
                  <div className="runningSurveyMetaLabel">AI analysis</div>
                  <div className="runningSurveyMetaValue">{analysis.analyzed_count ?? 0} analysed · {analysis.pending_analysis ?? 0} pending</div>
                </div>
                <div className="runningSurveyMetaBlock">
                  <div className="runningSurveyMetaLabel">Started</div>
                  <div className="runningSurveyMetaValue">{fmtWhen(selected.started_at)}</div>
                </div>
              </div>
            ) : null}

            {panelTab === 'overview' ? (
              <OrderAdminBillingPanel order={selected} showMetrics={false} showFootnote />
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
                    {contactDetail.wa_survey_session ? (
                      <div style={{ marginTop: 14 }}>
                        <WaSurveySessionPanel data={contactDetail.wa_survey_session} compact />
                      </div>
                    ) : isWaOrder ? (
                      <div className="muted" style={{ marginTop: 10 }}>No WA session started for this contact yet.</div>
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
                        {!isWaOrder ? (
                          <>
                            <th>Call type</th>
                            <th>Call time</th>
                            <th>Bill min</th>
                          </>
                        ) : null}
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {recipients.map((r) => {
                        const canAiCall = !isWaOrder && isRunning && r.status !== 'calling'
                        const canRetry = ['failed', 'no_answer', 'busy', 'completed'].includes(String(r.status || '').toLowerCase())
                        const waSess = isWaOrder ? waSessions.find((s) => s.recipient_id === r.id) : null
                        return (
                          <tr key={r.id}>
                            <td>{r.row_number}</td>
                            <td>{r.name}</td>
                            <td>{r.phone}</td>
                            <td>{r.email || '—'}</td>
                            <td>
                              {waSess ? (
                                <span className={waSessionStatusPill(waSess.status)} title="WA session">{waSess.status}</span>
                              ) : (
                                <span className={contactPill(r.status)}>{r.status || 'pending'}</span>
                              )}
                            </td>
                            {!isWaOrder ? (
                              <>
                                <td>{r.call_type || '—'}</td>
                                <td>{formatDurationSeconds(r.duration_seconds)}</td>
                                <td>{r.billable_minutes != null ? r.billable_minutes : '—'}</td>
                              </>
                            ) : null}
                            <td>
                              <div className="runningSurveyRowActions">
                                {canAiCall ? (
                                  <button
                                    type="button"
                                    className="btn primary bsm"
                                    disabled={busyKey === `call-${r.id}`}
                                    title={isRunning ? 'Place AI survey call via Telnyx' : 'Start the survey first'}
                                    onClick={() => runAiCall(r, canRetry)}
                                  >
                                    {busyKey === `call-${r.id}` ? 'Calling…' : canRetry ? 'Call again' : 'Run AI call'}
                                  </button>
                                ) : null}
                                {!isWaOrder && r.phone ? <a className="btn soft bsm" href={`tel:${r.phone}`}>Phone</a> : null}
                                {waSess ? (
                                  <button type="button" className="btn soft bsm" onClick={() => openWaSession(waSess.id)}>WA session</button>
                                ) : null}
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

            {panelTab === 'wa-sessions' && isWaOrder ? (
              <div className="runningSurveyContactsPane">
                {waSessionsLoading ? <div className="muted">Loading WA sessions…</div> : null}
                {!waSessionsLoading && !waSessions.length ? (
                  <div className="muted">No adaptive sessions for this order yet. Sessions appear after WhatsApp launch.</div>
                ) : null}
                {waSessionDetail ? (
                  <div style={{ marginBottom: 14 }}>
                    <div className="runningSurveyContactDetailHead">
                      <strong>Session {selectedWaSessionId?.slice(0, 8)}…</strong>
                      <button type="button" className="btn soft bsm" onClick={() => { setWaSessionDetail(null); setSelectedWaSessionId(null) }}>Close</button>
                    </div>
                    <WaSurveySessionPanel data={waSessionDetail} />
                  </div>
                ) : null}
                {!waSessionsLoading && waSessions.length ? (
                  <div className="tableWrap">
                    <table className="table runningSurveyContactsTable">
                      <thead>
                        <tr>
                          <th>Status</th>
                          <th>Flow</th>
                          <th>Outcome</th>
                          <th>Delivery</th>
                          <th>Picker</th>
                          <th></th>
                        </tr>
                      </thead>
                      <tbody>
                        {waSessions.map((s) => {
                          const del = deliveryOkBadge(s.outcome_delivery)
                          const recip = recipients.find((r) => r.id === s.recipient_id)
                          return (
                            <tr key={s.id} className={selectedWaSessionId === s.id ? 'isSelected' : ''}>
                              <td><span className={waSessionStatusPill(s.status)}>{s.status}</span></td>
                              <td>{s.flow_mode}</td>
                              <td>{s.outcome_key || '—'}</td>
                              <td><span className={del.className}>{del.label}</span></td>
                              <td>{s.picker_invocation_count ?? 0}</td>
                              <td>
                                <button type="button" className="btn soft bsm" onClick={() => openWaSession(s.id)}>
                                  {recip?.name || 'Detail'}
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

            <div className="runningSurveyControlsLabel">Campaign controls</div>
            <div className="runningSurveyActionBar">
              <button type="button" className="btn primary bsm" disabled={busyKey === selected.id} onClick={() => runAction(selected.id, 'start')}>
                <Play size={14} /> Start survey
              </button>
              {!isWaOrder ? (
                <button type="button" className="btn soft bsm" disabled={!isRunning || busyKey === 'dial-next'} onClick={dialNext}>
                  <PhoneCall size={14} /> Dial next contact
                </button>
              ) : null}
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
          </div>
        </div>
      ) : null}

      {!selected ? (
        <div className="ds-scope grid grid-cols-2 gap-3 lg:grid-cols-4">
          {overviewCards.map((c, i) => (
            <KpiCard key={c.label} icon={c.icon} label={c.label} value={c.value} hint={c.hint} tone={c.tone} index={i} />
          ))}
        </div>
      ) : null}

      <div className="card runningSurveyListCard">
        <div className="cardHead runningSurveyListHead">
          <h3><ClipboardList size={16} /> Surveys</h3>
          <div className="runningSurveyTabs">
            <button type="button" className={`runningSurveyTab${listTab === 'running' ? ' on' : ''}`} onClick={() => setListTab('running')}>Running surveys</button>
            <button type="button" className={`runningSurveyTab${listTab === 'finished' ? ' on' : ''}`} onClick={() => setListTab('finished')}>Finished surveys</button>
          </div>
        </div>
        <div className="cardBody">
          {loading ? <div className="muted">Loading surveys…</div> : null}
          {!loading && !filteredOrders.length ? (
            <div className="muted">{listTab === 'running' ? 'No running surveys right now.' : 'No finished surveys yet.'}</div>
          ) : null}
          {!loading && filteredOrders.length ? (
            <div className="tableWrap">
              <table className="table runningSurveyTable">
                <thead>
                  <tr>
                    <th>Survey</th>
                    <th>Organisation</th>
                    <th>Owner</th>
                    <th>Status</th>
                    <th>Progress</th>
                    <th>Quote (est.)</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredOrders.map((o) => {
                    const sent = surveyResponded(o.report)
                    const total = o.recipient_count || 0
                    return (
                      <tr
                        key={o.id}
                        className={`isClickable${selected?.id === o.id ? ' isSelected' : ''}`}
                        onClick={() => openRow(o)}
                      >
                        <td><strong>{o.title}</strong></td>
                        <td>{o.org_name || o.org_id}</td>
                        <td>{o.owner_email || '—'}</td>
                        <td><span className={statusPill(o.status, o.payment_status)}>{o.status_label || o.status}</span></td>
                        <td>{sent} / {total}</td>
                        <td>{o.quote_total_gbp || '—'}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  )
}
