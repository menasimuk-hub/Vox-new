import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Activity, Briefcase, CheckCircle2, CreditCard, Download, Pause, Play, RefreshCw, Square, Users } from 'lucide-react'
import { apiFetch, apiFetchBlob } from '../lib/api'
import OrderAdminBillingPanel from '../components/OrderAdminBillingPanel'
import { formatDurationSeconds, sortServiceOrders } from '../lib/serviceOrderAdmin'
import { KpiCard } from '@/components/ui/KpiCard'
import { Input } from '@/components/ui/Input'
import { Button } from '@/components/ui/Button'
import '../styles/ops-theme.css'

const LIVE_INTERVIEW_STATUSES = new Set(['running', 'paused', 'scheduled'])
const EMPTY_CANDIDATE = { name: '', phone: '', email: '', status: '' }

function orderSortTs(o) {
  const raw = o.updated_at || o.started_at || o.created_at
  if (!raw) return 0
  const t = new Date(raw).getTime()
  return Number.isNaN(t) ? 0 : t
}

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

function activityStatusLabel(code) {
  const map = {
    pending: 'Pending',
    booking_email_sent: 'Booking email sent',
    awaiting_booking: 'Awaiting booking',
    booked_waiting: 'Booked (upcoming)',
    booked: 'Booked',
    booking_cancelled: 'Booking cancelled',
    calling: 'Calling',
    interview_completed: 'Interview done',
    report_ready: 'Report ready',
    scheduling_sent: 'Scheduling sent',
    call_failed: 'Call failed',
  }
  return map[String(code || '').toLowerCase()] || code || 'Pending'
}

const ACTIVITY_PIPELINE = [
  'pending',
  'booking_email_sent',
  'awaiting_booking',
  'booked_waiting',
  'booked',
  'calling',
  'interview_completed',
  'report_ready',
  'booking_cancelled',
  'call_failed',
]

function activityPipelineIndex(code) {
  const idx = ACTIVITY_PIPELINE.indexOf(String(code || 'pending').toLowerCase())
  return idx >= 0 ? idx : 0
}

function ActivityStatusRail({ current }) {
  const currentIdx = activityPipelineIndex(current)
  const isTerminal = ['booking_cancelled', 'call_failed', 'report_ready'].includes(String(current || '').toLowerCase())
  return (
    <div className="activityStatusRail" aria-label="Candidate status progress">
      {ACTIVITY_PIPELINE.filter((code) => code !== 'call_failed' || current === 'call_failed').map((code, idx) => {
        const on = code === String(current || '').toLowerCase()
        const done = !isTerminal && idx < currentIdx
        const show = code !== 'booking_cancelled' || on
        if (!show) return null
        return (
          <span
            key={code}
            className={`activityStatusChip${on ? ' on' : ''}${done ? ' done' : ''}`}
          >
            {activityStatusLabel(code)}
          </span>
        )
      })}
    </div>
  )
}

function activityPill(code) {
  const s = String(code || 'pending').toLowerCase()
  if (s === 'report_ready' || s === 'interview_completed') return 'leadPill leadPillAdvance'
  if (s === 'calling' || s === 'awaiting_booking' || s === 'booking_email_sent') return 'leadPill leadPillHold'
  if (s === 'call_failed' || s === 'booking_cancelled') return 'leadPill leadPillDecline'
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
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const [orders, setOrders] = useState([])
  const [overview, setOverview] = useState(null)
  const [selected, setSelected] = useState(null)
  const [audit, setAudit] = useState([])
  const [panelTab, setPanelTab] = useState('overview')
  const [listTab, setListTab] = useState('finished')
  const [searchQuery, setSearchQuery] = useState('')
  const [sortBy, setSortBy] = useState('amount_desc')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busyKey, setBusyKey] = useState('')
  const [editingId, setEditingId] = useState(null)
  const [editForm, setEditForm] = useState(EMPTY_CANDIDATE)
  const [activityRow, setActivityRow] = useState(null)
  const [activityData, setActivityData] = useState(null)
  const [activityLoading, setActivityLoading] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const detailRef = React.useRef(null)

  const load = useCallback(async () => {
    setError('')
    const [rows, stats] = await Promise.all([
      apiFetch('/admin/platform-services/orders?service_code=interview'),
      apiFetch('/admin/platform-services/interviews/overview'),
    ])
    setOrders(Array.isArray(rows) ? rows : [])
    setOverview(stats || null)
  }, [])

  const loadDetail = useCallback(async (orderId, { auditOnly = false } = {}) => {
    if (!orderId) return
    if (!auditOnly) {
      const row = await apiFetch(`/admin/platform-services/orders/${encodeURIComponent(orderId)}`)
      setSelected(row)
    }
    try {
      const auditRes = await apiFetch(`/admin/platform-services/orders/${encodeURIComponent(orderId)}/audit`)
      setAudit(auditRes?.timeline || [])
    } catch {
      if (!auditOnly) setAudit([])
    }
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

  useEffect(() => {
    const orderId = searchParams.get('order')
    if (!orderId || loading) return
    let cancelled = false
    ;(async () => {
      setPanelTab('overview')
      try {
        await loadDetail(orderId)
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
    setError('')
    setDetailLoading(true)
    try {
      await loadDetail(order.id)
      window.setTimeout(() => {
        detailRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
      }, 50)
    } catch (e) {
      setError(e?.message || 'Could not load interview detail')
    } finally {
      setDetailLoading(false)
    }
  }

  const closeDetail = () => {
    setSelected(null)
    setEditingId(null)
    if (searchParams.get('order')) {
      navigate('/operations/running-interviews', { replace: true })
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
      a.download = recipient.cv_filename || `cv-${recipient.id}`
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

  const openActivity = async (recipient) => {
    if (!selected?.id || !recipient?.id) return
    setActivityRow(recipient)
    setActivityData(null)
    setActivityLoading(true)
    setError('')
    try {
      const data = await apiFetch(
        `/admin/platform-services/orders/${encodeURIComponent(selected.id)}/recipients/${encodeURIComponent(recipient.id)}/activity`,
      )
      setActivityData(data)
    } catch (e) {
      setError(e?.message || 'Could not load activity')
      setActivityRow(null)
    } finally {
      setActivityLoading(false)
    }
  }

  const closeActivity = () => {
    setActivityRow(null)
    setActivityData(null)
  }

  const downloadReport = async (recipient, kind) => {
    if (!selected?.id || !recipient?.id) return
    const key = `report-${kind}-${recipient.id}`
    setBusyKey(key)
    setError('')
    try {
      const path =
        kind === 'pdf'
          ? `/admin/platform-services/orders/${encodeURIComponent(selected.id)}/recipients/${encodeURIComponent(recipient.id)}/interview-candidate-report.pdf`
          : `/admin/platform-services/orders/${encodeURIComponent(selected.id)}/recipients/${encodeURIComponent(recipient.id)}/interview-candidate-report.html`
      const blob = await apiFetchBlob(path)
      const url = URL.createObjectURL(blob)
      if (kind === 'html') {
        window.open(url, '_blank', 'noopener,noreferrer')
      } else {
        const a = document.createElement('a')
        a.href = url
        a.download = `interview-report-${recipient.id}.pdf`
        document.body.appendChild(a)
        a.click()
        a.remove()
      }
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
    } catch (e) {
      setError(e?.message || 'Could not download report')
    } finally {
      setBusyKey('')
    }
  }

  const resendInvite = async (recipient) => {
    if (!selected?.id || !recipient?.id) return
    const locked =
      recipient.status === 'completed' ||
      ['report_ready', 'interview_completed', 'scheduling_sent'].includes(String(recipient.activity_status || ''))
    if (locked) {
      setError('This candidate has already completed screening — booking invites cannot be resent.')
      return
    }
    setBusyKey(`invite-${recipient.id}`)
    setError('')
    try {
      await apiFetch(`/admin/platform-services/orders/${encodeURIComponent(selected.id)}/send-invites`, {
        method: 'POST',
        body: JSON.stringify({ recipient_ids: [recipient.id], force_resend: true }),
      })
      await loadDetail(selected.id)
    } catch (e) {
      setError(e?.message || 'Could not resend invite')
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
      { label: 'Live interviews', value: overview?.live ?? '—', hint: `${overview?.scheduled ?? 0} scheduled · drafts hidden`, icon: Activity, tone: 'info' },
      { label: 'Running now', value: overview?.running ?? '—', hint: `${overview?.paused ?? 0} paused`, icon: Play, tone: 'success' },
      { label: 'Completed', value: overview?.completed ?? '—', hint: 'All time', icon: CheckCircle2, tone: 'primary' },
      { label: 'Pending payment', value: overview?.pending_payment_approval ?? '—', hint: `${overview?.failed_payments ?? 0} rejected`, icon: CreditCard, tone: 'warning' },
    ],
    [overview],
  )

  const timeline = audit.length ? audit : selected?.audit_timeline || []

  const filteredOrders = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    const fromTs = dateFrom ? new Date(`${dateFrom}T00:00:00`).getTime() : null
    const toTs = dateTo ? new Date(`${dateTo}T23:59:59`).getTime() : null
    const rows = orders.filter((o) => {
      const status = String(o.status || '').toLowerCase()
      if (listTab === 'running') {
        if (!LIVE_INTERVIEW_STATUSES.has(status)) return false
      } else if (listTab === 'finished') {
        if (!o.is_finished) return false
      }
      const ts = orderSortTs(o)
      if (fromTs != null && ts < fromTs) return false
      if (toTs != null && ts > toTs) return false
      if (!q) return true
      return (
        String(o.title || '').toLowerCase().includes(q) ||
        String(o.org_name || '').toLowerCase().includes(q) ||
        String(o.reference_id || '').toLowerCase().includes(q) ||
        String(o.campaign_id || '').toLowerCase().includes(q)
      )
    })
    return sortServiceOrders(rows, sortBy)
  }, [orders, listTab, searchQuery, sortBy, dateFrom, dateTo])

  return (
    <div className="opsTheme">
      <div className="pageTop">
        <div>
          <h1>Interviews</h1>
          <p>
            Live and finished AI phone interview campaigns. Drafts are hidden — customers manage drafts in their dashboard.
          </p>
        </div>
      </div>

      <div className="ds-scope flex w-full flex-wrap items-center gap-2">
        <Input
          type="search"
          placeholder="Search name, reference, or company…"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="h-9 min-w-[200px] flex-1"
        />
        <Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} title="From date" className="h-9 w-auto shrink-0" />
        <Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} title="To date" className="h-9 w-auto shrink-0" />
        <select
          className="h-9 shrink-0 rounded-md border border-input bg-transparent px-2 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value)}
        >
          <option value="amount_desc">Amount (high → low)</option>
          <option value="amount_asc">Amount (low → high)</option>
          <option value="date_desc">Newest first</option>
          <option value="date_asc">Oldest first</option>
          <option value="order_asc">Reference A–Z</option>
          <option value="name_asc">Name A–Z</option>
          <option value="name_desc">Name Z–A</option>
        </select>
        <Button type="button" variant="outline" className="h-9 shrink-0" onClick={load} disabled={loading}>
          <RefreshCw size={15} />
          Refresh
        </Button>
      </div>

      {error ? <div className="note runningSurveyError">{error}</div> : null}

      {selected ? (
        <div className="card runningSurveyDetailCard runningSurveyDetailCard--top" ref={detailRef}>
          <div className="cardHead runningSurveyDetailHead">
            <div>
              <h3>{selected.title}</h3>
              <div className="muted runningSurveyDetailSub">
                {selected.reference_id ? <><code>{selected.reference_id}</code> · </> : null}
                {selected.org_name} · {selected.owner_email} · {selected.recipient_count} candidates
              </div>
            </div>
            <div className="runningSurveyDetailHeadActions">
              <span className={statusPill(selected.status, selected.payment_status)}>{selected.status_label || selected.status}</span>
              <Link className="btn soft bsm" to={`/operations/orders/${encodeURIComponent(selected.id)}`}>Full order view</Link>
              <button type="button" className="btn soft bsm" onClick={closeDetail}>Close</button>
            </div>
          </div>

          <div className="cardBody">
            <OrderAdminBillingPanel order={selected} showCallTable={false} showFootnote={false} />

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
                  <div className="runningSurveyMetaValue"><code>{selected.reference_id || '—'}</code></div>
                </div>
                <div className="runningSurveyMetaBlock">
                  <div className="runningSurveyMetaLabel">Schedule</div>
                  <div className="runningSurveyMetaValue">{fmtWhen(selected.scheduled_start_at)} → {fmtWhen(selected.scheduled_end_at)}</div>
                </div>
                <div className="runningSurveyMetaBlock">
                  <div className="runningSurveyMetaLabel">Role</div>
                  <div className="runningSurveyMetaValue">{config.role || '—'}</div>
                </div>
                <div className="runningSurveyMetaBlock">
                  <div className="runningSurveyMetaLabel">Criteria</div>
                  <div className="runningSurveyMetaValue">{config.criteria || '—'}</div>
                </div>
                <div className="runningSurveyMetaBlock">
                  <div className="runningSurveyMetaLabel">Script</div>
                  <div className={`runningSurveyMetaValue${config.script_approved ? ' isOk' : ' isWarn'}`}>{config.script_approved ? 'Approved' : 'Not approved'}</div>
                </div>
                <div className="runningSurveyMetaBlock">
                  <div className="runningSurveyMetaLabel">Call progress</div>
                  <div className="runningSurveyMetaValue">{interviewProgress(report)} screened · {Math.max(0, (selected.recipient_count || 0) - interviewProgress(report))} pending</div>
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
                        <th>Activity</th>
                        <th>Status</th>
                        <th>Call type</th>
                        <th>Call time</th>
                        <th>Bill min</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {recipients.map((r) => (
                        <tr key={r.id}>
                          <td>{r.row_number}</td>
                          <td title={r.id}>{r.name}</td>
                          <td>{r.phone || '—'}</td>
                          <td>{r.email || '—'}</td>
                          <td>{cvQualityLabel(r.cv_quality)}{r.cv_filename ? ` · ${r.cv_filename}` : ''}</td>
                          <td>{r.intake_source || '—'}</td>
                          <td>
                            <span className={activityPill(r.activity_status)}>{activityStatusLabel(r.activity_status)}</span>
                          </td>
                          <td><span className={candidatePill(r.status)}>{r.status || 'pending'}</span></td>
                          <td>{r.call_type || '—'}</td>
                          <td>{formatDurationSeconds(r.duration_seconds)}</td>
                          <td>{r.billable_minutes != null ? r.billable_minutes : '—'}</td>
                          <td>
                            <div className="runningSurveyRowActions">
                              <button type="button" className="btn soft bsm" onClick={() => openActivity(r)}>
                                <Activity size={14} /> Activity
                              </button>
                              {r.activity_status === 'report_ready' || r.status === 'completed' ? (
                                <>
                                  <button type="button" className="btn soft bsm" disabled={busyKey === `report-html-${r.id}`} onClick={() => downloadReport(r, 'html')}>
                                    Report
                                  </button>
                                  <button type="button" className="btn soft bsm" disabled={busyKey === `report-pdf-${r.id}`} onClick={() => downloadReport(r, 'pdf')}>
                                    PDF
                                  </button>
                                </>
                              ) : null}
                              <button
                                type="button"
                                className="btn soft bsm"
                                disabled={
                                  busyKey === `invite-${r.id}` ||
                                  r.status === 'completed' ||
                                  ['report_ready', 'interview_completed', 'scheduling_sent'].includes(String(r.activity_status || ''))
                                }
                                title={
                                  r.status === 'completed' ||
                                  ['report_ready', 'interview_completed', 'scheduling_sent'].includes(String(r.activity_status || ''))
                                    ? 'Interview complete — cannot resend slot booking'
                                    : 'Resend booking invite'
                                }
                                onClick={() => resendInvite(r)}
                              >
                                Resend
                              </button>
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

            <div className="runningSurveyControlsLabel">Campaign controls</div>
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
              <button type="button" className="btn soft bsm" disabled={busyKey === selected.id} onClick={() => {
                if (!window.confirm(`Stop interview "${selected.title}"? Pending calls will not be placed.`)) return
                if (!window.confirm('Final confirmation: stop this interview campaign now?')) return
                runAction(selected.id, 'stop', { reason: 'Stopped by admin' })
              }}>
                <Square size={14} /> Stop
              </button>
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
          <h3><Briefcase size={16} /> Interviews</h3>
          <div className="runningSurveyTabs">
            <button type="button" className={`runningSurveyTab${listTab === 'finished' ? ' on' : ''}`} onClick={() => setListTab('finished')}>Finished</button>
            <button type="button" className={`runningSurveyTab${listTab === 'running' ? ' on' : ''}`} onClick={() => setListTab('running')}>Live</button>
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
                    <th>Interview #</th>
                    <th>Name</th>
                    <th>Status</th>
                    <th>Candidates</th>
                    <th>Quote</th>
                    <th>Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredOrders.map((o) => {
                    const total = o.recipient_count || 0
                    return (
                      <tr
                        key={o.id}
                        className={`isClickable${selected?.id === o.id ? ' isSelected' : ''}`}
                        onClick={() => !detailLoading && openRow(o)}
                      >
                        <td><code>{o.reference_id || o.campaign_id || '—'}</code></td>
                        <td><strong>{o.title}</strong></td>
                        <td><span className={statusPill(o.status, o.payment_status)}>{o.status_label || o.status}</span></td>
                        <td>{total || '—'}</td>
                        <td>{o.quote_total_gbp || '—'}</td>
                        <td className="muted" style={{ fontSize: 12 }}>{fmtWhen(o.updated_at || o.started_at || o.created_at)}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          ) : null}
        </div>
      </div>

      {activityRow ? (
        <div className="modalOverlay" role="presentation" onClick={closeActivity}>
          <div className="ticketModal runningSurveyActivityModal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
            <div className="cardHead">
              <h3>Candidate activity — {activityRow.name || activityRow.email || activityRow.id}</h3>
              <button type="button" className="btn soft bsm" onClick={closeActivity}>Close</button>
            </div>
            <div className="cardBody">
              {activityLoading ? <div className="muted">Loading activity…</div> : null}
              {!activityLoading && activityData ? (
                <>
                  <ActivityStatusRail current={activityData.activity_status} />
                  <div className="runningSurveyMetaBlock" style={{ marginBottom: 12 }}>
                    <span className={activityPill(activityData.activity_status)}>{activityStatusLabel(activityData.activity_status)}</span>
                    {activityData.booked_start_at ? (
                      <span className="muted" style={{ marginLeft: 10 }}>Booked: {fmtWhen(activityData.booked_start_at)}</span>
                    ) : null}
                  </div>
                  <ul className="activityTimeline">
                    {(activityData.events || []).map((ev, idx) => (
                      <li key={`${ev.at}-${idx}`} className="isDone">
                        <div className="activityTimelineLabel">{ev.label}</div>
                        <div className="muted">{fmtWhen(ev.at)}</div>
                        {ev.detail ? <div className="runningSurveyAuditDetail">{ev.detail}</div> : null}
                      </li>
                    ))}
                    {!(activityData.events || []).length ? <li className="muted">No activity recorded yet.</li> : null}
                  </ul>
                </>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
