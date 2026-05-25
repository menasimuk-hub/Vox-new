import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Activity, Briefcase, Download, Pause, Play, RefreshCw, Square, Users } from 'lucide-react'
import { apiFetch, apiFetchBlob } from '../lib/api'

const EMPTY_CANDIDATE = { name: '', phone: '', email: '', status: '' }

function interviewProgress(report) {
  return Number(report?.completed ?? report?.reached ?? 0)
}

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
  if (status === 'draft') return 'leadPill leadPillNeutral'
  return 'leadPill'
}

function candidatePill(status) {
  const s = String(status || 'pending').toLowerCase()
  if (s === 'calling') return 'leadPill leadPillHold'
  if (s === 'completed') return 'leadPill leadPillAdvance'
  if (['failed', 'no_answer', 'busy', 'cancelled'].includes(s)) return 'leadPill leadPillDecline'
  return 'leadPill leadPillNeutral'
}

function cvQualityLabel(q) {
  const v = String(q || 'missing')
  if (v === 'good') return 'Good'
  if (v === 'low_quality') return 'Low quality'
  if (v === 'corrupt') return 'Error'
  return 'No CV'
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

export default function RunningInterviews() {
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
  const [editForm, setEditForm] = useState(EMPTY_CANDIDATE)

  const load = useCallback(async () => {
    setError('')
    const [rows, stats] = await Promise.all([
      apiFetch('/admin/platform-services/orders?service_code=interview'),
      apiFetch('/admin/platform-services/interviews/overview'),
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
        if (!cancelled) setError(e?.message || 'Could not load interviews')
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
    setError('')
    try {
      await loadDetail(order.id)
    } catch (e) {
      setError(e?.message || 'Could not load interview detail')
    }
  }

  const startEditCandidate = (recipient) => {
    setEditingId(recipient.id)
    setEditForm({
      name: recipient.name || '',
      phone: recipient.phone || '',
      email: recipient.email || '',
      status: recipient.status || '',
    })
    setPanelTab('candidates')
  }

  const saveCandidate = async () => {
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
      setError(e?.message || 'Could not save candidate')
    } finally {
      setBusyKey('')
    }
  }

  const downloadCv = async (recipient) => {
    if (!selected?.id || !recipient?.id) return
    setBusyKey(`cv-${recipient.id}`)
    setError('')
    try {
      const blob = await apiFetchBlob(
        `/admin/platform-services/orders/${encodeURIComponent(selected.id)}/recipients/${encodeURIComponent(recipient.id)}/cv`,
      )
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = recipient.cv_filename || `cv-${recipient.id}.pdf`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    } catch (e) {
      setError(e?.message || 'Could not download CV')
    } finally {
      setBusyKey('')
    }
  }

  const recipients = selected?.recipients || []
  const config = selected?.config || {}
  const report = selected?.report || {}
  const isRunning = selected?.status === 'running'

  const overviewCards = useMemo(
    () => [
      { label: 'Live interviews', value: overview?.live ?? '—', hint: `${overview?.drafts ?? 0} drafts · ${overview?.scheduled ?? 0} scheduled` },
      { label: 'Running now', value: overview?.running ?? '—', hint: `${overview?.paused ?? 0} paused` },
      { label: 'Completed', value: overview?.completed ?? '—', hint: 'All time' },
      { label: 'Pending payment', value: overview?.pending_payment_approval ?? '—', hint: `${overview?.failed_payments ?? 0} rejected` },
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
        String(o.org_name || '').toLowerCase().includes(q) ||
        String(o.reference_id || '').toLowerCase().includes(q)
      )
    })
  }, [orders, listTab, searchQuery])

  return (
    <>
      <div className="pageTop">
        <div>
          <h1>Interview operations</h1>
          <p>
            Monitor running and finished AI phone interview tasks. Approve payments, control campaign status, and support customers.
          </p>
        </div>
        <div className="actions">
          <input
            className="input runningSurveySearch"
            type="search"
            placeholder="Search task, reference, or company…"
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

      <div className="grid-4 runningSurveyStats">
        {overviewCards.map((c) => (
          <StatCard key={c.label} label={c.label} value={c.value} hint={c.hint} />
        ))}
      </div>

      <div className="note runningSurveyGuide">
        <strong>How to support a customer interview task</strong>
        <ol>
          <li>Select a task from the list and click <strong>Manage</strong>.</li>
          <li>Check the <strong>Task reference</strong> — candidates email CVs to careers@voxbulk.com with this ID.</li>
          <li>Approve cash payment if needed, then <strong>Start interview</strong> when the customer is ready.</li>
          <li>Use <strong>Candidates</strong> to edit contact details or download CV files.</li>
          <li>AI outbound calling for interviews is Phase 2 — status controls work now; live dial dispatch coming next.</li>
        </ol>
      </div>

      <div className="card runningSurveyListCard">
        <div className="cardHead runningSurveyListHead">
          <h3><Briefcase size={16} /> Interviews</h3>
          <div className="runningSurveyTabs">
            <button type="button" className={`runningSurveyTab${listTab === 'running' ? ' on' : ''}`} onClick={() => setListTab('running')}>Running interviews</button>
            <button type="button" className={`runningSurveyTab${listTab === 'finished' ? ' on' : ''}`} onClick={() => setListTab('finished')}>Finished interviews</button>
          </div>
        </div>
        <div className="cardBody">
          {loading ? <div className="muted">Loading interviews…</div> : null}
          {!loading && !filteredOrders.length ? (
            <div className="muted">{listTab === 'running' ? 'No running interview tasks right now.' : 'No finished interviews yet.'}</div>
          ) : null}
          {!loading && filteredOrders.length ? (
            <div className="tableWrap">
              <table className="table runningSurveyTable">
                <thead>
                  <tr>
                    <th>Task</th>
                    <th>Reference</th>
                    <th>Organisation</th>
                    <th>Owner</th>
                    <th>Status</th>
                    <th>Progress</th>
                    <th>Quote</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {filteredOrders.map((o) => {
                    const done = interviewProgress(o.report)
                    const total = o.recipient_count || 0
                    return (
                      <tr key={o.id} className={selected?.id === o.id ? 'isSelected' : ''}>
                        <td><strong>{o.title}</strong></td>
                        <td><code>{o.reference_id || '—'}</code></td>
                        <td>{o.org_name || o.org_id}</td>
                        <td>{o.owner_email || '—'}</td>
                        <td><span className={statusPill(o.status, o.payment_status)}>{o.status_label || o.status}</span></td>
                        <td>{done} / {total}</td>
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
                {selected.reference_id ? <><code>{selected.reference_id}</code> · </> : null}
                {selected.org_name} · {selected.owner_email} · {selected.recipient_count} candidates · {selected.quote_total_gbp}
              </div>
            </div>
            <span className={statusPill(selected.status, selected.payment_status)}>{selected.status_label || selected.status}</span>
          </div>

          <div className="cardBody">
            <div className="runningSurveyActionBar">
              {selected.payment_status === 'pending_approval' ? (
                <>
                  <button type="button" className="btn primary bsm" disabled={busyKey === selected.id} onClick={() => runAction(selected.id, 'approve-payment')}>
                    Approve payment
                  </button>
                  <button type="button" className="btn soft bsm" disabled={busyKey === selected.id} onClick={() => runAction(selected.id, 'reject-payment', { note: 'Rejected by admin' })}>
                    Reject payment
                  </button>
                </>
              ) : null}
              <button type="button" className="btn primary bsm" disabled={busyKey === selected.id} onClick={() => runAction(selected.id, 'start')}>
                <Play size={14} /> Start interview
              </button>
              <button type="button" className="btn soft bsm" disabled={!isRunning || busyKey === selected.id} onClick={() => runAction(selected.id, 'pause')}>
                <Pause size={14} /> Pause
              </button>
              <button type="button" className="btn soft bsm" disabled={busyKey === selected.id} onClick={() => runAction(selected.id, 'resume')}>
                <Play size={14} /> Resume
              </button>
              <button type="button" className="btn soft bsm" disabled={busyKey === selected.id} onClick={() => runAction(selected.id, 'stop', { reason: 'Stopped by admin' })}>
                <Square size={14} /> Stop
              </button>
              {selected.owner_email ? (
                <a className="btn soft bsm" href={`mailto:${selected.owner_email}`}>Email owner</a>
              ) : null}
            </div>

            <div className="runningSurveyTabs">
              <button type="button" className={`runningSurveyTab${panelTab === 'overview' ? ' on' : ''}`} onClick={() => setPanelTab('overview')}>Overview</button>
              <button type="button" className={`runningSurveyTab${panelTab === 'candidates' ? ' on' : ''}`} onClick={() => setPanelTab('candidates')}>
                <Users size={14} /> Candidates ({recipients.length})
              </button>
              <button type="button" className={`runningSurveyTab${panelTab === 'audit' ? ' on' : ''}`} onClick={() => setPanelTab('audit')}>
                <Activity size={14} /> Audit
              </button>
            </div>

            {panelTab === 'overview' ? (
              <div className="runningSurveyMetaGrid">
                <div className="runningSurveyMetaBlock">
                  <div className="runningSurveyMetaLabel">Task reference</div>
                  <div><code>{selected.reference_id || '—'}</code></div>
                </div>
                <div className="runningSurveyMetaBlock">
                  <div className="runningSurveyMetaLabel">Payment</div>
                  <div>{selected.payment_status} · {selected.payment_method || 'none'}</div>
                </div>
                <div className="runningSurveyMetaBlock">
                  <div className="runningSurveyMetaLabel">Schedule</div>
                  <div>{fmtWhen(selected.scheduled_start_at)} → {fmtWhen(selected.scheduled_end_at)}</div>
                </div>
                <div className="runningSurveyMetaBlock">
                  <div className="runningSurveyMetaLabel">Role</div>
                  <div>{config.role || '—'}</div>
                </div>
                <div className="runningSurveyMetaBlock">
                  <div className="runningSurveyMetaLabel">Criteria</div>
                  <div>{config.criteria || '—'}</div>
                </div>
                <div className="runningSurveyMetaBlock">
                  <div className="runningSurveyMetaLabel">Script</div>
                  <div>{config.script_approved ? 'Approved' : 'Not approved'}</div>
                </div>
                <div className="runningSurveyMetaBlock">
                  <div className="runningSurveyMetaLabel">Call progress</div>
                  <div>{interviewProgress(report)} screened · {Math.max(0, (selected.recipient_count || 0) - interviewProgress(report))} pending</div>
                </div>
                <div className="runningSurveyMetaBlock">
                  <div className="runningSurveyMetaLabel">Started</div>
                  <div>{fmtWhen(selected.started_at)}</div>
                </div>
              </div>
            ) : null}

            {panelTab === 'candidates' ? (
              <div className="runningSurveyContactsPane">
                {editingId ? (
                  <div className="runningSurveyEditPanel">
                    <div className="runningSurveyEditTitle">Edit candidate</div>
                    <div className="runningSurveyEditGrid">
                      <label>Name<input className="input" value={editForm.name} onChange={(e) => setEditForm((f) => ({ ...f, name: e.target.value }))} /></label>
                      <label>Phone<input className="input" value={editForm.phone} onChange={(e) => setEditForm((f) => ({ ...f, phone: e.target.value }))} /></label>
                      <label>Email<input className="input" value={editForm.email} onChange={(e) => setEditForm((f) => ({ ...f, email: e.target.value }))} /></label>
                      <label>Status<input className="input" value={editForm.status} onChange={(e) => setEditForm((f) => ({ ...f, status: e.target.value }))} /></label>
                    </div>
                    <div className="runningSurveyActionBar">
                      <button type="button" className="btn primary bsm" disabled={busyKey === `save-${editingId}`} onClick={saveCandidate}>Save</button>
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
                        <th>CV</th>
                        <th>Source</th>
                        <th>Status</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {recipients.map((r) => (
                        <tr key={r.id}>
                          <td>{r.row_number}</td>
                          <td>{r.name}</td>
                          <td>{r.phone || '—'}</td>
                          <td>{r.email || '—'}</td>
                          <td>{cvQualityLabel(r.cv_quality)}{r.cv_filename ? ` · ${r.cv_filename}` : ''}</td>
                          <td>{r.intake_source || '—'}</td>
                          <td><span className={candidatePill(r.status)}>{r.status || 'pending'}</span></td>
                          <td>
                            <div className="runningSurveyRowActions">
                              {r.has_cv_file ? (
                                <button type="button" className="btn soft bsm" disabled={busyKey === `cv-${r.id}`} onClick={() => downloadCv(r)}>
                                  <Download size={14} /> CV
                                </button>
                              ) : null}
                              <button type="button" className="btn soft bsm" onClick={() => startEditCandidate(r)}>Edit</button>
                            </div>
                          </td>
                        </tr>
                      ))}
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
          <div className="cardBody muted">Select an interview task and click <strong>Manage</strong> to monitor and support the customer.</div>
        </div>
      )}
    </>
  )
}
